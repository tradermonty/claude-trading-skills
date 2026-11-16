"""Guards for the Issue #502 stage-module layout of the two UGS entry scripts.

``evaluate_candidates.py`` and ``run_pipeline.py`` stay the CLI entry points and
import surface; their implementation lives in ordered stage modules. These
tests keep the stage list, the re-export surface and the one-way import order
from drifting.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

LAYOUTS = {
    "evaluate_candidates": (
        "evaluation_common",
        "evaluation_financials",
        "evaluation_valuation",
        "evaluation_candidate",
        "evaluation_ranking",
        "evaluation_report",
    ),
    "run_pipeline": (
        "pipeline_common",
        "pipeline_universe",
        "pipeline_enrichment",
        "pipeline_discover",
        "pipeline_snapshot",
    ),
}
PREFIXES = {"evaluate_candidates": "evaluation_", "run_pipeline": "pipeline_"}


def _top_level_names(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.Try):
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom):
                    names.extend(alias.asname or alias.name for alias in stmt.names)
    return names


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
    return modules


@pytest.mark.parametrize("entry", sorted(LAYOUTS))
def test_stage_list_matches_directory(entry):
    found = sorted(p.stem for p in SCRIPTS_DIR.glob(f"{PREFIXES[entry]}*.py"))
    assert found == sorted(LAYOUTS[entry])


@pytest.mark.parametrize("entry", sorted(LAYOUTS))
def test_every_stage_definition_is_reexported_by_identity(entry):
    module = importlib.import_module(entry)
    exported = set(module.__all__)
    for stage_name in LAYOUTS[entry]:
        stage = importlib.import_module(stage_name)
        for name in _top_level_names(SCRIPTS_DIR / f"{stage_name}.py"):
            assert name in exported, f"{stage_name}.{name} is not in {entry}.__all__"
            assert getattr(module, name) is getattr(stage, name), f"{entry}.{name}"
    for name in exported:
        assert hasattr(module, name), f"{entry}.__all__ lists missing name {name}"


@pytest.mark.parametrize("entry", sorted(LAYOUTS))
def test_stages_import_only_earlier_stages(entry):
    order = LAYOUTS[entry]
    for index, stage_name in enumerate(order):
        imported = _imported_modules(SCRIPTS_DIR / f"{stage_name}.py")
        assert entry not in imported, f"{stage_name} imports its entry module"
        later = imported & set(order[index:])
        assert not later, f"{stage_name} imports itself or a later stage: {sorted(later)}"
