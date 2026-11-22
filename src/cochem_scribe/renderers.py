"""Verified-output scientific figure renderers for CoChem-SCRIBE.

Every renderer ingests verified upstream computational artifacts, validates
convergence and numeric finiteness, refuses to fabricate synthetic axes or
missing values, preserves explicit PENDING states, and records SHA-256
provenance in both the figure footer and JSON manifest receipts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

CANONICAL_KINETIC_STATES: tuple[str, ...] = ("R", "TS1", "Int_tet", "TS2", "P")
EXPECTED_N_IMAG: dict[str, int] = {
    "R": 0,
    "TS1": 1,
    "Int_tet": 0,
    "TS2": 1,
    "P": 0,
}


def sha256_file(filepath: str | Path) -> str:
    """Compute the lowercase hexadecimal SHA-256 digest of a file."""
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"Artifact file not found: {path}")
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _parse_finite_float(raw: Any, field_name: str) -> float:
    if raw is None:
        raise ValueError(f"Missing numeric value for {field_name!r}")
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text.upper() in {"PENDING", "NAN", "NONE", "NULL", "TBD", "N/A"}:
            raise ValueError(f"Unverified/non-numeric value {raw!r} for {field_name!r}")
        value = float(text)
    else:
        value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"Non-finite value {raw!r} for {field_name!r}")
    return value


def _try_finite_float(raw: Any) -> float | None:
    try:
        return _parse_finite_float(raw, "value")
    except (TypeError, ValueError):
        return None


def _is_row_converged(row: dict[str, Any]) -> bool:
    if "converged" in row and str(row["converged"]).strip() != "":
        val = str(row["converged"]).strip().lower()
        if val in {"true", "1", "yes", "converged", "verified"}:
            return True
        if val in {"false", "0", "no", "pending", "failed", "unconverged"}:
            return False
    if "status" in row and str(row["status"]).strip() != "":
        status = str(row["status"]).strip().upper()
        return status in {"CONVERGED", "VERIFIED", "OK", "PASS"}
    return False


class GeomColumnSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    status: str
    bond_angstrom: float | None = None
    bond_uncertainty_angstrom: float | None = None
    angle_deg: float | None = None
    angle_uncertainty_deg: float | None = None
    note: str | None = None


class KineticStationaryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    verified: bool
    status: str
    n_imag: int | None = None
    imag_freq_cm1: float | None = None
    e_elec_ha: float | None = None
    zpe_ha: float | None = None
    delta_e_kcal: float | None = None
    delta_h_kcal: float | None = None
    delta_g_kcal: float | None = None
    row_sha256: str | None = None
    reasons: list[str] = Field(default_factory=list)


def _apply_publication_rc() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11.0,
            "axes.labelsize": 10.0,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.8,
            "axes.linewidth": 1.0,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def render_geom_comparison(
    comparison_json_path: str | Path,
    out_png: str | Path,
    out_pdf: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render CoChem-GEOM's verified structural comparison JSON to PNG + PDF.

    Plots separated:
      - r_e (ORCA CCSD/cc-pVTZ)
      - r_e (PySCF CCSD/cc-pVDZ)
      - r_s (Kraitchman +/- sigma_Costain)
      - r_0 (Weighted fit +/- sigma_scaled)
      - r_e^SE (explicitly annotated as PENDING when unverified; never equated to r_0)
    """
    src_path = Path(comparison_json_path)
    if not src_path.is_file():
        raise FileNotFoundError(f"Comparison JSON not found: {src_path}")

    input_sha256 = sha256_file(src_path)
    payload = json.loads(src_path.read_text(encoding="utf-8"))

    schema = payload.get("schema_version")
    if schema != "cochem.geom.structural-comparison/1":
        raise ValueError(
            f"Unsupported comparison JSON schema {schema!r}; "
            "expected 'cochem.geom.structural-comparison/1'."
        )

    columns = payload.get("columns")
    if not isinstance(columns, dict):
        raise ValueError("Comparison JSON missing 'columns' mapping.")

    required_verified = (
        ("r_e_ccsd_cc_pvtz_orca", "r_e\nORCA CCSD\ncc-pVTZ", None, None),
        ("r_e_ccsd_cc_pvdz_pyscf", "r_e\nPySCF CCSD\ncc-pVDZ", None, None),
        (
            "r_s_kraitchman",
            "r_s\nKraitchman\n(±σ_Costain)",
            "bond_costain_uncertainty_angstrom",
            "angle_costain_uncertainty_deg",
        ),
        (
            "r_0_weighted_fit",
            "r_0\nWeighted Fit\n(±σ_scaled)",
            "bond_std_err_scaled_angstrom",
            "angle_std_err_scaled_deg",
        ),
    )

    summaries: list[GeomColumnSummary] = []
    for key, label, bond_unc_key, angle_unc_key in required_verified:
        if key not in columns or not isinstance(columns[key], dict):
            raise ValueError(f"Missing required verified column {key!r} in {src_path}")
        col = columns[key]
        status = str(col.get("status", "UNKNOWN")).upper()
        if status != "VERIFIED":
            raise ValueError(
                f"Column {key!r} has status {status!r}; render_geom_comparison "
                "refuses to plot unverified structural columns."
            )
        bond_val = _parse_finite_float(col.get("bond_angstrom"), f"{key}.bond_angstrom")
        angle_val = _parse_finite_float(col.get("angle_deg"), f"{key}.angle_deg")
        bond_unc = (
            _parse_finite_float(col.get(bond_unc_key), f"{key}.{bond_unc_key}")
            if bond_unc_key
            else None
        )
        angle_unc = (
            _parse_finite_float(col.get(angle_unc_key), f"{key}.{angle_unc_key}")
            if angle_unc_key
            else None
        )
        summaries.append(
            GeomColumnSummary(
                key=key,
                label=label,
                status=status,
                bond_angstrom=bond_val,
                bond_uncertainty_angstrom=bond_unc,
                angle_deg=angle_val,
                angle_uncertainty_deg=angle_unc,
            )
        )

    # r_e^SE column: must remain explicitly PENDING if unverified or null
    re_se_col = columns.get("r_e_se", {})
    re_se_status = str(re_se_col.get("status", "PENDING")).upper() if isinstance(re_se_col, dict) else "PENDING"
    re_se_bond = _try_finite_float(re_se_col.get("bond_angstrom")) if isinstance(re_se_col, dict) else None
    re_se_angle = _try_finite_float(re_se_col.get("angle_deg")) if isinstance(re_se_col, dict) else None
    re_se_verified = re_se_status == "VERIFIED" and re_se_bond is not None and re_se_angle is not None

    summaries.append(
        GeomColumnSummary(
            key="r_e_se",
            label="r_e^SE\nSemi-Exp.\n(requires ΔB_vib)",
            status="VERIFIED" if re_se_verified else "PENDING",
            bond_angstrom=re_se_bond if re_se_verified else None,
            angle_deg=re_se_angle if re_se_verified else None,
            note=(
                re_se_col.get("reason")
                if isinstance(re_se_col, dict)
                else "Requires isotope-specific anharmonic vibrational corrections."
            ),
        )
    )

    molecule = str(payload.get("molecule", "Molecule"))
    symmetry = str(payload.get("symmetry", ""))
    bond_label = str(columns["r_0_weighted_fit"].get("bond_label", "r(O-H)"))
    angle_label = str(columns["r_0_weighted_fit"].get("angle_label", "angle(H-O-H)"))
    exp_prov = payload.get("experimental_provenance", {})
    source_doi = str(exp_prov.get("source_doi", "N/A"))

    orca_sha = str(columns["r_e_ccsd_cc_pvtz_orca"].get("output_sha256", "N/A"))
    pyscf_sha = str(columns["r_e_ccsd_cc_pvdz_pyscf"].get("output_sha256", "N/A"))

    _apply_publication_rc()
    fig, (ax_r, ax_a) = plt.subplots(1, 2, figsize=(12.2, 5.4), dpi=300)

    palette = ["#0072B2", "#56B4E9", "#D55E00", "#009E73", "#6C757D"]
    markers = ["o", "s", "D", "^", "P"]
    x_positions = np.arange(len(summaries), dtype=float)
    x_labels = [s.label for s in summaries]

    # Compute honest y-ranges from verified data + uncertainties
    r_lows, r_highs = [], []
    a_lows, a_highs = [], []
    for s in summaries:
        if s.bond_angstrom is not None:
            du = s.bond_uncertainty_angstrom or 0.0
            r_lows.append(s.bond_angstrom - du)
            r_highs.append(s.bond_angstrom + du)
        if s.angle_deg is not None:
            du = s.angle_uncertainty_deg or 0.0
            a_lows.append(s.angle_deg - du)
            a_highs.append(s.angle_deg + du)

    r_span = max(max(r_highs) - min(r_lows), 0.02)
    a_span = max(max(a_highs) - min(a_lows), 2.0)
    r_ylim = (min(r_lows) - 0.28 * r_span, max(r_highs) + 0.36 * r_span)
    a_ylim = (min(a_lows) - 0.28 * a_span, max(a_highs) + 0.36 * a_span)

    # Subtle reference line at ORCA CCSD/cc-pVTZ equilibrium value
    orca_r = summaries[0].bond_angstrom
    orca_a = summaries[0].angle_deg
    assert orca_r is not None and orca_a is not None
    ax_r.axhline(orca_r, color="#0072B2", linestyle=":", linewidth=1.0, alpha=0.55, zorder=1)
    ax_a.axhline(orca_a, color="#0072B2", linestyle=":", linewidth=1.0, alpha=0.55, zorder=1)

    for idx, s in enumerate(summaries):
        color = palette[idx]
        marker = markers[idx]
        if s.status == "VERIFIED" and s.bond_angstrom is not None and s.angle_deg is not None:
            # Left panel: bond length
            if s.bond_uncertainty_angstrom is not None:
                ax_r.errorbar(
                    idx,
                    s.bond_angstrom,
                    yerr=s.bond_uncertainty_angstrom,
                    fmt=marker,
                    color=color,
                    markersize=7.5,
                    capsize=5,
                    elinewidth=1.6,
                    capthick=1.4,
                    zorder=4,
                )
                r_txt = f"{s.bond_angstrom:.4f}\n±{s.bond_uncertainty_angstrom:.4f} Å"
                r_text_y = s.bond_angstrom + s.bond_uncertainty_angstrom + 0.055 * r_span
            else:
                ax_r.scatter([idx], [s.bond_angstrom], color=color, marker=marker, s=68, zorder=4)
                r_txt = f"{s.bond_angstrom:.4f} Å"
                r_text_y = s.bond_angstrom + 0.065 * r_span
            ax_r.text(
                idx,
                r_text_y,
                r_txt,
                ha="center",
                va="bottom",
                fontsize=8.0,
                color="#1F2933",
                fontweight="normal",
            )

            # Right panel: bond angle
            if s.angle_uncertainty_deg is not None:
                ax_a.errorbar(
                    idx,
                    s.angle_deg,
                    yerr=s.angle_uncertainty_deg,
                    fmt=marker,
                    color=color,
                    markersize=7.5,
                    capsize=5,
                    elinewidth=1.6,
                    capthick=1.4,
                    zorder=4,
                )
                a_txt = f"{s.angle_deg:.2f}°\n±{s.angle_uncertainty_deg:.2f}°"
                a_text_y = s.angle_deg + s.angle_uncertainty_deg + 0.055 * a_span
            else:
                ax_a.scatter([idx], [s.angle_deg], color=color, marker=marker, s=68, zorder=4)
                a_txt = f"{s.angle_deg:.2f}°"
                a_text_y = s.angle_deg + 0.065 * a_span
            ax_a.text(
                idx,
                a_text_y,
                a_txt,
                ha="center",
                va="bottom",
                fontsize=8.0,
                color="#1F2933",
                fontweight="normal",
            )
        else:
            # Explicit PENDING slot — zero fabricated numeric bar or point
            for ax, ylim in ((ax_r, r_ylim), (ax_a, a_ylim)):
                ax.axvspan(
                    idx - 0.36,
                    idx + 0.36,
                    facecolor="#F1F3F5",
                    edgecolor="#868E96",
                    linestyle="--",
                    linewidth=1.1,
                    hatch="///",
                    alpha=0.65,
                    zorder=2,
                )
                mid_y = 0.5 * (ylim[0] + ylim[1])
                ax.text(
                    idx,
                    mid_y,
                    "PENDING\n(requires ΔB_vib)",
                    ha="center",
                    va="center",
                    fontsize=8.2,
                    fontweight="bold",
                    color="#495057",
                    bbox={
                        "boxstyle": "round,pad=0.3",
                        "facecolor": "white",
                        "edgecolor": "#868E96",
                        "linewidth": 0.9,
                    },
                    zorder=5,
                )

    for ax, ylabel, panel_title, ylim in (
        (ax_r, f"Bond Length {bond_label} (Å)", f"(a) {molecule} Bond Length Comparison", r_ylim),
        (ax_a, f"Bond Angle {angle_label} (°)", f"(b) {molecule} Bond Angle Comparison", a_ylim),
    ):
        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels)
        ax.set_xlim(-0.55, len(summaries) - 0.45)
        ax.set_ylim(*ylim)
        ax.set_ylabel(ylabel)
        ax.set_title(panel_title, pad=10, fontweight="bold")
        ax.yaxis.grid(True, linestyle="-", alpha=0.25, color="#ADB5BD")
        ax.set_axisbelow(True)

    sym_part = f" ({symmetry})" if symmetry else ""
    fig.suptitle(
        f"CoChem-GEOM Verified Structural Comparison: {molecule}{sym_part} — "
        r"$r_e$ vs. $r_s$ vs. $r_0$ ($r_e^{\mathrm{SE}}$ = PENDING)",
        fontsize=12.0,
        fontweight="bold",
        y=0.97,
    )

    footer = (
        f"Provenance | Input JSON SHA-256: {input_sha256[:16]}... | "
        f"ORCA out: {orca_sha[:12]}... | PySCF log: {pyscf_sha[:12]}... | "
        f"Exp. B0 DOI: {source_doi} | r_e^SE status: {summaries[-1].status}"
    )
    fig.text(0.5, 0.018, footer, ha="center", va="bottom", fontsize=7.6, color="#495057")
    fig.tight_layout(rect=(0.0, 0.055, 1.0, 0.92))

    png_path = Path(out_png)
    pdf_path = Path(out_pdf)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300)
    fig.savefig(pdf_path)
    plt.close(fig)

    png_sha256 = sha256_file(png_path)
    pdf_sha256 = sha256_file(pdf_path)

    receipt: dict[str, Any] = {
        "schema_version": "cochem.scribe.geom-figure-receipt/1",
        "renderer": "render_geom_comparison",
        "molecule": molecule,
        "symmetry": symmetry,
        "source_comparison_json": str(src_path),
        "source_comparison_sha256": input_sha256,
        "upstream_provenance": {
            "orca_ccsd_output_sha256": orca_sha,
            "pyscf_ccsd_output_sha256": pyscf_sha,
            "experimental_source_doi": source_doi,
        },
        "r_e_se_status": summaries[-1].status,
        "columns": [s.model_dump(mode="json") for s in summaries],
        "outputs": {
            "png": {
                "path": str(png_path),
                "bytes": png_path.stat().st_size,
                "sha256": png_sha256,
            },
            "pdf": {
                "path": str(pdf_path),
                "bytes": pdf_path.stat().st_size,
                "sha256": pdf_sha256,
            },
        },
    }

    if manifest_path is not None:
        mpath = Path(manifest_path)
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    return receipt


def _resolve_energy_column(fieldnames: list[str], requested: str) -> str:
    if requested in fieldnames:
        return requested
    fallbacks = ("delta_g_qrrho_kcal", "delta_g_rrho_kcal", "delta_g_kcal", "delta_g")
    for col in fallbacks:
        if col in fieldnames:
            return col
    raise ValueError(
        f"Requested energy column {requested!r} not found in CSV headers {fieldnames!r}."
    )


def _resolve_optional_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    for col in candidates:
        if col in fieldnames:
            return col
    return None


def _parse_kinetic_stationary_csv(
    csv_path: Path,
    *,
    energy_column: str,
) -> tuple[list[KineticStationaryPoint], str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"Empty or headerless CSV: {csv_path}")
        fieldnames = [f.strip() for f in reader.fieldnames]
        rows = [{k.strip(): v for k, v in r.items() if k is not None} for r in reader]

    if "state" not in fieldnames:
        raise ValueError(f"stationary_table.csv missing required 'state' column: {fieldnames}")

    g_col = _resolve_energy_column(fieldnames, energy_column)
    e_col = _resolve_optional_column(fieldnames, ("e_dft_ha", "electronic_energy_ha", "e_elec_ha"))
    zpe_col = _resolve_optional_column(fieldnames, ("zpe_ha", "zpe_kcal"))
    de_col = _resolve_optional_column(fieldnames, ("delta_e_kcal", "delta_e"))
    dh_col = _resolve_optional_column(fieldnames, ("delta_h_kcal", "delta_h"))
    imag_freq_col = _resolve_optional_column(fieldnames, ("imag_freq_cm1", "imag_freq"))
    sha_col = _resolve_optional_column(fieldnames, ("sha256", "provenance_sha256"))

    if e_col is None:
        raise ValueError(
            "stationary_table.csv missing electronic energy column "
            "(expected one of 'e_dft_ha', 'electronic_energy_ha', 'e_elec_ha')."
        )
    if zpe_col is None:
        raise ValueError("stationary_table.csv missing ZPE column ('zpe_ha' or 'zpe_kcal').")
    if dh_col is None:
        raise ValueError("stationary_table.csv missing enthalpy column ('delta_h_kcal' or 'delta_h').")
    if "n_imag" not in fieldnames:
        raise ValueError("stationary_table.csv missing required 'n_imag' Hessian mode column.")
    if "status" not in fieldnames and "converged" not in fieldnames:
        raise ValueError("stationary_table.csv missing required 'status' or 'converged' column.")

    by_state: dict[str, dict[str, Any]] = {}
    for row in rows:
        st = str(row.get("state", "")).strip()
        if st:
            by_state[st] = row

    points: list[KineticStationaryPoint] = []
    for st in CANONICAL_KINETIC_STATES:
        row = by_state.get(st)
        if row is None:
            points.append(
                KineticStationaryPoint(
                    state=st,
                    verified=False,
                    status="PENDING",
                    reasons=[f"Missing stationary point row {st!r}"],
                )
            )
            continue

        reasons: list[str] = []
        converged = _is_row_converged(row)
        if not converged:
            raw_st = row.get("status", row.get("converged", "PENDING"))
            reasons.append(f"State {st!r} is not converged (status/converged={raw_st!r})")

        n_imag_val: int | None = None
        raw_n_imag = str(row.get("n_imag", "")).strip()
        try:
            n_imag_val = int(float(raw_n_imag))
        except (TypeError, ValueError):
            reasons.append(f"State {st!r} has invalid n_imag={raw_n_imag!r}")
        else:
            expected_n = EXPECTED_N_IMAG[st]
            if n_imag_val != expected_n:
                reasons.append(
                    f"State {st!r} has n_imag={n_imag_val} (expected {expected_n})"
                )

        e_val = _try_finite_float(row.get(e_col))
        if e_val is None:
            reasons.append(f"State {st!r} has non-finite/missing {e_col}")

        zpe_val = _try_finite_float(row.get(zpe_col))
        if zpe_val is None:
            reasons.append(f"State {st!r} has non-finite/missing {zpe_col}")

        dh_val = _try_finite_float(row.get(dh_col))
        if dh_val is None:
            reasons.append(f"State {st!r} has non-finite/missing {dh_col}")

        dg_val = _try_finite_float(row.get(g_col))
        if dg_val is None:
            reasons.append(f"State {st!r} has non-finite/missing {g_col}")

        de_val = _try_finite_float(row.get(de_col)) if de_col else None
        imag_freq = _try_finite_float(row.get(imag_freq_col)) if imag_freq_col else None
        row_sha = str(row.get(sha_col, "")).strip() if sha_col else None
        if row_sha == "":
            row_sha = None

        verified = len(reasons) == 0
        points.append(
            KineticStationaryPoint(
                state=st,
                verified=verified,
                status="VERIFIED" if verified else "PENDING",
                n_imag=n_imag_val,
                imag_freq_cm1=imag_freq,
                e_elec_ha=e_val if verified else None,
                zpe_ha=zpe_val if verified else None,
                delta_e_kcal=de_val if verified else None,
                delta_h_kcal=dh_val if verified else None,
                delta_g_kcal=dg_val if verified else None,
                row_sha256=row_sha,
                reasons=reasons,
            )
        )

    return points, g_col


def render_kinetic_rxn_profile(
    stationary_csv_path: str | Path,
    out_png: str | Path,
    out_pdf: str | Path,
    *,
    energy_column: str = "delta_g_qrrho_kcal",
    strict: bool = True,
    title: str | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render a verified 5-stationary-point reaction-coordinate energy profile.

    Strictly validates R, TS1, Int_tet, TS2, P convergence, n_imag Hessian
    character (0 for minima, 1 for transition states), and finite energies.
    In strict mode (default), raises ValueError if any state is missing,
    unconverged, PENDING, or non-finite. In non-strict mode, unverified rows
    are explicitly rendered as shaded PENDING slots with zero numeric bars.
    """
    csv_path = Path(stationary_csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Stationary table CSV not found: {csv_path}")

    input_sha256 = sha256_file(csv_path)
    points, resolved_g_col = _parse_kinetic_stationary_csv(csv_path, energy_column=energy_column)

    unverified = [p for p in points if not p.verified]
    if strict and unverified:
        detail = "; ".join(f"{p.state}: {', '.join(p.reasons)}" for p in unverified)
        raise ValueError(
            "Refusing to render unverified/PENDING kinetic stationary table in strict mode: "
            + detail
        )

    verified_points = [p for p in points if p.verified and p.delta_g_kcal is not None]
    if not verified_points:
        raise ValueError(
            "No verified stationary points available in stationary_table.csv; "
            "cannot render an empty or unverified reaction profile."
        )

    _apply_publication_rc()
    fig, ax = plt.subplots(figsize=(10.6, 5.2), dpi=300)

    vals = [p.delta_g_kcal for p in verified_points if p.delta_g_kcal is not None]
    y_min = min(vals)
    y_max = max(vals)
    y_span = max(y_max - y_min, 5.0)
    ylim = (y_min - 0.25 * y_span, y_max + 0.32 * y_span)

    plateau_half = 0.28
    x_centers = np.arange(len(points), dtype=float)

    # Zero reference line
    ax.axhline(0.0, color="#ADB5BD", linestyle=":", linewidth=1.0, zorder=1)

    # Smooth dashed connectors between adjacent verified plateaus
    for idx in range(len(points) - 1):
        p_left = points[idx]
        p_right = points[idx + 1]
        if p_left.verified and p_right.verified and p_left.delta_g_kcal is not None and p_right.delta_g_kcal is not None:
            x0 = x_centers[idx] + plateau_half
            x1 = x_centers[idx + 1] - plateau_half
            t = np.linspace(0.0, 1.0, 40)
            xs = x0 + (x1 - x0) * t
            ys = p_left.delta_g_kcal + (p_right.delta_g_kcal - p_left.delta_g_kcal) * (
                0.5 * (1.0 - np.cos(np.pi * t))
            )
            ax.plot(xs, ys, linestyle="--", linewidth=1.4, color="#6C757D", zorder=2)

    # Draw verified plateaus or explicit PENDING slots
    for idx, pt in enumerate(points):
        xc = x_centers[idx]
        if pt.verified and pt.delta_g_kcal is not None:
            is_ts = pt.state in {"TS1", "TS2"}
            color = "#D55E00" if is_ts else "#0072B2"
            ax.hlines(
                pt.delta_g_kcal,
                xc - plateau_half,
                xc + plateau_half,
                colors=color,
                linewidth=4.0,
                zorder=4,
            )
            label_lines = [f"{pt.delta_g_kcal:+.2f} kcal/mol"]
            if pt.delta_h_kcal is not None:
                label_lines.append(f"(ΔH {pt.delta_h_kcal:+.2f})")
            if is_ts and pt.imag_freq_cm1 is not None and pt.imag_freq_cm1 != 0.0:
                label_lines.append(f"ν‡ = {pt.imag_freq_cm1:.1f} cm⁻¹")

            ax.text(
                xc,
                pt.delta_g_kcal + 0.045 * y_span,
                "\n".join(label_lines),
                ha="center",
                va="bottom",
                fontsize=8.2,
                fontweight="bold" if is_ts else "normal",
                color=color if is_ts else "#1F2933",
                zorder=5,
            )
        else:
            ax.axvspan(
                xc - 0.34,
                xc + 0.34,
                facecolor="#F1F3F5",
                edgecolor="#868E96",
                linestyle="--",
                linewidth=1.1,
                hatch="///",
                alpha=0.65,
                zorder=2,
            )
            ax.text(
                xc,
                0.5 * (ylim[0] + ylim[1]),
                f"{pt.state}\nPENDING",
                ha="center",
                va="center",
                fontsize=8.4,
                fontweight="bold",
                color="#495057",
                bbox={
                    "boxstyle": "round,pad=0.3",
                    "facecolor": "white",
                    "edgecolor": "#868E96",
                    "linewidth": 0.9,
                },
                zorder=5,
            )

    display_labels = {
        "R": "R\n(Reactant)\nN_imag = 0",
        "TS1": "TS1\n(Attack)\nN_imag = 1",
        "Int_tet": "Int_tet\n(Tetrahedral)\nN_imag = 0",
        "TS2": "TS2\n(Collapse)\nN_imag = 1",
        "P": "P\n(Product)\nN_imag = 0",
    }
    ax.set_xticks(x_centers)
    ax.set_xticklabels([display_labels[p.state] for p in points])
    ax.set_xlim(-0.6, len(points) - 0.4)
    ax.set_ylim(*ylim)
    ax.set_xlabel("Reaction Coordinate (Verified Stationary Points)", labelpad=8)

    y_label = (
        r"Relative Free Energy $\Delta G_{\mathrm{qRRHO}}$ (kcal/mol)"
        if "qrrho" in resolved_g_col.lower()
        else r"Relative Free Energy $\Delta G(T)$ (kcal/mol)"
    )
    ax.set_ylabel(y_label)
    ax.yaxis.grid(True, linestyle="-", alpha=0.25, color="#ADB5BD")
    ax.set_axisbelow(True)

    fig_title = title or "CoChem-KINETIC Verified 5-Point Reaction-Coordinate Free Energy Profile"
    ax.set_title(fig_title, pad=12, fontweight="bold")

    verified_count = len(verified_points)
    pending_states = [p.state for p in unverified]
    status_tag = (
        f"5/5 VERIFIED" if not pending_states else f"{verified_count}/5 VERIFIED | PENDING: {','.join(pending_states)}"
    )
    footer = (
        f"Provenance | stationary_table.csv SHA-256: {input_sha256[:16]}... | "
        f"Column: {resolved_g_col} | Status: {status_tag}"
    )
    fig.text(0.5, 0.018, footer, ha="center", va="bottom", fontsize=7.8, color="#495057")
    fig.tight_layout(rect=(0.0, 0.055, 1.0, 0.98))

    png_path = Path(out_png)
    pdf_path = Path(out_pdf)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300)
    fig.savefig(pdf_path)
    plt.close(fig)

    receipt: dict[str, Any] = {
        "schema_version": "cochem.scribe.kinetic-figure-receipt/1",
        "renderer": "render_kinetic_rxn_profile",
        "source_csv": str(csv_path),
        "source_csv_sha256": input_sha256,
        "energy_column": resolved_g_col,
        "strict_mode": strict,
        "verified_states": [p.state for p in verified_points],
        "pending_states": pending_states,
        "stationary_points": [p.model_dump(mode="json") for p in points],
        "outputs": {
            "png": {
                "path": str(png_path),
                "bytes": png_path.stat().st_size,
                "sha256": sha256_file(png_path),
            },
            "pdf": {
                "path": str(pdf_path),
                "bytes": pdf_path.stat().st_size,
                "sha256": sha256_file(pdf_path),
            },
        },
    }

    if manifest_path is not None:
        mpath = Path(manifest_path)
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    return receipt
