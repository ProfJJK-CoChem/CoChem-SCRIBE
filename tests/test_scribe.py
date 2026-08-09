#!/usr/bin/env python3
"""
PyTest Suite for CoChem-SCRIBE
Resolves SCRIBE-14: Comprehensive automated unit test coverage.
"""

import os
import sys
import tempfile
import json
import zipfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import scribe_payload_builder
import scribe_doc_manager
import scribe_orchestration
import scribe_figure_generator
import scribe_inference
import scribe_legacy_bundler

def test_payload_builder_crossref_caching():
    builder = scribe_payload_builder.ScribePayloadBuilder()
    cits = builder._query_crossref_citations(['Grimme D4'])
    assert 'Grimme D4' in cits
    assert Path("crossref_cache.json").exists()

def test_payload_builder_bibtex_generation():
    builder = scribe_payload_builder.ScribePayloadBuilder()
    cits = {
        'TestTheory': {
            'author': 'Smith, J.',
            'title': 'Test Method',
            'journal': 'J. Chem. Phys.',
            'year': '2024',
            'volume': '150',
            'pages': '100-110',
            'DOI': '10.1063/1.12345'
        }
    }
    bib = builder._generate_bibtex(cits)
    assert "@article" in bib
    assert "J. Chem. Phys." in bib
    assert "10.1063/1.12345" in bib

def test_extract_energetics_table():
    builder = scribe_payload_builder.ScribePayloadBuilder()
    tbl = builder.extract_energetics_table()
    assert "\\begin{table}" in tbl
    assert Path("manuscript_tables.tex").exists()

def test_doc_manager_chunked_compression():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_zst = Path(tmpdir) / "test_data.tar.zst"
        manager = scribe_doc_manager.ScribeDocumentManager()
        
        # Test slice writing using mock dataset
        class MockDataset:
            shape = (100,)
            name = "mock_ds"
            def __getitem__(self, idx):
                return range(100)[idx]
                
        manager._compress_dataset_chunked(MockDataset(), out_zst)
        assert out_zst.exists()

def test_legacy_bundler_checksum_and_zstd():
    bundler = scribe_legacy_bundler.LegacyVerificationBundler()
    mock_lin = Path("test_output.lin")
    mock_lin.write_text("1 0 1 0 0 0 12500.00 0.05 1.0\n")
    bundler.legacy_files = [mock_lin]
    
    bundler.create_legacy_bundle()
    assert Path("Legacy_Verification.zip").exists()
    assert Path("checksums.sha256").exists()
    
    with zipfile.ZipFile("Legacy_Verification.zip", "r") as z:
        names = z.namelist()
        assert "test_output.lin" in names
        assert "test_output.lin.zst" in names
        assert "checksums.sha256" in names
        
    # Clean up test artifact
    if mock_lin.exists():
        mock_lin.unlink()

def test_figure_generator():
    generator = scribe_figure_generator.ScribeFigureGenerator()
    generator.generate_all_artifacts()
    assert generator.output_dir.exists()

def test_inference_engine_offline_fallback():
    engine = scribe_inference.ScribeInferenceEngine()
    engine.api_key = ""
    res = engine._fallback_offline_jinja_rendering()
    assert "Notice: Generated via Offline Fallback Engine" in res

def test_orchestration_structure():
    orch = scribe_orchestration.ScribeOrchestrator()
    assert hasattr(orch, 'run_command')
    assert hasattr(orch, 'spawn_daemon')

def test_cochem_scribe_compiler():
    import h5py
    from cochem_scribe_compiler import ScribeCompiler
    with tempfile.TemporaryDirectory() as tmpdir:
        h5_path = Path(tmpdir) / "landscape.h5"
        with h5py.File(h5_path, 'w') as f:
            g1 = f.create_group("conformer_001")
            g1.attrs['energy'] = -154.234
            g1.attrs['enthalpy'] = -154.120
            g1.attrs['gibbs_free_energy'] = -154.150
            g2 = f.create_group("conformer_002")
            g2.attrs['energy'] = -154.230
            g2.attrs['enthalpy'] = -154.116
            g2.attrs['gibbs_free_energy'] = -154.145

        out_tex = Path(tmpdir) / "tables.tex"
        compiler = ScribeCompiler(str(h5_path))
        tex = compiler.generate_energetics_table(str(out_tex))
        assert "\\begin{table}" in tex
        assert "conformer_001" in tex
        assert out_tex.exists()

def test_cochem_scribe_master():
    from cochem_scribe_master import MethodologyTracker
    tracker = MethodologyTracker()
    tracker.compute_flags = {"ORCA_6", "MACE_OFF24m", "DLPNO-CCSD(T)"}
    m_tex = tracker.render_methods_tex("test_methods.tex")
    r_bib = tracker.render_references_bib("test_references.bib")
    assert "\\section{Computational Methods}" in m_tex
    assert "@article" in r_bib
    assert "ORCA" in m_tex or "DLPNO" in m_tex
    if Path("test_methods.tex").exists():
        Path("test_methods.tex").unlink()
    if Path("test_references.bib").exists():
        Path("test_references.bib").unlink()

def test_state_tensor_provenance_hash():
    import h5py
    import numpy as np
    from cochem_scribe_master import compute_state_tensor_provenance_hash
    with tempfile.TemporaryDirectory() as tmpdir:
        h5_path = Path(tmpdir) / "test_state.h5"
        with h5py.File(h5_path, 'w') as f:
            f.create_dataset("tensor_1", data=np.array([1.0, 2.0, 3.0]))
            f.attrs["calc_mode"] = "DLPNO-CCSD(T)"
        digest1 = compute_state_tensor_provenance_hash(h5_path)
        assert len(digest1) == 64

        # Verify hash changes when tensor data mutates
        with h5py.File(h5_path, 'a') as f:
            f["tensor_1"][:] = np.array([1.0, 2.0, 4.0])
        digest2 = compute_state_tensor_provenance_hash(h5_path)
        assert digest1 != digest2

def test_siunitx_table_formatting():
    from cochem_scribe_compiler import ScribeCompiler
    import h5py
    with tempfile.TemporaryDirectory() as tmpdir:
        h5_path = Path(tmpdir) / "landscape.h5"
        with h5py.File(h5_path, 'w') as f:
            g1 = f.create_group("conformer_A")
            g1.attrs['energy'] = -10.0
        out_tex = Path(tmpdir) / "tables_si.tex"
        compiler = ScribeCompiler(str(h5_path))
        tex = compiler.generate_energetics_table(str(out_tex))
        assert "\\usepackage{siunitx}" in tex
        assert "S[table-format=" in tex

