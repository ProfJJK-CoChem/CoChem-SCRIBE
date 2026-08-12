#!/usr/bin/env python3
"""
CoChem-SCRIBE: FAIR Publication Archive Builder (§6.3.4)
Aggregates publication-ready artifacts into a Submission_Archive.zip with
SHA-256 integrity signatures for FAIR (Findable, Accessible, Interoperable,
Reusable) data archiving compliance.

Resolves Suggestion 96: Automatically collects .tex tables (siunitx/booktabs),
Plotly HTML dashboards, Parquet catalogs, and .xyz coordinate files into a
single reproducible submission bundle.
"""

import hashlib
import json
import logging
logger = logging.getLogger(__name__)
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
artifact_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(artifact_dir / "cochem_scribe_archive.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class Colors:
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# File category definitions for FAIR archive bundling
# ---------------------------------------------------------------------------
ARCHIVE_CATEGORIES: dict[str, dict] = {
    "tex_tables": {
        "description": "LaTeX tables (siunitx/booktabs)",
        "patterns": ["*.tex"],
        "required": False,
    },
    "plotly_dashboards": {
        "description": "Plotly HTML interactive dashboards",
        "patterns": ["*.html"],
        "required": False,
    },
    "parquet_catalogs": {
        "description": "Apache Parquet data catalogs",
        "patterns": ["*.parquet"],
        "required": False,
    },
    "xyz_coordinates": {
        "description": "Molecular coordinate files",
        "patterns": ["*.xyz"],
        "required": False,
    },
    "bibtex": {
        "description": "BibTeX reference databases",
        "patterns": ["*.bib"],
        "required": False,
    },
}


def _sha256_file(filepath: Path) -> str:
    """Computes the SHA-256 hex digest of a file."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


class FAIRArchiveBuilder:
    """
    Aggregates publication-ready artifacts into ``Submission_Archive.zip``
    with per-file SHA-256 signatures and a machine-readable FAIR manifest.
    """

    def __init__(
        self,
        search_dirs: Optional[list[str]] = None,
        output_path: str = "Submission_Archive.zip",
    ) -> None:
        self.search_dirs: list[Path] = []
        if search_dirs:
            for d in search_dirs:
                p = Path(d)
                if p.is_dir():
                    self.search_dirs.append(p)
        if not self.search_dirs:
            # Default: current working directory and common artifact subdirs
            cwd = Path(".")
            self.search_dirs = [cwd]
            for sub in ("generated_figures", "Report_Archive", "tables", "dashboards"):
                sub_p = cwd / sub
                if sub_p.is_dir():
                    self.search_dirs.append(sub_p)

        self.output_path = Path(output_path)
        self.collected_files: list[tuple[Path, str]] = []  # (path, category)
        self.checksums: dict[str, str] = {}

    # --------------------------------------------------------------------- #
    # Discovery
    # --------------------------------------------------------------------- #
    def discover_artifacts(self) -> dict[str, list[Path]]:
        """
        Walks ``search_dirs`` and matches files against each
        ``ARCHIVE_CATEGORIES`` glob pattern.  Returns a dict mapping
        category name → list of discovered file paths.
        """
        logger.info(
            f"{Colors.OKCYAN}[INFO] Discovering FAIR archive artifacts...{Colors.ENDC}"
        )
        results: dict[str, list[Path]] = {cat: [] for cat in ARCHIVE_CATEGORIES}
        seen: set[Path] = set()

        for search_dir in self.search_dirs:
            for category, spec in ARCHIVE_CATEGORIES.items():
                for pattern in spec["patterns"]:
                    for match in search_dir.rglob(pattern):
                        resolved = match.resolve()
                        if resolved in seen:
                            continue
                        # Skip files inside Report_Archive .tar.zst bundles
                        if ".tar.zst" in str(match):
                            continue
                        seen.add(resolved)
                        results[category].append(match)
                        self.collected_files.append((match, category))

        for category, files in results.items():
            count = len(files)
            desc = ARCHIVE_CATEGORIES[category]["description"]
            if count > 0:
                    logger.info(
                    f"{Colors.OKGREEN}  [OK] {desc}: {count} file(s){Colors.ENDC}"
                )
            else:
                    logger.info(
                    f"{Colors.WARNING}  [WARN] {desc}: none found{Colors.ENDC}"
                )
            logging.info(f"FAIR discover: {category} -> {count} file(s)")

        return results

    # --------------------------------------------------------------------- #
    # Checksum generation
    # --------------------------------------------------------------------- #
    def compute_checksums(self) -> dict[str, str]:
        """
        Computes SHA-256 for every collected file.
        Returns dict mapping relative archive path → hex digest.
        """
        logger.info(
            f"{Colors.OKCYAN}[INFO] Computing SHA-256 checksums...{Colors.ENDC}"
        )
        self.checksums = {}
        for filepath, _category in self.collected_files:
            try:
                digest = _sha256_file(filepath)
                archive_name = filepath.name
                self.checksums[archive_name] = digest
            except Exception as e:
                logging.error(f"SHA-256 failed for {filepath}: {e}")
        return self.checksums

    # --------------------------------------------------------------------- #
    # FAIR manifest
    # --------------------------------------------------------------------- #
    def build_manifest(self) -> dict:
        """
        Builds a machine-readable FAIR manifest (JSON) describing every
        artifact, its category, SHA-256 digest, and archive metadata.
        """
        now = datetime.now(timezone.utc).isoformat()
        entries = []
        for filepath, category in self.collected_files:
            entry = {
                "filename": filepath.name,
                "category": category,
                "category_description": ARCHIVE_CATEGORIES[category]["description"],
                "original_path": str(filepath),
                "size_bytes": filepath.stat().st_size if filepath.exists() else 0,
                "sha256": self.checksums.get(filepath.name, ""),
            }
            entries.append(entry)

        manifest = {
            "archive_format": "Submission_Archive.zip",
            "fair_version": "1.0",
            "created_utc": now,
            "generator": "CoChem-SCRIBE FAIRArchiveBuilder",
            "total_files": len(entries),
            "categories": {
                cat: {
                    "description": spec["description"],
                    "count": sum(1 for e in entries if e["category"] == cat),
                }
                for cat, spec in ARCHIVE_CATEGORIES.items()
            },
            "files": entries,
        }
        return manifest

    # --------------------------------------------------------------------- #
    # Archive creation
    # --------------------------------------------------------------------- #
    def create_archive(self) -> Path:
        """
        Creates ``Submission_Archive.zip`` containing all discovered artifacts,
        a ``checksums.sha256`` manifest, and a ``FAIR_manifest.json`` metadata
        file.
        """
        # 1. Discover
        self.discover_artifacts()
        if not self.collected_files:
            msg = (
                "No publication artifacts discovered for FAIR archive. "
                "Run the CoChem pipeline to generate .tex, .html, .parquet, "
                "and .xyz outputs before archiving."
            )
            logger.info(f"{Colors.WARNING}[WARN] {msg}{Colors.ENDC}")
            logging.warning(msg)
            return self.output_path

        # 2. Checksums
        self.compute_checksums()

        # 3. Manifest
        manifest = self.build_manifest()

        # 4. Write ZIP
        logger.info(
            f"{Colors.OKCYAN}[INFO] Building {self.output_path.name}...{Colors.ENDC}"
        )
        try:
            with zipfile.ZipFile(
                self.output_path, "w", zipfile.ZIP_DEFLATED
            ) as zf:
                # Add each collected file
                for filepath, category in self.collected_files:
                    arcname = f"{category}/{filepath.name}"
                    zf.write(filepath, arcname=arcname)

                # Add checksum manifest
                checksum_lines = [
                    f"{digest}  {fname}"
                    for fname, digest in sorted(self.checksums.items())
                ]
                checksum_text = "\n".join(checksum_lines) + "\n"
                zf.writestr("checksums.sha256", checksum_text)

                # Add FAIR manifest JSON
                manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
                zf.writestr("FAIR_manifest.json", manifest_json)

            # 5. Compute archive-level checksum
            archive_sha = _sha256_file(self.output_path)
            sig_path = self.output_path.with_suffix(".zip.sha256")
            sig_path.write_text(
                f"{archive_sha}  {self.output_path.name}\n", encoding="utf-8"
            )

            total = len(self.collected_files)
            logger.info(
                f"{Colors.OKGREEN}[OK] FAIR archive created: "
                f"{self.output_path.name} ({total} files){Colors.ENDC}"
            )
            logger.info(
                f"{Colors.OKGREEN}   SHA-256 signature: "
                f"{sig_path.name}{Colors.ENDC}"
            )
            logging.info(
                f"FAIR archive created: {self.output_path.name} "
                f"({total} files, SHA-256={archive_sha[:16]}...)"
            )

        except Exception as e:
            logger.info(
                f"{Colors.FAIL}[FAIL] Failed to create FAIR archive: {e}{Colors.ENDC}"
            )
            logging.error(f"FAIR archive creation failed: {e}")

        return self.output_path


# --------------------------------------------------------------------------- #
# Module-level convenience function
# --------------------------------------------------------------------------- #
def build_fair_archive(
    search_dirs: Optional[list[str]] = None,
    output_path: str = "Submission_Archive.zip",
) -> Path:
    """
    One-call convenience wrapper for building the FAIR submission archive.
    """
    builder = FAIRArchiveBuilder(
        search_dirs=search_dirs, output_path=output_path
    )
    return builder.create_archive()


def main() -> None:
    logger.info(
        f"\n{Colors.BOLD}--- CoChem-SCRIBE: FAIR Publication Archive Builder ---{Colors.ENDC}"
    )
    archive_path = build_fair_archive()
    logger.info(
        f"\n{Colors.BOLD}Archive location: {archive_path.absolute()}{Colors.ENDC}\n"
    )


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