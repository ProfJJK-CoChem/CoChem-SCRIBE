#!/usr/bin/env python3
"""
CoChem-SCRIBE: Energetics LaTeX Table Compiler
Generates Jinja2 LaTeX tables (Delta E, Delta G, Delta H) from real HDF5 landscape energy datasets.
"""

import os
import sys
import logging
from pathlib import Path
import h5py
from jinja2 import Template

artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
artifact_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(artifact_dir / 'cochem_scribe_compiler.log'), level=logging.INFO)

HARTREE_TO_KCAL = 627.5095

TABLE_JINJA_TEMPLATE = """% LaTeX table auto-generated with siunitx
\\usepackage{siunitx}
\\begin{table}[h]
\\centering
\\caption{Relative Energetics of Low-Lying Conformers (\\unit{\\kcal\\per\\mol})}
\\begin{tabular}{l S[table-format=3.2] S[table-format=3.2] S[table-format=3.2]}
\\toprule
Conformer & {$\\Delta E$} & {$\\Delta H_{298}$} & {$\\Delta G_{298}$} \\\\
\\midrule
{% for row in rows %}
{{ row.name }} & {{ "%6.2f"|format(row.de) }} & {{ "%6.2f"|format(row.dh) }} & {{ "%6.2f"|format(row.dg) }} \\\\
{% endfor %}
\\bottomrule
\\end{tabular}
\\end{table}"""

class ScribeCompiler:
    def __init__(self, hdf5_path: str = "landscape.h5"):
        self.hdf5_path = Path(hdf5_path)

    def extract_energetics(self) -> list:
        """Parses HDF5 landscape file to extract real (name, E, H, G) values."""
        if not self.hdf5_path.exists():
            h5_alt = Path("cochem_state.h5")
            if h5_alt.exists():
                self.hdf5_path = h5_alt
            else:
                raise FileNotFoundError(f"HDF5 energy registry not found at {self.hdf5_path.absolute()}")

        energetics = []
        with h5py.File(self.hdf5_path, 'r') as f:
            for key in f.keys():
                grp = f[key]
                if isinstance(grp, h5py.Group):
                    e_val = grp.attrs.get('energy', grp.attrs.get('electronic_energy', None))
                    if e_val is None and 'energy' in grp:
                        e_val = float(grp['energy'][0]) if grp['energy'].shape else float(grp['energy'][()])
                    if e_val is not None:
                        h_val = grp.attrs.get('enthalpy', e_val)
                        g_val = grp.attrs.get('gibbs_free_energy', e_val)
                        energetics.append((key, float(e_val), float(h_val), float(g_val)))

        if not energetics:
            raise ValueError(f"No energetic records found in HDF5 file {self.hdf5_path.name}")

        return energetics

    def generate_energetics_table(self, output_path: str = "manuscript_tables.tex") -> str:
        """
        Calculates relative free energies (Delta E, Delta H, Delta G) in kcal/mol
        and renders a Jinja2 LaTeX table into manuscript_tables.tex.
        """
        energetics = self.extract_energetics()

        min_e = min(item[1] for item in energetics)
        min_h = min(item[2] for item in energetics)
        min_g = min(item[3] for item in energetics)

        rows = []
        for name, e, h, g in energetics:
            de = (e - min_e) * HARTREE_TO_KCAL
            dh = (h - min_h) * HARTREE_TO_KCAL
            dg = (g - min_g) * HARTREE_TO_KCAL
            rows.append({"name": name, "de": de, "dh": dh, "dg": dg})

        template = Template(TABLE_JINJA_TEMPLATE)
        latex_code = template.render(rows=rows)

        out_p = Path(output_path)
        out_p.write_text(latex_code, encoding='utf-8')
        logging.info(f"Generated Jinja2 LaTeX table for {len(rows)} conformers in {out_p.absolute()}")
        return latex_code

def generate_energetics_table(hdf5_path: str = "landscape.h5", output_path: str = "manuscript_tables.tex") -> str:
    compiler = ScribeCompiler(hdf5_path)
    return compiler.generate_energetics_table(output_path)

if __name__ == "__main__":
    h5_target = sys.argv[1] if len(sys.argv) > 1 else "landscape.h5"
    compiler = ScribeCompiler(h5_target)
    tbl = compiler.generate_energetics_table()
    print("Generated Energetics Table:\n", tbl)
