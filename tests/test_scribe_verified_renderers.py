"""Zero-mock tests for CoChem-SCRIBE verified-output renderers, 19/19 register, and provider."""

from __future__ import annotations

import csv
import hashlib
import json
from importlib import metadata, resources
from pathlib import Path

import pytest

from cochem_scribe.cli import main as scribe_cli_main
from cochem_scribe.provider import scribe_provider
from cochem_scribe.register import (
    FarIRExclusionError,
    audit_farir_exclusion,
    default_manifest_path,
    verify_source_register,
)
from cochem_scribe.renderers import (
    render_basis_convergence,
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
KINETIC_CASE_A_CSV = (
    REPO_ROOT.parent
    / "CoChem-KINETIC"
    / "benchmarks"
    / "chem312_t_kin_01"
    / "case_a_team1_formate"
    / "stationary_table.csv"
)
KINETIC_CASE_B_CSV = (
    REPO_ROOT.parent
    / "CoChem-KINETIC"
    / "benchmarks"
    / "chem312_t_kin_01"
    / "case_b_team4_ec_cyclization"
    / "stationary_table.csv"
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
        "render_basis_convergence",
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


def test_live_render_chem312_verified_kinetic_profiles(tmp_path: Path) -> None:
    """Live zero-mock render of BOTH V-A6 verified CoChem-KINETIC CHEM 312 CSVs + manifest check."""
    assert KINETIC_CASE_A_CSV.is_file(), f"Missing verified Case A CSV: {KINETIC_CASE_A_CSV}"
    assert KINETIC_CASE_B_CSV.is_file(), f"Missing verified Case B CSV: {KINETIC_CASE_B_CSV}"

    cases = [
        (
            "chem312_team1_formate_rxn_profile",
            KINETIC_CASE_A_CSV,
            "CHEM 312 Case A (Team 1, C5H10O6S, Q=0): DF-ωB97X-D3/def2-TZVPP + C-PCM(MeCN)",
            18.1319,
            18.3319,
        ),
        (
            "chem312_team4_carbonate_rxn_profile",
            KINETIC_CASE_B_CSV,
            "CHEM 312 Case B (Team 4, C4H7O4-, Q=-1): DF-ωB97X-D3/def2-TZVPP + C-PCM(MeCN)",
            0.9262,
            0.7090,
        ),
    ]

    manifest = json.loads((CHECKED_IN_VERIFIED_DIR / "manifest_sha256.json").read_text(encoding="utf-8"))

    for stem, csv_path, title, expected_ts1_dg, expected_ts2_dg in cases:
        out_png = tmp_path / f"{stem}.png"
        out_pdf = tmp_path / f"{stem}.pdf"
        out_manifest = tmp_path / f"{stem}.json"

        receipt = render_kinetic_rxn_profile(
            csv_path,
            out_png,
            out_pdf,
            strict=True,
            title=title,
            manifest_path=out_manifest,
        )

        assert out_png.is_file() and out_png.stat().st_size > 10_000
        assert out_pdf.is_file() and out_pdf.stat().st_size > 5_000
        assert out_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert out_pdf.read_bytes()[:5] == b"%PDF-"
        assert receipt["verified_states"] == ["R", "TS1", "Int_tet", "TS2", "P"]
        assert receipt["pending_states"] == []
        assert receipt["source_csv_sha256"] == sha256_file(csv_path)

        by_state = {pt["state"]: pt for pt in receipt["stationary_points"]}
        assert by_state["R"]["n_imag"] == 0
        assert by_state["TS1"]["n_imag"] == 1
        assert by_state["Int_tet"]["n_imag"] == 0
        assert by_state["TS2"]["n_imag"] == 1
        assert by_state["P"]["n_imag"] == 0
        assert by_state["TS1"]["delta_g_kcal"] == pytest.approx(expected_ts1_dg, abs=1e-4)
        assert by_state["TS2"]["delta_g_kcal"] == pytest.approx(expected_ts2_dg, abs=1e-4)

        # Verify checked-in benchmark artifacts & unified manifest hashes match disk
        checked_png = CHECKED_IN_VERIFIED_DIR / f"{stem}.png"
        checked_pdf = CHECKED_IN_VERIFIED_DIR / f"{stem}.pdf"
        assert checked_png.is_file() and checked_pdf.is_file()
        assert manifest["files_sha256"][checked_png.name] == sha256_file(checked_png)
        assert manifest["files_sha256"][checked_pdf.name] == sha256_file(checked_pdf)
        assert manifest["verified_figures"][stem]["source_csv_sha256"] == sha256_file(csv_path)


def _valid_three_point_rows(bond_col: str = "forming_breaking_co") -> list[dict[str, object]]:
    return [
        {
            "state": "R",
            "status": "CONVERGED",
            "n_imag": 0,
            "imag_freq_cm1": "0.00",
            bond_col: "",
            "e_dft_ha": "-132.7051234500",
            "zpe_ha": "0.0451200000",
            "delta_e_kcal": "0.0000",
            "delta_h_kcal": "0.0000",
            "delta_g_rrho_kcal": "0.0000",
            "delta_g_qrrho_kcal": "0.0000",
        },
        {
            "state": "TS",
            "status": "CONVERGED",
            "n_imag": 1,
            "imag_freq_cm1": "-896.91",
            bond_col: "C0-N4=1.954A",
            "e_dft_ha": "-132.6352000000",
            "zpe_ha": "0.0439000000",
            "delta_e_kcal": "43.8777",
            "delta_h_kcal": "43.0457",
            "delta_g_rrho_kcal": "42.7100",
            "delta_g_qrrho_kcal": "42.6849",
        },
        {
            "state": "P",
            "status": "CONVERGED",
            "n_imag": 0,
            "imag_freq_cm1": "0.00",
            bond_col: "",
            "e_dft_ha": "-132.7412000000",
            "zpe_ha": "0.0454000000",
            "delta_e_kcal": "-22.6384",
            "delta_h_kcal": "-22.4900",
            "delta_g_rrho_kcal": "-22.6000",
            "delta_g_qrrho_kcal": "-22.5884",
        },
    ]


def test_kinetic_rxn_profile_renders_3pt_and_generic_bond_columns(tmp_path: Path) -> None:
    """FINDING-410-04: support 3-point (R, TS, P) CSVs with forming_breaking_co or generic bond columns."""
    for bond_col in ("forming_breaking_co", "reaction_coordinate_bond", "key_active_bond"):
        rows = _valid_three_point_rows(bond_col=bond_col)
        csv_path = tmp_path / f"stationary_3pt_{bond_col}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        out_png = tmp_path / f"rxn_3pt_{bond_col}.png"
        out_pdf = tmp_path / f"rxn_3pt_{bond_col}.pdf"
        out_manifest = tmp_path / f"rxn_3pt_{bond_col}.json"
        receipt = render_kinetic_rxn_profile(
            csv_path,
            out_png,
            out_pdf,
            strict=True,
            manifest_path=out_manifest,
        )
        assert out_png.is_file() and out_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert out_pdf.is_file() and out_pdf.read_bytes()[:5] == b"%PDF-"
        assert receipt["pathway_mode"] == "elementary_3pt"
        assert receipt["n_stationary_points"] == 3
        assert receipt["bond_column"] == bond_col
        assert receipt["verified_states"] == ["R", "TS", "P"]
        assert receipt["pending_states"] == []
        ts_pt = next(p for p in receipt["stationary_points"] if p["state"] == "TS")
        assert ts_pt["active_bond"] == "C0-N4=1.954A"
        assert audit_farir_exclusion(out_manifest)["passed"] is True

    # Also verify CLI round-trip on 3-point CSV without any bond column
    rows_no_bond = [{k: v for k, v in r.items() if k != "forming_breaking_co"} for r in _valid_three_point_rows()]
    csv_no_bond = tmp_path / "stationary_3pt_nobond.csv"
    with csv_no_bond.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows_no_bond[0].keys()))
        writer.writeheader()
        writer.writerows(rows_no_bond)

    rc = scribe_cli_main(
        [
            "render-kinetic",
            "--input",
            str(csv_no_bond),
            "--out-png",
            str(tmp_path / "cli_3pt.png"),
            "--out-pdf",
            str(tmp_path / "cli_3pt.pdf"),
            "--manifest",
            str(tmp_path / "cli_3pt.json"),
        ]
    )
    assert rc == 0
    assert (tmp_path / "cli_3pt.png").is_file()
    assert (tmp_path / "cli_3pt.pdf").is_file()

    # Fail closed on bad n_imag for 3-point TS and on mixed TS + TS1 ambiguity
    bad_ts = _valid_three_point_rows()
    bad_ts[1]["n_imag"] = 0
    csv_bad = tmp_path / "bad_3pt_ts.csv"
    with csv_bad.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(bad_ts[0].keys()))
        writer.writeheader()
        writer.writerows(bad_ts)
    with pytest.raises(ValueError, match="n_imag=0"):
        render_kinetic_rxn_profile(csv_bad, tmp_path / "bad.png", tmp_path / "bad.pdf", strict=True)

    mixed_rows = _valid_three_point_rows() + [
        {** _valid_three_point_rows()[1], "state": "TS1"}
    ]
    csv_mixed = tmp_path / "mixed.csv"
    with csv_mixed.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(mixed_rows[0].keys()))
        writer.writeheader()
        writer.writerows(mixed_rows)
    with pytest.raises(ValueError, match="Ambiguous"):
        render_kinetic_rxn_profile(csv_mixed, tmp_path / "mix.png", tmp_path / "mix.pdf", strict=True)


def test_render_geom_non_ccsd_pending_omitted_and_fail_closed(tmp_path: Path) -> None:
    """FINDING-411-04 & FINDING-490-04: render verified non-CCSD columns, annotate CCSD: PENDING, fail closed on 0 verified."""
    # Case 1: CCSD columns explicitly PENDING/NaN (e.g., `cochem-geom benchmark-h2o` without --run-qm)
    pending_ccsd_payload = {
        "schema_version": "cochem.geom.structural-comparison/1",
        "molecule": "H2O",
        "symmetry": "C2v",
        "columns": {
            "r_e_ccsd_cc_pvtz_orca": {"status": "PENDING"},
            "r_e_ccsd_cc_pvdz_pyscf": {"status": "PENDING", "bond_angstrom": "NaN", "angle_deg": "NaN"},
            "r_s_kraitchman": {
                "status": "VERIFIED",
                "bond_angstrom": 0.965592,
                "bond_costain_uncertainty_angstrom": 0.014363,
                "angle_deg": 103.4504,
                "angle_costain_uncertainty_deg": 2.1525,
            },
            "r_0_weighted_fit": {
                "status": "VERIFIED",
                "bond_label": "r(O-H)",
                "angle_label": "angle(H-O-H)",
                "bond_angstrom": 0.957470,
                "bond_std_err_scaled_angstrom": 0.001191,
                "angle_deg": 104.9839,
                "angle_std_err_scaled_deg": 0.1643,
            },
            "r_e_se": {"status": "PENDING", "bond_angstrom": None, "angle_deg": None},
        },
        "experimental_provenance": {"source_doi": "10.1021/jp511432m"},
    }
    p1_json = tmp_path / "h2o_non_ccsd_pending.json"
    p1_json.write_text(json.dumps(pending_ccsd_payload, indent=2), encoding="utf-8")
    p1_png = tmp_path / "h2o_non_ccsd.png"
    p1_pdf = tmp_path / "h2o_non_ccsd.pdf"
    p1_man = tmp_path / "h2o_non_ccsd_manifest.json"
    r1 = render_geom_comparison(p1_json, p1_png, p1_pdf, manifest_path=p1_man)
    assert p1_png.is_file() and p1_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert p1_pdf.is_file() and p1_pdf.read_bytes()[:5] == b"%PDF-"
    assert r1["ccsd_status"] == "PENDING"
    assert r1["verified_columns"] == ["r_s_kraitchman", "r_0_weighted_fit"]
    assert "r_e_ccsd_cc_pvtz_orca" in r1["pending_columns"]
    assert audit_farir_exclusion(p1_man)["passed"] is True

    # Case 2: CCSD columns omitted completely, local revDSD CHEM 490 column verified
    revdsd_payload = {
        "schema_version": "cochem.geom.structural-comparison/1",
        "molecule": "H2O",
        "symmetry": "C2v",
        "columns": {
            "r_e_revdsd_def2_tzvpp_orca": {
                "status": "VERIFIED",
                "backend": "orca_revdsd",
                "method": "revDSD-PBEP86-D4",
                "basis": "def2-TZVPP",
                "bond_angstrom": 0.959387,
                "angle_deg": 104.244,
            },
            "r_0_weighted_fit": {
                "status": "VERIFIED",
                "bond_label": "r(O-H)",
                "angle_label": "angle(H-O-H)",
                "bond_angstrom": 0.957470,
                "bond_std_err_scaled_angstrom": 0.001191,
                "angle_deg": 104.9839,
                "angle_std_err_scaled_deg": 0.1643,
            },
        },
    }
    p2_json = tmp_path / "h2o_revdsd_only.json"
    p2_json.write_text(json.dumps(revdsd_payload, indent=2), encoding="utf-8")
    r2 = render_geom_comparison(p2_json, tmp_path / "revdsd.png", tmp_path / "revdsd.pdf")
    assert r2["ccsd_status"] == "PENDING"
    assert r2["verified_columns"] == ["r_e_revdsd_def2_tzvpp_orca", "r_0_weighted_fit"]
    assert (tmp_path / "revdsd.png").is_file()

    # Case 3: Fail closed when ZERO verified data columns exist
    all_pending_payload = {
        "schema_version": "cochem.geom.structural-comparison/1",
        "molecule": "H2O",
        "columns": {
            "r_e_ccsd_cc_pvtz_orca": {"status": "PENDING"},
            "r_e_ccsd_cc_pvdz_pyscf": {"status": "PENDING"},
            "r_e_se": {"status": "PENDING"},
        },
    }
    p3_json = tmp_path / "h2o_all_pending.json"
    p3_json.write_text(json.dumps(all_pending_payload, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="No verified structural columns"):
        render_geom_comparison(p3_json, tmp_path / "empty.png", tmp_path / "empty.pdf")
    assert not (tmp_path / "empty.png").exists()


def test_render_basis_convergence_json_csv_cli_and_farir(tmp_path: Path) -> None:
    """FINDING-411-04 & FINDING-490-04: render-convergence PNG+PDF+SHA-256 manifest, FARIR-clean, fail-closed."""
    # 1. CHEM 411 M2 authentic H2CO basis-set convergence JSON via CLI
    m2_payload = {
        "molecule": "H2CO (Formaldehyde)",
        "pyscf_convergence": [
            {
                "basis": "def2-SVP",
                "nao": 38,
                "rhf_converged": True,
                "rhf_energy_eh": -113.77890351964737,
                "b3lyp_converged": True,
                "b3lyp_energy_eh": -114.41527315255871,
                "mp2_total_energy_eh": -114.09457304964101,
            },
            {
                "basis": "cc-pVDZ",
                "nao": 38,
                "rhf_converged": True,
                "rhf_energy_eh": -113.87661760667604,
                "b3lyp_converged": True,
                "b3lyp_energy_eh": -114.50739223124799,
                "mp2_total_energy_eh": -114.19263618752215,
            },
            {
                "basis": "def2-TZVP",
                "nao": 74,
                "rhf_converged": True,
                "rhf_energy_eh": -113.91675505558379,
                "b3lyp_converged": True,
                "b3lyp_energy_eh": -114.5542564739603,
                "mp2_total_energy_eh": -114.30471615662576,
            },
            {
                "basis": "cc-pVTZ",
                "nao": 88,
                "rhf_converged": True,
                "rhf_energy_eh": -113.91205807638676,
                "b3lyp_converged": True,
                "b3lyp_energy_eh": -114.54940498725674,
                "mp2_total_energy_eh": -114.30696488116314,
            },
        ],
        "orca_convergence": [
            {
                "basis": "def2-SVP",
                "terminated_normally": True,
                "rhf_energy_eh": -113.778903518805,
                "b3lyp_energy_eh": -114.356101732971,
                "mp2_total_energy_eh": -114.094572985161,
            },
            {
                "basis": "def2-TZVP",
                "terminated_normally": True,
                "rhf_energy_eh": -113.916755054387,
                "b3lyp_energy_eh": -114.49509381295,
                "mp2_total_energy_eh": -114.304715304005,
            },
            {
                "basis": "cc-pVTZ",
                "terminated_normally": True,
                "rhf_energy_eh": -113.912058075813,
                "b3lyp_energy_eh": -114.490238594513,
                "mp2_total_energy_eh": -114.30696489301,
            },
        ],
        "helgaker_cbs_mp2_corr_dz_tz_eh": -0.4281228990628114,
    }
    json_in = tmp_path / "chem411_m2_basis_convergence.json"
    json_in.write_text(json.dumps(m2_payload, indent=2), encoding="utf-8")
    out_dir = tmp_path / "conv_out"

    rc = scribe_cli_main(
        [
            "render-convergence",
            "--input",
            str(json_in),
            "--output-dir",
            str(out_dir),
            "--prefix",
            "h2co_m2_convergence",
        ]
    )
    assert rc == 0
    png_file = out_dir / "h2co_m2_convergence.png"
    pdf_file = out_dir / "h2co_m2_convergence.pdf"
    man_file = out_dir / "h2co_m2_convergence_manifest_sha256.json"
    assert png_file.is_file() and png_file.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert pdf_file.is_file() and pdf_file.read_bytes()[:5] == b"%PDF-"
    assert man_file.is_file()

    manifest = json.loads(man_file.read_text(encoding="utf-8"))
    assert manifest["mode"] == "basis_set_convergence"
    assert manifest["verified_point_count"] == 21
    assert manifest["pending_point_count"] == 0
    assert manifest["outputs"]["png"]["sha256"] == sha256_file(png_file)
    assert manifest["outputs"]["pdf"]["sha256"] == sha256_file(pdf_file)
    farir_report = audit_farir_exclusion(out_dir, raise_on_violation=False)
    assert farir_report["passed"] is True
    assert farir_report["violation_count"] == 0

    # 2. CHEM 490 CSV method comparison with explicit PENDING CCSD entry
    csv_in = tmp_path / "chem490_methods.csv"
    csv_rows = [
        {"molecule": "H2CO", "engine": "ORCA", "method": "B3LYP-D4", "basis": "def2-TZVPP", "energy_eh": "-114.495084", "status": "VERIFIED"},
        {"molecule": "H2CO", "engine": "ORCA", "method": "revDSD-PBEP86-D4", "basis": "def2-TZVPP", "energy_eh": "-114.357977", "status": "VERIFIED"},
        {"molecule": "H2CO", "engine": "ORCA", "method": "CCSD(T)", "basis": "cc-pVTZ", "energy_eh": "PENDING", "status": "PENDING"},
    ]
    with csv_in.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    csv_out = tmp_path / "conv_csv_out"
    receipt_csv = render_basis_convergence(csv_in, csv_out, prefix="chem490_h2co")
    assert receipt_csv["mode"] == "method_comparison"
    assert receipt_csv["verified_point_count"] == 2
    assert receipt_csv["pending_point_count"] == 1
    assert (csv_out / "chem490_h2co.png").is_file()
    assert (csv_out / "chem490_h2co.pdf").is_file()
    assert audit_farir_exclusion(csv_out)["passed"] is True

    # Strict mode rejects PENDING entry
    with pytest.raises(ValueError, match="PENDING"):
        render_basis_convergence(csv_in, tmp_path / "strict_fail", strict=True)

    # All-PENDING input fails closed even when strict=False
    empty_json = tmp_path / "all_pending_conv.json"
    empty_json.write_text(
        json.dumps({"records": [{"basis": "cc-pVTZ", "method": "CCSD", "energy_eh": "NaN", "status": "PENDING"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="No verified finite energy convergence points"):
        render_basis_convergence(empty_json, tmp_path / "zero_out")

    # Provider dispatch check
    prov_res = scribe_provider.dispatch_operation(
        "render_basis_convergence",
        {
            "input_path": str(json_in),
            "output_dir": str(tmp_path / "prov_conv"),
            "prefix": "prov_h2co",
        },
    )
    assert prov_res["verified_point_count"] == 21
    assert Path(prov_res["outputs"]["png"]["path"]).is_file()


def test_packaged_figure_register_resource_and_default_cli() -> None:
    """FINDING-411-05 / 490-06 / 312-09: packaged manifest matches repo manifest and default CLI exits 0."""
    pkg_res = resources.files("cochem_scribe").joinpath("manifests", "in_scope_figure_register.json")
    assert pkg_res.is_file(), "Packaged in_scope_figure_register.json missing from cochem_scribe package data"

    repo_manifest = REPO_ROOT / "manifests" / "in_scope_figure_register.json"
    assert repo_manifest.is_file()
    with resources.as_file(pkg_res) as pkg_path:
        pkg_lf_sha = hashlib.sha256(pkg_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        repo_lf_sha = hashlib.sha256(repo_manifest.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert pkg_lf_sha == repo_lf_sha
        assert json.loads(pkg_path.read_text(encoding="utf-8")) == json.loads(
            repo_manifest.read_text(encoding="utf-8")
        )

    report = verify_source_register()
    assert report["passed"] is True
    assert report["total_figures"] == 19
    assert scribe_cli_main(["verify-register"]) == 0

