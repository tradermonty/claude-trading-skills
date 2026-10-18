"""Line-ending policy: tracked text files must check out as LF on every OS.

Packaged ``.skill`` archives are byte-compared against fresh builds by the
package-drift gates. A Windows checkout with ``core.autocrlf=true`` and no
``.gitattributes`` rewrites text files to CRLF, so every package looks stale
locally even though nothing changed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _check_attr(attr: str, *paths: str) -> dict[str, str]:
    out = subprocess.run(
        ["git", "check-attr", attr, "--", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # Format: "<path>: <attr>: <value>"
    return {line.split(": ")[0]: line.split(": ")[2] for line in out.splitlines()}


def test_text_files_check_out_as_lf() -> None:
    paths = ("skills/position-sizer/SKILL.md", "scripts/package_skills.py", "skills-index.yaml")
    assert _check_attr("eol", *paths) == dict.fromkeys(paths, "lf")


def test_packaged_skills_are_binary() -> None:
    path = "skill-packages/position-sizer.skill"
    assert _check_attr("text", path) == {path: "unset"}
