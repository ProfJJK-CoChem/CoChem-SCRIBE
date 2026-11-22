"""CoChem-SCRIBE: verified-output scientific figure renderers and provenance manifests."""

from __future__ import annotations

from .provider import VERSION, scribe_provider
from .register import (
    FarIRExclusionError,
    audit_farir_exclusion,
    build_in_scope_register_manifest,
    verify_source_register,
)
from .renderers import render_geom_comparison, render_kinetic_rxn_profile, sha256_file

__version__ = VERSION

__all__ = [
    "FarIRExclusionError",
    "__version__",
    "audit_farir_exclusion",
    "build_in_scope_register_manifest",
    "render_geom_comparison",
    "render_kinetic_rxn_profile",
    "scribe_provider",
    "sha256_file",
    "verify_source_register",
]
