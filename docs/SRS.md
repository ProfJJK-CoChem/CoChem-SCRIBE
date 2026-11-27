---
schema: cochem-srs/5.0
repo: CoChem-SCRIBE
status: ACTIVE_CORE (v0.2.0 verified renderers active; full publication catalog redesign staged for Gemini Web)
pipeline_baseline: 5.0.0
source_commit: 137451d1543521bc3602ca8cdfda28b3f8036bcb
decision_ref: swarm-1126-8efd
---

# Software Requirements Specification: CoChem-SCRIBE (Pipeline 5.0.0)

## 1. Purpose, Scope & System Classification

`CoChem-SCRIBE` (`ProfJJK-CoChem/CoChem-SCRIBE`, Python distribution `cochem-scribe` v0.2.0) is classified as an **`ACTIVE_CORE`** (`wave1_core_9`) repository in the CoChem Pipeline 5.0.0 ecosystem. It delivers deterministic, zero-fabrication scientific figure rendering, cryptographic SHA-256 source-register verification, far-IR exclusion auditing, and FAIR reporting primitives.

The shipped, installable package lives exclusively under `src/cochem_scribe/` (`pyproject.toml` `where = ["src"]`, `include = ["cochem_scribe*"]`) with console entrypoint `cochem-scribe = "cochem_scribe.cli:main"` exposing 5 subcommands (`render-geom`, `render-kinetic`, `verify-register`, `audit-farir`, `provider-info`). Primary active modules are `src/cochem_scribe/renderers.py`, `src/cochem_scribe/register.py`, `src/cochem_scribe/provider.py`, and `src/cochem_scribe/cli.py`. Eleven legacy root modules (`scribe_*.py`, `cochem_scribe_*.py`) remain unshipped in the repository root pending the staged Gemini Web publication redesign.

## 2. Pipeline 5.0.0 Architecture Alignment & Resolved Conflicts

`CoChem-SCRIBE` aligns with signed Portal decision `swarm-1126-8efd` and enforces strict separation between verified deterministic rendering and staged redesign scope:
- **`CONTRA-01` (Compute Topology & `HC-1`):** All figure rendering and register verification runs locally or in stateless CI without scheduled GitHub Actions crons (`.github/workflows/zero_mock_ci.yml` only). Hardcoded legacy Windows drive paths were removed in commit `137451d1`.
- **`CONTRA-04` (Deterministic Publication & `CoChem-ORACLE` Redesign Pairing):** Together with `CoChem-ORACLE` (`REDESIGN_STAGED_WEB`), `CoChem-SCRIBE`'s full multi-pathway publication figure/table catalog is intentionally staged in Google Drive (`CoChem_Pipeline/lanes/gemini_web/oracle_scribe_redesign_staging_20261126`). No LLM text fabrication of scientific numbers is permitted; every plotted datum MUST trace to a SHA-256-verified computational artifact.
- **`CONTRA-06` (Unified Contracts):** Future publication packages align with `cochem-quantities/1` (`OWN-117`), `cochem-job-handoff/1`, and the staged `cochem-publication-package/1` byte-span provenance contract consumed by the redesigned zero-LLM `CoChem-ORACLE` Student Audit Portal.

## 3. Authoritative Scientific Engines, Methods & Method Matrix Constraints

`CoChem-SCRIBE` performs zero quantum-chemical calculation; it is strictly a deterministic downstream verification and visualization consumer:
- **Verified Matplotlib Renderers (`src/cochem_scribe/renderers.py`):** Renders `CoChem-GEOM` rotational/structural comparison plots (`render-geom`) and `CoChem-KINETIC` 5-point CHEM 312 reaction profiles (`render-kinetic`) directly from verified JSON/CSV computational receipts with zero fabricated or interpolated synthetic series.
- **Cryptographic Figure Source Register (`src/cochem_scribe/register.py`):** Maintains and audits the 19-entry SHA-256 source-file provenance register (`verify-register`) and enforces the far-IR exclusion gate (`audit-farir`) so unverified or excluded spectral regions cannot enter publication figures.
- **Formatting & NLP Helpers (`src/cochem_scribe/formatting/latex_math.py`, `src/cochem_scribe/nlp/table_generation.py`, `src/cochem_scribe/nlp/citation_manager.py`):** Shipped deterministic formatting utilities awaiting integration into the staged publication catalog.

## 4. Cross-Repo Interfaces, Contracts & Canonical Schemas

- **CoChem-BASE Module Provider:** `pyproject.toml` registers `[project.entry-points."cochem.modules"]` `scribe = "cochem_scribe.provider:scribe_provider"` (`src/cochem_scribe/provider.py`), exposing `render_geom_comparison` and `render_kinetic_rxn_profile` operations.
- **Upstream Artifact Inputs:** Consumes verified output bundles from `CoChem-GEOM` and `CoChem-KINETIC`.
- **Canonical Pipeline 5.0.0 Schemas:** Targets `cochem-job-handoff/1`, `cochem-quantities/1` (`OWN-117`), and `cochem-portal-dossier/1.1` DRAFT schemas in `CoChem-BASE`, plus the staged 19-column `energy_results.csv` and `cochem-publication-package/1` contract for `CoChem-ORACLE` student verification.

## 5. Verification, Zero-Mock CI Gates & Acceptance Criteria

- **Zero-Mock CI Gate:** `tests/test_zero_mock_and_no_sim_gate.py` and `tests/test_anti_spoofing.py` enforce AST zero-mock compliance across `.py` and `.ipynb` files (`.anti_spoof_amnesty.json` strictly `[]`), passing `zero_mock_gate` on PR #3 via `.github/workflows/zero_mock_ci.yml`.
- **Renderer & Audit Test Suite:** `tests/test_scribe_verified_renderers.py`, `tests/test_scribe.py`, `tests/test_audit_075.py`, and `tests/test_audit_075_script.py` verify deterministic matplotlib outputs, register SHA-256 verification, and anti-spoofing invariants.
- **Branch Protection:** `main` is branch-protected requiring authentic `blind-s3-p10` parity before PR #3 merges.

## 6. Verified Implementation Gaps, Known Holds & Non-Goals

The following verified gaps from the 2026-11-26 Opus-verified audit remain open and explicitly bounded:
1. **Staged Gemini Web Publication Redesign (Intentional Hold):** Full cross-pathway publication figures/tables across `TOPOS`, `TORQ`, `SPYFY`, `BENCH`, and `KINETIC` (siunitx tables, DVR contours, Boltzmann population bars, CrossRef BibTeX, conditional `Methodology.tex`, and `pubstyle.py` unification from `CoChem-Tools`) are intentionally staged for the Gemini Web redesign (`oracle_scribe_redesign_staging_20261126`) and are NOT shipped in `src/cochem_scribe/` v0.2.0.
2. **Unshipped Legacy Root Modules (11 Files, 138 KB):** Root scripts (`scribe_doc_manager.py`, `scribe_payload_builder.py`, `cochem_scribe_compiler.py`, `scribe_figure_generator.py`, `scribe_inference.py`, `scribe_legacy_bundler.py`, `cochem_scribe_master.py`, `cochem_scribe_archive.py`, `scribe_orchestration.py`, `cochem_scribe_web.py`) are excluded from the wheel (`where = ["src"]`) and contain stale `cochem_base.config_loader` imports; they must be formally archived or replaced during redesign execution.
3. **Zenodo Archival API Absent:** Direct Zenodo deposit automation is unimplemented across `src/cochem_scribe/`.
4. **Unwired Internal Helpers:** 14 formatting/NLP/interface helper modules inside `src/cochem_scribe/{formatting,nlp,interfaces}/` are not yet wired into `src/cochem_scribe/cli.py` or `src/cochem_scribe/provider.py`.
5. **Non-Goals:** `CoChem-SCRIBE` never runs electronic-structure engines or fabricates numerical claims via generative LLMs.

## 7. Legacy Specification Disposition (Non-Normative Archive)

Prior to `swarm-1126-8efd`, `CoChem-SCRIBE` lacked a formal SRS. The following pre-v5 documents are non-normative archives superseded by `docs/SRS.md`:
- `.old_plan_docs/20260807_scribe_architectural_changes.md` and `.old_plan_docs/20260807_scribe_workflow.md` (retired asyncio Zstd daemon / LLM Results & Discussion draft plan).
- Root `Results_and_Discussion.md` and `CoChem_User_Guide.md` (historical snapshots).
- `docs/USER_GUIDE.md` remains the operational v0.2.0 guide subordinate to this normative `docs/SRS.md`.
