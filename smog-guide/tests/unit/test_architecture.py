"""Architecture boundary tests.

These tests parse every Python source file under src/smogguide with the
``ast`` module and assert that each layer only imports from layers it is
permitted to depend on. No code is executed; only the AST is inspected.

Failure messages name the offending file and the illegal import so the
developer knows exactly what to fix.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Root of the smogguide source tree.
SRC_ROOT = Path(__file__).parents[2] / "src" / "smogguide"

# ---------------------------------------------------------------------------
# Forbidden import rules per layer.
# Each entry maps a layer directory name to a set of module-name substrings
# that must NOT appear in any import within that layer.
# ---------------------------------------------------------------------------
LAYER_FORBIDDEN: dict[str, frozenset[str]] = {
    "utils": frozenset(
        {
            # utils is the leaf: it must not import any other smogguide layer.
            "smogguide.domain",
            "smogguide.prompts",
            "smogguide.services",
            "smogguide.api",
        }
    ),
    "domain": frozenset(
        {
            # domain is pure logic: no I/O, no framework dependencies.
            "smogguide.services",
            "smogguide.api",
            "smogguide.prompts",
            "fastapi",
            "httpx",
            "anthropic",
            "google.generativeai",
            "openai",
        }
    ),
    "prompts": frozenset(
        {
            # prompts may only import domain and utils.
            "smogguide.services",
            "smogguide.api",
            "fastapi",
            "httpx",
        }
    ),
    "services": frozenset(
        {
            # services may not import the api layer.
            "smogguide.api",
            "fastapi",
        }
    ),
    # api layer: no restrictions beyond what mypy enforces; tested via type checking.
}


def _collect_imports(source_path: Path) -> list[str]:
    """Return a flat list of all module names imported in a Python source file.

    Args:
        source_path: Absolute path to a .py file.

    Returns:
        Module name strings (e.g. ``"httpx"``, ``"smogguide.domain.aqi"``).
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _python_files_in_layer(layer: str) -> list[Path]:
    """Return all .py files inside a named layer directory.

    Args:
        layer: Directory name relative to SRC_ROOT (e.g. ``"domain"``).

    Returns:
        Sorted list of absolute Path objects.
    """
    layer_dir = SRC_ROOT / layer
    if not layer_dir.is_dir():
        return []
    return sorted(layer_dir.glob("**/*.py"))


# Build a parametrize list of (file, forbidden_import) pairs to give pytest
# one test case per violation candidate, so each failure is reported individually.
_violation_cases: list[tuple[Path, str, str]] = []
for _layer, _forbidden_set in LAYER_FORBIDDEN.items():
    for _file in _python_files_in_layer(_layer):
        for _imported in _collect_imports(_file):
            for _forbidden in _forbidden_set:
                if _imported.startswith(_forbidden):
                    _violation_cases.append((_file, _layer, _imported))

# Also collect all (file, layer, imported) triples for the parametrized happy-path.
_all_cases: list[tuple[Path, str, str]] = []
for _layer, _forbidden_set in LAYER_FORBIDDEN.items():
    for _file in _python_files_in_layer(_layer):
        for _imported in _collect_imports(_file):
            _all_cases.append((_file, _layer, _imported))


@pytest.mark.parametrize(
    "source_file,layer,imported_module",
    _all_cases or [pytest.param(Path("."), "none", "none", marks=pytest.mark.skip)],
)  # type: ignore[misc]
def test_architecture_layer_import_is_allowed(
    source_file: Path, layer: str, imported_module: str
) -> None:
    """Assert that an import found in a layer file is not forbidden for that layer.

    Failure message names the file and the offending import.
    """
    forbidden = LAYER_FORBIDDEN.get(layer, frozenset())
    for forbidden_prefix in forbidden:
        assert not imported_module.startswith(forbidden_prefix), (
            f"Layer boundary violation in {source_file.relative_to(SRC_ROOT.parent.parent)}: "
            f"'{layer}' layer must not import '{imported_module}' "
            f"(forbidden prefix: '{forbidden_prefix}')"
        )
