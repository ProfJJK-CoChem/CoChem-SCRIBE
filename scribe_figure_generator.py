import hashlib
from typing import Any, Dict, List, Optional
#!/usr/bin/env python3
"""
CoChem-SCRIBE: Figure Generator (Stage 6.2)
Generates publication-ready scientific figures and visualizations from HDF5 tensors.
Implements visualization pipelines for TOPOS, TORQ, SpycFit, and mass spectrometry artifacts.
"""

import os
import sys
from pathlib import Path

# Resolves SCRIBE-08: Enforce non-interactive headless backend for Matplotlib and PyVista prior to imports
try:
    import matplotlib
    matplotlib.use('Agg')
except ImportError as e:
    logging.warning(f"Matplotlib not available or could not set headless Agg backend: {e}")

import h5py
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import logging
logger = logging.getLogger(__name__)
import json
import zstandard as zstd
from datetime import datetime

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
artifact_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(artifact_dir / 'cochem_scribe_figures.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ScribeFigureGenerator:
    def __init__(self) -> None:
        self.h5_file_path = Path("cochem_state.h5")
        self.output_dir = artifact_dir / "generated_figures"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.figures_generated = 0

    def _generate_topos_artifacts(self) -> Any:
        """Generates TOPOS artifacts: 3D carousels, NCI domains, etc."""
        logger.info(f"{Colors.OKCYAN}[INFO] Generating TOPOS visualization artifacts...{Colors.ENDC}")
        
        try:
            if not self.h5_file_path.exists():
                logging.warning("cochem_state.h5 not found for TOPOS artifacts")
                return
                
            with h5py.File(self.h5_file_path, 'r') as f:
                if 'isomers' in f:
                    isomers_group = f['isomers']
                    for key in isomers_group.keys():
                        if key.startswith('geometry_'):
                            geom_data = isomers_group[key][:]
                            self._generate_isomer_3d(geom_data, key)
                            
                if 'chiral_buckets' in f:
                    buckets = f['chiral_buckets']
                    self._generate_chiral_bucket_table(buckets)
                    
        except Exception as e:
            logging.error(f"Error generating TOPOS artifacts: {e}")

    def _generate_isomer_3d(self, geometry_data, isomer_name) -> Any:
        """Generate 3D visualization of an isomer."""
        try:
            fig = go.Figure()
            if len(geometry_data) > 0:
                x_coords = geometry_data[:, 0]
                y_coords = geometry_data[:, 1]
                z_coords = geometry_data[:, 2]
                
                fig.add_trace(go.Scatter3d(
                    x=x_coords, y=y_coords, z=z_coords,
                    mode='markers', marker=dict(size=5, color='blue'),
                    name=isomer_name
                ))
                
                output_file = self.output_dir / f"{isomer_name}_3d.html"
                fig.write_html(str(output_file))
                logging.info(f"Generated 3D isomer visualization: {output_file}")
                self.figures_generated += 1
                
        except Exception as e:
            logging.error(f"Error generating 3D isomer {isomer_name}: {e}")

    def _generate_chiral_bucket_table(self, buckets) -> Any:
        """Generate LaTeX table for chiral bucket distributions."""
        try:
            table_content = "\\begin{table}[h]\n\\centering\n\\caption{Enantiomeric Excess Distribution}\n\\begin{tabular}{|c|c|}\n\\hline\nIsomer & Enantiomeric Excess \\\\\\hline\n"
            if hasattr(buckets, 'shape') and len(buckets.shape) > 0:
                for i, bucket in enumerate(buckets):
                    table_content += f"Isomer_{i} & {bucket:.2f}\\\\\\hline\n"
            table_content += "\\end{tabular}\n\\end{table}"
            
            output_file = self.output_dir / "chiral_buckets_table.tex"
            with open(output_file, 'w') as f:
                f.write(table_content)
                
            logging.info(f"Generated chiral bucket table: {output_file}")
            self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error generating chiral bucket table: {e}")

    def _generate_torq_artifacts(self) -> Any:
        """Generates TORQ artifacts: Sinc-DVR wavefunctions, IR spectra, etc."""
        logger.info(f"{Colors.OKCYAN}[INFO] Generating TORQ visualization artifacts...{Colors.ENDC}")
        try:
            if not self.h5_file_path.exists():
                logging.warning("cochem_state.h5 not found for TORQ artifacts")
                return
                
            with h5py.File(self.h5_file_path, 'r') as f:
                if 'dvr_wavefunctions' in f:
                    wavefunctions = f['dvr_wavefunctions']
                    self._generate_dvr_probability_maps(wavefunctions)
                if 'pes_grids' in f:
                    pes_data = f['pes_grids']
                    self._generate_pes_contour_maps(pes_data)
                if 'ir_spectra' in f:
                    ir_data = f['ir_spectra']
                    self._generate_ir_comparison_plot(ir_data)
        except Exception as e:
            logging.error(f"Error generating TORQ artifacts: {e}")

    def _generate_dvr_probability_maps(self, wavefunctions) -> Any:
        try:
            fig = go.Figure()
            if len(wavefunctions) > 0:
                for i, wf in enumerate(wavefunctions):
                    if len(wf.shape) >= 2:
                        x = np.linspace(0, 10, wf.shape[1])
                        y = np.linspace(0, 10, wf.shape[0])
                        fig.add_trace(go.Contour(z=wf, x=x, y=y, name=f"Wavefunction_{i}", colorscale='Viridis'))
                output_file = self.output_dir / "dvr_probability_maps.html"
                fig.write_html(str(output_file))
                logging.info(f"Generated DVR probability maps: {output_file}")
                self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error generating DVR probability maps: {e}")

    def _generate_pes_contour_maps(self, pes_data) -> Any:
        try:
            fig = go.Figure()
            if len(pes_data) > 0 and len(pes_data.shape) >= 2:
                x = np.linspace(0, 10, pes_data.shape[1])
                y = np.linspace(0, 10, pes_data.shape[0])
                fig.add_trace(go.Contour(z=pes_data, x=x, y=y, name="PES", colorscale='Jet'))
                output_file = self.output_dir / "pes_contour_maps.html"
                fig.write_html(str(output_file))
                logging.info(f"Generated PES contour maps: {output_file}")
                self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error generating PES contour maps: {e}")

    def _generate_ir_comparison_plot(self, ir_data) -> Any:
        try:
            fig = go.Figure()
            if len(ir_data) >= 2:
                harmonic_freqs = ir_data[0]
                anharmonic_freqs = ir_data[1]
                fig.add_trace(go.Scatter(x=harmonic_freqs, y=np.ones_like(harmonic_freqs), mode='markers', name='Harmonic'))
                fig.add_trace(go.Scatter(x=anharmonic_freqs, y=np.ones_like(anharmonic_freqs) * 0.8, mode='markers', name='Anharmonic'))
                output_file = self.output_dir / "ir_comparison.html"
                fig.write_html(str(output_file))
                logging.info(f"Generated IR comparison plot: {output_file}")
                self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error generating IR comparison plot: {e}")

    def _generate_spYcFit_artifacts(self) -> Any:
        logger.info(f"{Colors.OKCYAN}[INFO] Generating SpycFit visualization artifacts...{Colors.ENDC}")
        try:
            if not self.h5_file_path.exists():
                logging.warning("cochem_state.h5 not found for SpycFit artifacts")
                return
            with h5py.File(self.h5_file_path, 'r') as f:
                if 'bayesian_convergence' in f:
                    self._generate_bayesian_convergence_plot(f['bayesian_convergence'])
                if 'loio_results' in f:
                    self._generate_loio_boxplot(f['loio_results'])
                if 'voigt_convolution' in f:
                    self._generate_voigt_spectrum(f['voigt_convolution'])
        except Exception as e:
            logging.error(f"Error generating SpycFit artifacts: {e}")

    def _generate_bayesian_convergence_plot(self, conv_data) -> Any:
        try:
            fig = go.Figure()
            if len(conv_data) > 0:
                fig.add_trace(go.Scatter(x=list(range(len(conv_data))), y=conv_data, mode='lines+markers', name='Convergence'))
                output_file = self.output_dir / "bayesian_convergence.html"
                fig.write_html(str(output_file))
                logging.info(f"Generated Bayesian convergence plot: {output_file}")
                self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error generating Bayesian convergence plot: {e}")

    def _generate_loio_boxplot(self, loio_data) -> Any:
        try:
            fig = go.Figure()
            if len(loio_data) > 0:
                fig.add_trace(go.Box(y=loio_data, name='LOIO Results'))
                output_file = self.output_dir / "loio_boxplot.html"
                fig.write_html(str(output_file))
                logging.info(f"Generated LOIO boxplot: {output_file}")
                self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error generating LOIO boxplot: {e}")

    def _generate_voigt_spectrum(self, spec_data) -> Any:
        try:
            fig = go.Figure()
            if len(spec_data) >= 2:
                fig.add_trace(go.Scatter(x=spec_data[0], y=spec_data[1], mode='lines', name='Voigt Spectrum'))
                output_file = self.output_dir / "voigt_spectrum.html"
                fig.write_html(str(output_file))
                logging.info(f"Generated Voigt spectrum: {output_file}")
                self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error generating Voigt spectrum: {e}")

    def _generate_mass_spectrometry_artifacts(self) -> Any:
        logger.info(f"{Colors.OKCYAN}[INFO] Generating mass spectrometry visualization artifacts...{Colors.ENDC}")
        try:
            qcxms_files = list(Path(".").glob("*.res"))
            if len(qcxms_files) > 0:
                for res_file in qcxms_files:
                    self._parse_qcxms_file(res_file)
        except Exception as e:
            logging.error(f"Error generating mass spectrometry artifacts: {e}")

    def _parse_qcxms_file(self, res_file) -> Any:
        try:
            mz_values = []
            intensities = []
            with open(res_file, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            mz_values.append(float(parts[0]))
                            intensities.append(float(parts[1]))
                        except ValueError:
                            continue
            if not mz_values:
                logging.warning(f"No valid MS data found in {res_file}")
                return

            fig = go.Figure()
            fig.add_trace(go.Bar(x=mz_values, y=intensities, name='Theoretical MS'))
            output_file = self.output_dir / f"{res_file.stem}_ms.html"
            fig.write_html(str(output_file))
            logging.info(f"Generated MS fragmentation chart: {output_file}")
            self.figures_generated += 1
        except Exception as e:
            logging.error(f"Error parsing QCxMS file {res_file}: {e}")

    def generate_all_artifacts(self) -> Any:
        logger.info(f"{Colors.OKCYAN}[INFO] Generating all publication-ready artifacts...{Colors.ENDC}")
        self._generate_topos_artifacts()
        self._generate_torq_artifacts()
        self._generate_spYcFit_artifacts()
        self._generate_mass_spectrometry_artifacts()
        logger.info(f"{Colors.OKGREEN}[OK] Generated {self.figures_generated} visualization artifacts.{Colors.ENDC}")
        logging.info(f"Total figures generated: {self.figures_generated}")

def main() -> Any:
    logger.info(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Figure Generator ---{Colors.ENDC}")
    generator = ScribeFigureGenerator()
    generator.generate_all_artifacts()

if __name__ == "__main__":
    main()
def calculate_artifact_sha256(filepath: str | Path) -> str:
    """Calculates SHA-256 hash of a computational artifact."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"Artifact file not found: {filepath}")
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()