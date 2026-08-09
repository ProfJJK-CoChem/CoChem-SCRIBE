# CoChem-SCRIBE

**CoChem-SCRIBE** is the Asynchronous Data Provenance and Publication Daemon of the CoChem suite.

Running silently in the background alongside the other 4 modules, SCRIBE is responsible for:
- **Memory-Aware Serialization:** SCRIBE monitors the massive memory footprint of `cochem_state.h5`. When large DVR tensors or partition functions are generated, SCRIBE chunks and compresses the payload to disk using Zstandard (`.tar.zst`) in 500MB batches, safely archiving the data without crashing the Jupyter kernel.
- **Artifact Visualization:** Generates publication-ready artifacts, including HTML 3D carousels, `.cube` files of NCI domains, Sinc-DVR probability wavefunctions mapped onto classical potentials, and high-resolution `.svg` Voigt spectral convolutions.
- **Manuscript Scaffolding:** Translates the execution logs into an APS-compliant `Methodology.tex` document, dynamically querying the CrossRef API for citations (e.g., Grimme's D4, Sinc-DVR). It utilizes Jinja2 templating to gracefully format the manuscript even if certain modules were bypassed.
- **LAM Protocol Justification:** If LAM_TRIGGER_REQUIRED flag was activated during execution, SCRIBE automatically injects a standardized paragraph into the LaTeX file justifying the use of Sinc-DVR over the rigid-rotor harmonic oscillator approximation.

## Usage
Please refer to the authoritative [CoChem Master User Manual](../CoChem-BASE/CoChem_Master_User_Manual.md) for full execution instructions across the entire 5-module pipeline.