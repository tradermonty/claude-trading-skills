"""Regression checks for locked orchestration and the independent PR gate."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SYNC = "uv sync --locked --no-install-project --extra dev --extra ci"


def workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


def test_every_project_job_uses_locked_environment():
    for name in ("ci.yml", "fmp-contract-canary.yml", "packaged-deps-nightly.yml"):
        config = workflow(name)
        assert config["permissions"] == {"contents": "read"}
        for job_id, job in config["jobs"].items():
            if job_id in {"market-calendar-compat", "dependency-review", "compatibility"}:
                continue
            steps = job["steps"]
            sync_steps = [step for step in steps if SYNC in step.get("run", "")]
            assert len(sync_steps) == 1, (name, job_id)
            assert 'echo "$PWD/.venv/bin" >> "$GITHUB_PATH"' in sync_steps[0]["run"]
            uv_steps = [step for step in steps if "astral-sh/setup-uv@" in step.get("uses", "")]
            assert len(uv_steps) == 1
            assert uv_steps[0]["with"]["version"] == "0.12.10"
            # Standalone smoke intentionally invokes pip only within its fresh venvs.
            assert all(not step.get("run", "").startswith("pip install") for step in steps)
            assert all("pip install -e" not in step.get("run", "") for step in steps)


def test_cross_platform_jobs_use_locked_environment_without_posix_path_wiring():
    for name in ("ci.yml", "compatibility-nightly.yml"):
        config = workflow(name)
        assert config["permissions"] == {"contents": "read"}
        job = config["jobs"]["compatibility"]
        steps = job["steps"]
        sync_steps = [step for step in steps if SYNC in step.get("run", "")]
        assert len(sync_steps) == 1, name
        assert "GITHUB_PATH" not in sync_steps[0]["run"]
        assert job["env"]["TRADER_MEMORY_CLI_INNER"] == "1"
        uv_steps = [step for step in steps if "astral-sh/setup-uv@" in step.get("uses", "")]
        assert len(uv_steps) == 1
        assert uv_steps[0]["with"]["version"] == "0.12.10"
        command_steps = [step["run"] for step in steps if "uv run" in step.get("run", "")]
        assert command_steps
        assert all("uv run --no-sync" in run for run in command_steps)

    nightly_discover = workflow("compatibility-nightly.yml")["jobs"]["discover"]["steps"]
    sync_steps = [step for step in nightly_discover if SYNC in step.get("run", "")]
    assert len(sync_steps) == 1
    assert 'echo "$PWD/.venv/bin" >> "$GITHUB_PATH"' in sync_steps[0]["run"]


def test_matrix_only_checks_installed_requirements_and_security_uses_python311():
    jobs = workflow("ci.yml")["jobs"]
    runs = [step.get("run", "") for step in jobs["test"]["steps"]]
    assert 'python scripts/ci_test_matrix.py install --check "${{ matrix.id }}"' in runs
    python_steps = [
        step
        for step in jobs["security"]["steps"]
        if "actions/setup-python@" in step.get("uses", "")
    ]
    assert python_steps[0]["with"]["python-version"] == "3.11"


def test_audit_is_blocking_and_uploads_failure_evidence():
    job = workflow("ci.yml")["jobs"]["supply-chain"]
    assert job.get("continue-on-error", "false") == "false"
    runs = [step.get("run", "") for step in job["steps"]]
    assert "python scripts/check_supply_chain.py check" in runs
    assert "python scripts/check_supply_chain.py audit --report supply-chain-audit.json" in runs
    upload = next(step for step in job["steps"] if "upload-artifact@" in step.get("uses", ""))
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "supply-chain-audit.json"


def test_dependency_review_is_strict_pr_only_and_read_only():
    job = workflow("ci.yml")["jobs"]["dependency-review"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job["permissions"] == {"contents": "read"}
    assert job.get("continue-on-error", "false") == "false"
    action = next(
        step for step in job["steps"] if "dependency-review-action@" in step.get("uses", "")
    )
    assert action["with"] == {
        "fail-on-severity": "low",
        "fail-on-scopes": "runtime, development, unknown",
        "license-check": "false",
    }


def test_dependabot_tracks_all_three_manifest_families_weekly():
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    assert {(item["package-ecosystem"], item["directory"]) for item in config["updates"]} == {
        ("uv", "/"),
        ("github-actions", "/"),
        ("bundler", "/docs"),
    }
    assert all(item["schedule"]["interval"] == "weekly" for item in config["updates"])
