"""Offline guided run, decision gate, and resume integrity regressions."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_market_regime_daily.py"
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("guided_regime", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data))


def cli(directory, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--run-dir", str(directory), *args],
        input="",
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("full,score", [(False, 48.5), (True, 55.9)])
def test_cli_pause_resume_and_idempotent_completion(tmp_path, full, score, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "private-key-must-never-be-recorded")
    directory = tmp_path / "run"
    result = cli(directory, *(["--include-top-risk"] if full else []))
    assert result.returncode == 3, result.stderr
    manifest = read(directory / "manifest.json")
    assert manifest["status"] == "AWAITING_DECISION"
    assert manifest["steps"][2]["status"] == ("COMPLETED" if full else "SKIPPED")
    proposal = read(directory / "04_exposure_proposal.json")
    assert proposal["result"]["composite_score"] == score
    assert proposal["run_id"] == manifest["run_id"]
    provenance = read(directory / "01_market_breadth_report.json")["provenance"]
    assert "report_generator.generate_json_report" not in provenance["native_surface"]
    assert "scorer.calculate_composite_score" in provenance["native_surface"]
    assert not (directory / "journal.json").exists()
    stable = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.glob("0*.json")}
    result = cli(directory, "--resume", "--decision", "restrict")
    assert result.returncode == 0, result.stderr
    complete = read(directory / "manifest.json")
    assert complete["status"] == "COMPLETED"
    assert complete["steps"][3]["decision"] == "restrict"
    assert read(directory / "journal.json")["destination"] == "trader-memory-core"
    assert read(directory / "journal.json")["delivery"] == "handoff_only"
    for name, (data, mtime) in stable.items():
        assert (directory / name).read_bytes() == data
        assert (directory / name).stat().st_mtime_ns == mtime
    before = {p.name: p.read_bytes() for p in directory.rglob("*.json")}
    assert cli(directory, "--resume").returncode == 0
    assert cli(directory, "--status").returncode == 0
    assert before == {p.name: p.read_bytes() for p in directory.rglob("*.json")}
    assert cli(directory, "--resume", "--decision", "allow").returncode == 1
    assert all(b"private-key-must-never-be-recorded" not in data for data in before.values())


def test_new_run_never_reuses_existing_directory_or_accepts_early_decision(tmp_path):
    directory = tmp_path / "run"
    assert cli(directory, "--decision", "allow").returncode == 2
    assert not directory.exists()
    directory.mkdir()
    (directory / "unrelated").write_text("keep")
    assert cli(directory).returncode == 1
    assert (directory / "unrelated").read_text() == "keep"


@pytest.mark.parametrize("target", ["01_market_breadth_report.json", "inputs/breadth.json"])
def test_changed_missing_and_cross_run_artifacts_block_before_decision(tmp_path, target):
    a, b = tmp_path / "a", tmp_path / "b"
    assert cli(a).returncode == cli(b).returncode == 3
    path = a / target
    path.write_bytes((b / target).read_bytes() if target.startswith("01") else b"{}")
    result = cli(a, "--resume", "--decision", "allow")
    assert result.returncode == 1
    assert not (a / "journal.json").exists()
    path.unlink()
    assert cli(a, "--resume").returncode == 1


@pytest.mark.parametrize("mutation", ["hash", "run_id", "skip", "complete", "path", "running"])
def test_manifest_forgery_cannot_bypass_gate(tmp_path, mutation):
    directory = tmp_path / mutation
    assert cli(directory).returncode == 3
    path = directory / "manifest.json"
    state = read(path)
    if mutation == "hash":
        output = directory / "01_market_breadth_report.json"
        payload = read(output)
        payload["composite"]["composite_score"] = 100
        save(output, payload)
        state["steps"][0]["output"]["sha256"] = runner.digest(output.read_bytes())
    elif mutation == "run_id":
        state["run_id"] = "other-run"
    elif mutation == "skip":
        state["steps"][0]["status"] = "SKIPPED"
    elif mutation == "complete":
        state["status"] = "COMPLETED"
    elif mutation == "path":
        state["steps"][0]["output"]["path"] = "../outside.json"
    else:
        state["steps"][0]["status"] = "RUNNING"
    save(path, state)
    assert cli(directory, "--resume", "--decision", "allow").returncode == 1
    assert not (directory / "journal.json").exists()


def test_resume_after_between_step_interruption_does_not_duplicate_steps(tmp_path, monkeypatch):
    directory = tmp_path / "run"
    original = runner.after_checkpoint

    def interrupt(state):
        if state["steps"][0]["status"] == "COMPLETED":
            raise KeyboardInterrupt

    monkeypatch.setattr(runner, "after_checkpoint", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.run(directory)
    first = directory / "01_market_breadth_report.json"
    before = first.stat().st_mtime_ns
    monkeypatch.setattr(runner, "after_checkpoint", original)
    assert runner.run(directory, resume=True)["status"] == "AWAITING_DECISION"
    assert first.stat().st_mtime_ns == before


def test_execution_failure_records_failed_and_refuses_implicit_retry(tmp_path, monkeypatch):
    directory = tmp_path / "run"

    def fail(*args, **kwargs):
        raise ValueError("untrusted-provider-data-must-not-be-logged")

    monkeypatch.setattr(runner, "execute_step", fail)
    with pytest.raises(runner.RunError):
        runner.run(directory)
    state = read(directory / "manifest.json")
    assert state["steps"][0]["status"] == "FAILED"
    assert state["status"] == "FAILED"
    assert "untrusted-provider-data" not in (directory / "manifest.json").read_text()
    assert cli(directory, "--resume").returncode == 1


def test_lock_and_symlink_are_never_adopted_or_removed(tmp_path):
    directory = tmp_path / "run"
    assert cli(directory).returncode == 3
    lock = directory / ".lock"
    lock.write_text("existing-owner")
    assert cli(directory, "--resume").returncode == 1
    assert lock.read_text() == "existing-owner"
    lock.unlink()
    output = directory / "01_market_breadth_report.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(output.read_bytes())
    output.unlink()
    output.symlink_to(outside)
    assert cli(directory, "--resume").returncode == 1
    assert outside.exists()


def test_source_fingerprint_mismatch_and_resume_configuration_change(tmp_path, monkeypatch):
    directory = tmp_path / "run"
    assert cli(directory).returncode == 3
    assert cli(directory, "--resume", "--include-top-risk").returncode == 2
    monkeypatch.setattr(runner, "source_fingerprint", lambda: {"changed": "revision"})
    with pytest.raises(runner.RunError, match="source"):
        runner.run(directory, resume=True)


def test_invalid_manifest_diagnostic_does_not_echo_contents(tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "manifest.json").write_text('{"private_field": "do-not-echo",')
    result = cli(directory, "--resume")
    assert result.returncode == 1
    assert "do-not-echo" not in result.stdout + result.stderr


@pytest.mark.parametrize("kind,code", [("missing", 1), ("invalid", 1), ("dependency", 2)])
def test_readiness_failures_have_safe_cli_diagnostics(tmp_path, monkeypatch, capsys, kind, code):
    import workflow_replay as replay

    def failed_contract():
        if kind == "dependency":
            try:
                raise ImportError("private-import-path")
            except ImportError as error:
                raise replay.ReplayError("private-helper-data") from error
        raise replay.ReplayError("private-fixture-data")

    monkeypatch.setattr(runner, "contract", failed_contract)
    directory = tmp_path / "run"
    assert runner.main(["--run-dir", str(directory)]) == code
    assert not directory.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private-" not in captured.err
    assert "Traceback" not in captured.err
    assert ("missing runtime dependencies" if code == 2 else "BLOCKED") in captured.err


def test_real_invalid_fixture_fails_readiness_before_allocating_run(tmp_path, monkeypatch, capsys):
    import workflow_replay as replay

    original = replay._load_json

    def invalid_fixture(path, label):
        if path.name == "breadth-components.json":
            return {"schema_version": 1, "kind": "private-fixture-content"}
        return original(path, label)

    monkeypatch.setattr(replay, "_load_json", invalid_fixture)
    directory = tmp_path / "run"
    assert runner.main(["--run-dir", str(directory)]) == 1
    assert not directory.exists()
    assert "private-fixture" not in capsys.readouterr().err
