#!/usr/bin/env python3
"""
CoChem-SCRIBE: Figure Generator (Stage 6.2)
Legacy-compatible entry point backed by verified-output CoChem-SCRIBE renderers.
All synthetic np.linspace(0, 10, ...) axes and hardcoded flat 1.0/0.8 IR heights
have been removed; every figure requires verified coordinates and intensities.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import numpy as np

try:
    import h5py
except ImportError:
    h5py = None  # type: ignore[assignment]

try:
    import plotly.graph_objects as go
except ImportError:
    go = None  # type: ignore[assignment]

try:
    import zstandard as zstd
except ImportError:
    zstd = None  # type: ignore[assignment]

from cochem_scribe.renderers import (
    render_geom_comparison,
    render_kinetic_rxn_profile,
    sha256_file,
)

logger = logging.getLogger(__name__)


class Colors:
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def calculate_artifact_sha256(filepath: str | Path) -> str:
    """Calculate SHA-256 hash of a computational artifact."""
    return sha256_file(filepath)


class ScribeFigureGenerator:
    """Verified-output HDF5 / artifact figure generator (zero synthetic axes)."""

    def __init__(
        self,
        h5_file_path: str | Path = "cochem_state.h5",
        output_dir: str | Path | None = None,
    ) -> None:
        artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
        self.h5_file_path = Path(h5_file_path)
        self.output_dir = Path(output_dir) if output_dir is not None else artifact_dir / "generated_figures"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.figures_generated = 0

    def _require_plotly(self) -> Any:
        if go is None:
            raise ImportError(
                "plotly is required for legacy HTML HDF5 figures; install 'cochem-scribe[legacy]'."
            )
        return go

    def _require_h5py(self) -> Any:
        if h5py is None:
            raise ImportError(
                "h5py is required to read cochem_state.h5; install 'cochem-scribe[legacy]'."
            )
        return h5py

    def _extract_verified_2d_axes(
        self,
        dataset: Any,
        parent_group: Any,
        x_key: str,
        y_key: str,
        expected_shape: tuple[int, ...],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Load verified coordinate axes from HDF5 dataset/group; refuse synthetic grids."""
        x_raw = dataset.attrs.get(x_key) if hasattr(dataset, "attrs") else None
        y_raw = dataset.attrs.get(y_key) if hasattr(dataset, "attrs") else None
        if x_raw is None and parent_group is not None and x_key in parent_group:
            x_raw = parent_group[x_key][:]
        if y_raw is None and parent_group is not None and y_key in parent_group:
            y_raw = parent_group[y_key][:]
        if x_raw is None or y_raw is None:
            raise ValueError(
                f"Missing verified coordinate axes ({x_key!r}, {y_key!r}) in HDF5 artifact; "
                "fabricating synthetic axes is prohibited."
            )
        x_arr = np.asarray(x_raw, dtype=float)
        y_arr = np.asarray(y_raw, dtype=float)
        if x_arr.shape != (expected_shape[1],) or y_arr.shape != (expected_shape[0],):
            raise ValueError(
                f"Axis shape mismatch: expected x=({expected_shape[1]},), y=({expected_shape[0]},), "
                f"got x={x_arr.shape}, y={y_arr.shape}."
            )
        if not (np.all(np.isfinite(x_arr)) and np.all(np.isfinite(y_arr))):
            raise ValueError("Coordinate axes must contain only finite numeric values.")
        return x_arr, y_arr

    def _generate_topos_artifacts(self) -> None:
        """Generate verified TOPOS 3D isomer scatter plots and chiral tables from HDF5."""
        if not self.h5_file_path.exists():
            logger.warning("cochem_state.h5 not found for TOPOS artifacts: %s", self.h5_file_path)
            return
        h5 = self._require_h5py()
        with h5.File(self.h5_file_path, "r") as f:
            if "isomers" in f:
                isomers_group = f["isomers"]
                for key in isomers_group.keys():
                    if key.startswith("geometry_"):
                        geom_data = np.asarray(isomers_group[key][:], dtype=float)
                        self._generate_isomer_3d(geom_data, key)
            if "chiral_buckets" in f:
                self._generate_chiral_bucket_table(f["chiral_buckets"][:])

    def _generate_isomer_3d(self, geometry_data: np.ndarray, isomer_name: str) -> None:
        plotly_go = self._require_plotly()
        arr = np.asarray(geometry_data, dtype=float)
        if arr.ndim != 2 or arr.shape[1] < 3 or arr.shape[0] == 0:
            raise ValueError(f"Invalid 3D geometry array for {isomer_name!r}: shape={arr.shape}")
        fig = plotly_go.Figure()
        fig.add_trace(
            plotly_go.Scatter3d(
                x=arr[:, 0],
                y=arr[:, 1],
                z=arr[:, 2],
                mode="markers",
                marker={"size": 5, "color": "#0072B2"},
                name=isomer_name,
            )
        )
        output_file = self.output_dir / f"{isomer_name}_3d.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def _generate_chiral_bucket_table(self, buckets: Any) -> None:
        vals = np.asarray(buckets, dtype=float)
        if vals.size == 0 or not np.all(np.isfinite(vals)):
            raise ValueError("chiral_buckets dataset must contain finite values.")
        lines = [
            "\\begin{table}[h]",
            "\\centering",
            "\\caption{Enantiomeric Excess Distribution}",
            "\\begin{tabular}{|c|c|}",
            "\\hline",
            "Isomer & Enantiomeric Excess \\\\\\hline",
        ]
        for i, bucket in enumerate(vals.ravel()):
            lines.append(f"Isomer_{i} & {float(bucket):.2f}\\\\\\hline")
        lines.extend(["\\end{tabular}", "\\end{table}"])
        output_file = self.output_dir / "chiral_buckets_table.tex"
        output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.figures_generated += 1

    def _generate_torq_artifacts(self) -> None:
        """Generate verified TORQ DVR, PES, and IR figures using authentic coordinate/intensity data."""
        if not self.h5_file_path.exists():
            logger.warning("cochem_state.h5 not found for TORQ artifacts: %s", self.h5_file_path)
            return
        h5 = self._require_h5py()
        with h5.File(self.h5_file_path, "r") as f:
            if "dvr_wavefunctions" in f:
                self._generate_dvr_probability_maps(f["dvr_wavefunctions"], parent_group=f)
            if "pes_grids" in f:
                self._generate_pes_contour_maps(f["pes_grids"], parent_group=f)
            if "ir_spectra" in f:
                self._generate_ir_comparison_plot(f["ir_spectra"])

    def _generate_dvr_probability_maps(self, wavefunctions: Any, parent_group: Any = None) -> None:
        plotly_go = self._require_plotly()
        arr = np.asarray(wavefunctions[:], dtype=float)
        if arr.ndim < 3 or arr.shape[0] == 0:
            raise ValueError(f"Expected 3D stack of verified DVR wavefunctions, got shape {arr.shape}")
        x, y = self._extract_verified_2d_axes(
            wavefunctions, parent_group, "dvr_x_axis", "dvr_y_axis", arr.shape[1:3]
        )
        fig = plotly_go.Figure()
        for i, wf in enumerate(arr):
            fig.add_trace(
                plotly_go.Contour(z=wf, x=x, y=y, name=f"Wavefunction_{i}", colorscale="Viridis")
            )
        output_file = self.output_dir / "dvr_probability_maps.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def _generate_pes_contour_maps(self, pes_data: Any, parent_group: Any = None) -> None:
        plotly_go = self._require_plotly()
        arr = np.asarray(pes_data[:], dtype=float)
        if arr.ndim != 2 or arr.size == 0:
            raise ValueError(f"Expected 2D verified PES grid, got shape {arr.shape}")
        x, y = self._extract_verified_2d_axes(
            pes_data, parent_group, "pes_x_axis", "pes_y_axis", arr.shape
        )
        fig = plotly_go.Figure()
        fig.add_trace(plotly_go.Contour(z=arr, x=x, y=y, name="PES", colorscale="Viridis"))
        output_file = self.output_dir / "pes_contour_maps.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def _generate_ir_comparison_plot(self, ir_data: Any) -> None:
        """Plot verified harmonic and anharmonic IR spectra with real computed intensities.

        Requires a 4-row array [harmonic_freqs, harmonic_intensities, anharmonic_freqs,
        anharmonic_intensities] or a mapping/group with explicit frequency and intensity arrays.
        Flat hardcoded unit/scaled stick heights are strictly prohibited.
        """
        plotly_go = self._require_plotly()
        if hasattr(ir_data, "keys") and not isinstance(ir_data, np.ndarray):
            required = (
                "harmonic_frequencies_cm1",
                "harmonic_intensities_km_mol",
                "anharmonic_frequencies_cm1",
                "anharmonic_intensities_km_mol",
            )
            missing = [k for k in required if k not in ir_data]
            if missing:
                raise ValueError(
                    f"IR spectrum group missing verified datasets {missing!r}; "
                    "hardcoded flat IR stick heights are prohibited."
                )
            h_freq = np.asarray(ir_data["harmonic_frequencies_cm1"][:], dtype=float)
            h_int = np.asarray(ir_data["harmonic_intensities_km_mol"][:], dtype=float)
            a_freq = np.asarray(ir_data["anharmonic_frequencies_cm1"][:], dtype=float)
            a_int = np.asarray(ir_data["anharmonic_intensities_km_mol"][:], dtype=float)
        else:
            arr = np.asarray(ir_data[:], dtype=float)
            if arr.ndim != 2 or arr.shape[0] < 4:
                raise ValueError(
                    "ir_spectra array must provide 4 rows: "
                    "[harmonic_freqs, harmonic_intensities, anharmonic_freqs, anharmonic_intensities]; "
                    "hardcoded flat IR bar heights are prohibited."
                )
            h_freq, h_int, a_freq, a_int = arr[0], arr[1], arr[2], arr[3]

        for name, vec in (
            ("harmonic_freqs", h_freq),
            ("harmonic_intensities", h_int),
            ("anharmonic_freqs", a_freq),
            ("anharmonic_intensities", a_int),
        ):
            if vec.size == 0 or not np.all(np.isfinite(vec)):
                raise ValueError(f"IR vector {name!r} must be non-empty and finite.")

        fig = plotly_go.Figure()
        fig.add_trace(plotly_go.Bar(x=h_freq, y=h_int, name="Harmonic (verified km/mol)"))
        fig.add_trace(plotly_go.Bar(x=a_freq, y=a_int, name="Anharmonic (verified km/mol)"))
        fig.update_layout(
            xaxis_title="Wavenumber (cm^-1)",
            yaxis_title="IR Intensity (km/mol)",
            barmode="group",
        )
        output_file = self.output_dir / "ir_comparison.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def _generate_spYcFit_artifacts(self) -> None:
        if not self.h5_file_path.exists():
            return
        h5 = self._require_h5py()
        with h5.File(self.h5_file_path, "r") as f:
            if "bayesian_convergence" in f:
                self._generate_bayesian_convergence_plot(f["bayesian_convergence"][:])
            if "loio_results" in f:
                self._generate_loio_boxplot(f["loio_results"][:])
            if "voigt_convolution" in f:
                self._generate_voigt_spectrum(f["voigt_convolution"][:])

    def _generate_bayesian_convergence_plot(self, conv_data: Any) -> None:
        plotly_go = self._require_plotly()
        arr = np.asarray(conv_data, dtype=float)
        if arr.size == 0:
            raise ValueError("bayesian_convergence dataset is empty.")
        fig = plotly_go.Figure()
        fig.add_trace(
            plotly_go.Scatter(
                x=list(range(len(arr))), y=arr, mode="lines+markers", name="Convergence"
            )
        )
        output_file = self.output_dir / "bayesian_convergence.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def _generate_loio_boxplot(self, loio_data: Any) -> None:
        plotly_go = self._require_plotly()
        arr = np.asarray(loio_data, dtype=float)
        if arr.size == 0:
            raise ValueError("loio_results dataset is empty.")
        fig = plotly_go.Figure()
        fig.add_trace(plotly_go.Box(y=arr, name="LOIO Results"))
        output_file = self.output_dir / "loio_boxplot.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def _generate_voigt_spectrum(self, spec_data: Any) -> None:
        plotly_go = self._require_plotly()
        arr = np.asarray(spec_data, dtype=float)
        if arr.ndim != 2 or arr.shape[0] < 2:
            raise ValueError("voigt_convolution dataset must have 2 rows (frequency, intensity).")
        fig = plotly_go.Figure()
        fig.add_trace(plotly_go.Scatter(x=arr[0], y=arr[1], mode="lines", name="Voigt Spectrum"))
        output_file = self.output_dir / "voigt_spectrum.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def _generate_mass_spectrometry_artifacts(self, search_dir: str | Path = ".") -> None:
        for res_file in sorted(Path(search_dir).glob("*.res")):
            self._parse_qcxms_file(res_file)

    def _parse_qcxms_file(self, res_file: Path) -> None:
        plotly_go = self._require_plotly()
        mz_values: list[float] = []
        intensities: list[float] = []
        with res_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        mz_values.append(float(parts[0]))
                        intensities.append(float(parts[1]))
                    except ValueError:
                        continue
        if not mz_values:
            raise ValueError(f"No valid MS peaks found in {res_file}")
        fig = plotly_go.Figure()
        fig.add_trace(plotly_go.Bar(x=mz_values, y=intensities, name="Theoretical MS"))
        output_file = self.output_dir / f"{res_file.stem}_ms.html"
        fig.write_html(str(output_file))
        self.figures_generated += 1

    def generate_all_artifacts(self, search_dir: str | Path = ".") -> int:
        self._generate_topos_artifacts()
        self._generate_torq_artifacts()
        self._generate_spYcFit_artifacts()
        self._generate_mass_spectrometry_artifacts(search_dir=search_dir)
        logger.info("Total figures generated: %d", self.figures_generated)
        return self.figures_generated


def main() -> None:
    generator = ScribeFigureGenerator()
    generator.generate_all_artifacts()


__all__ = [
    "Colors",
    "ScribeFigureGenerator",
    "calculate_artifact_sha256",
    "main",
    "render_geom_comparison",
    "render_kinetic_rxn_profile",
]

if __name__ == "__main__":
    main()
