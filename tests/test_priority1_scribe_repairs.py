"""Zero-mock regression tests for FRIC-11 (render-geom with optional PENDING PySCF) & FRIC-12 (packaged register)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cochem_scribe.cli import main as cli_main
from cochem_scribe.register import default_manifest_path, verify_source_register
from cochem_scribe.renderers import render_geom_comparison, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[1]
GEOM_COMPARISON_JSON = (
    REPO_ROOT.parent
    / "CoChem-GEOM"
    / "benchmarks"
    / "h2o_t_geom_01"
    / "h2o_t_geom_01_comparison.json"
)


def test_render_geom_allows_pending_optional_pyscf_and_strict_rejects(tmp_path: Path) -> None:
    """FRIC-11: CHEM 490 student pack has VERIFIED ORCA + r_s + r_0 with PENDING PySCF r_e."""
    if not GEOM_COMPARISON_JSON.is_file():
        pytest.skip("CoChem-GEOM benchmark JSON not found")
    payload = json.loads(GEOM_COMPARISON_JSON.read_text(encoding="utf-8"))
    payload["columns"]["r_e_ccsd_cc_pvdz_pyscf"] = {
        "status": "PENDING",
        "bond_angstrom": None,
        "angle_deg": None,
        "reason": "Optional PySCF CCSD not executed in CHEM 490 student pack.",
    }
    student_json = tmp_path / "chem490_h2o_comparison.json"
    student_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    out_png = tmp_path / "chem490_geom.png"
    out_pdf = tmp_path / "chem490_geom.pdf"
    receipt = render_geom_comparison(student_json, out_png, out_pdf)
    assert out_png.is_file() and out_png.stat().st_size > 10_000
    assert out_pdf.is_file() and out_pdf.stat().st_size > 5_000
    by_key = {c["key"]: c for c in receipt["columns"]}
    assert by_key["r_e_ccsd_cc_pvtz_orca"]["status"] == "VERIFIED"
    assert by_key["r_e_ccsd_cc_pvdz_pyscf"]["status"] == "PENDING"
    assert by_key["r_e_ccsd_cc_pvdz_pyscf"]["bond_angstrom"] is None

    # Strict mode still refuses PENDING optional columns
    with pytest.raises(ValueError, match="r_e_ccsd_cc_pvdz_pyscf"):
        render_geom_comparison(student_json, tmp_path / "s.png", tmp_path / "s.pdf", allow_pending_optional=False)

    # Zero verified r_e columns MUST fail closed even in default mode
    both_pending = json.loads(json.dumps(payload))
    both_pending["columns"]["r_e_ccsd_cc_pvtz_orca"] = {"status": "PENDING", "bond_angstrom": None, "angle_deg": None}
    bad_json = tmp_path / "no_re.json"
    bad_json.write_text(json.dumps(both_pending), encoding="utf-8")
    with pytest.raises(ValueError, match="At least one verified equilibrium r_e column"):
        render_geom_comparison(bad_json, tmp_path / "b.png", tmp_path / "b.pdf")

    # CLI default succeeds on student pack
    assert cli_main(["render-geom", "--input", str(student_json), "--out-png", str(tmp_path / "cli.png"), "--out-pdf", str(tmp_path / "cli.pdf")]) == 0


def test_packaged_figure_register_matches_repo_manifest_sha256() -> None:
    """FRIC-12 / FRICTION-312-09: Wheel-bundled manifest matches repo manifest byte-for-byte."""
    repo_manifest = REPO_ROOT / "manifests" / "in_scope_figure_register.json"
    pkg_manifest = REPO_ROOT / "src" / "cochem_scribe" / "manifests" / "in_scope_figure_register.json"
    assert repo_manifest.is_file()
    assert pkg_manifest.is_file()
    assert sha256_file(repo_manifest) == sha256_file(pkg_manifest)
    assert default_manifest_path().is_file()
    report = verify_source_register(pkg_manifest, verify_on_disk=False)
    assert report["passed"] is True and report["total_figures"] == 19
