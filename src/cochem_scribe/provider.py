"""CoChem-BASE `cochem.modules` entry point provider (`scribe_provider`).

Conforms to `cochem.module-provider/1` and exposes side-effect-free discovery,
versioned operation metadata, and execution dispatch for CoChem-SCRIBE's
verified-output renderers, 19-entry Drive figure register verifier, and
out-of-scope encyclopedia exclusion gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .register import audit_farir_exclusion, verify_source_register
from .renderers import (
    render_basis_convergence,
    render_geom_comparison,
    render_kinetic_rxn_profile,
    sha256_file,
)

INTEGRATION_CONTRACT = "cochem.module-handoff/1"
SCIENTIFIC_API_VERSION = "cochem.module-provider/1"
VERSION = "0.2.0"

OPERATIONS: tuple[str, ...] = (
    "render_geom_comparison",
    "render_kinetic_rxn_profile",
    "render_basis_convergence",
    "verify_source_register",
    "audit_farir_exclusion",
)


def metadata() -> dict[str, Any]:
    """Return side-effect-free `cochem.module-provider/1` capability metadata."""
    return {
        "module_id": "scribe",
        "distribution": "CoChem-SCRIBE",
        "package_name": "cochem-scribe",
        "version": VERSION,
        "integration_contract": INTEGRATION_CONTRACT,
        "scientific_api_version": SCIENTIFIC_API_VERSION,
        "operations": list(OPERATIONS),
        "execute_handoff": "cochem_scribe.provider:execute_handoff",
        "scientific_apis": {
            "render_geom_comparison": {
                "available": True,
                "required_engines": [],
                "supported_engines": ["matplotlib"],
                "scope": (
                    "Render verified CoChem-GEOM structural comparisons "
                    "(r_e CCSD or non-CCSD DFT/revDSD, r_s Kraitchman, r_0 weighted fit, "
                    "explicit PENDING annotations) with SHA-256 provenance."
                ),
            },
            "render_kinetic_rxn_profile": {
                "available": True,
                "required_engines": [],
                "supported_engines": ["matplotlib"],
                "scope": (
                    "Render verified 3-point (R, TS, P) or 5-point (R, TS1, Int_tet, TS2, P) "
                    "reaction-coordinate free-energy profiles strictly rejecting or marking "
                    "PENDING unverified rows."
                ),
            },
            "render_basis_convergence": {
                "available": True,
                "required_engines": [],
                "supported_engines": ["matplotlib"],
                "scope": (
                    "Render publication-grade 300-DPI PNG + vector PDF + SHA-256 manifest "
                    "basis-set and method energy convergence figures from verified JSON or CSV."
                ),
            },
            "verify_source_register": {
                "available": True,
                "required_engines": [],
                "supported_engines": ["python"],
                "scope": (
                    "Verify the 19-entry in-scope Drive figure register (4 FTMW + 15 Keratin v1.1.0) "
                    "and enforce encyclopedia exclusion."
                ),
            },
            "audit_farir_exclusion": {
                "available": True,
                "required_engines": [],
                "supported_engines": ["python"],
                "scope": (
                    "Audit files, directories, or structured records for out-of-scope "
                    "encyclopedia material."
                ),
            },
        },
    }


def dispatch_operation(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one of the declared canonical CoChem-SCRIBE operations."""
    if operation not in OPERATIONS:
        raise ValueError(
            f"Unsupported CoChem-SCRIBE operation {operation!r}; valid: {OPERATIONS}"
        )

    if operation == "render_geom_comparison":
        return render_geom_comparison(
            comparison_json_path=payload["comparison_json_path"],
            out_png=payload["out_png"],
            out_pdf=payload["out_pdf"],
            manifest_path=payload.get("manifest_path"),
        )

    if operation == "render_kinetic_rxn_profile":
        return render_kinetic_rxn_profile(
            stationary_csv_path=payload["stationary_csv_path"],
            out_png=payload["out_png"],
            out_pdf=payload["out_pdf"],
            energy_column=str(payload.get("energy_column", "delta_g_qrrho_kcal")),
            strict=bool(payload.get("strict", True)),
            title=payload.get("title"),
            manifest_path=payload.get("manifest_path"),
            pathway_mode=str(payload.get("pathway_mode", "auto")),
        )

    if operation == "render_basis_convergence":
        return render_basis_convergence(
            input_path=payload["input_path"],
            output_dir=payload["output_dir"],
            prefix=str(payload.get("prefix", "convergence")),
            title=payload.get("title"),
            manifest_path=payload.get("manifest_path"),
            units=str(payload.get("units", "kcal/mol")),
            strict=bool(payload.get("strict", False)),
        )

    if operation == "verify_source_register":
        return verify_source_register(
            register_csv_path=payload.get("register_csv_path"),
            verify_on_disk=bool(payload.get("verify_on_disk", False)),
        )

    if operation == "audit_farir_exclusion":
        return audit_farir_exclusion(
            target=payload["target"],
            raise_on_violation=bool(payload.get("raise_on_violation", True)),
        )

    raise ValueError(f"Unhandled CoChem-SCRIBE operation {operation!r}")


def execute_handoff(
    *,
    handoff_path: str | Path,
    output_directory: str | Path,
    registry: str | Path | None = None,
) -> dict[str, Any]:
    """Execute a `cochem.module-handoff/1` manifest and return a `cochem.module-operation/1` receipt."""
    hpath = Path(handoff_path)
    out_dir = Path(output_directory)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(hpath.read_text(encoding="utf-8"))
    operation = str(manifest.get("operation", "")).strip()
    options = dict(manifest.get("options", {}))

    if operation == "render_geom_comparison":
        options.setdefault("out_png", str(out_dir / "geom_comparison.png"))
        options.setdefault("out_pdf", str(out_dir / "geom_comparison.pdf"))
        options.setdefault("manifest_path", str(out_dir / "manifest_sha256.json"))
    elif operation == "render_kinetic_rxn_profile":
        options.setdefault("out_png", str(out_dir / "kinetic_rxn_profile.png"))
        options.setdefault("out_pdf", str(out_dir / "kinetic_rxn_profile.pdf"))
        options.setdefault("manifest_path", str(out_dir / "manifest_sha256.json"))
    elif operation == "render_basis_convergence":
        options.setdefault("output_dir", str(out_dir))
        options.setdefault("prefix", "basis_convergence")

    result = dispatch_operation(operation, options)
    provider_file = Path(__file__).resolve()
    return {
        "schema_version": "cochem.module-operation/1",
        "module_id": "scribe",
        "operation": operation,
        "status": "completed",
        "input_sha256": sha256_file(hpath),
        "provider_file": str(provider_file),
        "provider_sha256": sha256_file(provider_file),
        "registry": str(registry) if registry is not None else None,
        "result": result,
    }


class ScribeProvider:
    """CoChem-BASE `cochem.modules` callable provider object for CoChem-SCRIBE."""

    module_id = "scribe"
    distribution = "CoChem-SCRIBE"
    scientific_api_version = SCIENTIFIC_API_VERSION
    integration_contract = INTEGRATION_CONTRACT
    operations = OPERATIONS
    metadata = staticmethod(metadata)
    dispatch_operation = staticmethod(dispatch_operation)
    execute_handoff = staticmethod(execute_handoff)

    def __call__(self) -> dict[str, Any]:
        return metadata()


scribe_provider = ScribeProvider()
