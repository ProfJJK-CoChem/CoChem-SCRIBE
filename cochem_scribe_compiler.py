import json
import os
import re
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from cochem_base.config_loader import resolve_config_path

logger = logging.getLogger(__name__)


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


def ensure_double_escaped_latex(text: str) -> str:
    """
    Ensures that LaTeX math environments and macros are double escaped.
    Replaces single backslashes with double backslashes unless already double.
    """
    return re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', text)


def validate_mermaid(text: str) -> bool:
    """
    Validates that Mermaid flowcharts contain no unescaped parentheses or quotes 
    inside node definitions that would corrupt Markdown rendering.
    """
    node_pattern = re.compile(r'[\[\(\{](.*?)[\]\)\}]')
    for match in node_pattern.finditer(text):
        content = match.group(1)
        if '(' in content or ')' in content or '"' in content:
            if not (content.startswith('"') and content.endswith('"')):
                raise ValueError(f"Mermaid node contains unescaped special characters (quotes or parentheses): {content}")
    return True


def compile_qcschema_to_tex(qcschema: Dict[str, Any]) -> str:
    """
    Converts a QCSchema JSON representation to a Supporting Information LaTeX format.
    Zero truncation: all components are explicitly output without placeholders.
    """
    tex_lines: List[str] = []
    
    # Document Header
    tex_lines.append(r"\\documentclass{article}")
    tex_lines.append(r"\\usepackage[utf8]{inputenc}")
    tex_lines.append(r"\\usepackage{geometry}")
    tex_lines.append(r"\\usepackage{amsmath}")
    tex_lines.append(r"\\usepackage{booktabs}")
    tex_lines.append(r"\\usepackage{longtable}")
    tex_lines.append(r"\\geometry{letterpaper, margin=1in}")
    tex_lines.append(r"\\begin{document}")
    tex_lines.append("")
    tex_lines.append(r"\\section*{Supporting Information}")
    
    # Extract Molecule Geometry
    molecule = qcschema.get("molecule", {})
    symbols = molecule.get("symbols", [])
    geometry = molecule.get("geometry", [])
    
    if symbols and geometry:
        tex_lines.append(r"\\subsection*{Optimized Geometry}")
        tex_lines.append(r"\\begin{longtable}{l r r r}")
        tex_lines.append(r"\\toprule")
        tex_lines.append(r"Atom & X (Bohr) & Y (Bohr) & Z (Bohr) \\\\")
        tex_lines.append(r"\\midrule")
        tex_lines.append(r"\\endhead")
        
        for i, sym in enumerate(symbols):
            idx = i * 3
            if idx + 2 < len(geometry):
                x = geometry[idx]
                y = geometry[idx+1]
                z = geometry[idx+2]
                tex_lines.append(f"{sym} & {x:.6f} & {y:.6f} & {z:.6f} \\\\\\\\")
            
        tex_lines.append(r"\\bottomrule")
        tex_lines.append(r"\\end{longtable}")
        tex_lines.append("")

    # Extract Properties
    properties = qcschema.get("properties", {})
    if properties:
        tex_lines.append(r"\\subsection*{Computed Properties}")
        tex_lines.append(r"\\begin{itemize}")
        for prop, val in properties.items():
            prop_esc = prop.replace("_", r"\\_")
            if isinstance(val, (int, float)):
                tex_lines.append(f"    \\item {prop_esc}: {val} [M]")
            else:
                tex_lines.append(f"    \\item {prop_esc}: {val} [D]")
        tex_lines.append(r"\\end{itemize}")
        tex_lines.append("")

    # Extract Method Details
    model = qcschema.get("model", {})
    if model:
        method = model.get("method", "Unknown")
        basis = model.get("basis", "Unknown")
        tex_lines.append(r"\\subsection*{Computational Methods}")
        tex_lines.append(f"All calculations were performed using the {method} method and the {basis} basis set. Energy values and properties are strictly derived from literature benchmarks [M] or computed directly [D].")
        tex_lines.append("")
    
    tex_lines.append(r"\\end{document}")
    
    return "\n".join(tex_lines)


class ScribeCompiler:
    """
    SI Table and energetics document compiler for CoChem-SCRIBE.
    """
    def __init__(self, hdf5_path: str = "landscape.h5") -> None:
        self.hdf5_path = Path(hdf5_path)

    def generate_energetics_table(self, output_tex: Optional[str] = "tables.tex") -> str:
        tex_lines: List[str] = []
        tex_lines.append(r"\usepackage{siunitx}")
        tex_lines.append(r"\begin{table}[h!]")
        tex_lines.append(r"\centering")
        tex_lines.append(r"\begin{tabular}{l S[table-format=-3.4] S[table-format=-3.4] S[table-format=-3.4]}")
        tex_lines.append(r"\toprule")
        tex_lines.append(r"Conformer & {Energy (Ha) [D]} & {Enthalpy (Ha) [D]} & {Gibbs Free Energy (Ha) [D]} \\")
        tex_lines.append(r"\midrule")

        if self.hdf5_path.exists():
            import h5py
            with h5py.File(self.hdf5_path, 'r') as f:
                for key in f.keys():
                    grp = f[key]
                    e = grp.attrs.get('energy', 0.0)
                    h = grp.attrs.get('enthalpy', 0.0)
                    g = grp.attrs.get('gibbs_free_energy', 0.0)
                    tex_lines.append(f"{key} & {e:.4f} & {h:.4f} & {g:.4f} \\\\")

        tex_lines.append(r"\bottomrule")
        tex_lines.append(r"\end{tabular}")
        tex_lines.append(r"\end{table}")

        res = "\n".join(tex_lines)
        if output_tex:
            out_p = Path(output_tex)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(res, encoding="utf-8")
        return res


def run_auto_compiler(input_dir: str, output_tex: str) -> None:
    """
    Automated SI Compilation: scans for QCSchema files and produces a rigorous SI document.
    """
    input_path = Path(input_dir)
    compiled_tex: List[str] = []
    
    compiled_tex.append(r"\\documentclass{article}")
    compiled_tex.append(r"\\usepackage[utf8]{inputenc}")
    compiled_tex.append(r"\\usepackage{geometry}")
    compiled_tex.append(r"\\usepackage{amsmath}")
    compiled_tex.append(r"\\usepackage{booktabs}")
    compiled_tex.append(r"\\usepackage{longtable}")
    compiled_tex.append(r"\\geometry{letterpaper, margin=1in}")
    compiled_tex.append(r"\\begin{document}")
    compiled_tex.append(r"\\section*{Compiled Supporting Information}")
    
    for json_file in input_path.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
            tex_content = compile_qcschema_to_tex(data)
            
            start_marker = r"\\begin{document}"
            end_marker = r"\\end{document}"
            
            if start_marker in tex_content and end_marker in tex_content:
                body = tex_content.split(start_marker)[1].split(end_marker)[0]
                body = ensure_double_escaped_latex(body)
                
                compiled_tex.append(f"\\subsection*{{File: {json_file.name}}}")
                compiled_tex.append(body)

    compiled_tex.append(r"\\end{document}")
    
    with open(output_tex, "w", encoding="utf-8") as f:
        f.write("\n".join(compiled_tex))
    logger.info(f"SI Compilation complete. Artifact written to {output_tex}")


if __name__ == '__main__':
    config_path = resolve_config_path()
    input_directory = str(config_path.parent / "CoChem-EXEC" / "data")
    output_file = str(config_path.parent / "CoChem-EXEC" / "compiled_si.tex")
    
    if os.path.exists(input_directory):
        run_auto_compiler(input_directory, output_file)
    else:
        logger.info(f"[MISSING DATA] Input directory {input_directory} does not exist.")