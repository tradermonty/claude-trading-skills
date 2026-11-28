"""Guard the CI gate wiring from issue #503 (lint root, full package check, mypy)."""

from __future__ import annotations

from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_ruff_runs_over_repo_root() -> None:
    assert "run: ruff check .\n" in CI
    assert "run: ruff format --check .\n" in CI


def test_package_check_covers_all_skills() -> None:
    assert "run: python3 scripts/package_skills.py --check\n" in CI
    assert "package_skills.py --check --skill" not in CI


def test_mypy_is_blocking_and_scoped() -> None:
    assert "run: mypy\n" in CI
    dev = PYPROJECT["project"]["optional-dependencies"]["dev"]
    assert any(dep.startswith("mypy") for dep in dev)
    files = PYPROJECT["tool"]["mypy"]["files"]
    for expected in (
        "scripts/fmp_client",
        "scripts/market_calendar",
        "skills/trader-memory-core/scripts",
        "skills/position-sizer/scripts",
    ):
        assert expected in files
        assert (ROOT / expected).is_dir()
