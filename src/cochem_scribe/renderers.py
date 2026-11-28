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

HARTREE_TO_KCAL = 627.5094740631

CANONICAL_KINETIC_STATES_5PT: tuple[str, ...] = ("R", "TS1", "Int_tet", "TS2", "P")
CANONICAL_KINETIC_STATES_3PT: tuple[str, ...] = ("R", "TS", "P")
CANONICAL_KINETIC_STATES: tuple[str, ...] = CANONICAL_KINETIC_STATES_5PT

EXPECTED_N_IMAG: dict[str, int] = {
    "R": 0,
    "TS": 1,
    "TS1": 1,
    "Int_tet": 0,
    "TS2": 1,
    "P": 0,
}

CCSD_GEOM_KEYS: tuple[str, ...] = (
    "r_e_ccsd_cc_pvtz_orca",
    "r_e_ccsd_cc_pvdz_pyscf",
)

OKABE_ITO_PALETTE: tuple[str, ...] = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#000000",
    "#6C757D",
)

SERIES_MARKERS: tuple[str, ...] = ("o", "s", "D", "^", "v", "P", "X", "*")


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
    if raw is None or isinstance(raw, bool):
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


def _is_explicitly_unconverged(row: dict[str, Any], method_prefix: str | None = None) -> bool:
    """Return True if a convergence row explicitly signals non-convergence or PENDING."""
    if method_prefix:
        specific_key = f"{method_prefix}_converged"
        if specific_key in row and row[specific_key] is not None:
            val = str(row[specific_key]).strip().lower()
            if val in {"false", "0", "no", "pending", "failed", "unconverged"}:
                return True
    for flag_key in ("converged", "terminated_normally"):
        if flag_key in row and row[flag_key] is not None and str(row[flag_key]).strip() != "":
            val = str(row[flag_key]).strip().lower()
            if val in {"false", "0", "no", "pending", "failed", "unconverged"}:
                return True
    if "status" in row and row["status"] is not None and str(row["status"]).strip() != "":
        status = str(row["status"]).strip().upper()
        if status in {"PENDING", "FAILED", "ERROR", "UNCONVERGED", "TBD", "OMITTED"}:
            return True
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
    active_bond: str | None = None
    e_elec_ha: float | None = None
    zpe_ha: float | None = None
    delta_e_kcal: float | None = None
    delta_h_kcal: float | None = None
    delta_g_kcal: float | None = None
    row_sha256: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ConvergencePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series: str
    engine: str | None = None
    method: str
    basis: str
    nao: int | None = None
    status: str
    energy_eh: float | None = None
    reason: str | None = None


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


def _format_extra_geom_label(key: str, col: dict[str, Any]) -> str:
    if col.get("label"):
        return str(col["label"])
    method = str(col.get("method", "")).strip()
    basis = str(col.get("basis", "")).strip()
    backend = str(col.get("backend", col.get("engine", ""))).strip()
    prefix = "r_e" if key.startswith("r_e") else key.split("_")[0]
    if method and basis:
        if backend:
            engine_tag = backend.split("_")[0].upper()
            return f"{prefix}\n{engine_tag} {method}\n{basis}"
        return f"{prefix}\n{method}\n{basis}"
    parts = [p for p in key.split("_") if p]
    if len(parts) >= 3:
        return "\n".join([f"{parts[0]}_{parts[1]}", " ".join(parts[2:4]), " ".join(parts[4:])]).strip()
    return key.replace("_", "\n")


def _extract_optional_uncertainty(
    col: dict[str, Any],
    preferred_key: str | None,
    fallback_keys: tuple[str, ...],
) -> float | None:
    candidates = ([preferred_key] if preferred_key else []) + list(fallback_keys)
    for k in candidates:
        if k in col and col[k] is not None:
            val = _try_finite_float(col[k])
            if val is not None:
                return val
    return None


def render_geom_comparison(
    comparison_json_path: str | Path,
    out_png: str | Path,
    out_pdf: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render CoChem-GEOM's verified structural comparison JSON to PNG + PDF.

    Plots verified structural columns including equilibrium ab initio columns
    (`r_e_ccsd_*` or non-CCSD DFT/revDSD columns), Kraitchman substitution
    (`r_s_kraitchman`), weighted ground-state fit (`r_0_weighted_fit`), and
    semi-experimental (`r_e_se`).

    When CCSD columns (`r_e_ccsd_*`) are PENDING, NaN, or omitted (e.g.,
    non-CCSD CHEM 411 or local revDSD CHEM 490 runs), verified non-CCSD
    columns render cleanly while annotating `CCSD: PENDING` honestly. Fails
    closed (`ValueError`) if zero verified data columns exist.
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

    canonical_specs: dict[str, tuple[str, str | None, str | None]] = {
        "r_e_ccsd_cc_pvtz_orca": ("r_e\nORCA CCSD\ncc-pVTZ", None, None),
        "r_e_ccsd_cc_pvdz_pyscf": ("r_e\nPySCF CCSD\ncc-pVDZ", None, None),
        "r_s_kraitchman": (
            "r_s\nKraitchman\n(±σ_Costain)",
            "bond_costain_uncertainty_angstrom",
            "angle_costain_uncertainty_deg",
        ),
        "r_0_weighted_fit": (
            "r_0\nWeighted Fit\n(±σ_scaled)",
            "bond_std_err_scaled_angstrom",
            "angle_std_err_scaled_deg",
        ),
    }

    extra_keys = [
        k
        for k in columns
        if k not in canonical_specs and k != "r_e_se" and isinstance(columns[k], dict)
    ]

    ordered_keys: list[str] = []
    for k in CCSD_GEOM_KEYS:
        if k in columns and isinstance(columns[k], dict):
            ordered_keys.append(k)
    ordered_keys.extend(extra_keys)
    for k in ("r_s_kraitchman", "r_0_weighted_fit"):
        if k in columns and isinstance(columns[k], dict):
            ordered_keys.append(k)

    summaries: list[GeomColumnSummary] = []
    for key in ordered_keys:
        col = columns[key]
        is_ccsd = key in CCSD_GEOM_KEYS or "ccsd" in key.lower()
        if key in canonical_specs:
            default_label, bond_unc_key, angle_unc_key = canonical_specs[key]
            label = str(col.get("label") or default_label)
        else:
            label = _format_extra_geom_label(key, col)
            bond_unc_key = None
            angle_unc_key = None

        status = str(col.get("status", "PENDING")).strip().upper()
        bond_val = _try_finite_float(col.get("bond_angstrom"))
        angle_val = _try_finite_float(col.get("angle_deg"))

        if status == "VERIFIED":
            if bond_val is None or angle_val is None:
                if is_ccsd:
                    summaries.append(
                        GeomColumnSummary(
                            key=key,
                            label=label,
                            status="PENDING",
                            note=str(col.get("reason") or "CCSD: PENDING (non-finite/missing values)"),
                        )
                    )
                    continue
                raise ValueError(
                    f"Column {key!r} is marked VERIFIED but has missing/non-finite "
                    f"bond_angstrom={col.get('bond_angstrom')!r} or angle_deg={col.get('angle_deg')!r}."
                )
            bond_unc = _extract_optional_uncertainty(
                col,
                bond_unc_key,
                (
                    "bond_uncertainty_angstrom",
                    "bond_costain_uncertainty_angstrom",
                    "bond_std_err_scaled_angstrom",
                ),
            )
            angle_unc = _extract_optional_uncertainty(
                col,
                angle_unc_key,
                (
                    "angle_uncertainty_deg",
                    "angle_costain_uncertainty_deg",
                    "angle_std_err_scaled_deg",
                ),
            )
            summaries.append(
                GeomColumnSummary(
                    key=key,
                    label=label,
                    status="VERIFIED",
                    bond_angstrom=bond_val,
                    bond_uncertainty_angstrom=bond_unc,
                    angle_deg=angle_val,
                    angle_uncertainty_deg=angle_unc,
                )
            )
        elif status in {"PENDING", "OMITTED", "TBD", "SKIPPED"} or is_ccsd:
            summaries.append(
                GeomColumnSummary(
                    key=key,
                    label=label,
                    status="PENDING",
                    note=str(col.get("reason") or ("CCSD: PENDING" if is_ccsd else "PENDING")),
                )
            )
        else:
            raise ValueError(
                f"Column {key!r} has unverified status {status!r}; "
                "render_geom_comparison refuses to plot unverified structural columns."
            )

    # r_e^SE column: must remain explicitly PENDING if unverified or null
    re_se_col = columns.get("r_e_se", {})
    re_se_status = (
        str(re_se_col.get("status", "PENDING")).strip().upper()
        if isinstance(re_se_col, dict)
        else "PENDING"
    )
    re_se_bond = (
        _try_finite_float(re_se_col.get("bond_angstrom")) if isinstance(re_se_col, dict) else None
    )
    re_se_angle = (
        _try_finite_float(re_se_col.get("angle_deg")) if isinstance(re_se_col, dict) else None
    )
    re_se_verified = re_se_status == "VERIFIED" and re_se_bond is not None and re_se_angle is not None

    summaries.append(
        GeomColumnSummary(
            key="r_e_se",
            label="r_e^SE\nSemi-Exp.\n(requires ΔB_vib)",
            status="VERIFIED" if re_se_verified else "PENDING",
            bond_angstrom=re_se_bond if re_se_verified else None,
            bond_uncertainty_angstrom=(
                _extract_optional_uncertainty(
                    re_se_col,
                    "bond_uncertainty_angstrom",
                    ("bond_std_err_scaled_angstrom",),
                )
                if re_se_verified and isinstance(re_se_col, dict)
                else None
            ),
            angle_deg=re_se_angle if re_se_verified else None,
            angle_uncertainty_deg=(
                _extract_optional_uncertainty(
                    re_se_col,
                    "angle_uncertainty_deg",
                    ("angle_std_err_scaled_deg",),
                )
                if re_se_verified and isinstance(re_se_col, dict)
                else None
            ),
            note=(
                str(re_se_col.get("reason"))
                if isinstance(re_se_col, dict) and re_se_col.get("reason")
                else "Requires isotope-specific anharmonic vibrational corrections."
            ),
        )
    )

    verified_summaries = [
        s
        for s in summaries
        if s.status == "VERIFIED" and s.bond_angstrom is not None and s.angle_deg is not None
    ]
    if not verified_summaries:
        raise ValueError(
            "No verified structural columns available in comparison JSON; "
            "refusing to render an empty or all-PENDING structural comparison figure."
        )

    molecule = str(payload.get("molecule", "Molecule"))
    symmetry = str(payload.get("symmetry", ""))

    bond_label = str(payload.get("bond_label", "")).strip()
    angle_label = str(payload.get("angle_label", "")).strip()
    r0_col = columns.get("r_0_weighted_fit") if isinstance(columns.get("r_0_weighted_fit"), dict) else {}
    if not bond_label:
        bond_label = str(r0_col.get("bond_label", "")).strip()
    if not angle_label:
        angle_label = str(r0_col.get("angle_label", "")).strip()
    if not bond_label or not angle_label:
        for col_obj in columns.values():
            if isinstance(col_obj, dict):
                if not bond_label and col_obj.get("bond_label"):
                    bond_label = str(col_obj["bond_label"]).strip()
                if not angle_label and col_obj.get("angle_label"):
                    angle_label = str(col_obj["angle_label"]).strip()
    bond_label = bond_label or "r(O-H)"
    angle_label = angle_label or "angle(H-O-H)"

    exp_prov = payload.get("experimental_provenance", {})
    source_doi = str(exp_prov.get("source_doi", "N/A")) if isinstance(exp_prov, dict) else "N/A"

    orca_col = columns.get("r_e_ccsd_cc_pvtz_orca")
    pyscf_col = columns.get("r_e_ccsd_cc_pvdz_pyscf")
    orca_sha = (
        str(orca_col.get("output_sha256", "PENDING"))
        if isinstance(orca_col, dict) and str(orca_col.get("status", "")).upper() == "VERIFIED"
        else "PENDING"
    )
    pyscf_sha = (
        str(pyscf_col.get("output_sha256", "PENDING"))
        if isinstance(pyscf_col, dict) and str(pyscf_col.get("status", "")).upper() == "VERIFIED"
        else "PENDING"
    )

    by_key = {s.key: s for s in summaries}
    ccsd_verified_count = sum(
        1 for k in CCSD_GEOM_KEYS if k in by_key and by_key[k].status == "VERIFIED"
    )
    if ccsd_verified_count == len(CCSD_GEOM_KEYS):
        ccsd_status = "VERIFIED"
    elif ccsd_verified_count > 0:
        ccsd_status = "PARTIAL"
    else:
        ccsd_status = "PENDING"
    ccsd_omitted = not any(k in by_key for k in CCSD_GEOM_KEYS)

    _apply_publication_rc()
    fig_width = max(12.2, 2.2 * len(summaries) + 1.2)
    fig, (ax_r, ax_a) = plt.subplots(1, 2, figsize=(fig_width, 5.4), dpi=300)

    palette = ["#0072B2", "#56B4E9", "#D55E00", "#009E73", "#6C757D", "#CC79A7", "#E69F00"]
    markers = ["o", "s", "D", "^", "P", "v", "X"]
    x_positions = np.arange(len(summaries), dtype=float)
    x_labels = [s.label for s in summaries]

    # Compute honest y-ranges from verified data + uncertainties
    r_lows, r_highs = [], []
    a_lows, a_highs = [], []
    for s in verified_summaries:
        assert s.bond_angstrom is not None and s.angle_deg is not None
        r_du = s.bond_uncertainty_angstrom or 0.0
        a_du = s.angle_uncertainty_deg or 0.0
        r_lows.append(s.bond_angstrom - r_du)
        r_highs.append(s.bond_angstrom + r_du)
        a_lows.append(s.angle_deg - a_du)
        a_highs.append(s.angle_deg + a_du)

    r_span = max(max(r_highs) - min(r_lows), 0.02)
    a_span = max(max(a_highs) - min(a_lows), 2.0)
    r_ylim = (min(r_lows) - 0.28 * r_span, max(r_highs) + 0.36 * r_span)
    a_ylim = (min(a_lows) - 0.28 * a_span, max(a_highs) + 0.36 * a_span)

    # Subtle reference line at first verified equilibrium (r_e) column, else first verified column
    ref_summary = next(
        (s for s in verified_summaries if s.key.startswith("r_e")),
        verified_summaries[0],
    )
    assert ref_summary.bond_angstrom is not None and ref_summary.angle_deg is not None
    ax_r.axhline(
        ref_summary.bond_angstrom, color="#0072B2", linestyle=":", linewidth=1.0, alpha=0.55, zorder=1
    )
    ax_a.axhline(
        ref_summary.angle_deg, color="#0072B2", linestyle=":", linewidth=1.0, alpha=0.55, zorder=1
    )

    for idx, s in enumerate(summaries):
        color = palette[idx % len(palette)]
        marker = markers[idx % len(markers)]
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
            if s.key == "r_e_se":
                pending_label = "PENDING\n(requires ΔB_vib)"
            elif s.key in CCSD_GEOM_KEYS or "ccsd" in s.key.lower():
                pending_label = "CCSD:\nPENDING"
            else:
                pending_label = "PENDING"
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
                    pending_label,
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
        if ccsd_omitted:
            ax.text(
                0.98,
                0.96,
                "CCSD: PENDING",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=8.0,
                fontweight="bold",
                color="#495057",
                bbox={
                    "boxstyle": "round,pad=0.28",
                    "facecolor": "#F8F9FA",
                    "edgecolor": "#868E96",
                    "linestyle": "--",
                    "linewidth": 0.9,
                },
                zorder=6,
            )

    sym_part = f" ({symmetry})" if symmetry else ""
    ccsd_title_note = "" if ccsd_status == "VERIFIED" else f" | CCSD: {ccsd_status}"
    fig.suptitle(
        f"CoChem-GEOM Verified Structural Comparison: {molecule}{sym_part} — "
        rf"$r_e$ vs. $r_s$ vs. $r_0$ ($r_e^{{\mathrm{{SE}}}}$ = {summaries[-1].status}{ccsd_title_note})",
        fontsize=11.6,
        fontweight="bold",
        y=0.97,
    )

    orca_tag = f"{orca_sha[:12]}..." if orca_sha != "PENDING" else "PENDING"
    pyscf_tag = f"{pyscf_sha[:12]}..." if pyscf_sha != "PENDING" else "PENDING"
    footer = (
        f"Provenance | Input JSON SHA-256: {input_sha256[:16]}... | "
        f"CCSD: {ccsd_status} (ORCA: {orca_tag}, PySCF: {pyscf_tag}) | "
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
        "ccsd_status": ccsd_status,
        "r_e_se_status": summaries[-1].status,
        "verified_columns": [s.key for s in verified_summaries],
        "pending_columns": [s.key for s in summaries if s.status != "VERIFIED"],
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


def _resolve_bond_column(fieldnames: list[str]) -> str | None:
    exact = _resolve_optional_column(
        fieldnames,
        (
            "forming_breaking_co",
            "key_active_bond",
            "active_bond",
            "reaction_coordinate_bond",
            "forming_breaking_bond",
            "bond_coordinate",
            "rc_bond",
            "forming_breaking",
        ),
    )
    if exact is not None:
        return exact
    for col in fieldnames:
        lower = col.lower()
        if "forming_breaking" in lower or "active_bond" in lower or "rxn_bond" in lower or "rc_bond" in lower:
            return col
    return None


def _resolve_kinetic_pathway(
    by_state: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    pathway_mode: str,
) -> tuple[tuple[str, ...], str]:
    normalized = pathway_mode.strip().lower()
    if normalized in {"3pt", "elementary_3pt"}:
        return CANONICAL_KINETIC_STATES_3PT, "elementary_3pt"
    if normalized in {"5pt", "stepwise_5pt"}:
        return CANONICAL_KINETIC_STATES_5PT, "stepwise_5pt"
    if normalized != "auto":
        raise ValueError(
            f"Unsupported pathway_mode {pathway_mode!r}; expected 'auto', '3pt', or '5pt'."
        )

    has_3pt_ts = "TS" in by_state
    has_5pt_states = any(st in by_state for st in ("TS1", "Int_tet", "TS2"))
    if has_3pt_ts and has_5pt_states:
        raise ValueError(
            "Ambiguous stationary_table.csv mixes 3-point state 'TS' with 5-point states "
            "('TS1'/'Int_tet'/'TS2')."
        )
    if has_3pt_ts:
        return CANONICAL_KINETIC_STATES_3PT, "elementary_3pt"
    if has_5pt_states:
        return CANONICAL_KINETIC_STATES_5PT, "stepwise_5pt"

    for row in rows:
        raw_mode = str(row.get("pathway_mode", "")).strip().lower()
        if raw_mode in {"3pt", "elementary_3pt"}:
            return CANONICAL_KINETIC_STATES_3PT, "elementary_3pt"
        if raw_mode in {"5pt", "stepwise_5pt"}:
            return CANONICAL_KINETIC_STATES_5PT, "stepwise_5pt"

    return CANONICAL_KINETIC_STATES_5PT, "stepwise_5pt"


def _parse_kinetic_stationary_csv(
    csv_path: Path,
    *,
    energy_column: str,
    pathway_mode: str = "auto",
) -> tuple[list[KineticStationaryPoint], str, str, str | None]:
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
    bond_col = _resolve_bond_column(fieldnames)
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

    canonical_states, resolved_pathway = _resolve_kinetic_pathway(by_state, rows, pathway_mode)

    points: list[KineticStationaryPoint] = []
    for st in canonical_states:
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
        raw_bond = str(row.get(bond_col, "")).strip() if bond_col else ""
        active_bond = raw_bond if raw_bond and raw_bond not in {"-", "N/A", "None"} else None
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
                active_bond=active_bond,
                e_elec_ha=e_val if verified else None,
                zpe_ha=zpe_val if verified else None,
                delta_e_kcal=de_val if verified else None,
                delta_h_kcal=dh_val if verified else None,
                delta_g_kcal=dg_val if verified else None,
                row_sha256=row_sha,
                reasons=reasons,
            )
        )

    return points, g_col, resolved_pathway, bond_col


def render_kinetic_rxn_profile(
    stationary_csv_path: str | Path,
    out_png: str | Path,
    out_pdf: str | Path,
    *,
    energy_column: str = "delta_g_qrrho_kcal",
    strict: bool = True,
    title: str | None = None,
    manifest_path: str | Path | None = None,
    pathway_mode: str = "auto",
) -> dict[str, Any]:
    """Render a verified 3-point or 5-point reaction-coordinate energy profile.

    Supports both elementary 3-point pathways (`R, TS, P`) and stepwise 5-point
    pathways (`R, TS1, Int_tet, TS2, P`), strictly validating convergence,
    Hessian `n_imag` character (0 for minima, 1 for transition states), and
    finite energies. Accepts `forming_breaking_co`, generic reaction-coordinate
    bond columns, or no bond column without crashing.
    """
    csv_path = Path(stationary_csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Stationary table CSV not found: {csv_path}")

    input_sha256 = sha256_file(csv_path)
    points, resolved_g_col, resolved_pathway, resolved_bond_col = _parse_kinetic_stationary_csv(
        csv_path,
        energy_column=energy_column,
        pathway_mode=pathway_mode,
    )

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
    n_total = len(points)
    fig_width = 8.8 if n_total == 3 else 10.6
    fig, ax = plt.subplots(figsize=(fig_width, 5.2), dpi=300)

    vals = [p.delta_g_kcal for p in verified_points if p.delta_g_kcal is not None]
    y_min = min(vals)
    y_max = max(vals)
    y_span = max(y_max - y_min, 5.0)
    ylim = (y_min - 0.25 * y_span, y_max + 0.36 * y_span)

    plateau_half = 0.28
    x_centers = np.arange(n_total, dtype=float)

    # Zero reference line
    ax.axhline(0.0, color="#ADB5BD", linestyle=":", linewidth=1.0, zorder=1)

    # Smooth dashed connectors between adjacent verified plateaus
    for idx in range(n_total - 1):
        p_left = points[idx]
        p_right = points[idx + 1]
        if (
            p_left.verified
            and p_right.verified
            and p_left.delta_g_kcal is not None
            and p_right.delta_g_kcal is not None
        ):
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
            is_ts = pt.state in {"TS", "TS1", "TS2"}
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
            if is_ts and pt.active_bond:
                label_lines.append(pt.active_bond)

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
        "TS": "TS\n(Transition State)\nN_imag = 1",
        "TS1": "TS1\n(Attack)\nN_imag = 1",
        "Int_tet": "Int_tet\n(Tetrahedral)\nN_imag = 0",
        "TS2": "TS2\n(Collapse)\nN_imag = 1",
        "P": "P\n(Product)\nN_imag = 0",
    }
    ax.set_xticks(x_centers)
    ax.set_xticklabels([display_labels[p.state] for p in points])
    ax.set_xlim(-0.6, n_total - 0.4)
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

    fig_title = (
        title
        or f"CoChem-KINETIC Verified {n_total}-Point Reaction-Coordinate Free Energy Profile"
    )
    ax.set_title(fig_title, pad=12, fontweight="bold")

    verified_count = len(verified_points)
    pending_states = [p.state for p in unverified]
    status_tag = (
        f"{n_total}/{n_total} VERIFIED"
        if not pending_states
        else f"{verified_count}/{n_total} VERIFIED | PENDING: {','.join(pending_states)}"
    )
    footer = (
        f"Provenance | stationary_table.csv SHA-256: {input_sha256[:16]}... | "
        f"Pathway: {resolved_pathway} | Column: {resolved_g_col} | Status: {status_tag}"
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
        "pathway_mode": resolved_pathway,
        "n_stationary_points": n_total,
        "bond_column": resolved_bond_col,
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


_WIDE_METHOD_ENERGY_MAP: tuple[tuple[str, str, str], ...] = (
    ("rhf_energy_eh", "RHF", "rhf"),
    ("hf_energy_eh", "HF", "hf"),
    ("b3lyp_energy_eh", "B3LYP", "b3lyp"),
    ("pbe0_energy_eh", "PBE0", "pbe0"),
    ("wb97x_energy_eh", "wB97X-D", "wb97x"),
    ("mp2_total_energy_eh", "MP2", "mp2"),
    ("mp2_energy_eh", "MP2", "mp2"),
    ("revdsd_energy_eh", "revDSD-PBEP86-D4", "revdsd"),
    ("revdsd_pbep86_energy_eh", "revDSD-PBEP86-D4", "revdsd"),
    ("ccsd_energy_eh", "CCSD", "ccsd"),
    ("ccsd_t_energy_eh", "CCSD(T)", "ccsd_t"),
)

_SINGLE_ENERGY_KEYS: tuple[str, ...] = (
    "energy_eh",
    "total_energy_eh",
    "e_tot_eh",
    "e_elec_eh",
    "energy_ha",
    "e_dft_ha",
    "electronic_energy_hartree",
    "final_energy_eh",
    "energy",
)


def _extract_nao(row: dict[str, Any]) -> int | None:
    for key in ("nao", "n_basis", "n_bf", "basis_functions"):
        val = _try_finite_float(row.get(key))
        if val is not None and val > 0:
            return int(round(val))
    return None


def _extract_basis_label(row: dict[str, Any]) -> str | None:
    for key in ("basis", "basis_set", "level", "label"):
        raw = row.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _ingest_convergence_rows(
    rows: list[dict[str, Any]],
    *,
    default_engine: str | None = None,
) -> list[ConvergencePoint]:
    points: list[ConvergencePoint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        basis = _extract_basis_label(row)
        if not basis:
            continue
        engine_raw = row.get("engine", row.get("backend", default_engine))
        engine = str(engine_raw).strip() if engine_raw is not None and str(engine_raw).strip() else None
        nao = _extract_nao(row)

        # Check for single-energy (long) format first
        single_key = next((k for k in _SINGLE_ENERGY_KEYS if k in row), None)
        if single_key is not None:
            method_raw = row.get("method", row.get("theory", row.get("functional", "Energy")))
            method = str(method_raw).strip() if method_raw is not None and str(method_raw).strip() else "Energy"
            series = f"{engine} {method}".strip() if engine else method
            unconv = _is_explicitly_unconverged(row)
            val = _try_finite_float(row.get(single_key))
            if unconv or val is None:
                reason = (
                    "Row marked unconverged/PENDING"
                    if unconv
                    else f"Non-finite or PENDING {single_key}={row.get(single_key)!r}"
                )
                points.append(
                    ConvergencePoint(
                        series=series,
                        engine=engine,
                        method=method,
                        basis=basis,
                        nao=nao,
                        status="PENDING",
                        energy_eh=None,
                        reason=reason,
                    )
                )
            else:
                points.append(
                    ConvergencePoint(
                        series=series,
                        engine=engine,
                        method=method,
                        basis=basis,
                        nao=nao,
                        status="VERIFIED",
                        energy_eh=val,
                    )
                )
            continue

        # Wide format: inspect known *_energy_eh columns plus any other *_energy_eh / *_energy_ha columns
        matched_wide = False
        seen_cols: set[str] = set()
        for col_key, method_label, method_prefix in _WIDE_METHOD_ENERGY_MAP:
            if col_key in row:
                matched_wide = True
                seen_cols.add(col_key)
                series = f"{engine} {method_label}".strip() if engine else method_label
                unconv = _is_explicitly_unconverged(row, method_prefix=method_prefix)
                val = _try_finite_float(row.get(col_key))
                if unconv or val is None:
                    reason = (
                        f"{method_label} marked unconverged/PENDING"
                        if unconv
                        else f"Non-finite or PENDING {col_key}={row.get(col_key)!r}"
                    )
                    points.append(
                        ConvergencePoint(
                            series=series,
                            engine=engine,
                            method=method_label,
                            basis=basis,
                            nao=nao,
                            status="PENDING",
                            energy_eh=None,
                            reason=reason,
                        )
                    )
                else:
                    points.append(
                        ConvergencePoint(
                            series=series,
                            engine=engine,
                            method=method_label,
                            basis=basis,
                            nao=nao,
                            status="VERIFIED",
                            energy_eh=val,
                        )
                    )

        for col_key, raw_val in row.items():
            if col_key in seen_cols:
                continue
            lower = col_key.lower()
            if lower.startswith("delta_") or "_corr_" in lower:
                continue
            if lower.endswith(("_energy_eh", "_energy_ha", "_total_eh", "_total_ha")):
                matched_wide = True
                method_label = (
                    col_key.replace("_total_energy_eh", "")
                    .replace("_energy_eh", "")
                    .replace("_energy_ha", "")
                    .replace("_total_eh", "")
                    .replace("_total_ha", "")
                    .upper()
                )
                series = f"{engine} {method_label}".strip() if engine else method_label
                unconv = _is_explicitly_unconverged(row, method_prefix=method_label.lower())
                val = _try_finite_float(raw_val)
                if unconv or val is None:
                    points.append(
                        ConvergencePoint(
                            series=series,
                            engine=engine,
                            method=method_label,
                            basis=basis,
                            nao=nao,
                            status="PENDING",
                            energy_eh=None,
                            reason=f"Non-finite or PENDING {col_key}={raw_val!r}",
                        )
                    )
                else:
                    points.append(
                        ConvergencePoint(
                            series=series,
                            engine=engine,
                            method=method_label,
                            basis=basis,
                            nao=nao,
                            status="VERIFIED",
                            energy_eh=val,
                        )
                    )

        if not matched_wide:
            # Explicit PENDING stub row without energy columns (e.g. {"basis": "cc-pVTZ", "method": "CCSD", "status": "PENDING"})
            if _is_explicitly_unconverged(row):
                method_label = str(row.get("method", "Method")).strip() or "Method"
                series = f"{engine} {method_label}".strip() if engine else method_label
                points.append(
                    ConvergencePoint(
                        series=series,
                        engine=engine,
                        method=method_label,
                        basis=basis,
                        nao=nao,
                        status="PENDING",
                        energy_eh=None,
                        reason=str(row.get("reason") or "Marked PENDING without energy value"),
                    )
                )

    return points


def _parse_convergence_input(
    src_path: Path,
) -> tuple[str, list[ConvergencePoint], dict[str, Any]]:
    suffix = src_path.suffix.lower()
    extra_meta: dict[str, Any] = {}

    if suffix == ".csv":
        with src_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise ValueError(f"Empty or headerless convergence CSV: {src_path}")
            rows = [{k.strip(): v for k, v in r.items() if k is not None} for r in reader]
        molecule = src_path.stem
        for r in rows:
            if r.get("molecule") and str(r["molecule"]).strip():
                molecule = str(r["molecule"]).strip()
                break
        points = _ingest_convergence_rows(rows)
        return molecule, points, extra_meta

    if suffix != ".json":
        raise ValueError(
            f"Unsupported convergence input format {suffix!r}; expected '.json' or '.csv'."
        )

    payload = json.loads(src_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        molecule = src_path.stem
        for r in payload:
            if isinstance(r, dict) and r.get("molecule"):
                molecule = str(r["molecule"]).strip()
                break
        return molecule, _ingest_convergence_rows(payload), extra_meta

    if not isinstance(payload, dict):
        raise ValueError(f"Convergence JSON must be an object or list of records: {src_path}")

    # Support unwrapping CHEM 411 M2 receipt style (`milestones.M2`) if provided directly
    data_obj = payload
    if (
        "milestones" in payload
        and isinstance(payload["milestones"], dict)
        and isinstance(payload["milestones"].get("M2"), dict)
        and (
            "pyscf_convergence" in payload["milestones"]["M2"]
            or "orca_convergence" in payload["milestones"]["M2"]
        )
    ):
        data_obj = payload["milestones"]["M2"]

    molecule = str(data_obj.get("molecule", payload.get("molecule", src_path.stem))).strip()

    for cbs_key in (
        "helgaker_cbs_mp2_corr_dz_tz_eh",
        "helgaker_cbs_mp2_corr_dz_tz_kcal_mol",
        "cbs_extrapolation_eh",
    ):
        cbs_val = _try_finite_float(data_obj.get(cbs_key))
        if cbs_val is not None:
            extra_meta[cbs_key] = cbs_val

    points: list[ConvergencePoint] = []
    if isinstance(data_obj.get("pyscf_convergence"), list):
        points.extend(_ingest_convergence_rows(data_obj["pyscf_convergence"], default_engine="PySCF"))
    if isinstance(data_obj.get("orca_convergence"), list):
        points.extend(_ingest_convergence_rows(data_obj["orca_convergence"], default_engine="ORCA"))

    for list_key in ("records", "points", "rows", "entries", "data", "convergence"):
        if isinstance(data_obj.get(list_key), list):
            points.extend(_ingest_convergence_rows(data_obj[list_key]))

    if isinstance(data_obj.get("series"), dict):
        for series_name, series_rows in data_obj["series"].items():
            if not isinstance(series_rows, list):
                continue
            for row in series_rows:
                if not isinstance(row, dict):
                    continue
                enriched = dict(row)
                enriched.setdefault("method", str(series_name))
                points.extend(_ingest_convergence_rows([enriched]))

    return molecule, points, extra_meta


def render_basis_convergence(
    input_path: str | Path,
    output_dir: str | Path,
    prefix: str = "convergence",
    *,
    title: str | None = None,
    manifest_path: str | Path | None = None,
    units: str = "kcal/mol",
    strict: bool = False,
) -> dict[str, Any]:
    """Render publication-grade basis-set / method energy convergence PNG + PDF + SHA-256 manifest.

    Ingests verified JSON or CSV convergence tables (including CHEM 411 M2
    PySCF/ORCA basis ladders and CHEM 490 local revDSD/DFT method ladders),
    honestly annotates any PENDING/unconverged rows without fabricating values,
    fails closed if zero verified points exist, and outputs a 300-DPI PNG,
    vector PDF, and SHA-256 provenance manifest.
    """
    src_path = Path(input_path)
    if not src_path.is_file():
        raise FileNotFoundError(f"Convergence input file not found: {src_path}")

    if units not in {"kcal/mol", "mEh", "Eh"}:
        raise ValueError(f"Unsupported units {units!r}; expected 'kcal/mol', 'mEh', or 'Eh'.")

    input_sha256 = sha256_file(src_path)
    molecule, all_points, extra_meta = _parse_convergence_input(src_path)

    verified_points = [
        p for p in all_points if p.status == "VERIFIED" and p.energy_eh is not None
    ]
    pending_points = [p for p in all_points if p.status != "VERIFIED" or p.energy_eh is None]

    if strict and pending_points:
        detail = "; ".join(f"{p.series}@{p.basis}: {p.reason or 'PENDING'}" for p in pending_points)
        raise ValueError(
            "Refusing to render convergence figure with PENDING/unconverged entries in strict mode: "
            + detail
        )

    if not verified_points:
        raise ValueError(
            f"No verified finite energy convergence points found in {src_path}; "
            "refusing to render an empty or unverified convergence figure."
        )

    # Preserve first-seen basis order and series order
    basis_order: list[str] = []
    basis_nao: dict[str, int] = {}
    for pt in all_points:
        if pt.basis not in basis_order:
            basis_order.append(pt.basis)
        if pt.nao is not None and pt.basis not in basis_nao:
            basis_nao[pt.basis] = pt.nao

    basis_index = {b: i for i, b in enumerate(basis_order)}
    series_order: list[str] = []
    series_verified: dict[str, list[ConvergencePoint]] = {}
    for pt in verified_points:
        if pt.series not in series_order:
            series_order.append(pt.series)
            series_verified[pt.series] = []
        series_verified[pt.series].append(pt)

    unit_scale = (
        HARTREE_TO_KCAL if units == "kcal/mol" else (1000.0 if units == "mEh" else 1.0)
    )
    unit_label = "kcal/mol" if units == "kcal/mol" else ("mE_h" if units == "mEh" else "E_h")

    multi_basis_mode = len(basis_order) > 1 and any(
        len(pts) >= 2 for pts in series_verified.values()
    )

    _apply_publication_rc()
    fig, (ax_tot, ax_rel) = plt.subplots(1, 2, figsize=(12.6, 5.4), dpi=300)

    series_summary: list[dict[str, Any]] = []
    if multi_basis_mode:
        x_ticks = np.arange(len(basis_order), dtype=float)
        x_tick_labels = [
            f"{b}\n(NAO={basis_nao[b]})" if b in basis_nao else b for b in basis_order
        ]

        for s_idx, s_name in enumerate(series_order):
            pts = sorted(series_verified[s_name], key=lambda p: basis_index[p.basis])
            xs = [float(basis_index[p.basis]) for p in pts]
            ys_eh = [float(p.energy_eh) for p in pts if p.energy_eh is not None]
            ref_e = ys_eh[-1]
            ys_rel = [(e - ref_e) * unit_scale for e in ys_eh]

            color = OKABE_ITO_PALETTE[s_idx % len(OKABE_ITO_PALETTE)]
            marker = SERIES_MARKERS[s_idx % len(SERIES_MARKERS)]
            linestyle = "--" if s_name.upper().startswith("ORCA") else "-"

            ax_tot.plot(
                xs,
                ys_eh,
                color=color,
                marker=marker,
                linestyle=linestyle,
                linewidth=1.8,
                markersize=6.8,
                label=s_name,
                zorder=4,
            )
            ax_rel.plot(
                xs,
                ys_rel,
                color=color,
                marker=marker,
                linestyle=linestyle,
                linewidth=1.8,
                markersize=6.8,
                label=s_name,
                zorder=4,
            )
            series_summary.append(
                {
                    "series": s_name,
                    "n_verified": len(pts),
                    "reference_basis": pts[-1].basis,
                    "reference_energy_eh": ref_e,
                    "points": [
                        {
                            "basis": p.basis,
                            "nao": p.nao,
                            "energy_eh": p.energy_eh,
                            f"delta_from_largest_{units.replace('/', '_')}": (
                                (float(p.energy_eh) - ref_e) * unit_scale
                                if p.energy_eh is not None
                                else None
                            ),
                        }
                        for p in pts
                    ],
                }
            )

        ax_rel.axhline(0.0, color="#868E96", linestyle=":", linewidth=1.1, zorder=1)
        for ax, ylabel, ptitle in (
            (
                ax_tot,
                r"Total Electronic Energy $E_{\mathrm{tot}}$ ($E_{\mathrm{h}}$)",
                "(a) Total Energy vs. Basis Set",
            ),
            (
                ax_rel,
                rf"$\Delta E = E(\mathrm{{basis}}) - E(\mathrm{{largest}})$ ({unit_label})",
                "(b) Basis-Set Energy Convergence",
            ),
        ):
            ax.set_xticks(x_ticks)
            ax.set_xticklabels(x_tick_labels)
            ax.set_xlim(-0.35, len(basis_order) - 0.65)
            ax.set_xlabel("Basis Set")
            ax.set_ylabel(ylabel)
            ax.set_title(ptitle, pad=10, fontweight="bold")
            ax.yaxis.grid(True, linestyle="-", alpha=0.25, color="#ADB5BD")
            ax.set_axisbelow(True)
            ax.legend(frameon=True, facecolor="white", edgecolor="#CED4DA", fontsize=8.0, loc="best")
    else:
        # Single-basis / method comparison mode (e.g., CHEM 490 local revDSD vs B3LYP)
        ordered_verified = list(verified_points)
        x_ticks = np.arange(len(ordered_verified), dtype=float)
        x_tick_labels = [f"{p.series}\n({p.basis})" for p in ordered_verified]
        ys_eh = [float(p.energy_eh) for p in ordered_verified if p.energy_eh is not None]
        min_e = min(ys_eh)
        ys_rel = [(e - min_e) * unit_scale for e in ys_eh]

        colors = [
            OKABE_ITO_PALETTE[i % len(OKABE_ITO_PALETTE)] for i in range(len(ordered_verified))
        ]
        markers = [SERIES_MARKERS[i % len(SERIES_MARKERS)] for i in range(len(ordered_verified))]

        e_span = max(max(ys_eh) - min(ys_eh), 0.05)
        rel_span = max(max(ys_rel) - min(ys_rel), 1.0)
        for idx, (pt, e_val, rel_val) in enumerate(zip(ordered_verified, ys_eh, ys_rel)):
            ax_tot.scatter([idx], [e_val], color=colors[idx], marker=markers[idx], s=78, zorder=4)
            ax_tot.text(
                idx,
                e_val + 0.04 * e_span,
                f"{e_val:.5f} Eh",
                ha="center",
                va="bottom",
                fontsize=7.8,
                color="#1F2933",
            )
            ax_rel.bar(idx, rel_val, width=0.52, color=colors[idx], alpha=0.88, zorder=3)
            ax_rel.text(
                idx,
                rel_val + 0.03 * rel_span,
                f"{rel_val:+.2f}",
                ha="center",
                va="bottom",
                fontsize=8.0,
                color="#1F2933",
            )
            series_summary.append(
                {
                    "series": pt.series,
                    "n_verified": 1,
                    "reference_basis": pt.basis,
                    "reference_energy_eh": e_val,
                    "points": [
                        {
                            "basis": pt.basis,
                            "nao": pt.nao,
                            "energy_eh": e_val,
                            f"delta_from_min_{units.replace('/', '_')}": rel_val,
                        }
                    ],
                }
            )

        ax_tot.set_ylim(min(ys_eh) - 0.18 * e_span, max(ys_eh) + 0.25 * e_span)
        ax_rel.set_ylim(0.0, max(ys_rel) + 0.24 * rel_span)
        for ax, ylabel, ptitle in (
            (
                ax_tot,
                r"Total Electronic Energy $E_{\mathrm{tot}}$ ($E_{\mathrm{h}}$)",
                "(a) Verified Method Total Energies",
            ),
            (
                ax_rel,
                rf"$\Delta E = E - E_{{\min}}$ ({unit_label})",
                "(b) Relative Method Energy Offset",
            ),
        ):
            ax.set_xticks(x_ticks)
            ax.set_xticklabels(x_tick_labels)
            ax.set_xlim(-0.55, len(ordered_verified) - 0.45)
            ax.set_xlabel("Verified Method / Basis")
            ax.set_ylabel(ylabel)
            ax.set_title(ptitle, pad=10, fontweight="bold")
            ax.yaxis.grid(True, linestyle="-", alpha=0.25, color="#ADB5BD")
            ax.set_axisbelow(True)

    if pending_points:
        pending_badge = f"PENDING ({len(pending_points)}): " + ", ".join(
            f"{p.series}@{p.basis}" for p in pending_points[:3]
        )
        if len(pending_points) > 3:
            pending_badge += ", ..."
        ax_rel.text(
            0.98,
            0.96,
            pending_badge,
            transform=ax_rel.transAxes,
            ha="right",
            va="top",
            fontsize=7.6,
            fontweight="bold",
            color="#495057",
            bbox={
                "boxstyle": "round,pad=0.28",
                "facecolor": "#F8F9FA",
                "edgecolor": "#868E96",
                "linestyle": "--",
                "linewidth": 0.9,
            },
            zorder=6,
        )

    fig_title = title or f"CoChem-SCRIBE Verified Energy Convergence: {molecule}"
    fig.suptitle(fig_title, fontsize=12.0, fontweight="bold", y=0.97)

    cbs_note = ""
    if "helgaker_cbs_mp2_corr_dz_tz_eh" in extra_meta:
        cbs_note = f" | Helgaker CBS MP2 corr: {extra_meta['helgaker_cbs_mp2_corr_dz_tz_eh']:.6f} Eh"
    elif "cbs_extrapolation_eh" in extra_meta:
        cbs_note = f" | CBS: {extra_meta['cbs_extrapolation_eh']:.6f} Eh"

    footer = (
        f"Provenance | Input SHA-256: {input_sha256[:16]}... | "
        f"Verified: {len(verified_points)} pts | Pending: {len(pending_points)}{cbs_note}"
    )
    fig.text(0.5, 0.018, footer, ha="center", va="bottom", fontsize=7.6, color="#495057")
    fig.tight_layout(rect=(0.0, 0.055, 1.0, 0.92))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{prefix}.png"
    pdf_path = out_dir / f"{prefix}.pdf"
    mpath = Path(manifest_path) if manifest_path is not None else out_dir / f"{prefix}_manifest_sha256.json"
    mpath.parent.mkdir(parents=True, exist_ok=True)

    fig.savefig(png_path, dpi=300)
    fig.savefig(pdf_path)
    plt.close(fig)

    receipt: dict[str, Any] = {
        "schema_version": "cochem.scribe.convergence-figure-receipt/1",
        "renderer": "render_basis_convergence",
        "molecule": molecule,
        "source_input": str(src_path),
        "source_input_sha256": input_sha256,
        "units": units,
        "mode": "basis_set_convergence" if multi_basis_mode else "method_comparison",
        "basis_order": basis_order,
        "verified_point_count": len(verified_points),
        "pending_point_count": len(pending_points),
        "extra_metadata": extra_meta,
        "series_summary": series_summary,
        "pending_points": [p.model_dump(mode="json") for p in pending_points],
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
        "manifest_path": str(mpath),
    }

    mpath.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt
