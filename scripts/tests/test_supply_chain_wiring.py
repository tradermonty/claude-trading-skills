"""PR integrity gates must protect the environments CI actually executes."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_stale_project_metadata_is_rejected_without_rewriting_lock(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv CLI is required for the real lock refusal contract")
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    env = {**os.environ, "UV_CACHE_DIR": str(tmp_path / "cache")}
    command = [uv, "lock", "--check", "--offline", "--python", os.sys.executable]
    valid = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert valid.returncode == 0, valid.stderr
    original_lock = (tmp_path / "uv.lock").read_bytes()
    project = tmp_path / "pyproject.toml"
    project.write_text(
        project.read_text().replace('"requests>=2.31.0"', '"requests==0.0.1"'),
        encoding="utf-8",
    )
    stale = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert stale.returncode != 0
    assert (tmp_path / "uv.lock").read_bytes() == original_lock
