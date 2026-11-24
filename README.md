# CoChem-SCRIBE: Verified-Output Scientific Figures & Cryptographic FAIR Reporting

**Author/PI:** Dr. Joshua John Klaassen  
**Institution:** Tennessee Tech University  
**ORCiD:** [https://orcid.org/0009-0007-1506-4401](https://orcid.org/0009-0007-1506-4401)  
**GitHub Organization:** [https://github.com/ProfJJK-CoChem](https://github.com/ProfJJK-CoChem)  
**License:** Apache License 2.0 ([LICENSE](LICENSE))

---

## 1. Module Overview

`CoChem-SCRIBE` is the verified-output scientific figure rendering, cryptographic provenance manifest, and FAIR reporting module of the CoChem ecosystem.

Every figure emitted by `CoChem-SCRIBE` is built strictly from verified upstream numerical outputs with SHA-256 provenance footers and manifests:

- **Zero Fabrication:** Unverified, unconverged, or unavailable quantities (such as semi-experimental equilibrium structures $r_e^{\mathrm{SE}}$ without isotope-specific anharmonic vibrational corrections $\Delta B_{\mathrm{vib}}$, or unconverged stationary points) are never synthesized or silently plotted as zero—they are either explicitly labeled `PENDING` or rejected in strict mode.
- **No Synthetic Axes or Hardcoded Intensities:** Legacy synthetic `np.linspace(0, 10, ...)` axes and flat hardcoded `1.0`/`0.8` IR bar heights have been removed.
- **Strict Scope & Asset Hygiene:** Private manuscript generator scripts and archival PDFs stay in their Instructor Google Drive collections and are never copied into this public repository. `manifests/in_scope_figure_register.json` records the SHA-256 register for all 19 in-scope figures (4 FTMW methodology manuscript figures + 15 Keratin v1.1.0 figures) and enforces an exclusion gate against out-of-scope encyclopedia material.

---

## 2. Installation

CPU-only core installation (Windows and WSL2 Linux):

```bash
pip install --no-build-isolation -e .
```

Optional extras for Zstandard archiving and legacy HDF5/Plotly/Jinja2 tooling:

```bash
pip install --no-build-isolation -e ".[legacy,dev]"
```

---

## 3. Verified-Output Renderers & CLI

### 3.1 `CoChem-GEOM` Structural Comparison Renderer (`render_geom_comparison`)

Ingests `CoChem-GEOM`'s `cochem.geom.structural-comparison/1` JSON output (e.g., verified $\mathrm{H_2O}$ `h2o_t_geom_01_comparison.json`) and plots separated:

- $r_e$ (ORCA CCSD/cc-pVTZ)
- $r_e$ (PySCF CCSD/cc-pVDZ)
- $r_s$ (Kraitchman $\pm \sigma_{\mathrm{Costain}}$)
- $r_0$ (weighted fit $\pm \sigma_{\mathrm{scaled}}$)
- $r_e^{\mathrm{SE}}$ explicitly annotated as `PENDING` (never equated to $r_0$ or $r_e$)

```bash
cochem-scribe render-geom \
  --input path/to/h2o_t_geom_01_comparison.json \
  --out-png benchmarks/verified_figures/h2o_geom_comparison.png \
  --out-pdf benchmarks/verified_figures/h2o_geom_comparison.pdf \
  --manifest benchmarks/verified_figures/manifest_sha256.json
```

### 3.2 `CoChem-KINETIC` Reaction-Coordinate Profile Renderer (`render_kinetic_rxn_profile`)

Strictly ingests a verified 5-point `stationary_table.csv` (`R`, `TS1`, `Int_tet`, `TS2`, `P`) with electronic energies, ZPE, $\Delta H$, $\Delta G(T)$, convergence status, `n_imag`, and SHA-256 provenance. In strict mode (default), any missing, unconverged, `PENDING`, or Hessian-mismatched stationary point raises `ValueError`; in `--allow-pending` mode, unverified states are rendered as explicit `PENDING` slots with zero numeric bars.

```bash
cochem-scribe render-kinetic \
  --input path/to/stationary_table.csv \
  --out-png rxn_profile.png \
  --out-pdf rxn_profile.pdf
```

### 3.3 19-Entry Drive Source Register & Scope Audit (`verify_source_register`)

Validates the 19 in-scope figure entries (4 FTMW methodology manuscript + 15 Keratin v1.1.0), checks 64-hex SHA-256 format (and live Drive file/archive hashes when `--verify-on-disk` is passed), and enforces the hard encyclopedia exclusion gate:

```bash
cochem-scribe verify-register
```

---

## 4. `CoChem-BASE` Module Provider (`cochem.modules`)

`CoChem-SCRIBE` exposes the `cochem.module-provider/1` entry point registered under `cochem.modules`:

```toml
[project.entry-points."cochem.modules"]
scribe = "cochem_scribe.provider:scribe_provider"
```

Supported operations:
- `render_geom_comparison`
- `render_kinetic_rxn_profile`
- `verify_source_register`
- `audit_farir_exclusion`

---

## 5. Documentation & User Guide

- **[User Guide (`docs/USER_GUIDE.md`)](docs/USER_GUIDE.md)** — Worked CLI and Python examples for `render_geom_comparison`, `render_kinetic_rxn_profile`, `verify_source_register`, `audit_farir_exclusion`, `CoChem-BASE` provider handoffs, and `CoChem-SPYFY` legacy Pickett verification bundling.

---

## 6. Citation Policy

If this module is utilized in the generation of published figures or tables, please cite:
- *Klaassen, J. J. et al. "CoChem: Reproducible Ab Initio and Spectroscopic Workflows." Tennessee Tech University (2026).*

---

## 7. License

Licensed under the **Apache License, Version 2.0** (the "License"). You may not use this repository except in compliance with the License. See [LICENSE](LICENSE) for the full text.
