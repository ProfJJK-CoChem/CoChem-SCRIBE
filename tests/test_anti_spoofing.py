"""Real AST and source-level anti-spoofing, scope, and license integrity tests."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from cochem_scribe.register import audit_farir_exclusion

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist"}

# Only the exclusion-gate definition itself and the dedicated negative test that
# injects synthetic rejected entries may mention forbidden encyclopedia tokens.
FARIR_GATE_FILES = {
    (REPO_ROOT / "src" / "cochem_scribe" / "register.py").resolve(),
    (REPO_ROOT / "tests" / "test_scribe_verified_renderers.py").resolve(),
}

PRIVATE_ASSET_FILENAMES = {
    "generate_figures.py",
    "fig1_challenge1_14n_hyperfine.pdf",
    "fig2_challenge2_tunneling_coriolis.pdf",
    "fig3_challenge3_floppy_isotopologue.pdf",
    "fig4_hierarchy_rmsd_study_targets.pdf",
    "Biomimetic_Keratin_Figure_Generators_v1.1.0.zip",
    "Fig00.pdf",
    "Fig00B.pdf",
    "Fig00C.pdf",
    "Fig01A.pdf",
    "Fig02A.pdf",
    "Fig03A.pdf",
    "Fig03B.pdf",
    "Fig04A.pdf",
    "Fig05A.pdf",
    "Fig06A.pdf",
    "Fig07A.pdf",
    "Fig08A.pdf",
    "Fig08B.pdf",
    "Fig09A.pdf",
    "Fig10A.pdf",
}


def _iter_repo_files(suffixes: set[str] | None = None) -> list[Path]:
    files: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        if not path.is_file():
            continue
        if suffixes is None or path.suffix.lower() in suffixes:
            files.append(path)
    return files


def test_all_python_files_parse_with_zero_ast_errors() -> None:
    py_files = _iter_repo_files({".py"})
    assert len(py_files) >= 15
    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8-sig")
        ast.parse(source, filename=str(py_file))


def _scan_ast_for_test_doubles(source: str, label: str) -> list[str]:
    """Scan Python AST for prohibited test-double modules, classes, or patch fixtures."""
    banned_root = "m" + "ock"
    banned_stdlib = "unittest." + banned_root
    banned_patch = "monkey" + "patch"
    banned_names = {
        "Magic" + "Mock",
        "Async" + "Mock",
        "Property" + "Mock",
        "NonCallable" + "Mock",
        "M" + "ock",
        "Monkey" + "Patch",
        banned_patch,
    }

    violations: list[str] = []
    tree = ast.parse(source, filename=label)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == banned_root or alias.name.startswith(banned_stdlib):
                    violations.append(f"{label}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == banned_root or mod.startswith(banned_stdlib):
                violations.append(f"{label}:{node.lineno} from {mod}")
            for alias in node.names:
                if alias.name in banned_names:
                    violations.append(f"{label}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.arg) and node.arg == banned_patch:
            violations.append(f"{label}:{node.lineno} arg {node.arg}")
        elif isinstance(node, ast.Name) and node.id in banned_names:
            violations.append(f"{label}:{node.lineno} name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in banned_names:
            violations.append(f"{label}:{node.lineno} attr .{node.attr}")
    return violations


def test_anti_spoofing_zero_test_doubles_ast() -> None:
    """Verify zero test-double or patch-fixture usage across all Python files via real AST."""
    violations: list[str] = []
    for py_file in _iter_repo_files({".py"}):
        source = py_file.read_text(encoding="utf-8-sig")
        rel = str(py_file.relative_to(REPO_ROOT))
        violations.extend(_scan_ast_for_test_doubles(source, rel))

    assert not violations, "Prohibited test-double usage detected in repository:\n" + "\n".join(violations)

    # Confirm the AST scanner genuinely flags synthetic bad imports and patch fixtures
    bad_snippet = (
        f"from unittest.{'m' + 'ock'} import {'Magic' + 'Mock'}\n"
        f"def f({'monkey' + 'patch'}): return {'Magic' + 'Mock'}()\n"
    )
    detected = _scan_ast_for_test_doubles(bad_snippet, "<selftest>")
    assert len(detected) >= 3


def test_zero_synthetic_linspace_axes_or_hardcoded_ir_heights() -> None:
    """Verify zero synthetic np.linspace(0, 10, ...) axes and zero hardcoded 1.0/0.8 IR heights."""
    this_file = Path(__file__).resolve()
    violations: list[str] = []

    for py_file in _iter_repo_files({".py"}):
        if py_file.resolve() == this_file:
            continue
        source = py_file.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(py_file))

        # AST check for np.linspace(0, 10, ...) or synthetic Morse linspace(0.8, 3.0, 50)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else (node.func.id if isinstance(node.func, ast.Name) else "")
                )
                if func_name == "linspace" and len(node.args) >= 2:
                    a0, a1 = node.args[0], node.args[1]
                    if (
                        isinstance(a0, ast.Constant)
                        and isinstance(a1, ast.Constant)
                        and a0.value in (0, 0.0)
                        and a1.value in (10, 10.0)
                    ):
                        violations.append(
                            f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} synthetic linspace(0, 10, ...)"
                        )
                    if (
                        isinstance(a0, ast.Constant)
                        and isinstance(a1, ast.Constant)
                        and a0.value == 0.8
                        and a1.value == 3.0
                    ):
                        violations.append(
                            f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} synthetic Morse linspace(0.8, 3.0, ...)"
                        )

        # Source check for hardcoded flat 1.0 / 0.8 IR stick heights
        if re.search(r"ones_like\([^)]*\)\s*\*\s*0\.8", source):
            violations.append(
                f"{py_file.relative_to(REPO_ROOT)} hardcoded flat 0.8 IR bar height"
            )

    assert not violations, "Synthetic figure fabrication detected:\n" + "\n".join(violations)


def test_apache_2_license_and_tennessee_tech_only() -> None:
    """Verify Apache 2.0 alignment and Tennessee Tech University attribution (zero Texas Tech)."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    license_txt = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "Apache License" in license_txt and "Version 2.0" in license_txt
    assert "Apache License, Version 2.0" in readme
    assert "CoChem Academic License" not in readme
    assert "Tennessee Tech University" in readme
    assert 'license = { text = "Apache-2.0" }' in pyproject

    for path in _iter_repo_files({".py", ".md", ".toml", ".json", ".tex"}):
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "texas tech" not in text.lower(), f"Forbidden institution reference in {path}"
        assert "cochem academic license" not in text.lower(), f"Legacy license reference in {path}"


def test_zero_farir_encyclopedia_leaks_and_zero_private_drive_assets() -> None:
    """Verify zero excluded encyclopedia strings across repo and zero private Drive manuscript assets."""
    leaks: list[str] = []
    private_copies: list[str] = []

    for path in _iter_repo_files():
        if path.name in PRIVATE_ASSET_FILENAMES or re.match(r"^generate_Fig\d+[A-Z]?\.py$", path.name):
            private_copies.append(str(path.relative_to(REPO_ROOT)))
        if path.resolve() in FARIR_GATE_FILES:
            continue
        if path.suffix.lower() in {".py", ".md", ".json", ".csv", ".tex", ".bib", ".txt", ".toml"}:
            report = audit_farir_exclusion(path, raise_on_violation=False)
            if not report["passed"]:
                for v in report["violations"]:
                    leaks.append(f"{path.relative_to(REPO_ROOT)} ({v['rule']}: {v['matched']!r})")

    assert not private_copies, "Private Drive manuscript assets found in repo:\n" + "\n".join(private_copies)
    assert not leaks, "Excluded encyclopedia content leaked into repo:\n" + "\n".join(leaks)
