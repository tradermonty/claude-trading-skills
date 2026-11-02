"""Structural and behavioural tests for the FMP contract canary workflow (Issue #332).

The workflow must never be silently green: a missing secret turns the
``preflight`` job red unless the maintainer opts out explicitly, and drift
stays report-only (only the probe step keeps ``continue-on-error``) but is surfaced via
a step summary and annotations.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
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
    assert config["defaults"] == {"run": {"shell": "bash"}}


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
    assert "continue-on-error" not in canary
    probe = next(s for s in canary["steps"] if s.get("id") == "probe")
    assert probe["continue-on-error"] == "true"
    assert canary["if"] == (
        "needs.preflight.result == 'success' && needs.preflight.outputs.run_canary == 'true'"
    )


def _assert_safe_run(run, *, preflight=False):
    if preflight:
        run = run.replace('[ -n "$FMP_API_KEY" ]', "", 1)
    assert not re.search(r"\bFMP_API_KEY\b", run)
    assert not re.search(r"(?:^|[;\n|&])\s*(?:\S*/)?(?:env|printenv)(?:\s|$)", run)
    assert not re.search(r"(?:^|[;\n])\s*(?:set|export -p)\s*(?:[;\n]|$)", run)


@pytest.mark.parametrize(
    "run",
    [
        "echo $FMP_API_KEY",
        'echo "${FMP_API_KEY}"',
        'printf "%s" "$FMP_API_KEY"',
        "env",
        "printenv",
        "/usr/bin/env | sort",
        "set",
        "export -p",
    ],
)
def test_secret_guard_rejects_reference_and_dump_variants(run):
    with pytest.raises(AssertionError):
        _assert_safe_run(run, preflight=True)


def test_secrets_only_in_step_env(config):
    for job_id, step in _all_steps(config):
        run = step.get("run", "")
        assert "secrets." not in run and "${{" not in run, (job_id, step.get("name"))
        assert "set -x" not in run
        _assert_safe_run(run, preflight=job_id == "preflight")
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


def test_summarize_step_runs_always_and_write_failures_are_fatal(canary):
    steps = [
        s for s in canary["steps"] if "check_provider_contracts.py summarize" in s.get("run", "")
    ]
    assert len(steps) == 1
    step = steps[0]
    assert step["if"] == "always()"
    assert "--summary-file" in step["run"] and '"$GITHUB_STEP_SUMMARY"' in step["run"]
    assert "--github" in step["run"]
    assert "||" not in step["run"] and "continue-on-error" not in step
    health = next(
        s for s in canary["steps"] if "check_provider_contracts.py health" in s.get("run", "")
    )
    assert health["if"] == "always()" and "continue-on-error" not in health
    assert health["env"]["PROBE_OUTCOME"] == "${{ steps.probe.outcome }}"
    assert health["env"]["PROBE_EXIT_CODE"] == "${{ steps.probe.outputs.exit_code }}"


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
        [BASH, "-eo", "pipefail", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
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
    assert "API key secret" in summary and "FMP_CANARY_ENABLED" in summary
    assert "No live contract probe ran because the API key secret is not set." in summary


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_configured_secret_overrides_disable_variable(script, tmp_path):
    result, out, summary = _run_preflight(script, tmp_path, "PLACEHOLDER", "false")
    assert result.returncode == 0
    assert "run_canary=true" in out and "state=configured" in out
    assert "PLACEHOLDER" not in result.stdout + result.stderr + out + summary


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize(
    "scenario,failed",
    [
        ("healthy", False),
        ("drift", False),
        ("partial", False),
        ("unreachable", True),
        ("empty", True),
        ("missing", True),
        ("malformed", True),
        ("no-contracts", True),
        ("unexpected-exit", True),
        ("skipped", True),
        ("setup-failure", True),
        ("summary-write-error", True),
    ],
)
def test_actual_workflow_steps_distinguish_infrastructure_from_drift(
    tmp_path, canary, scenario, failed
):
    """Run real shell steps; only the provider transport and uv setup are fake.

    Emulate Actions' step-level continue-on-error independently of job failures.
    No GitHub dispatch, provider request or real credential is needed.
    """
    from scripts import check_provider_contracts as cli

    entry = {"status": 200, "rows": 1, "ok": True, "anomalies": [], "deprecations": []}
    entries = {
        name: copy.deepcopy(entry)
        for name, contract in cli.load_contracts(ROOT).items()
        if contract.provider == "fmp"
    }
    if scenario in {"drift", "unreachable", "empty", "partial"}:
        for index, value in enumerate(entries.values()):
            if scenario == "partial" and index == 0:
                continue
            value.update(
                status=-1 if scenario in {"unreachable", "partial"} else 200,
                rows=0 if scenario in {"unreachable", "partial", "empty"} else 1,
                ok=False,
                anomalies=[{"code": "missing_required_field:symbol", "severity": "fatal"}],
            )
    report = {
        "provider": "fmp",
        "generated_at": "2026-11-01T12:00:00+00:00",
        "budget": {"used": len(entries), "max": len(entries)},
        "ok": all(e["ok"] for e in entries.values()),
        "contracts": entries,
    }
    if scenario == "no-contracts":
        report["contracts"] = []
    payload = "not-json" if scenario == "malformed" else json.dumps(report)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(payload)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "python3"
    shim.write_text(
        f"#!{sys.executable}\n"
        "import os,sys,runpy\nfrom pathlib import Path\n"
        "if len(sys.argv)>2 and sys.argv[2]=='canary':\n"
        "    mode=os.environ['SCENARIO']\n"
        "    if mode!='missing':\n"
        "        out=Path('reports/fmp-canary-report.json')\n"
        "        out.parent.mkdir(parents=True,exist_ok=True)\n"
        "        out.write_text(Path(os.environ['FIXTURE']).read_text())\n"
        "    sys.exit(int(os.environ['PROBE_CODE']))\n"
        "os.execv(sys.executable,[sys.executable,*sys.argv[1:]])\n"
    )
    shim.chmod(0o755)
    uv = bin_dir / "uv"
    uv.write_text("#!/bin/sh\nexit 7\n")
    uv.chmod(0o755)
    (tmp_path / "scripts").symlink_to(ROOT / "scripts", target_is_directory=True)
    output, summary = tmp_path / "output", tmp_path / "summary"
    output.write_text("")
    summary.write_text("")
    report_path = tmp_path / "reports/fmp-canary-report.json"
    report_path.parent.mkdir()
    report_path.write_text(json.dumps(report))  # Stale evidence must be removed by probe.
    probe_code = 2 if scenario == "unexpected-exit" else (0 if report["ok"] else 1)
    if scenario in {"missing", "malformed", "no-contracts"}:
        probe_code = 1
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_PATH": str(tmp_path / "github-path"),
        "SCENARIO": scenario,
        "FIXTURE": str(fixture),
        "PROBE_CODE": str(probe_code),
        "FMP_API_KEY": "",
    }
    if scenario == "summary-write-error":
        env["GITHUB_STEP_SUMMARY"] = str(tmp_path)

    def execute(step):
        return subprocess.run(
            [BASH, "-eo", "pipefail", "-c", step["run"]],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    sync = next(s for s in canary["steps"] if s.get("name") == "Sync locked project environment")
    probe = next(s for s in canary["steps"] if s.get("id") == "probe")
    summarize = next(
        s for s in canary["steps"] if "check_provider_contracts.py summarize" in s.get("run", "")
    )
    health = next(
        s for s in canary["steps"] if "check_provider_contracts.py health" in s.get("run", "")
    )
    job_failed = False
    if scenario in {"skipped", "setup-failure"}:
        if scenario == "setup-failure":
            assert execute(sync).returncode == 7
            job_failed = True
        env.update(PROBE_OUTCOME="skipped", PROBE_EXIT_CODE="")
    else:
        result = execute(probe)
        assert result.returncode == probe_code
        assert output.read_text().strip() == f"exit_code={probe_code}"
        if result.returncode and probe.get("continue-on-error") != "true":
            job_failed = True
        env.update(
            PROBE_OUTCOME="failure" if result.returncode else "success",
            PROBE_EXIT_CODE=str(probe_code),
        )
    summary_result = execute(summarize)
    health_result = execute(health)
    job_failed |= bool(summary_result.returncode or health_result.returncode)
    assert job_failed is failed, (
        summary_result.stdout + summary_result.stderr + health_result.stdout + health_result.stderr
    )
    if scenario == "drift":
        assert "::error" in summary_result.stdout and health_result.returncode == 0
    if scenario in {
        "skipped",
        "setup-failure",
        "unexpected-exit",
        "unreachable",
        "empty",
        "missing",
        "malformed",
        "no-contracts",
    }:
        assert health_result.returncode != 0
        assert "::error" in health_result.stdout
    if scenario == "missing":
        assert not report_path.exists()
