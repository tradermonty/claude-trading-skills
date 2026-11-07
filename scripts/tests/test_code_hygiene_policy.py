"""Prevent regression of the Issue 618 lint and deprecated UTC API budget."""

import ast
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_complexity_and_bug_rules_remain_enforced():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lint = config["tool"]["ruff"]["lint"]
    rules = {"B904", "B007", "B017", "C901"}
    assert {"B", "C901"} <= set(lint["select"])
    assert not rules.intersection(lint["ignore"])
    assert lint["mccabe"]["max-complexity"] <= 128
    for ignores in lint["per-file-ignores"].values():
        assert not rules.intersection(ignores)
    assert (
        "-p scripts.pytest_firstparty_warnings"
        in config["tool"]["pytest"]["ini_options"]["addopts"]
    )


def test_production_code_has_no_deprecated_utcnow():
    offenders = []
    for directory in (ROOT / "skills", ROOT / "scripts"):
        for path in directory.rglob("*.py"):
            if "tests" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "utcnow"
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders
