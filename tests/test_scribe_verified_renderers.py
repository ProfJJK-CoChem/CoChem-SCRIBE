"""Zero-mock tests for CoChem-SCRIBE verified-output renderers, 19/19 register, and provider."""

from __future__ import annotations

import csv
import json
from importlib import metadata
from pathlib import Path

import pytest

from cochem_scribe.provider import scribe_provider
from cochem_scribe.register import (
    FarIRExclusionError,
    audit_farir_exclusion,
    default_manifest_path,
    verify_source_register,
)
from cochem_scribe.renderers import (
    render_geom_comparison,
    render_kinetic_rxn_profile,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GEOM_COMPARISON_JSON = (
    REPO_ROOT.parent
    / "CoChem-GEOM"
    / "benchmarks"
    / "h2o_t_geom_01"
    / "h2o_t_geom_01_comparison.json"
)
CHECKED_IN_VERIFIED_DIR = REPO_ROOT / "benchmarks" / "verified_figures"


def _write_stationary_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    fieldnames = [
        "state",
        "status",
        "n_imag",
        "imag_freq_cm1",
        "e_dft_ha",
        "zpe_ha",
        "delta_e_kcal",
        "delta_h_kcal",
        "delta_g_rrho_kcal",
        "delta_g_qrrho_kcal",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _valid_five_point_rows() -> list[dict[str, object]]:
    return [
        {
            "state": "R",
            "status": "CONVERGED",
            "n_imag": 0,
            "imag_freq_cm1": "0.00",
            "e_dft_ha": "-456.1000000000",
            "zpe_ha": "0.1123400000",
            "delta_e_kcal": "0.0000",
            "delta_h_kcal": "0.0000",
            "delta_g_rrho_kcal": "0.0000",
            "delta_g_qrrho_kcal": "0.0000",
        },
        {
            "state": "TS1",
            "status": "CONVERGED",
            "n_imag": 1,
            "imag_freq_cm1": "-245.60",
            "e_dft_ha": "-456.0710000000",
            "zpe_ha": "0.1112000000",
            "delta_e_kcal": "18.1978",
            "delta_h_kcal": "17.4824",
            "delta_g_rrho_kcal": "20.1500",
            "delta_g_qrrho_kcal": "19.8200",
        },
        {
            "state": "Int_tet",
            "status": "CONVERGED",
            "n_imag": 0,
            "imag_freq_cm1": "0.00",
            "e_dft_ha": "-456.0850000000",
            "zpe_ha": "0.1131000000",
            "delta_e_kcal": "9.4126",
            "delta_h_kcal": "9.8895",
            "delta_g_rrho_kcal": "12.4000",
            "delta_g_qrrho_kcal": "12.0500",
        },
        {
            "state": "TS2",
            "status": "CONVERGED",
            "n_imag": 1,
            "imag_freq_cm1": "-198.40",
            "e_dft_ha": "-456.0760000000",
            "zpe_ha": "0.1115000000",
            "delta_e_kcal": "15.0602",
            "delta_h_kcal": "14.5331",
            "delta_g_rrho_kcal": "16.9000",
            "delta_g_qrrho_kcal": "16.5500",
        },
        {
            "state": "P",
            "status": "CONVERGED",
            "n_imag": 0,
            "imag_freq_cm1": "0.00",
            "e_dft_ha": "-456.1080000000",
            "zpe_ha": "0.1128000000",
            "delta_e_kcal": "-5.0201",
            "delta_h_kcal": "-4.7314",
            "delta_g_rrho_kcal": "-6.1200",
            "delta_g_qrrho_kcal": "-5.9500",
        },
    ]


def test_live_render_geom_comparison_h2o_and_provenance(tmp_path: Path) -> None:
    """Live render of CoChem-GEOM's V-A6 verified H2O comparison JSON."""
    assert GEOM_COMPARISON_JSON.is_file(), f"Missing verified GEOM input: {GEOM_COMPARISON_JSON}"

    out_png = tmp_path / "h2o_geom_comparison.png"
    out_pdf = tmp_path / "h2o_geom_comparison.pdf"
    manifest = tmp_path / "manifest_sha256.json"

    receipt = render_geom_comparison(
        GEOM_COMPARISON_JSON, out_png, out_pdf, manifest_path=manifest
    )

    assert out_png.is_file() and out_png.stat().st_size > 10_000
    assert out_pdf.is_file() and out_pdf.stat().st_size > 5_000
    assert out_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out_pdf.read_bytes()[:5] == b"%PDF-"
    assert manifest.is_file()

    assert receipt["r_e_se_status"] == "PENDING"
    assert receipt["source_comparison_sha256"] == sha256_file(GEOM_COMPARISON_JSON)
    assert receipt["outputs"]["png"]["sha256"] == sha256_file(out_png)
    assert receipt["outputs"]["pdf"]["sha256"] == sha256_file(out_pdf)

    by_key = {col["key"]: col for col in receipt["columns"]}
    assert by_key["r_e_ccsd_cc_pvtz_orca"]["status"] == "VERIFIED"
    assert by_key["r_e_ccsd_cc_pvdz_pyscf"]["status"] == "VERIFIED"
    assert by_key["r_s_kraitchman"]["bond_uncertainty_angstrom"] > 0.0
    assert by_key["r_0_weighted_fit"]["bond_uncertainty_angstrom"] > 0.0
    assert by_key["r_e_se"]["status"] == "PENDING"
    assert by_key["r_e_se"]["bond_angstrom"] is None
    assert by_key["r_e_se"]["angle_deg"] is None


def test_checked_in_verified_geom_benchmark_manifest_matches_disk() -> None:
    """Verify the checked-in benchmarks/verified_figures/ artifacts match their SHA-256 manifest."""
    manifest_path = CHECKED_IN_VERIFIED_DIR / "manifest_sha256.json"
    png_path = CHECKED_IN_VERIFIED_DIR / "h2o_geom_comparison.png"
    pdf_path = CHECKED_IN_VERIFIED_DIR / "h2o_geom_comparison.pdf"
    assert manifest_path.is_file()
    assert png_path.is_file()
    assert pdf_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["r_e_se_status"] == "PENDING"
    assert manifest["outputs"]["png"]["sha256"] == sha256_file(png_path)
    assert manifest["outputs"]["pdf"]["sha256"] == sha256_file(pdf_path)
    if GEOM_COMPARISON_JSON.is_file():
        assert manifest["source_comparison_sha256"] == sha256_file(GEOM_COMPARISON_JSON)


def test_kinetic_rxn_profile_strict_rejects_unverified_and_pending_rows(tmp_path: Path) -> None:
    """Verify render_kinetic_rxn_profile rejects PENDING, missing, and wrong-n_imag rows."""
    # Case 1: TS2 is PENDING with NaN energies
    rows_pending = _valid_five_point_rows()
    rows_pending[3]["status"] = "PENDING"
    rows_pending[3]["delta_g_qrrho_kcal"] = "NaN"
    csv_pending = _write_stationary_csv(tmp_path / "pending.csv", rows_pending)

    with pytest.raises(ValueError, match="TS2"):
        render_kinetic_rxn_profile(
            csv_pending, tmp_path / "p.png", tmp_path / "p.pdf", strict=True
        )
    assert not (tmp_path / "p.png").exists()

    # Non-strict mode marks TS2 PENDING explicitly while plotting verified points
    receipt_partial = render_kinetic_rxn_profile(
        csv_pending, tmp_path / "partial.png", tmp_path / "partial.pdf", strict=False
    )
    assert receipt_partial["pending_states"] == ["TS2"]
    assert receipt_partial["verified_states"] == ["R", "TS1", "Int_tet", "P"]
    assert (tmp_path / "partial.png").is_file()
    assert (tmp_path / "partial.pdf").is_file()

    # Case 2: Missing Int_tet row
    rows_missing = [r for r in _valid_five_point_rows() if r["state"] != "Int_tet"]
    csv_missing = _write_stationary_csv(tmp_path / "missing.csv", rows_missing)
    with pytest.raises(ValueError, match="Int_tet"):
        render_kinetic_rxn_profile(
            csv_missing, tmp_path / "m.png", tmp_path / "m.pdf", strict=True
        )

    # Case 3: TS1 has wrong Hessian index (n_imag = 0 instead of 1)
    rows_bad_imag = _valid_five_point_rows()
    rows_bad_imag[1]["n_imag"] = 0
    csv_bad_imag = _write_stationary_csv(tmp_path / "bad_imag.csv", rows_bad_imag)
    with pytest.raises(ValueError, match="n_imag=0"):
        render_kinetic_rxn_profile(
            csv_bad_imag, tmp_path / "b.png", tmp_path / "b.pdf", strict=True
        )


def test_kinetic_rxn_profile_renders_valid_five_point_schema_fixture(tmp_path: Path) -> None:
    """Verify render_kinetic_rxn_profile cleanly plots a valid 5-point verified schema fixture."""
    csv_ok = _write_stationary_csv(tmp_path / "stationary_table.csv", _valid_five_point_rows())
    out_png = tmp_path / "rxn_profile.png"
    out_pdf = tmp_path / "rxn_profile.pdf"
    manifest = tmp_path / "rxn_manifest.json"

    receipt = render_kinetic_rxn_profile(
        csv_ok, out_png, out_pdf, strict=True, manifest_path=manifest
    )

    assert out_png.is_file() and out_png.stat().st_size > 10_000
    assert out_pdf.is_file() and out_pdf.stat().st_size > 5_000
    assert out_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out_pdf.read_bytes()[:5] == b"%PDF-"
    assert receipt["verified_states"] == ["R", "TS1", "Int_tet", "TS2", "P"]
    assert receipt["pending_states"] == []
    assert receipt["source_csv_sha256"] == sha256_file(csv_ok)
    assert receipt["outputs"]["png"]["sha256"] == sha256_file(out_png)
    assert receipt["outputs"]["pdf"]["sha256"] == sha256_file(out_pdf)


def test_verify_source_register_19_of_19_and_farir_rejection(tmp_path: Path) -> None:
    """Verify 19/19 in-scope Drive figure register (4 FTMW + 15 Keratin) and Far-IR rejection."""
    manifest_file = default_manifest_path()
    assert manifest_file.is_file()

    report = verify_source_register(manifest_file, verify_on_disk=False)
    assert report["passed"] is True
    assert report["total_figures"] == 19
    assert report["collection_counts"] == {
        "FTMW methodology manuscript": 4,
        "Keratin v1.1.0": 15,
    }
    assert report["farir_exclusion_passed"] is True

    # Negative tests: every prohibited Far-IR encyclopedia marker must raise FarIRExclusionError
    base_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    for bad_token in ("FarIR_v16", "MRW_Permission", "SPCT", "Elsevier"):
        poisoned = json.loads(json.dumps(base_data))
        poisoned["entries"][0]["figure"] = f"injected_{bad_token}_fig"
        poisoned_path = tmp_path / f"poisoned_{bad_token}.json"
        poisoned_path.write_text(json.dumps(poisoned), encoding="utf-8")
        with pytest.raises(FarIRExclusionError):
            verify_source_register(poisoned_path)

    audit_clean = audit_farir_exclusion({"collection": "Keratin v1.1.0", "figure": "Fig00"})
    assert audit_clean["passed"] is True
    assert audit_clean["violation_count"] == 0


def test_cochem_modules_entry_point_and_scribe_provider_dispatch(tmp_path: Path) -> None:
    """Verify cochem.modules entry point loads scribe_provider and conforms to module-provider/1."""
    eps = [ep for ep in metadata.entry_points(group="cochem.modules") if ep.name == "scribe"]
    assert len(eps) == 1, f"Expected exactly 1 cochem.modules 'scribe' entry point, found {eps!r}"
    assert eps[0].value == "cochem_scribe.provider:scribe_provider"

    loaded = eps[0].load()
    assert loaded is scribe_provider

    meta = loaded()
    assert meta["module_id"] == "scribe"
    assert meta["distribution"] == "CoChem-SCRIBE"
    assert meta["integration_contract"] == "cochem.module-handoff/1"
    assert meta["scientific_api_version"] == "cochem.module-provider/1"
    assert set(meta["operations"]) == {
        "render_geom_comparison",
        "render_kinetic_rxn_profile",
        "verify_source_register",
        "audit_farir_exclusion",
    }

    reg_res = loaded.dispatch_operation("verify_source_register", {})
    assert reg_res["total_figures"] == 19
    assert reg_res["passed"] is True

    audit_res = loaded.dispatch_operation(
        "audit_farir_exclusion", {"target": {"figure": "Fig01A"}, "raise_on_violation": True}
    )
    assert audit_res["passed"] is True

    geom_res = loaded.dispatch_operation(
        "render_geom_comparison",
        {
            "comparison_json_path": str(GEOM_COMPARISON_JSON),
            "out_png": str(tmp_path / "ep_geom.png"),
            "out_pdf": str(tmp_path / "ep_geom.pdf"),
        },
    )
    assert geom_res["r_e_se_status"] == "PENDING"
    assert Path(geom_res["outputs"]["png"]["path"]).is_file()
