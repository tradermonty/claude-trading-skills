"""Regression tests for the packaged-deps nightly smoke step exit handling.

The runner exits 0 (pass), 1 (fail) or 2 (incomplete). With today's contract
table it is always 2, so the workflow step must stay green on 2 with a visible
warning, while a real failure (1) or any other nonzero code must still fail.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "packaged-deps-nightly.yml"
STEP_NAME = "Clean-room venv smoke per skill"


@pytest.fixture(scope="module")
def config():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


@pytest.fixture(scope="module")
def smoke_step(config):
    steps = config["jobs"]["smoke"]["steps"]
    return next(step for step in steps if step.get("name") == STEP_NAME)


def test_job_stays_report_only(config):
    # Removing continue-on-error is #349's follow-up, not this change.
    assert config["jobs"]["smoke"]["continue-on-error"] == "true"


def test_step_uses_bash_and_runs_runner(smoke_step):
    assert smoke_step["shell"] == "bash"
    assert "scripts/smoke_contracts_runner.py" in smoke_step["run"]
    assert "--output deps-nightly-smoke.json" in smoke_step["run"]


def test_upload_step_still_runs_always(config):
    steps = config["jobs"]["smoke"]["steps"]
    upload = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
    assert upload["if"] == "always()"
    assert "deps-nightly-smoke.json" in upload["with"]["path"]


def _run_step(tmp_path, script, runner_exit):
    """Run the step script under `bash -e` with `uv` stubbed to a fixed exit code."""
    stub = tmp_path / "uv"
    stub.write_text(f"#!/bin/sh\necho stub-uv\nexit {runner_exit}\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )


@pytest.mark.parametrize(
    ("runner_exit", "step_exit"),
    [(0, 0), (1, 1), (2, 0), (3, 3), (127, 127)],
)
def test_step_exit_mapping(tmp_path, smoke_step, runner_exit, step_exit):
    result = _run_step(tmp_path, smoke_step["run"], runner_exit)
    assert result.returncode == step_exit, result.stdout + result.stderr


def test_incomplete_emits_visible_warning(tmp_path, smoke_step):
    result = _run_step(tmp_path, smoke_step["run"], 2)
    assert "::warning::" in result.stdout


@pytest.mark.parametrize("runner_exit", [0, 1])
def test_no_warning_for_pass_or_fail(tmp_path, smoke_step, runner_exit):
    result = _run_step(tmp_path, smoke_step["run"], runner_exit)
    assert "::warning::" not in result.stdout
