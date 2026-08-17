from typing import Any, Dict, List, Optional
#!/usr/bin/env python3
"""
CoChem-SCRIBE: Methodology Tracker & Master Document Compiler
Reads execution provenance & compute_flags from HDF5 and execution logs,
mapping method flags to publication-ready LaTeX method paragraphs (methods.tex)
and BibTeX citation databases (references.bib).
"""

import os
import sys
import json
import logging
logger = logging.getLogger(__name__)
import re
import hashlib
from pathlib import Path
import h5py
import numpy as np
from jinja2 import Template

def count_tags_in_attr(k: str, val_str: str, tag_counts: dict) -> Any:
    has_bracket_tag = False
    for tag in ["[M]", "[D]", "[E]"]:
        c = val_str.count(tag)
        if c > 0:
            tag_counts[tag] += c
            has_bracket_tag = True
    
    if not has_bracket_tag and k in ("provenance", "provenance_tag", "tag", "provenance_tags", "tags"):
        cleaned = val_str.strip().strip("[]").strip().upper()
        tag_map = {"M": "[M]", "D": "[D]", "E": "[E]"}
        if cleaned in tag_map:
            tag_counts[tag_map[cleaned]] += 1

def compute_state_tensor_provenance_hash(h5_path: Path) -> str:
    """
    Computes a cryptographic SHA-256 semantic provenance hash across all state tensors,
    groups, and dataset/group attributes in the given HDF5 file, auditing and recording
    [M], [D], and [E] provenance tags for all input variables, constants, and state tensors (§12.5).
    """
    if not h5_path.exists():
        return hashlib.sha256(b"empty_state_tensor_registry").hexdigest()
    
    sha = hashlib.sha256()
    tag_counts = {"[M]": 0, "[D]": 0, "[E]": 0}
    try:
        with h5py.File(h5_path, 'r') as f:
            items = []
            def visitor(name, obj) -> Any:
                if isinstance(obj, (h5py.Dataset, h5py.Group)):
                    items.append((name, obj))
            f.visititems(visitor)
            items.sort(key=lambda x: x[0])
            
            for name, obj in items:
                sha.update(name.encode('utf-8'))
                if isinstance(obj, h5py.Dataset):
                    sha.update(b"dataset")
                    sha.update(str(obj.shape).encode('utf-8'))
                    sha.update(str(obj.dtype).encode('utf-8'))
                    try:
                        data_bytes = obj[()].tobytes()
                    except Exception:
                        data_bytes = str(obj[()]).encode('utf-8')
                    sha.update(data_bytes)
                elif isinstance(obj, h5py.Group):
                    sha.update(b"group")

                for k in sorted(obj.attrs.keys()):
                    val = str(obj.attrs[k])
                    sha.update(f"{k}:{val}".encode('utf-8'))
                    count_tags_in_attr(k, val, tag_counts)

            for k in sorted(f.attrs.keys()):
                if k not in ("tensor_provenance_hash", "provenance_tag_audit"):
                    val = str(f.attrs[k])
                    sha.update(f"root_{k}:{val}".encode('utf-8'))
                    count_tags_in_attr(k, val, tag_counts)

            audit_summary = f"provenance_audit:[M]={tag_counts['[M]']};[D]={tag_counts['[D]']};[E]={tag_counts['[E]']}"
            sha.update(audit_summary.encode('utf-8'))
            logging.info(f"State tensor provenance audit for {h5_path}: {audit_summary}")

    except Exception as e:
        logging.error(f"Error computing tensor provenance hash for {h5_path}: {e}")
        sha.update(str(e).encode('utf-8'))

    digest = sha.hexdigest()
    try:
        with h5py.File(h5_path, 'a') as f:
            f.attrs['tensor_provenance_hash'] = digest
            f.attrs['provenance_tag_audit'] = json.dumps(tag_counts)
    except Exception as e:
        logging.error(f"Failed to write provenance to {h5_path}: {e}")
    return digest


artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
artifact_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(artifact_dir / 'cochem_scribe_master.log'), level=logging.INFO)

# Standard BibTeX blocks for known quantum chemistry software & methods
BIBTEX_DATABASE = {
    "MPQC_4": """@article{MPQC4_2020,
    author = {Peng, Chong and Calvin, Justin A. and Pavo\\v{s}evi\\'{c}, Fabijan and Zhang, Jinjian and Moore, Benjamin G. and Bae, Cannada A. and Valeev, Edward F.},
    title = {Massively Parallel Quantum Chemistry: A robust parallel implementation of electronic structure theory},
    journal = {The Journal of Physical Chemistry A},
    volume = {124},
    pages = {11823--11835},
    year = {2020},
    doi = {10.1021/acs.jpca.0c09506}
}""",
    "MACE_OFF24m": """@article{MACE_2023,
    author = {Batatia, Ilyes and Kovacs, David P and Simm, Gregor N C and Ortner, Christoph and Csanyi, Gabor},
    title = {MACE: Higher Order Equivariant Message Passing Neural Networks for Fast and Accurate Force Fields},
    journal = {Advances in Neural Information Processing Systems},
    volume = {35},
    pages = {11423--11436},
    year = {2022}
}""",
    "CCSD(T)-F12": """@article{Valeev_2004,
    author = {Valeev, Edward F.},
    title = {Improving on the resolution of the identity in linear R12 ab initio theories},
    journal = {Chemical Physics Letters},
    volume = {395},
    pages = {190--195},
    year = {2004},
    doi = {10.1016/j.cplett.2004.07.061}
}""",
    "r2SCAN-3c": """@article{Grimme_r2SCAN3c,
    author = {Grimme, Stefan and Hansen, Andreas and Ehlert, Sebastian and Mewes, Jan-Michael},
    title = {r2SCAN-3c: A composite quantum chemical method for structures and energies},
    journal = {The Journal of Chemical Physics},
    volume = {154},
    pages = {064103},
    year = {2021},
    doi = {10.1063/5.0040021}
}""",
    "def2-TZVP": """@article{Weigend_2005,
    author = {Weigend, Florian and Ahlrichs, Reinhart},
    title = {Balanced basis sets of split valence, triple zeta valence and quadruple zeta valence quality for H to Rn},
    journal = {Physical Chemistry Chemical Physics},
    volume = {7},
    pages = {3297--3305},
    year = {2005},
    doi = {10.1039/B508541A}
}"""
}

# Pre-written LaTeX methodology paragraphs with v4 Provenance Discipline tags [M], [D], [E] (§12.5)
METHOD_PARAGRAPHS = {
    "MPQC_4": "Electronic structure calculations were performed using the MPQC 4.0 quantum chemistry suite [M] \\cite{MPQC4_2020}.",
    "MACE_OFF24m": "Conformational sampling and potential energy surface exploration utilized the MACE-OFF24m equivariant neural network force field [M] \\cite{MACE_2023}, providing GPU-accelerated force evaluations with batch inference [D].",
    "CCSD(T)-F12": "Single-point correlation energies were calculated using explicitly correlated coupled-cluster with single, double, and perturbative triple excitations (CCSD(T)-F12) [M] \\cite{Valeev_2004}, dramatically accelerating basis set convergence [M] (cc-pVTZ-F12).",
    "r2SCAN-3c": "Geometry optimizations and harmonic vibrational frequency evaluations were conducted using the composite r2SCAN-3c functional [M] \\cite{Grimme_r2SCAN3c}, incorporating composite D4 dispersion and gCP basis set superposition corrections [D].",
    "def2-TZVP": "Calculations employed the def2-TZVP triple-zeta basis set [M] \\cite{Weigend_2005} with appropriate auxiliary fitting basis sets [D]."
}

class MethodologyTracker:
    def __init__(self, hdf5_path: str = "landscape.h5") -> None:
        self.hdf5_path = Path(hdf5_path)
        self.compute_flags = set()

    def harvest_compute_flags(self) -> list:
        """
        Reads compute_flags from HDF5 root attributes and inspects per-group
        execution metadata (method, engine, calculator attrs) to determine
        which computational methods were actually executed.

        Resolves MOCK-26: No hardcoded default method flags are injected.
        Resolves Suggestion 95: Emits warnings for unresolvable methods.
        """
        if self.compute_flags:
            return list(self.compute_flags)

        flags: set[str] = set()

        # 1. Read explicit compute_flags from HDF5 root attributes
        h5_candidates = [self.hdf5_path, Path("cochem_state.h5"), Path("landscape.h5")]
        for h5_p in h5_candidates:
            if h5_p.exists():
                try:
                    with h5py.File(h5_p, 'r') as f:
                        if "compute_flags" in f.attrs:
                            raw_flags = f.attrs["compute_flags"]
                            if isinstance(raw_flags, (list, tuple, np.ndarray)):
                                for flag in raw_flags:
                                    flags.add(str(flag))
                            elif isinstance(raw_flags, str):
                                flags.update(
                                    json.loads(raw_flags)
                                    if raw_flags.startswith("[")
                                    else [s.strip() for s in raw_flags.split(",") if s.strip()]
                                )
                except Exception as e:
                    logging.warning(f"Error reading compute_flags from {h5_p}: {e}")

        # 2. Inspect per-group execution metadata in HDF5
        if not flags:
            flags = self._inspect_hdf5_execution_metadata(h5_candidates)

        # 3. Parse MPQC .out headers for actually-used methods (not blind glob)
        if not flags:
            flags = self._parse_mpqc_output_headers()

        # MOCK-26 fix: Do NOT inject hardcoded default flags.
        # Instead, warn the user that no execution data was found.
        if not flags:
            logging.warning(
                "SCRIBE: No compute_flags found in HDF5 attributes, group metadata, "
                "or MPQC output files. methods.tex and references.bib will contain "
                "placeholder templates only. Run the computational pipeline first."
            )

        self.compute_flags = flags
        return list(flags)

    def _inspect_hdf5_execution_metadata(self, h5_candidates: list[Path]) -> set[str]:
        """
        Inspects per-group HDF5 attributes (method, engine, calculator, basis_set)
        to determine which methods were actually executed rather than assuming
        defaults from file existence.
        """
        flags: set[str] = set()
        # Map commonly found HDF5 attribute values to canonical flag names
        engine_map = {
            "mpqc": "MPQC_4",
            "mpqc4": "MPQC_4",
            "mace": "MACE_OFF24m",
            "mace-off24m": "MACE_OFF24m",
            "mace_off24m": "MACE_OFF24m",
            "aimnet2": "AIMNet2",
        }
        method_map = {
            "ccsd(t)-f12": "CCSD(T)-F12",
            "ccsdt-f12": "CCSD(T)-F12",
            "r2scan-3c": "r2SCAN-3c",
            "r2scan3c": "r2SCAN-3c",
            "b3lyp": "B3LYP",
            "pbe0": "PBE0",
            "wb97x-d": "wB97X-D",
            "wb97x-d3": "wB97X-D3",
        }
        basis_map = {
            "cc-pvtz-f12": "cc-pVTZ-F12",
            "def2-tzvp": "def2-TZVP",
            "def2-svp": "def2-SVP",
            "cc-pvtz": "cc-pVTZ",
            "cc-pvdz": "cc-pVDZ",
            "aug-cc-pvtz": "aug-cc-pVTZ",
        }

        for h5_p in h5_candidates:
            if not h5_p.exists():
                continue
            try:
                with h5py.File(h5_p, 'r') as f:
                    def _visit_group(name: str, obj: object) -> None:
                        if not isinstance(obj, h5py.Group):
                            return
                        for attr_key in ("engine", "calculator", "software"):
                            val = obj.attrs.get(attr_key, None)
                            if val is not None:
                                val_lower = str(val).strip().lower()
                                if val_lower in engine_map:
                                    flags.add(engine_map[val_lower])
                        for attr_key in ("method", "functional", "level_of_theory"):
                            val = obj.attrs.get(attr_key, None)
                            if val is not None:
                                val_lower = str(val).strip().lower()
                                if val_lower in method_map:
                                    flags.add(method_map[val_lower])
                        for attr_key in ("basis_set", "basis"):
                            val = obj.attrs.get(attr_key, None)
                            if val is not None:
                                val_lower = str(val).strip().lower()
                                if val_lower in basis_map:
                                    flags.add(basis_map[val_lower])
                    f.visititems(_visit_group)
            except Exception as e:
                logging.warning(f"Error inspecting HDF5 group metadata in {h5_p}: {e}")

        return flags

    def _parse_mpqc_output_headers(self) -> set[str]:
        """
        Parses actual MPQC .out file input headers to extract which DFT
        functionals, basis sets, and correlation methods were truly invoked.
        Only flags methods confirmed by parsed output content.
        """
        flags: set[str] = set()
        mpqc_files = list(Path(".").rglob("*.out"))

        for mpqc_file in mpqc_files:
            try:
                with open(mpqc_file, 'r', errors='ignore') as fh:
                    content = fh.read()

                # Confirm this is actually an MPQC output file
                if 'MPQC' not in content and 'Massively Parallel Quantum Chemistry' not in content:
                    continue

                flags.add("MPQC_4")

                # Parse file content for methods and basis sets
                tok_lower = content.lower()
                if 'ccsd(t)-f12' in tok_lower or 'ccsdt-f12' in tok_lower:
                    flags.add("CCSD(T)-F12")
                if 'r2scan-3c' in tok_lower or 'r2scan3c' in tok_lower:
                    flags.add("r2SCAN-3c")
                for m in ('b3lyp', 'pbe0', 'wb97x-d', 'wb97x-d3'):
                    if m in tok_lower:
                        flags.add(m.upper() if m != 'wb97x-d3' else 'wB97X-D3')
                
                if 'cc-pvtz-f12' in tok_lower:
                    flags.add("cc-pVTZ-F12")
                elif 'def2-tzvp' in tok_lower:
                    flags.add("def2-TZVP")
                elif 'def2-svp' in tok_lower:
                    flags.add("def2-SVP")

            except Exception as e:
                logging.warning(f"Error parsing MPQC output {mpqc_file}: {e}")

        # Check for MACE logs only if they contain MACE-specific output markers
        for log_file in Path(".").rglob("*.log"):
            try:
                with open(log_file, 'r', errors='ignore') as fh:
                    head = fh.read(8192)
                if 'MACE' in head and ('energy' in head.lower() or 'forces' in head.lower()):
                    flags.add("MACE_OFF24m")
                    break
            except Exception as e:
                logging.warning(f"Error parsing MACE log {log_file}: {e}")
        return flags

    def render_methods_tex(self, output_path: str = "methods.tex") -> str:
        """
        Renders methods.tex containing context-aware LaTeX methodology paragraphs
        mapped from active compute_flags.

        Resolves Suggestion 95: When no compute flags are discovered from actual
        execution logs, emits a warning template instead of fabricating citations
        for unexecuted methods.
        """
        flags = self.harvest_compute_flags()
        paragraphs = []
        for flag in sorted(flags):
            if flag in METHOD_PARAGRAPHS:
                paragraphs.append(METHOD_PARAGRAPHS[flag])
            else:
                logging.warning(
                    f"Compute flag '{flag}' has no pre-written methodology "
                    f"paragraph -- skipping in methods.tex."
                )

        tensor_hash = compute_state_tensor_provenance_hash(self.hdf5_path)

        latex_content = "% Auto-generated by CoChem-SCRIBE MethodologyTracker\n"
        latex_content += "% Semantic Provenance SHA-256 Hash: " + tensor_hash + "\n"
        latex_content += "\\usepackage{siunitx}\n\n"
        latex_content += "\\section{State Tensor Provenance Digest}\n"
        latex_content += f"\\texttt{{SHA-256: {tensor_hash}}}\n\n"
        latex_content += "\\section{Computational Methods}\n\n"

        if paragraphs:
            latex_content += "\n\n".join(paragraphs) + "\n"
        else:
            # Suggestion 95: Render unassigned methodology template instead
            # of fabricating citations for MPQC_4, MACE_OFF24m, etc.
            latex_content += (
                "% WARNING: No computational methods were detected from HDF5 execution logs.\n"
                "% Run the CoChem compute pipeline before generating the manuscript.\n"
                "% Placeholder template -- fill in after pipeline execution.\n\n"
                "\\textit{[Methodology section pending: no execution provenance found. "
                "Run the computational pipeline and re-invoke SCRIBE to auto-populate "
                "this section from HDF5 execution metadata.]}\n"
            )
            logging.warning(
                "methods.tex: No compute flags resolved from execution data. "
                "Rendered placeholder template instead of fabricating default citations."
            )

        out_p = Path(output_path)
        out_p.write_text(latex_content, encoding='utf-8')

        # Also sync to Methodology.tex
        Path("Methodology.tex").write_text(latex_content, encoding='utf-8')

        logging.info(f"Rendered methods.tex ({len(paragraphs)} paragraphs) for flags {flags}")
        return latex_content

    def render_references_bib(self, output_path: str = "references.bib") -> str:
        """
        Renders references.bib containing BibTeX blocks for active compute_flags.

        Resolves Suggestion 95: Only emits BibTeX entries for methods confirmed
        by HDF5 execution logs. Does not fabricate citations for unexecuted methods.
        """
        flags = self.harvest_compute_flags()
        bib_entries = []
        for flag in sorted(flags):
            if flag in BIBTEX_DATABASE:
                bib_entries.append(BIBTEX_DATABASE[flag])

        bib_content = "% Auto-generated by CoChem-SCRIBE MethodologyTracker\n\n"
        if bib_entries:
            bib_content += "\n\n".join(bib_entries) + "\n"
        else:
            bib_content += (
                "% WARNING: No computational methods detected from HDF5 execution logs.\n"
                "% No BibTeX entries emitted. Run the CoChem compute pipeline first,\n"
                "% then re-invoke SCRIBE to populate references from execution metadata.\n"
            )
            logging.warning(
                "references.bib: No compute flags resolved from execution data. "
                "No BibTeX entries emitted -- avoiding fabricated citations."
            )

        out_p = Path(output_path)
        out_p.write_text(bib_content, encoding='utf-8')

        # Also sync to manuscript.bib
        Path("manuscript.bib").write_text(bib_content, encoding='utf-8')

        logging.info(f"Rendered references.bib ({len(bib_entries)} entries) for flags {flags}")
        return bib_content

def render_methodology(hdf5_path: str = "landscape.h5") -> tuple:
    tracker = MethodologyTracker(hdf5_path)
    m_tex = tracker.render_methods_tex("methods.tex")
    r_bib = tracker.render_references_bib("references.bib")
    return m_tex, r_bib

if __name__ == "__main__":
    h5_path = sys.argv[1] if len(sys.argv) > 1 else "landscape.h5"
    tracker = MethodologyTracker(h5_path)
    m_tex = tracker.render_methods_tex()
    r_bib = tracker.render_references_bib()
    logger.info(f"=== methods.tex ===\n{m_tex}")
    logger.info(f"=== references.bib ===\n{r_bib}")
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