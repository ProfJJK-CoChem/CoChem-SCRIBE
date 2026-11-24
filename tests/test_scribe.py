#!/usr/bin/env python3
"""
PyTest Suite for CoChem-SCRIBE legacy & archiving components.
Zero mocks, real HDF5/Zstandard round-trips, isolated tmp_path execution,
and strict verified-figure assertions (never passes with figures_generated == 0).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scribe_doc_manager
import scribe_figure_generator
import scribe_inference
import scribe_legacy_bundler
import scribe_orchestration
import scribe_payload_builder


def test_payload_builder_crossref_caching(tmp_path: Path) -> None:
    with contextlib.chdir(tmp_path):
        cache_file = tmp_path / "crossref_cache.json"
        cache_file.write_text(
            json.dumps(
                {
                    "Grimme D4": {
                        "author": "Caldeweyher, E. et al.",
                        "title": "A generally applicable atomic-charge dependent London dispersion correction",
                        "journal": "J. Chem. Phys.",
                        "year": "2019",
                        "volume": "150",
                        "pages": "154122",
                        "DOI": "10.1063/1.5090222",
                    }
                }
            ),
            encoding="utf-8",
        )
        builder = scribe_payload_builder.ScribePayloadBuilder()
        cits = builder._query_crossref_citations(["Grimme D4"])
        assert "Grimme D4" in cits
        assert cits["Grimme D4"]["DOI"] == "10.1063/1.5090222"
        assert cache_file.exists()


def test_payload_builder_bibtex_generation(tmp_path: Path) -> None:
    with contextlib.chdir(tmp_path):
        builder = scribe_payload_builder.ScribePayloadBuilder()
        cits = {
            "TestTheory": {
                "author": "Smith, J.",
                "title": "Test Method",
                "journal": "J. Chem. Phys.",
                "year": "2024",
                "volume": "150",
                "pages": "100-110",
                "DOI": "10.1063/1.12345",
            }
        }
        bib = builder._generate_bibtex(cits)
        assert "@article" in bib
        assert "J. Chem. Phys." in bib
        assert "10.1063/1.12345" in bib


def test_extract_energetics_table(tmp_path: Path) -> None:
    with contextlib.chdir(tmp_path):
        h5_path = tmp_path / "cochem_state.h5"
        with h5py.File(h5_path, "w") as f:
            g1 = f.create_group("conformer_001")
            g1.attrs["energy"] = -76.324556
            g1.attrs["enthalpy"] = -76.300100
            g1.attrs["gibbs_free_energy"] = -76.321500
        builder = scribe_payload_builder.ScribePayloadBuilder()
        tbl = builder.extract_energetics_table()
        assert "\\begin{table}" in tbl
        assert "conformer_001" in tbl
        assert (tmp_path / "manuscript_tables.tex").exists()


def test_doc_manager_chunked_compression(tmp_path: Path) -> None:
    """Real HDF5 dataset chunked Zstandard compression and decompression round-trip."""
    with contextlib.chdir(tmp_path):
        h5_path = tmp_path / "real_tensor.h5"
        expected_array = np.arange(256, dtype=np.float64) * 0.125
        with h5py.File(h5_path, "w") as f:
            f.create_dataset("verified_pes_slice", data=expected_array)

        out_zst = tmp_path / "verified_pes_slice.tar.zst"
        manager = scribe_doc_manager.ScribeDocumentManager()

        with h5py.File(h5_path, "r") as f:
            ds = f["verified_pes_slice"]
            if scribe_doc_manager.zstd is None:
                with pytest.raises(ImportError, match="zstandard"):
                    manager._compress_dataset_chunked(ds, out_zst)
            else:
                manager._compress_dataset_chunked(ds, out_zst)
                assert out_zst.exists()
                assert out_zst.stat().st_size > 0
                dctx = scribe_doc_manager.zstd.ZstdDecompressor()
                with out_zst.open("rb") as fh:
                    with dctx.stream_reader(fh) as reader:
                        raw = reader.read()
                recovered = np.frombuffer(raw, dtype=np.float64)
                np.testing.assert_array_equal(recovered, expected_array)


def test_legacy_bundler_checksum_and_zstd(tmp_path: Path) -> None:
    with contextlib.chdir(tmp_path):
        bundler = scribe_legacy_bundler.LegacyVerificationBundler()
        sample_lin = tmp_path / "sample_h2o.lin"
        sample_lin.write_text("1 0 1 0 0 0 12500.00 0.05 1.0\n", encoding="utf-8")
        bundler.legacy_files = [sample_lin]

        if scribe_legacy_bundler.zstd is None:
            with pytest.raises(ImportError, match="zstandard"):
                bundler.compress_zstd_legacy_file(sample_lin)
            return

        bundler.create_legacy_bundle()
        assert (tmp_path / "Legacy_Verification.zip").exists()
        assert (tmp_path / "checksums.sha256").exists()

        with zipfile.ZipFile(tmp_path / "Legacy_Verification.zip", "r") as zf:
            names = zf.namelist()
            assert "sample_h2o.lin" in names
            assert "sample_h2o.lin.zst" in names
            assert "checksums.sha256" in names
            dctx = scribe_legacy_bundler.zstd.ZstdDecompressor()
            assert dctx.decompress(zf.read("sample_h2o.lin.zst")) == sample_lin.read_bytes()


def test_figure_generator_real_verified_hdf5_and_no_synthetic_axes(tmp_path: Path) -> None:
    """Verify ScribeFigureGenerator produces real figures (>0) and rejects missing axes/intensities."""
    h5_path = tmp_path / "cochem_state.h5"
    with h5py.File(h5_path, "w") as f:
        iso = f.create_group("isomers")
        iso.create_dataset(
            "geometry_h2o",
            data=np.array([[0.0, 0.0, 0.0656], [0.0, 0.7580, -0.5326], [0.0, -0.7580, -0.5326]]),
        )
        f.create_dataset("chiral_buckets", data=np.array([0.0, 1.0]))

        wf_ds = f.create_dataset("dvr_wavefunctions", data=np.array([[[0.1, 0.2], [0.3, 0.4]]]))
        wf_ds.attrs["dvr_x_axis"] = np.array([-1.0, 1.0])
        wf_ds.attrs["dvr_y_axis"] = np.array([0.85, 1.05])

        pes_ds = f.create_dataset("pes_grids", data=np.array([[-76.32, -76.31], [-76.30, -76.29]]))
        pes_ds.attrs["pes_x_axis"] = np.array([0.90, 1.00])
        pes_ds.attrs["pes_y_axis"] = np.array([102.0, 105.0])

        # Verified 4-row IR spectrum: [harm_freq, harm_int, anharm_freq, anharm_int]
        f.create_dataset(
            "ir_spectra",
            data=np.array(
                [
                    [1678.19, 3875.60, 3978.72],
                    [72.4, 5.1, 44.8],
                    [1594.75, 3657.05, 3755.93],
                    [68.9, 4.7, 41.2],
                ]
            ),
        )

    out_dir = tmp_path / "figs"
    generator = scribe_figure_generator.ScribeFigureGenerator(h5_file_path=h5_path, output_dir=out_dir)
    generated_count = generator.generate_all_artifacts(search_dir=tmp_path)
    assert generated_count == 5
    assert generator.figures_generated == 5
    assert (out_dir / "geometry_h2o_3d.html").is_file()
    assert (out_dir / "chiral_buckets_table.tex").is_file()
    assert (out_dir / "dvr_probability_maps.html").is_file()
    assert (out_dir / "pes_contour_maps.html").is_file()
    assert (out_dir / "ir_comparison.html").is_file()

    # Refuses missing coordinate axes (no synthetic linspace(0, 10))
    bad_pes = tmp_path / "bad_pes.h5"
    with h5py.File(bad_pes, "w") as f:
        f.create_dataset("pes_grids", data=np.array([[1.0, 2.0], [3.0, 4.0]]))
    gen_bad_pes = scribe_figure_generator.ScribeFigureGenerator(
        h5_file_path=bad_pes, output_dir=tmp_path / "bad_pes_out"
    )
    with pytest.raises(ValueError, match="Missing verified coordinate axes"):
        gen_bad_pes._generate_torq_artifacts()

    # Refuses 2-row IR frequencies without verified intensities (no hardcoded 1.0/0.8)
    bad_ir = tmp_path / "bad_ir.h5"
    with h5py.File(bad_ir, "w") as f:
        f.create_dataset("ir_spectra", data=np.array([[1678.19, 3875.60], [1594.75, 3657.05]]))
    gen_bad_ir = scribe_figure_generator.ScribeFigureGenerator(
        h5_file_path=bad_ir, output_dir=tmp_path / "bad_ir_out"
    )
    with pytest.raises(ValueError, match="hardcoded flat IR bar heights are prohibited"):
        gen_bad_ir._generate_torq_artifacts()


def test_inference_engine_offline_fallback(tmp_path: Path) -> None:
    with contextlib.chdir(tmp_path):
        engine = scribe_inference.ScribeInferenceEngine()
        engine.api_key = ""
        res = engine._fallback_offline_jinja_rendering()
        assert "Notice: Generated via Offline Fallback Engine" in res


def test_orchestration_structure() -> None:
    orch = scribe_orchestration.ScribeOrchestrator()
    assert hasattr(orch, "run_command")
    assert hasattr(orch, "spawn_daemon")


def test_cochem_scribe_compiler(tmp_path: Path) -> None:
    from cochem_scribe_compiler import ScribeCompiler

    h5_path = tmp_path / "landscape.h5"
    with h5py.File(h5_path, "w") as f:
        g1 = f.create_group("conformer_001")
        g1.attrs["energy"] = -154.234
        g1.attrs["enthalpy"] = -154.120
        g1.attrs["gibbs_free_energy"] = -154.150
        g2 = f.create_group("conformer_002")
        g2.attrs["energy"] = -154.230
        g2.attrs["enthalpy"] = -154.116
        g2.attrs["gibbs_free_energy"] = -154.145

    out_tex = tmp_path / "tables.tex"
    compiler = ScribeCompiler(str(h5_path))
    tex = compiler.generate_energetics_table(str(out_tex))
    assert "\\begin{table}" in tex
    assert "conformer_001" in tex
    assert out_tex.exists()


def test_cochem_scribe_master(tmp_path: Path) -> None:
    with contextlib.chdir(tmp_path):
        from cochem_scribe_master import MethodologyTracker

        tracker = MethodologyTracker()
        tracker.compute_flags = {"MPQC_4", "MACE_OFF24m", "CCSD(T)-F12"}
        m_path = tmp_path / "test_methods.tex"
        r_path = tmp_path / "test_references.bib"
        m_tex = tracker.render_methods_tex(str(m_path))
        r_bib = tracker.render_references_bib(str(r_path))
        assert "\\section{Computational Methods}" in m_tex
        assert "@article" in r_bib
        assert "MPQC" in m_tex or "CCSD" in m_tex


def test_state_tensor_provenance_hash(tmp_path: Path) -> None:
    from cochem_scribe_master import compute_state_tensor_provenance_hash

    h5_path = tmp_path / "test_state.h5"
    with h5py.File(h5_path, "w") as f:
        f.create_dataset("tensor_1", data=np.array([1.0, 2.0, 3.0]))
        f.attrs["calc_mode"] = "CCSD(T)-F12"
    digest1 = compute_state_tensor_provenance_hash(h5_path)
    assert len(digest1) == 64

    with h5py.File(h5_path, "a") as f:
        f["tensor_1"][:] = np.array([1.0, 2.0, 4.0])
    digest2 = compute_state_tensor_provenance_hash(h5_path)
    assert digest1 != digest2


def test_siunitx_table_formatting(tmp_path: Path) -> None:
    from cochem_scribe_compiler import ScribeCompiler

    h5_path = tmp_path / "landscape.h5"
    with h5py.File(h5_path, "w") as f:
        g1 = f.create_group("conformer_A")
        g1.attrs["energy"] = -10.0
    out_tex = tmp_path / "tables_si.tex"
    compiler = ScribeCompiler(str(h5_path))
    tex = compiler.generate_energetics_table(str(out_tex))
    assert "\\usepackage{siunitx}" in tex
    assert "S[table-format=" in tex


def test_validate_standing_rule_7() -> None:
    from scribe_payload_builder import validate_standing_rule_7

    violating_payload = {
        "accuracy_claims": [
            {"description": "GPU ban gate", "provenance": "[E]", "used_as_routing_gate": True}
        ]
    }
    violations = validate_standing_rule_7(violating_payload)
    assert len(violations) == 1
    assert "RULE 7 VIOLATION" in violations[0]
    assert "GPU ban gate" in violations[0]

    valid_payload = {
        "accuracy_claims": [
            {"description": "Measured benchmark", "provenance": "[M]", "used_as_routing_gate": True},
            {"description": "Derived metric", "provenance": "[D]", "used_as_routing_gate": False},
        ]
    }
    assert len(validate_standing_rule_7(valid_payload)) == 0


def test_method_paragraphs_provenance_tags() -> None:
    from cochem_scribe_master import METHOD_PARAGRAPHS

    for key, text in METHOD_PARAGRAPHS.items():
        assert any(tag in text for tag in ["[M]", "[D]", "[E]"]), (
            f"Missing provenance tag in METHOD_PARAGRAPHS[{key}]"
        )


def test_state_tensor_provenance_hash_audit(tmp_path: Path) -> None:
    from cochem_scribe_master import compute_state_tensor_provenance_hash

    h5_path = tmp_path / "audit_test.h5"
    with h5py.File(h5_path, "w") as f:
        ds = f.create_dataset("state_tensor", data=np.ones((5, 5)))
        ds.attrs["provenance_tag"] = "[M]"
        f.attrs["tier_tag"] = "T1-1h [D]"

    digest1 = compute_state_tensor_provenance_hash(h5_path)
    assert len(digest1) == 64
    with h5py.File(h5_path, "r") as f:
        assert "provenance_tag_audit" in f.attrs
        audit = json.loads(f.attrs["provenance_tag_audit"])
        assert audit["[M]"] >= 1
        assert audit["[D]"] >= 1


def test_payload_builder_v4_schema(tmp_path: Path) -> None:
    with contextlib.chdir(tmp_path):
        builder = scribe_payload_builder.ScribePayloadBuilder()
        payload = builder.get_payload()
        assert "product_class" in payload
        assert "tier_category" in payload
        assert "tier_tag" in payload
        assert "max_mace_batch_size" in payload
        assert "standing_rule_7_violations" in payload

        prompt = builder.construct_user_guide_prompt()
        assert "Max MACE-OFF24m Batch Size" in prompt
        assert "Product Class" in prompt
        assert "Standing Rule 7 Audit" in prompt


def test_scribe_orchestration_v4_tiers() -> None:
    orch = scribe_orchestration.ScribeOrchestrator()
    assert hasattr(orch, "tier_categories")
    assert "T1" in orch.tier_categories
    assert "T4" in orch.tier_categories


def test_validate_standing_rule_7_dict_and_nested_claims() -> None:
    from scribe_payload_builder import validate_standing_rule_7

    nested_dict_payload = {
        "modules": {
            "mage": {
                "accuracy_claims": {
                    "claim_1": {
                        "description": "Dict structured estimated gate",
                        "provenance": "[e]",
                        "used_as_routing_gate": True,
                    }
                }
            }
        }
    }
    violations = validate_standing_rule_7(nested_dict_payload)
    assert len(violations) == 1
    assert "Dict structured estimated gate" in violations[0]


def test_group_attribute_provenance_hash_and_exact_counting(tmp_path: Path) -> None:
    from cochem_scribe_master import compute_state_tensor_provenance_hash

    h5_path = tmp_path / "group_test.h5"
    with h5py.File(h5_path, "w") as f:
        grp = f.create_group("conformer_001")
        grp.attrs["energy"] = -100.5
        grp.attrs["provenance_tag"] = "[M]"
        ds = f.create_dataset("tensor_1", data=np.array([1.0]))
        ds.attrs["tag"] = "[D]"

    hash_before = compute_state_tensor_provenance_hash(h5_path)
    with h5py.File(h5_path, "r") as f:
        audit = json.loads(f.attrs["provenance_tag_audit"])
        assert audit["[M]"] == 1
        assert audit["[D]"] == 1

    with h5py.File(h5_path, "a") as f:
        f["conformer_001"].attrs["energy"] = -200.0

    hash_after = compute_state_tensor_provenance_hash(h5_path)
    assert hash_before != hash_after


def calculate_artifact_sha256(filepath: str | Path) -> str:
    """Calculate SHA-256 hash of a computational artifact."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"Artifact file not found: {filepath}")
    hasher = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()
