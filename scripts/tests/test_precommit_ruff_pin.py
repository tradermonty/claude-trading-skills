"""Keep the ruff releases used by pre-commit and CI in sync (issue #503).

``pyproject.toml`` pins the ruff release installed for CI and for local
``uv run`` commands, while ``.pre-commit-config.yaml`` pins the
ruff-pre-commit tag that the hooks install. When the two drift, a commit can
pass the hooks and still fail the lint job (or the other way around). This
test fails on a mismatch so a dependency bump updates both pins.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUFF_PIN = re.compile(r'"ruff==([0-9][0-9.]*)"')
PRE_COMMIT_REPO = "https://github.com/astral-sh/ruff-pre-commit"


def pyproject_ruff_version() -> str:
    """Return the ruff version pinned in pyproject.toml."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = RUFF_PIN.search(text)
    if match is None:
        raise AssertionError("pyproject.toml does not pin ruff with `ruff==<version>`")
    return match.group(1)


def pre_commit_ruff_tag() -> str:
    """Return the rev of the ruff-pre-commit repository in the hook config."""
    lines = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8").splitlines()
    in_ruff_repo = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- repo:"):
            in_ruff_repo = stripped.split(":", 1)[1].strip() == PRE_COMMIT_REPO
        elif in_ruff_repo and stripped.startswith("rev:"):
            return stripped.split(":", 1)[1].strip()
    raise AssertionError(".pre-commit-config.yaml has no ruff-pre-commit rev")


class RuffPinTest(unittest.TestCase):
    def test_pre_commit_tag_matches_pyproject_pin(self) -> None:
        pin = pyproject_ruff_version()
        tag = pre_commit_ruff_tag()
        self.assertEqual(
            tag,
            f"v{pin}",
            "ruff-pre-commit must install the same ruff release as pyproject.toml",
        )


if __name__ == "__main__":
    unittest.main()
