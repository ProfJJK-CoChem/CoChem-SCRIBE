"""Command-line interface for CoChem-SCRIBE (`cochem-scribe`)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .provider import scribe_provider
from .register import audit_farir_exclusion, verify_source_register
from .renderers import (
    render_basis_convergence,
    render_geom_comparison,
    render_kinetic_rxn_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cochem-scribe",
        description="CoChem-SCRIBE verified-output scientific figure renderer and provenance auditor.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_geom = sub.add_parser(
        "render-geom",
        help="Render CoChem-GEOM verified structural comparison JSON to PNG + PDF.",
    )
    p_geom.add_argument("--input", required=True, help="Path to CoChem-GEOM comparison JSON.")
    p_geom.add_argument("--out-png", required=True, help="Output PNG figure path.")
    p_geom.add_argument("--out-pdf", required=True, help="Output PDF figure path.")
    p_geom.add_argument("--manifest", default=None, help="Optional SHA-256 provenance JSON path.")

    p_kin = sub.add_parser(
        "render-kinetic",
        help="Render CoChem-KINETIC verified 3-point or 5-point stationary_table.csv to PNG + PDF.",
    )
    p_kin.add_argument("--input", required=True, help="Path to stationary_table.csv.")
    p_kin.add_argument("--out-png", required=True, help="Output PNG figure path.")
    p_kin.add_argument("--out-pdf", required=True, help="Output PDF figure path.")
    p_kin.add_argument(
        "--energy-column",
        default="delta_g_qrrho_kcal",
        help="Relative free-energy column name (default: delta_g_qrrho_kcal).",
    )
    p_kin.add_argument(
        "--pathway-mode",
        choices=["auto", "3pt", "5pt"],
        default="auto",
        help="Stationary-point pathway mode: auto-detect (default), 3pt (R, TS, P), or 5pt (R, TS1, Int_tet, TS2, P).",
    )
    p_kin.add_argument(
        "--allow-pending",
        action="store_true",
        help="Allow rendering explicit PENDING slots instead of raising in strict mode.",
    )
    p_kin.add_argument("--title", default=None, help="Optional custom figure title.")
    p_kin.add_argument("--manifest", default=None, help="Optional SHA-256 provenance JSON path.")

    p_conv = sub.add_parser(
        "render-convergence",
        help="Render basis-set / method energy convergence JSON or CSV to 300-DPI PNG + PDF + SHA-256 manifest.",
    )
    p_conv.add_argument(
        "--input",
        required=True,
        help="Path to basis-set / method convergence JSON or CSV.",
    )
    p_conv.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for PNG, vector PDF, and SHA-256 manifest.",
    )
    p_conv.add_argument(
        "--prefix",
        default="convergence",
        help="Filename prefix for rendered outputs (default: convergence).",
    )
    p_conv.add_argument(
        "--units",
        choices=["kcal/mol", "mEh", "Eh"],
        default="kcal/mol",
        help="Relative convergence delta-E panel units (default: kcal/mol).",
    )
    p_conv.add_argument(
        "--strict",
        action="store_true",
        help="Fail closed if any input entry is PENDING or unconverged instead of annotating it.",
    )
    p_conv.add_argument("--title", default=None, help="Optional custom figure title.")
    p_conv.add_argument(
        "--manifest",
        default=None,
        help="Optional explicit SHA-256 provenance manifest JSON path (defaults to <output-dir>/<prefix>_manifest_sha256.json).",
    )

    p_reg = sub.add_parser(
        "verify-register",
        help="Verify the 19-entry Drive figure source register and encyclopedia exclusion gate.",
    )
    p_reg.add_argument(
        "--register",
        default=None,
        help="Path to CSV or JSON figure register (defaults to packaged manifest).",
    )
    p_reg.add_argument(
        "--verify-on-disk",
        action="store_true",
        help="Re-hash all 19 Drive source scripts and archived reference PDFs on disk.",
    )

    p_audit = sub.add_parser(
        "audit-farir",
        help="Audit a file or directory for out-of-scope encyclopedia strings.",
    )
    p_audit.add_argument("--path", required=True, help="File or directory to audit.")

    sub.add_parser(
        "provider-info",
        help="Print CoChem-BASE `cochem.module-provider/1` metadata as JSON.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "render-geom":
        receipt = render_geom_comparison(
            comparison_json_path=args.input,
            out_png=args.out_png,
            out_pdf=args.out_pdf,
            manifest_path=args.manifest,
        )
        print(json.dumps(receipt, indent=2))
        return 0

    if args.command == "render-kinetic":
        receipt = render_kinetic_rxn_profile(
            stationary_csv_path=args.input,
            out_png=args.out_png,
            out_pdf=args.out_pdf,
            energy_column=args.energy_column,
            strict=not args.allow_pending,
            title=args.title,
            manifest_path=args.manifest,
            pathway_mode=args.pathway_mode,
        )
        print(json.dumps(receipt, indent=2))
        return 0

    if args.command == "render-convergence":
        receipt = render_basis_convergence(
            input_path=args.input,
            output_dir=args.output_dir,
            prefix=args.prefix,
            title=args.title,
            manifest_path=args.manifest,
            units=args.units,
            strict=args.strict,
        )
        print(json.dumps(receipt, indent=2))
        return 0

    if args.command == "verify-register":
        report = verify_source_register(
            register_csv_path=args.register,
            verify_on_disk=args.verify_on_disk,
        )
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "audit-farir":
        report = audit_farir_exclusion(args.path, raise_on_violation=False)
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1

    if args.command == "provider-info":
        print(json.dumps(scribe_provider(), indent=2))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
