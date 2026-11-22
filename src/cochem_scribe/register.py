"""19-Entry Drive Figure Source Register Verifier & Far-IR Exclusion Gate.

Preserves exact metadata and SHA-256 checksums for the 19 in-scope figures
(4 FTMW methodology manuscript + 15 Keratin v1.1.0) pointing to their
Instructor Google Drive source collections without copying private manuscript
assets into git. Enforces a hard exclusion gate against out-of-scope
encyclopedia Far-IR material.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

# Hard Far-IR Encyclopedia Exclusion Gate patterns (case-insensitive)
FORBIDDEN_FARIR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("farir_v16", re.compile(r"far[\s_-]*ir[\s_-]*v\d+|farir_v16", re.IGNORECASE)),
    ("mrw_permission", re.compile(r"mrw[\s_-]*permission", re.IGNORECASE)),
    ("spct_code", re.compile(r"\bspct\b|spct[_-]", re.IGNORECASE)),
    ("elsevier_farir", re.compile(r"elsevier", re.IGNORECASE)),
    ("far_ir_encyclopedia", re.compile(r"(?<!audit-)\bfar[\s_-]*ir\b", re.IGNORECASE)),
)

EXPECTED_COLLECTIONS: dict[str, int] = {
    "FTMW methodology manuscript": 4,
    "Keratin v1.1.0": 15,
}
EXPECTED_TOTAL_FIGURES = 19


class FarIRExclusionError(ValueError):
    """Raised when out-of-scope Far-IR encyclopedia content is detected."""


class FigureRegisterEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    figure: str
    evidence_class: str
    source_script_or_archive_member: str
    script_sha256: str
    archived_reference_image: str
    reference_sha256: str
    instructor_drive_source: str
    required_work_before_reproduction_or_release: str


def default_manifest_path() -> Path:
    """Return the repository-tracked 19-entry in-scope figure register manifest."""
    return Path(__file__).resolve().parents[2] / "manifests" / "in_scope_figure_register.json"


def audit_farir_exclusion(
    target: str | Path | dict[str, Any] | list[Any],
    *,
    raise_on_violation: bool = True,
) -> dict[str, Any]:
    """Audit text, structured records, or a file/directory for Far-IR encyclopedia leaks.

    Rejects any match for FarIR_v16, MRW_Permission, SPCT, Elsevier, or Far-IR
    encyclopedia entries.
    """
    violations: list[dict[str, str]] = []

    def _scan_text(label: str, text: str) -> None:
        for rule_id, pattern in FORBIDDEN_FARIR_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                violations.append(
                    {
                        "location": label,
                        "rule": rule_id,
                        "matched": match.group(0),
                    }
                )

    def _scan_obj(prefix: str, obj: Any) -> None:
        if isinstance(obj, str):
            _scan_text(prefix, obj)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _scan_obj(f"{prefix}.{k}" if prefix else str(k), k)
                _scan_obj(f"{prefix}.{k}" if prefix else str(k), v)
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                _scan_obj(f"{prefix}[{i}]", item)

    if isinstance(target, Path) or (isinstance(target, str) and Path(target).exists()):
        path = Path(target)
        if path.is_file():
            _scan_text(str(path), path.name)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                content = ""
            _scan_text(str(path), content)
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if ".git" in child.parts or "__pycache__" in child.parts:
                    continue
                _scan_text(str(child), child.name)
                if child.is_file() and child.suffix.lower() in {
                    ".py",
                    ".md",
                    ".json",
                    ".csv",
                    ".tex",
                    ".bib",
                    ".txt",
                    ".toml",
                    ".yml",
                    ".yaml",
                }:
                    _scan_text(str(child), child.read_text(encoding="utf-8", errors="ignore"))
    else:
        _scan_obj("payload", target)

    report = {
        "schema_version": "cochem.scribe.farir-exclusion-audit/1",
        "passed": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
    }
    if violations and raise_on_violation:
        summary = "; ".join(f"{v['location']} ({v['rule']}: {v['matched']!r})" for v in violations[:5])
        raise FarIRExclusionError(
            f"Far-IR encyclopedia exclusion gate triggered ({len(violations)} violation(s)): {summary}"
        )
    return report


def _sha256_source_spec(spec: str) -> str:
    """Hash either a plain file path or a `zip_path!/member_path` archive member."""
    if "!/" in spec:
        zip_path_str, member = spec.split("!/", 1)
        zip_path = Path(zip_path_str)
        if not zip_path.is_file():
            raise FileNotFoundError(f"Archive not found on disk: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            return hashlib.sha256(zf.read(member)).hexdigest()
    path = Path(spec)
    if not path.is_file():
        raise FileNotFoundError(f"Source file not found on disk: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_entries_from_csv(csv_path: Path) -> list[FigureRegisterEntry]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    entries: list[FigureRegisterEntry] = []
    for row in rows:
        entries.append(
            FigureRegisterEntry(
                collection=row["Collection"].strip(),
                figure=row["Figure"].strip(),
                evidence_class=row["Evidence class"].strip(),
                source_script_or_archive_member=row["Source script or archive member"].strip(),
                script_sha256=row["Script SHA-256"].strip().lower(),
                archived_reference_image=row["Archived reference image"].strip(),
                reference_sha256=row["Reference SHA-256"].strip().lower(),
                instructor_drive_source=row["Instructor Drive source"].strip(),
                required_work_before_reproduction_or_release=row[
                    "Required work before reproduction or release"
                ].strip(),
            )
        )
    return entries


def _load_entries_from_json(json_path: Path) -> list[FigureRegisterEntry]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if "entries" not in data or not isinstance(data["entries"], list):
        raise ValueError(f"Register JSON missing 'entries' list: {json_path}")
    return [FigureRegisterEntry.model_validate(item) for item in data["entries"]]


def verify_source_register(
    register_csv_path: str | Path | None = None,
    *,
    verify_on_disk: bool = False,
) -> dict[str, Any]:
    """Verify the 19-entry in-scope figure source register and enforce Far-IR exclusion.

    Accepts either a CSV register or the packaged JSON manifest (defaults to
    `manifests/in_scope_figure_register.json`).
    """
    path = Path(register_csv_path) if register_csv_path is not None else default_manifest_path()
    if not path.is_file():
        raise FileNotFoundError(f"Figure source register not found: {path}")

    if path.suffix.lower() == ".csv":
        entries = _load_entries_from_csv(path)
    elif path.suffix.lower() == ".json":
        entries = _load_entries_from_json(path)
    else:
        raise ValueError(f"Unsupported register file format {path.suffix!r}; expected .csv or .json")

    # 1. Hard Far-IR Encyclopedia Exclusion Gate across every row & field
    audit_farir_exclusion([e.model_dump(mode="json") for e in entries], raise_on_violation=True)

    # 2. Validate SHA-256 format, uniqueness, and Drive URL pointers
    seen_keys: set[tuple[str, str]] = set()
    collection_counts: dict[str, int] = {}
    disk_verified_count = 0

    for entry in entries:
        key = (entry.collection, entry.figure)
        if key in seen_keys:
            raise ValueError(f"Duplicate figure entry in register: {key!r}")
        seen_keys.add(key)

        if not SHA256_HEX_RE.match(entry.script_sha256):
            raise ValueError(f"Invalid Script SHA-256 for {entry.figure!r}: {entry.script_sha256!r}")
        if not SHA256_HEX_RE.match(entry.reference_sha256):
            raise ValueError(
                f"Invalid Reference SHA-256 for {entry.figure!r}: {entry.reference_sha256!r}"
            )
        if not entry.instructor_drive_source.startswith("https://drive.google.com/"):
            raise ValueError(
                f"Expected Instructor Drive collection URL for {entry.figure!r}, "
                f"got {entry.instructor_drive_source!r}"
            )

        collection_counts[entry.collection] = collection_counts.get(entry.collection, 0) + 1

        if verify_on_disk:
            actual_script_sha = _sha256_source_spec(entry.source_script_or_archive_member)
            if actual_script_sha != entry.script_sha256:
                raise ValueError(
                    f"Script SHA-256 mismatch on disk for {entry.figure!r}: "
                    f"expected {entry.script_sha256}, observed {actual_script_sha}"
                )
            actual_ref_sha = _sha256_source_spec(entry.archived_reference_image)
            if actual_ref_sha != entry.reference_sha256:
                raise ValueError(
                    f"Reference image SHA-256 mismatch on disk for {entry.figure!r}: "
                    f"expected {entry.reference_sha256}, observed {actual_ref_sha}"
                )
            disk_verified_count += 1

    if len(entries) != EXPECTED_TOTAL_FIGURES:
        raise ValueError(
            f"Expected {EXPECTED_TOTAL_FIGURES} in-scope figures, found {len(entries)}."
        )
    if collection_counts != EXPECTED_COLLECTIONS:
        raise ValueError(
            f"Collection breakdown mismatch: expected {EXPECTED_COLLECTIONS}, got {collection_counts}."
        )

    register_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "schema_version": "cochem.scribe.register-verification/1",
        "register_path": str(path),
        "register_sha256": register_sha256,
        "passed": True,
        "total_figures": len(entries),
        "collection_counts": collection_counts,
        "farir_exclusion_passed": True,
        "verify_on_disk": verify_on_disk,
        "disk_verified_figures": disk_verified_count if verify_on_disk else 0,
        "figures": [e.figure for e in entries],
    }


def build_in_scope_register_manifest(
    register_csv_path: str | Path,
    out_json_path: str | Path,
    *,
    verify_on_disk: bool = False,
) -> dict[str, Any]:
    """Generate `manifests/in_scope_figure_register.json` from the verified CSV register."""
    csv_path = Path(register_csv_path)
    verification = verify_source_register(csv_path, verify_on_disk=verify_on_disk)
    entries = _load_entries_from_csv(csv_path)

    manifest = {
        "schema_version": "cochem.scribe.figure-source-register/1",
        "policy": (
            "Metadata and SHA-256 provenance register for all 19 in-scope figures "
            "(4 FTMW methodology manuscript + 15 Keratin v1.1.0). Private manuscript "
            "scripts and archival PDFs remain exclusively on Instructor Google Drive "
            "and are never duplicated into this public repository. Out-of-scope "
            "encyclopedia material is strictly excluded."
        ),
        "private_assets_bundled_in_repo": False,
        "source_register_csv_sha256": verification["register_sha256"],
        "total_figures": verification["total_figures"],
        "collection_counts": verification["collection_counts"],
        "scope_exclusion_gate": {
            "status": "PASSED",
            "violation_count": 0,
        },
        "entries": [e.model_dump(mode="json") for e in entries],
    }

    out_path = Path(out_json_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
