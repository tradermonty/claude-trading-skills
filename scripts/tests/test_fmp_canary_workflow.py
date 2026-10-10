"""Structural and behavioural tests for the FMP contract canary workflow (Issue #332).

The workflow must never be silently green: a missing secret turns the
``preflight`` job red unless the maintainer opts out explicitly, and drift
stays report-only (``canary`` keeps ``continue-on-error``) but is surfaced via
a step summary and annotations.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "fmp-contract-canary.yml"
REPO_SLUG = "tradermonty/claude-trading-skills"
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def config():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


@pytest.fixture(scope="module")
def preflight(config):
    return config["jobs"]["preflight"]


@pytest.fixture(scope="module")
def canary(config):
    return config["jobs"]["canary"]


def _all_steps(config):
    for job_id, job in config["jobs"].items():
        for step in job["steps"]:
            yield job_id, step


def test_top_level_permissions_read_only(config):
    assert config["permissions"] == {"contents": "read"}


def test_two_jobs(config):
    assert set(config["jobs"]) == {"preflight", "canary"}


def test_preflight_shape(preflight):
    assert "continue-on-error" not in preflight
    assert preflight["if"] == f"github.repository == '{REPO_SLUG}'"
    assert preflight["outputs"] == {
        "run_canary": "${{ steps.gate.outputs.run_canary }}",
        "state": "${{ steps.gate.outputs.state }}",
    }
    assert len(preflight["steps"]) == 1
    step = preflight["steps"][0]
    assert step["id"] == "gate"
    assert "uses" not in step  # bash only: no checkout, no setup-python


def test_canary_shape(canary):
    assert canary["needs"] == "preflight"
    assert canary["continue-on-error"] == "true"
    assert canary["if"] == (
        "needs.preflight.result == 'success' && needs.preflight.outputs.run_canary == 'true'"
    )


def test_secrets_only_in_step_env(config):
    for job_id, step in _all_steps(config):
        run = step.get("run", "")
        assert "secrets." not in run and "${{" not in run, (job_id, step.get("name"))
        assert "set -x" not in run
        assert 'echo "$FMP_API_KEY"' not in run
        for key, value in (step.get("with") or {}).items():
            assert "secrets." not in value, (job_id, key)
    text = WORKFLOW.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "secrets." in line and not line.lstrip().startswith("#"):
            assert "FMP_API_KEY: ${{ secrets.FMP_API_KEY }}" in line


def test_preflight_script_contract(preflight):
    env = preflight["steps"][0]["env"]
    assert env["FMP_API_KEY"] == "${{ secrets.FMP_API_KEY }}"
    assert env["FMP_CANARY_ENABLED"] == "${{ vars.FMP_CANARY_ENABLED }}"
    script = preflight["steps"][0]["run"]
    assert "exit 1" in script
    assert "::error title=FMP canary not configured::" in script


def test_summarize_step_runs_always_with_fallback(canary):
    steps = [
        s for s in canary["steps"] if "check_provider_contracts.py summarize" in s.get("run", "")
    ]
    assert len(steps) == 1
    step = steps[0]
    assert step["if"] == "always()"
    assert "--summary-file" in step["run"] and '"$GITHUB_STEP_SUMMARY"' in step["run"]
    assert "--github" in step["run"]
    assert "::error title=FMP canary summarize failed::" in step["run"]


def test_upload_step_runs_always(canary):
    uploads = [s for s in canary["steps"] if "upload-artifact" in s.get("uses", "")]
    assert len(uploads) == 1
    assert uploads[0]["if"] == "always()"


def test_canary_steps_not_gated_on_removed_key_check(canary):
    assert "key_check" not in yaml.dump(canary)


def test_every_uses_is_sha_pinned(config):
    for job_id, step in _all_steps(config):
        uses = step.get("uses")
        if uses:
            assert SHA_RE.match(uses), (job_id, uses)


def test_canary_job_syncs_locked_env(canary):
    runs = "\n".join(s.get("run", "") for s in canary["steps"])
    assert "uv sync --locked --no-install-project --extra dev --extra ci" in runs
    assert "check_provider_contracts.py canary" in runs


# --- preflight behaviour (bash subprocess) ---------------------------------

BASH = shutil.which("bash")


def _run_preflight(script: str, tmp_path: Path, secret: str | None, enabled: str | None):
    out = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    out.write_text("")
    summary.write_text("")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
        "FMP_API_KEY": secret or "",
        "FMP_CANARY_ENABLED": enabled or "",
    }
    result = subprocess.run(
        [BASH, "-c", script], env=env, capture_output=True, text=True, check=False
    )
    return result, out.read_text(), summary.read_text()


@pytest.fixture(scope="module")
def script(preflight):
    return preflight["steps"][0]["run"]


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_preflight_script_bash_syntax(script, tmp_path):
    path = tmp_path / "preflight.sh"
    path.write_text(script)
    assert subprocess.run([BASH, "-n", str(path)], check=False).returncode == 0


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_preflight_secret_set(script, tmp_path):
    result, out, summary = _run_preflight(script, tmp_path, "PLACEHOLDER", None)
    assert result.returncode == 0
    assert "run_canary=true" in out and "state=configured" in out
    assert "PLACEHOLDER" not in result.stdout + result.stderr + out + summary


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", " false ", "FALSE\n", "\t0 "])
def test_preflight_opt_out(script, tmp_path, value):
    result, out, summary = _run_preflight(script, tmp_path, None, value)
    assert result.returncode == 0
    assert "run_canary=false" in out and "state=disabled" in out
    assert "::notice title=FMP canary disabled::" in result.stdout
    assert "disabled" in summary.lower()


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("value", [None, "", "true", "no", "off"])
def test_preflight_not_configured_fails(script, tmp_path, value):
    result, out, summary = _run_preflight(script, tmp_path, None, value)
    assert result.returncode == 1
    assert "::error title=FMP canary not configured::" in result.stdout
    assert "run_canary=false" in out and "state=not_configured" in out
    assert "FMP_API_KEY" in summary and "FMP_CANARY_ENABLED" in summary
    assert "No live contract probe ran because the FMP_API_KEY secret is not set." in summary
