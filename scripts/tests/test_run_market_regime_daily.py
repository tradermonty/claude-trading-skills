"""Offline guided run, decision gate, and resume integrity regressions."""

import contextlib
import importlib.util
import io
import json
import shutil
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


# ======================================================================
# Issue #709: decision diff, revisit conditions, day-2 fictional fixtures
# ======================================================================

import market_regime_decision_diff as dd  # noqa: E402

MARKER = "SECRET-ECHO-MARKER"
LEGACY_MANIFEST_KEYS = {
    "schema_version",
    "workflow_id",
    "run_id",
    "created_at",
    "evaluation_at",
    "include_top_risk",
    "readiness",
    "sources",
    "inputs",
    "status",
    "limitations",
    "steps",
    "journal",
}
LEGACY_GATE_KEYS = {
    "step",
    "skill",
    "status",
    "started_at",
    "completed_at",
    "inputs",
    "output",
    "decision",
    "decision_at",
}
LEGACY_JOURNAL_KEYS = {
    "schema_version",
    "run_id",
    "fictional",
    "destination",
    "delivery",
    "decision",
    "recorded_at",
    "proposal",
    "limitations",
}
DEFAULT_CONDITIONS = [
    {
        "id": "breadth-weakens",
        "label": "Breadth composite falls below 60",
        "metric": "breadth.composite_score",
        "comparator": "lt",
        "threshold": 60,
    },
    {
        "id": "uptrend-weakens",
        "label": "Uptrend composite falls below 60",
        "metric": "uptrend.composite_score",
        "comparator": "lt",
        "threshold": 60,
    },
    {
        "id": "top-risk-rises",
        "label": "Top-risk composite reaches 50",
        "metric": "top_risk.composite_score",
        "comparator": "ge",
        "threshold": 50,
    },
]


class Out:
    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def call(directory, *args):
    """Run the CLI in-process (fast) and capture its exit code and streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = runner.main(["--run-dir", str(directory), *map(str, args)])
        except SystemExit as exit_:
            code = exit_.code
    return Out(code, out.getvalue(), err.getvalue())


def conditions_file(directory, conditions=None, name="conditions.json"):
    path = Path(directory) / name
    document = {
        "schema_version": 1,
        "conditions": DEFAULT_CONDITIONS if conditions is None else conditions,
    }
    path.write_text(json.dumps(document))
    return path


def snapshot_tree(directory):
    return {
        str(p.relative_to(directory)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(Path(directory).rglob("*"))
        if p.is_file()
    }


def rewrite_manifest(directory, mutate):
    path = Path(directory) / "manifest.json"
    state = read(path)
    mutate(state)
    save(path, state)


def rehash(directory, state_key, relative):
    """Re-record a tampered artifact's hash so only the semantic checks can catch it."""
    directory = Path(directory)

    def mutate(state):
        entry = state[state_key] if state_key != "gate_output" else state["steps"][3]["output"]
        entry["sha256"] = runner.digest((directory / relative).read_bytes())

    rewrite_manifest(directory, mutate)


@pytest.fixture(scope="module")
def day1_template(tmp_path_factory):
    """A completed full-path day-1 run that recorded the three revisit conditions."""
    base = tmp_path_factory.mktemp("day1-template")
    directory = base / "d1"
    code = call(directory, "--include-top-risk").returncode
    assert code == 3
    file = conditions_file(base)
    done = call(directory, "--resume", "--decision", "restrict", "--revisit-conditions", file)
    assert done.returncode == 0, done.stderr
    return directory


@pytest.fixture(scope="module")
def plain_template(tmp_path_factory):
    """A completed default (required-only) run made without any new option."""
    directory = tmp_path_factory.mktemp("plain-template") / "p1"
    assert call(directory).returncode == 3
    assert call(directory, "--resume", "--decision", "allow").returncode == 0
    return directory


def copy_run(source, destination):
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    return destination


def day2(directory, previous, *extra):
    return call(directory, "--fixture-set", "day-2", "--previous-run-dir", previous, *extra)


# ---------------------------------------------------------------- AC1


def test_two_day_replay_produces_changed_unchanged_not_evaluable(tmp_path):
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    assert cli(d1, "--include-top-risk").returncode == 3
    file = conditions_file(tmp_path)
    done = cli(d1, "--resume", "--decision", "restrict", "--revisit-conditions", str(file))
    assert done.returncode == 0, done.stderr
    journal = read(d1 / "journal.json")
    assert journal["schema_version"] == 2
    assert {"revisit_conditions", "data_as_of", "unevaluated", "decision_diff"} <= set(journal)
    assert journal["decision_diff"] is None
    values = {c["id"]: c["value_at_decision"] for c in journal["revisit_conditions"]}
    assert values == {"breadth-weakens": 66.1, "uptrend-weakens": 71.7, "top-risk-rises": 38.0}
    assert journal["data_as_of"]["inputs"]["breadth"] == "2026-01-14T21:00:00+00:00"
    day1_bytes = snapshot_tree(d1)

    result = cli(d2, "--fixture-set", "day-2", "--previous-run-dir", str(d1))
    assert result.returncode == 3, result.stderr
    diff = read(d2 / "decision_diff.json")
    by_id = {c["id"]: c for c in diff["conditions"]}
    assert diff["first_run"] is False
    assert by_id["breadth-weakens"]["status"] == "changed"
    assert by_id["uptrend-weakens"]["status"] == "unchanged"
    assert by_id["top-risk-rises"]["status"] == "not_evaluable"
    assert by_id["top-risk-rises"]["reason"] == "input_missing_today"
    assert diff["summary"] == {"changed": 1, "unchanged": 1, "not_evaluable": 1}
    assert diff["columns"]["previous_decision"]["decision"] == "restrict"
    assert diff["columns"]["changed_today"] == ["breadth-weakens"]
    confirm_ids = {i.get("id") for i in diff["columns"]["confirm"]}
    assert {"breadth-weakens", "top-risk-rises"} <= confirm_ids
    assert "Decision diff (read-only; it never records a decision):" in result.stdout
    assert "[changed] breadth-weakens" in result.stdout
    assert snapshot_tree(d1) == day1_bytes
    assert not (d1 / ".lock").exists()

    resumed = cli(d2, "--resume", "--decision", "allow")
    assert resumed.returncode == 0, resumed.stderr
    manifest = read(d2 / "manifest.json")
    assert read(d2 / "journal.json")["decision_diff"] == manifest["decision_diff"]
    assert read(d2 / "journal.json")["schema_version"] == 2
    stable = snapshot_tree(d2)
    assert cli(d2, "--resume").returncode == 0
    assert cli(d2, "--status").returncode == 0
    assert snapshot_tree(d2) == stable


@pytest.mark.parametrize("full,top_risk,exposure", [(False, None, 40.5), (True, 44.2, 48.3)])
def test_day2_pinned_composites(tmp_path, full, top_risk, exposure):
    d2 = tmp_path / "d2"
    extra = ["--include-top-risk"] if full else []
    assert call(d2, "--fixture-set", "day-2", *extra).returncode == 3
    assert read(d2 / "01_market_breadth_report.json")["composite"]["composite_score"] == 50.4
    assert read(d2 / "02_uptrend_report.json")["composite"]["composite_score"] == 71.5
    if full:
        assert read(d2 / "03_top_risk_report.json")["composite"]["composite_score"] == top_risk
    proposal = read(d2 / "04_exposure_proposal.json")["result"]
    assert proposal["composite_score"] == exposure
    assert proposal["recommendation"] == "REDUCE_ONLY"


def test_day2_fixture_set_is_fixed_on_resume_and_recorded(tmp_path, day1_template):
    d2 = tmp_path / "d2"
    assert day2(d2, day1_template).returncode == 3
    assert read(d2 / "manifest.json")["fixture_set"] == "day-2"
    assert call(d2, "--resume", "--fixture-set", "day-2").returncode == 2
    assert call(d2, "--status").returncode == 3
    assert call(d2, "--resume").returncode == 3
    for forged in ("delete", "day-1", "day-9"):
        copy = copy_run(d2, tmp_path / f"forged-{forged}")

        def mutate(state, forged=forged):
            if forged == "delete":
                del state["fixture_set"]
            else:
                state["fixture_set"] = forged

        rewrite_manifest(copy, mutate)
        assert call(copy, "--resume", "--decision", "allow").returncode == 1
        assert not (copy / "journal.json").exists()


def test_day1_default_manifest_has_no_fixture_set_key(day1_template):
    assert "fixture_set" not in read(day1_template / "manifest.json")


# ---------------------------------------------------------------- AC2

UNUSABLE = [
    "not_found",
    "invalid_empty",
    "invalid_not_json",
    "invalid_deep_json",
    "invalid_oversized",
    "other_workflow",
    "incomplete",
    "integrity_mismatch",
    "unavailable_lock",
    "unavailable_symlink",
    "not_earlier",
]
EXPECTED_STATUS = {
    "invalid_empty": "invalid",
    "invalid_not_json": "invalid",
    "invalid_deep_json": "invalid",
    "invalid_oversized": "invalid",
    "unavailable_lock": "unavailable",
    "unavailable_symlink": "unavailable",
}


def build_unusable(case, tmp_path, day1_template):
    target = tmp_path / "prev"
    if case == "not_found":
        return target
    if case.startswith("invalid") or case == "unavailable_lock":
        target.mkdir()
    if case == "invalid_not_json":
        (target / "manifest.json").write_text('{"x": "' + MARKER + '",')
    elif case == "invalid_deep_json":
        (target / "manifest.json").write_text("[" * 200000)
    elif case == "invalid_oversized":
        (target / "manifest.json").write_text('{"p": "' + "a" * (1024 * 1024 + 10) + '"}')
    elif case == "unavailable_lock":
        copy_run(day1_template, tmp_path / "locked")
        (tmp_path / "locked" / ".lock").write_text("existing-owner")
        return tmp_path / "locked"
    elif case == "unavailable_symlink":
        target.symlink_to(day1_template)
    elif case == "other_workflow":
        copy_run(day1_template, target)
        rewrite_manifest(target, lambda s: s.update(workflow_id=MARKER))
    elif case == "incomplete":
        assert call(target, "--include-top-risk").returncode == 3
    elif case == "integrity_mismatch":
        copy_run(day1_template, target)
        out = target / "01_market_breadth_report.json"
        payload = read(out)
        payload["composite"]["composite_score"] = 1
        save(out, payload)
    elif case == "not_earlier":
        assert call(target, "--fixture-set", "day-2").returncode == 3
        assert call(target, "--resume", "--decision", "allow").returncode == 0
    return target


@pytest.mark.parametrize("case", UNUSABLE)
def test_previous_run_unusable_continues_as_first_run(tmp_path, day1_template, case):
    target = build_unusable(case, tmp_path, day1_template)
    before = snapshot_tree(target) if target.exists() and not target.is_symlink() else None
    run_dir = tmp_path / "today"
    if case == "not_earlier":
        result = call(run_dir, "--previous-run-dir", target)  # day-1 today, previous is day-2
    else:
        result = day2(run_dir, target)
    assert result.returncode == 3, result.stderr
    diff = read(run_dir / "decision_diff.json")
    expected = EXPECTED_STATUS.get(case, case)
    assert diff["first_run"] is True
    assert diff["previous"]["status"] == expected
    assert diff["previous"]["message"] in dd.STATUS_MESSAGES[expected]
    assert diff["conditions"] == []
    assert diff["columns"]["confirm"][0]["item"] == "first_run"
    assert MARKER not in result.stdout + result.stderr
    assert MARKER not in (run_dir / "decision_diff.json").read_text()
    assert MARKER not in (run_dir / "inputs/previous_run.json").read_text()
    if case == "unavailable_lock":
        assert (target / ".lock").read_text() == "existing-owner"
    if before is not None:
        assert snapshot_tree(target) == before


def test_unexpected_exception_while_classifying_is_a_first_run(
    tmp_path, day1_template, monkeypatch
):
    original = runner.verify

    def explode(directory, state, setup):
        if Path(directory).name == "d1-copy":
            raise ZeroDivisionError(MARKER)
        return original(directory, state, setup)

    previous = copy_run(day1_template, tmp_path / "d1-copy")
    monkeypatch.setattr(runner, "verify", explode)
    result = day2(tmp_path / "today", previous)
    assert result.returncode == 3, result.stderr
    assert read(tmp_path / "today/decision_diff.json")["previous"]["status"] == "invalid"
    assert MARKER not in result.stdout + result.stderr


def test_previous_run_source_fingerprint_change_is_not_loaded(tmp_path, monkeypatch):
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    runner.run(d1)
    runner.run(d1, resume=True, decision="allow")
    monkeypatch.setattr(runner, "source_fingerprint", lambda: {"changed": "revision"})
    runner.run(d2, fixture_set="day-2", previous_run_dir=d1)
    snapshot = read(d2 / "inputs/previous_run.json")
    assert snapshot["previous"]["status"] == "source_changed"
    assert read(d2 / "decision_diff.json")["first_run"] is True


def test_previous_v1_record_without_conditions_is_loaded_with_explicit_notice(
    tmp_path, plain_template
):
    assert read(plain_template / "journal.json")["schema_version"] == 1
    d2 = tmp_path / "d2"
    assert day2(d2, plain_template).returncode == 3
    diff = read(d2 / "decision_diff.json")
    assert diff["previous"]["status"] == "loaded"
    assert diff["conditions"] == []
    assert any(i["item"] == "no_revisit_conditions" for i in diff["columns"]["confirm"])
    assert diff["columns"]["previous_decision"]["decision"] == "allow"


def test_lock_created_during_classification_makes_previous_unavailable(
    tmp_path, day1_template, monkeypatch
):
    previous = copy_run(day1_template, tmp_path / "prev")
    monkeypatch.setattr(
        runner, "after_previous_classification", lambda d: (Path(d) / ".lock").write_text("x")
    )
    assert day2(tmp_path / "today", previous).returncode == 3
    assert read(tmp_path / "today/decision_diff.json")["previous"]["status"] == "unavailable"
    assert (previous / ".lock").read_text() == "x"


# ---------------------------------------------------------------- AC3


def test_stale_inputs_never_classified_unchanged(tmp_path, day1_template):
    d2 = tmp_path / "d2"
    assert call(d2, "--include-top-risk", "--previous-run-dir", day1_template).returncode == 3
    diff = read(d2 / "decision_diff.json")
    assert diff["previous"]["status"] == "loaded"
    assert {c["status"] for c in diff["conditions"]} == {"not_evaluable"}
    assert {c["reason"] for c in diff["conditions"]} == {"input_not_refreshed"}
    assert diff["summary"]["unchanged"] == 0


def test_missing_top_risk_is_not_evaluable_in_both_directions(tmp_path, day1_template):
    # previous has top-risk, today does not -> input_missing_today (see the AC1 test).
    d2 = tmp_path / "d2"
    assert day2(d2, day1_template).returncode == 3
    top = next(c for c in read(d2 / "decision_diff.json")["conditions"] if "top" in c["id"])
    assert top["reason"] == "input_missing_today"
    assert top["detail"] == "optional_step_not_selected"
    # previous skipped top-risk, today includes it -> no_baseline_value.
    p = tmp_path / "p"
    assert call(p).returncode == 3
    file = conditions_file(tmp_path, [DEFAULT_CONDITIONS[2]], "only-top.json")
    assert call(p, "--resume", "--decision", "allow", "--revisit-conditions", file).returncode == 0
    d3 = tmp_path / "d3"
    assert (
        call(d3, "--fixture-set", "day-2", "--include-top-risk", "--previous-run-dir", p).returncode
        == 3
    )
    top = read(d3 / "decision_diff.json")["conditions"][0]
    assert top["status"] == "not_evaluable" and top["reason"] == "no_baseline_value"


def test_exposure_recommendation_condition_end_to_end(tmp_path):
    p = tmp_path / "p"
    assert call(p).returncode == 3
    cond = [
        {
            "id": "stays-reduce-only",
            "label": "Recommendation is REDUCE_ONLY",
            "metric": "exposure.recommendation",
            "comparator": "eq",
            "threshold": "REDUCE_ONLY",
        }
    ]
    file = conditions_file(tmp_path, cond)
    assert (
        call(p, "--resume", "--decision", "restrict", "--revisit-conditions", file).returncode == 0
    )
    d2 = tmp_path / "d2"
    assert day2(d2, p).returncode == 3
    entry = read(d2 / "decision_diff.json")["conditions"][0]
    assert entry["metric"] == "exposure.recommendation"
    assert entry["status"] in {"changed", "unchanged"}
    assert entry["previous"]["value"] == "REDUCE_ONLY"


# ------------------------------------------------- integrity of new artifacts


def day2_awaiting(tmp_path, previous):
    directory = tmp_path / "awaiting"
    assert day2(directory, previous).returncode == 3
    return directory


def forge_diff_bytes(d):
    path = d / "decision_diff.json"
    path.write_bytes(path.read_bytes() + b" ")


def forge_diff_rehashed(d):
    path = d / "decision_diff.json"
    value = read(path)
    value["summary"]["changed"] = 99
    save(path, value)
    rewrite_manifest(
        d, lambda s: s["decision_diff"].update(sha256=runner.digest(path.read_bytes()))
    )


def forge_snapshot_bytes(d):
    path = d / "inputs/previous_run.json"
    path.write_bytes(path.read_bytes() + b" ")


def forge_snapshot_control_char(d):
    path = d / "inputs/previous_run.json"
    value = read(path)
    value["previous"]["revisit_conditions"][0]["label"] = "bad\x07label"
    save(path, value)
    rewrite_manifest(d, lambda s: s["previous_run"].update(sha256=runner.digest(path.read_bytes())))


def forge_record_deleted(d):
    rewrite_manifest(d, lambda s: s.pop("decision_diff"))


@pytest.mark.parametrize(
    "forge",
    [
        forge_diff_bytes,
        forge_diff_rehashed,
        forge_snapshot_bytes,
        forge_snapshot_control_char,
        forge_record_deleted,
    ],
)
def test_decision_diff_artifacts_forgery_blocks_resume(tmp_path, day1_template, forge):
    d2 = day2_awaiting(tmp_path, day1_template)
    forge(d2)
    assert call(d2, "--resume", "--decision", "allow").returncode == 1
    assert not (d2 / "journal.json").exists()
    assert call(d2, "--status").returncode == 1


def test_decision_diff_planted_without_previous_option_blocks_resume(tmp_path):
    d = tmp_path / "plain"
    assert call(d).returncode == 3
    (d / "decision_diff.json").write_text("{}")
    assert call(d, "--resume", "--decision", "allow").returncode == 1
    assert not (d / "journal.json").exists()
    (d / "decision_diff.json").unlink()
    (d / "inputs/previous_run.json").write_text("{}")
    assert call(d, "--resume", "--decision", "allow").returncode == 1


def test_tampered_decision_record_value_blocks_completed_run(tmp_path, day1_template):
    d = copy_run(day1_template, tmp_path / "completed")
    journal_path = d / "journal.json"
    journal = read(journal_path)
    journal["revisit_conditions"][0]["value_at_decision"] = 12.3
    save(journal_path, journal)
    rewrite_manifest(
        d, lambda s: s["journal"].update(sha256=runner.digest(journal_path.read_bytes()))
    )
    assert call(d, "--status").returncode == 1

    d = copy_run(day1_template, tmp_path / "completed2")

    def tamper(state):
        state["steps"][3]["decision_record"]["revisit_conditions"][0]["value_at_decision"] = 12.3

    rewrite_manifest(d, tamper)
    assert call(d, "--resume").returncode == 1


def test_decision_record_cannot_precede_the_gate(tmp_path):
    d = tmp_path / "plain"
    assert call(d).returncode == 3
    rewrite_manifest(d, lambda s: s["steps"][3].update(decision_record={}))
    assert call(d, "--resume").returncode == 1


def test_interruption_during_diff_publication_requires_new_run(
    tmp_path, day1_template, monkeypatch
):
    d2 = tmp_path / "d2"

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "build_decision_diff", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.run(d2, fixture_set="day-2", previous_run_dir=day1_template)
    state = read(d2 / "manifest.json")
    assert state["steps"][3]["status"] == "RUNNING"
    assert (d2 / "04_exposure_proposal.json").exists()
    assert not (d2 / "decision_diff.json").exists()
    assert not (d2 / ".lock").exists()
    assert call(d2, "--resume").returncode == 1

    def fail(*args, **kwargs):
        raise ValueError(MARKER)

    monkeypatch.setattr(runner, "build_decision_diff", fail)
    d3 = tmp_path / "d3"
    with pytest.raises(runner.RunError):
        runner.run(d3, fixture_set="day-2", previous_run_dir=day1_template)
    state = read(d3 / "manifest.json")
    assert state["steps"][3]["status"] == "FAILED"
    assert MARKER not in (d3 / "manifest.json").read_text()
    assert call(d3, "--resume").returncode == 1


# ----------------------------------------------- revisit conditions input


def bad_conditions_variants():
    def doc(**changes):
        cond = dict(DEFAULT_CONDITIONS[0], label=MARKER)
        cond.update(changes)
        return json.dumps({"schema_version": 1, "conditions": [cond]})

    many = [dict(DEFAULT_CONDITIONS[0], id=f"c{i}", label=MARKER) for i in range(21)]
    return {
        "unknown_metric": doc(metric="made.up"),
        "bad_comparator": doc(comparator="approx"),
        "bool_threshold": doc(threshold=True),
        "nan": doc().replace("60", "NaN"),
        "string_threshold": doc(threshold="60"),
        "numeric_on_recommendation": doc(
            metric="exposure.recommendation", comparator="eq", threshold=5
        ),
        "extra_key": doc(extra=1),
        "non_printable": doc(label=MARKER + "\x07"),
        "too_many": json.dumps({"schema_version": 1, "conditions": many}),
        "duplicate_id_pair": json.dumps(
            {"schema_version": 1, "conditions": [dict(DEFAULT_CONDITIONS[0], label=MARKER)] * 2}
        ),
        "duplicate_json_key": '{"schema_version": 1, "schema_version": 1, "conditions": [], '
        f'"x": "{MARKER}"' + "}",
        "deep_nesting": "[" * 200000,
        "oversized": '{"schema_version": 1, "conditions": [], "pad": "' + "a" * 70000 + '"}',
    }


@pytest.mark.parametrize("variant", sorted(bad_conditions_variants()))
def test_invalid_revisit_conditions_keep_run_paused(tmp_path, variant):
    d = tmp_path / "run"
    assert call(d).returncode == 3
    file = tmp_path / "bad.json"
    file.write_text(bad_conditions_variants()[variant])
    result = call(d, "--resume", "--decision", "allow", "--revisit-conditions", file)
    assert result.returncode == 1
    assert read(d / "manifest.json")["status"] == "AWAITING_DECISION"
    assert not (d / "journal.json").exists()
    assert MARKER not in result.stdout + result.stderr


def test_missing_and_symlinked_conditions_file_keep_run_paused(tmp_path):
    d = tmp_path / "run"
    assert call(d).returncode == 3
    missing = call(
        d, "--resume", "--decision", "allow", "--revisit-conditions", tmp_path / "nope.json"
    )
    assert missing.returncode == 1
    real = conditions_file(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    linked = call(d, "--resume", "--decision", "allow", "--revisit-conditions", link)
    assert linked.returncode == 1
    assert read(d / "manifest.json")["status"] == "AWAITING_DECISION"
    assert not (d / "journal.json").exists()


def test_condition_already_met_at_decision_warns_and_is_flagged_next_day(tmp_path):
    d1 = tmp_path / "d1"
    assert call(d1).returncode == 3
    met = [dict(DEFAULT_CONDITIONS[0], id="already-met", threshold=90)]  # 66.1 < 90 holds
    file = conditions_file(tmp_path, met)
    done = call(d1, "--resume", "--decision", "restrict", "--revisit-conditions", file)
    assert done.returncode == 0
    assert "already-met" in done.stdout and "WARNING" in done.stdout
    d2 = tmp_path / "d2"
    assert day2(d2, d1).returncode == 3
    items = read(d2 / "decision_diff.json")["columns"]["confirm"]
    assert {"item": "condition_already_met_at_decision", "id": "already-met"} in items


def test_empty_conditions_list_is_recorded_explicitly(tmp_path):
    d1 = tmp_path / "d1"
    assert call(d1).returncode == 3
    file = conditions_file(tmp_path, [])
    assert call(d1, "--resume", "--decision", "allow", "--revisit-conditions", file).returncode == 0
    assert read(d1 / "journal.json")["revisit_conditions"] == []


def test_tty_posture_with_previous_run_records_null_conditions(
    tmp_path, day1_template, monkeypatch
):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty(""))
    monkeypatch.setattr("builtins.input", lambda prompt="": "cash-priority")
    d2 = tmp_path / "d2"
    assert day2(d2, day1_template).returncode == 0
    journal = read(d2 / "journal.json")
    assert journal["schema_version"] == 2 and journal["revisit_conditions"] is None
    assert journal["decision"] == "cash-priority"


def test_status_prints_the_decision_diff_block(tmp_path, day1_template):
    d2 = day2_awaiting(tmp_path, day1_template)
    out = call(d2, "--status")
    assert out.returncode == 3
    assert "Decision diff (read-only; it never records a decision):" in out.stdout
    assert "[not_evaluable] top-risk-rises" in out.stdout


# ------------------------------------------------------ CLI argument rules


@pytest.mark.parametrize(
    "args",
    [
        ["--resume", "--revisit-conditions", "x.json"],
        ["--revisit-conditions", "x.json"],
        ["--resume", "--fixture-set", "day-1"],
        ["--resume", "--fixture-set", "day-2"],
        ["--status", "--fixture-set", "day-2"],
        ["--resume", "--previous-run-dir", "x"],
        ["--status", "--previous-run-dir", "x"],
        ["--resume", "--previous-runs-root", "x"],
        ["--previous-run-dir", "x", "--previous-runs-root", "y"],
        ["--fixture-set", "day-3"],
    ],
)
def test_new_flag_argument_rules(tmp_path, args):
    d = tmp_path / "run"
    assert call(d, *args).returncode == 2
    assert not d.exists()


def test_run_rejects_creation_only_arguments_on_resume(tmp_path):
    d = tmp_path / "run"
    runner.run(d)
    for kwargs in (
        {"fixture_set": "day-2"},
        {"previous_run_dir": tmp_path},
        {"previous_runs_root": tmp_path},
    ):
        with pytest.raises(runner.RunError):
            runner.run(d, resume=True, **kwargs)


def test_day2_fixture_failure_blocks_before_allocating_run(tmp_path, monkeypatch, capsys):
    import workflow_replay as replay

    original = replay._load_json

    def invalid_fixture(path, label):
        if path.parent.name == "guided-day-2" and path.name == "breadth-components.json":
            return {"schema_version": 1, "kind": "private-fixture-content"}
        return original(path, label)

    monkeypatch.setattr(replay, "_load_json", invalid_fixture)
    d = tmp_path / "run"
    assert runner.main(["--run-dir", str(d), "--fixture-set", "day-2"]) == 1
    assert not d.exists()
    assert "private-fixture" not in capsys.readouterr().err


# ------------------------------------------------ nested / ancestor guards


def test_run_directory_inside_another_run_is_refused(tmp_path, plain_template):
    d1 = copy_run(plain_template, tmp_path / "root" / "d1")
    before = snapshot_tree(d1)
    for extra in ([], ["--previous-runs-root", str(tmp_path / "root")]):
        result = call(d1 / "sub", *extra)
        assert result.returncode == 1
        assert not (d1 / "sub").exists()
    assert snapshot_tree(d1) == before


def test_previous_dir_equal_or_ancestor_of_run_dir_is_refused(tmp_path):
    outer = tmp_path / "outer"
    outer.mkdir()
    assert call(outer / "run", "--previous-run-dir", outer).returncode == 1
    assert not (outer / "run").exists()
    assert call(outer, "--previous-run-dir", outer).returncode == 1


# ----------------------------------------------- --previous-runs-root mode


def make_root(tmp_path, count=2):
    root = tmp_path / "root"
    root.mkdir()
    dirs = []
    for i in range(count):
        d = root / f"r{i}"
        assert call(d).returncode == 3
        assert call(d, "--resume", "--decision", "allow").returncode == 0
        dirs.append(d)
    return root, dirs


def day2_root(tmp_path, root, name="today", *extra):
    return call(tmp_path / name, "--fixture-set", "day-2", "--previous-runs-root", root, *extra)


def test_root_picks_latest_decision_among_completed_runs(tmp_path):
    root, (older, newer) = make_root(tmp_path)
    assert day2_root(tmp_path, root).returncode == 3
    snapshot = read(tmp_path / "today/inputs/previous_run.json")
    assert snapshot["previous"]["run_id"] == read(newer / "manifest.json")["run_id"]
    assert snapshot["selection"] == {"mode": "root", "candidates": 2, "skipped_unreadable": 0}


def test_root_tie_is_ambiguous_and_nothing_is_classified(tmp_path):
    root, (a, b) = make_root(tmp_path)
    decision_at = read(a / "manifest.json")["steps"][3]["decision_at"]
    rewrite_manifest(b, lambda s: s["steps"][3].update(decision_at=decision_at))
    assert day2_root(tmp_path, root).returncode == 3
    snapshot = read(tmp_path / "today/inputs/previous_run.json")
    assert snapshot["previous"]["status"] == "ambiguous"
    assert snapshot["selection"]["candidates"] == 2
    assert "run_id" not in snapshot["previous"]
    assert read(tmp_path / "today/decision_diff.json")["first_run"] is True


def test_root_empty_and_missing_have_distinct_messages(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert day2_root(tmp_path, empty, "t1").returncode == 3
    previous = read(tmp_path / "t1/inputs/previous_run.json")["previous"]
    assert previous["status"] == "not_found"
    assert previous["message"] == "no completed earlier run found under the root"
    assert day2_root(tmp_path, tmp_path / "absent", "t2").returncode == 3
    previous = read(tmp_path / "t2/inputs/previous_run.json")["previous"]
    assert previous["status"] == "not_found"
    assert previous["message"] == "previous runs root not found"


def test_root_skips_incomplete_runs_even_when_newer(tmp_path):
    root, (only,) = make_root(tmp_path, 1)
    assert call(root / "awaiting", "--fixture-set", "day-2").returncode == 3
    assert day2_root(tmp_path, root).returncode == 3
    snapshot = read(tmp_path / "today/inputs/previous_run.json")
    assert snapshot["previous"]["run_id"] == read(only / "manifest.json")["run_id"]
    assert snapshot["selection"]["candidates"] == 1
    assert snapshot["selection"]["skipped_unreadable"] == 0


def test_root_second_day2_run_picks_first_and_reports_not_refreshed(tmp_path):
    root, _ = make_root(tmp_path, 1)
    file = conditions_file(tmp_path, [DEFAULT_CONDITIONS[0]])
    first = root / "day2-a"
    assert call(first, "--fixture-set", "day-2", "--previous-runs-root", root).returncode == 3
    done = call(first, "--resume", "--decision", "restrict", "--revisit-conditions", file)
    assert done.returncode == 0, done.stderr
    assert day2_root(tmp_path, root).returncode == 3
    diff = read(tmp_path / "today/decision_diff.json")
    assert diff["previous"]["run_id"] == read(first / "manifest.json")["run_id"]
    assert [c["reason"] for c in diff["conditions"]] == ["input_not_refreshed"]


def test_root_newest_tampered_is_not_replaced_by_older_run(tmp_path):
    root, (older, newer) = make_root(tmp_path)
    out = newer / "01_market_breadth_report.json"
    payload = read(out)
    payload["composite"]["composite_score"] = 1
    save(out, payload)
    older_bytes = snapshot_tree(older)
    older_id = read(older / "manifest.json")["run_id"]
    result = day2_root(tmp_path, root)
    assert result.returncode == 3
    snapshot = read(tmp_path / "today/inputs/previous_run.json")
    assert snapshot["previous"]["status"] == "integrity_mismatch"
    assert snapshot["selection"]["candidates"] == 2
    assert snapshot_tree(older) == older_bytes
    blob = result.stdout + (tmp_path / "today/decision_diff.json").read_text()
    blob += (tmp_path / "today/manifest.json").read_text()
    assert older_id not in blob


def test_root_symlink_and_unreadable_children(tmp_path):
    root, _ = make_root(tmp_path, 1)
    junk = root / "junk"
    junk.mkdir()
    (junk / "manifest.json").write_text("not json")
    assert day2_root(tmp_path, root, "t1").returncode == 3
    assert read(tmp_path / "t1/inputs/previous_run.json")["selection"]["skipped_unreadable"] == 1
    link = tmp_path / "root-link"
    link.symlink_to(root)
    assert day2_root(tmp_path, link, "t2").returncode == 3
    assert read(tmp_path / "t2/inputs/previous_run.json")["previous"]["status"] == "unavailable"


def test_root_counts_directories_only_and_caps_at_500(tmp_path):
    root, _ = make_root(tmp_path, 2)
    for i in range(600):
        (root / f"file-{i}.txt").write_text("x")
    assert day2_root(tmp_path, root, "t1").returncode == 3
    assert read(tmp_path / "t1/inputs/previous_run.json")["previous"]["status"] == "loaded"
    crowded = tmp_path / "crowded"
    crowded.mkdir()
    for i in range(501):
        (crowded / f"d{i}").mkdir()
    assert day2_root(tmp_path, crowded, "t2").returncode == 3
    previous = read(tmp_path / "t2/inputs/previous_run.json")["previous"]
    assert previous["status"] == "unavailable"
    assert "dedicated root" in previous["message"]


# ------------------------------------------------------ steady-state chain


def test_day1_day2_day3_chain_and_tampered_middle_run(tmp_path, day1_template):
    d2 = tmp_path / "d2"
    assert day2(d2, day1_template).returncode == 3
    file = conditions_file(tmp_path, DEFAULT_CONDITIONS[:2])
    assert (
        call(d2, "--resume", "--decision", "restrict", "--revisit-conditions", file).returncode == 0
    )
    d3 = tmp_path / "d3"
    assert day2(d3, d2).returncode == 3
    diff = read(d3 / "decision_diff.json")
    assert diff["previous"]["status"] == "loaded"
    assert {c["reason"] for c in diff["conditions"]} == {"input_not_refreshed"}
    assert call(d3, "--status").returncode == 3
    assert call(d2, "--status").returncode == 0

    tampered = copy_run(d2, tmp_path / "d2-tampered")
    path = tampered / "decision_diff.json"
    path.write_bytes(path.read_bytes() + b" ")
    d4 = tmp_path / "d4"
    assert day2(d4, tampered).returncode == 3
    assert read(d4 / "decision_diff.json")["previous"]["status"] == "integrity_mismatch"


# ----------------------------------------------- unchanged default behaviour


def test_default_run_artifacts_unchanged_without_new_options(plain_template):
    manifest = read(plain_template / "manifest.json")
    assert set(manifest) == LEGACY_MANIFEST_KEYS
    assert set(manifest["steps"][3]) == LEGACY_GATE_KEYS
    journal = read(plain_template / "journal.json")
    assert set(journal) == LEGACY_JOURNAL_KEYS and journal["schema_version"] == 1
    assert sorted(p.name for p in (plain_template / "inputs").iterdir()) == [
        "breadth.json",
        "top_risk.json",
        "uptrend.json",
    ]
    assert not (plain_template / "decision_diff.json").exists()


# ---------------------------------------------------- review round 1 additions


def retamper_record(directory, mutate):
    """Edit the stored decision record and keep the journal and its hash consistent."""
    rewrite_manifest(directory, lambda s: mutate(s["steps"][3]["decision_record"]))
    state = read(directory / "manifest.json")
    path = directory / "journal.json"
    save(path, runner.journal(state))
    rewrite_manifest(
        directory, lambda s: s["journal"].update(sha256=runner.digest(path.read_bytes()))
    )


def _shift_value(record):
    record["revisit_conditions"][0]["value_at_decision"] = 60.5  # same truth value as 66.1


def _shift_as_of(record):
    record["data_as_of"]["inputs"]["breadth"] = "2026-01-13T21:00:00+00:00"


def _drop_unevaluated(record):
    record["unevaluated"] = []


@pytest.mark.parametrize("mutate", [_shift_value, _shift_as_of, _drop_unevaluated])
def test_decision_record_is_recomputed_not_only_shape_checked(tmp_path, day1_template, mutate):
    d = copy_run(day1_template, tmp_path / "completed")
    retamper_record(d, mutate)
    result = call(d, "--status")
    assert result.returncode == 1
    assert "differs from its recomputation" in result.stderr


def test_root_with_exactly_500_directories_is_usable(tmp_path):
    root, _ = make_root(tmp_path, 2)
    for i in range(498):
        (root / f"empty{i}").mkdir()
    assert day2_root(tmp_path, root).returncode == 3
    assert read(tmp_path / "today/inputs/previous_run.json")["previous"]["status"] == "loaded"


def test_regular_bytes_cap_is_inclusive(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"x" * 10)
    assert runner.regular_bytes(path, cap=10) == b"x" * 10
    with pytest.raises(runner.RunError):
        runner.regular_bytes(path, cap=9)


def test_read_cap_is_scoped_reentrant_and_skips_source_fingerprint(tmp_path):
    import threading

    big = tmp_path / "big"
    big.write_bytes(b"x" * 100)
    seen = []
    with runner.capped_reads(10):
        with pytest.raises(runner.RunError):
            runner.regular_bytes(big)
        with runner.capped_reads(1000):
            assert len(runner.regular_bytes(big)) == 100
        with pytest.raises(runner.RunError):  # outer cap restored after the inner scope
            runner.regular_bytes(big)
        assert runner.source_fingerprint()  # trusted repository sources are never capped
        thread = threading.Thread(target=lambda: seen.append(len(runner.regular_bytes(big))))
        thread.start()
        thread.join()
    assert seen == [100]  # another thread does not inherit this thread's cap
    assert len(runner.regular_bytes(big)) == 100


def test_conditions_file_size_limit_is_exactly_64_kib(tmp_path):
    d = tmp_path / "run"
    assert call(d).returncode == 3
    body = json.dumps({"schema_version": 1, "conditions": []})
    exact = tmp_path / "exact.json"
    exact.write_text(body + " " * (65536 - len(body)))
    over = tmp_path / "over.json"
    over.write_text(body + " " * (65537 - len(body)))
    refused = call(d, "--resume", "--decision", "allow", "--revisit-conditions", over)
    assert refused.returncode == 1 and "size limit" in refused.stderr
    assert call(d, "--resume", "--decision", "allow", "--revisit-conditions", exact).returncode == 0


def test_previous_manifest_changed_during_classification_is_unavailable(
    tmp_path, day1_template, monkeypatch
):
    previous = copy_run(day1_template, tmp_path / "prev")

    def touch(directory):
        path = Path(directory) / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")

    monkeypatch.setattr(runner, "after_previous_classification", touch)
    assert day2(tmp_path / "today", previous).returncode == 3
    assert read(tmp_path / "today/inputs/previous_run.json")["previous"]["status"] == "unavailable"


def test_oserror_while_classifying_previous_is_unavailable(tmp_path, day1_template, monkeypatch):
    def fail(directory):
        raise OSError(MARKER)

    monkeypatch.setattr(runner, "after_previous_classification", fail)
    result = day2(tmp_path / "today", day1_template)
    assert result.returncode == 3
    assert read(tmp_path / "today/inputs/previous_run.json")["previous"]["status"] == "unavailable"
    assert MARKER not in result.stdout + result.stderr


def test_broken_symlink_as_previous_path_is_unavailable(tmp_path):
    link = tmp_path / "dangling"
    link.symlink_to(tmp_path / "nowhere")
    assert day2(tmp_path / "today", link).returncode == 3
    assert read(tmp_path / "today/inputs/previous_run.json")["previous"]["status"] == "unavailable"


def test_diff_planted_while_step_four_is_pending_blocks_resume(
    tmp_path, day1_template, monkeypatch
):
    d2 = tmp_path / "d2"
    original = runner.after_checkpoint

    def interrupt(state):
        if state["steps"][0]["status"] == "COMPLETED":
            raise KeyboardInterrupt

    monkeypatch.setattr(runner, "after_checkpoint", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.run(d2, fixture_set="day-2", previous_run_dir=day1_template)
    monkeypatch.setattr(runner, "after_checkpoint", original)
    assert read(d2 / "manifest.json")["steps"][3]["status"] == "PENDING"
    assert call(d2, "--status").returncode == 0
    (d2 / "decision_diff.json").write_text("{}")
    assert call(d2, "--status").returncode == 1


def test_removing_decision_record_from_a_previous_run_is_detected(tmp_path, day1_template):
    d2 = tmp_path / "d2"
    assert day2(d2, day1_template).returncode == 3
    assert call(d2, "--resume", "--decision", "allow").returncode == 0
    rewrite_manifest(d2, lambda s: s["steps"][3].pop("decision_record"))
    state = read(d2 / "manifest.json")
    v1 = runner.journal(state)
    v1.pop("decision_diff", None)
    path = d2 / "journal.json"
    save(path, v1)
    rewrite_manifest(d2, lambda s: s["journal"].update(sha256=runner.digest(path.read_bytes())))
    result = call(d2, "--status")
    assert result.returncode == 1 and "Decision record missing" in result.stderr


def test_root_skips_candidates_with_naive_decision_time(tmp_path):
    root, (good, naive_a, naive_b) = make_root(tmp_path, 3)
    for run_dir in (naive_a, naive_b):
        rewrite_manifest(run_dir, lambda s: s["steps"][3].update(decision_at="2026-01-15T13:30:00"))
    assert day2_root(tmp_path, root).returncode == 3
    snapshot = read(tmp_path / "today/inputs/previous_run.json")
    assert snapshot["selection"]["skipped_unreadable"] == 2
    assert snapshot["previous"]["run_id"] == read(good / "manifest.json")["run_id"]


def test_api_level_argument_rules(tmp_path):
    with pytest.raises(runner.RunError):
        runner.run(
            tmp_path / "a", previous_run_dir=tmp_path / "x", previous_runs_root=tmp_path / "y"
        )
    with pytest.raises(runner.RunError):
        runner.run(tmp_path / "b", revisit_conditions=tmp_path / "c.json")
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


# ---------------------------------------------------- review round 2 additions


def test_root_ancestor_of_the_new_run_is_excluded_not_counted_unreadable(tmp_path):
    root, _ = make_root(tmp_path, 1)
    (root / "sub").mkdir()  # no manifest; it will contain the new run
    assert day2_root(tmp_path, root, "root/sub/d2").returncode == 3
    snapshot = read(root / "sub/d2/inputs/previous_run.json")
    assert snapshot["previous"]["status"] == "loaded"
    assert snapshot["selection"] == {"mode": "root", "candidates": 1, "skipped_unreadable": 0}


def test_root_symlinked_child_is_ignored_entirely(tmp_path, day1_template):
    root, _ = make_root(tmp_path, 1)
    (root / "link").symlink_to(day1_template)
    assert day2_root(tmp_path, root).returncode == 3
    snapshot = read(tmp_path / "today/inputs/previous_run.json")
    assert snapshot["selection"] == {"mode": "root", "candidates": 1, "skipped_unreadable": 0}


def test_lock_released_during_classification_does_not_make_previous_loaded(
    tmp_path, day1_template, monkeypatch
):
    previous = copy_run(day1_template, tmp_path / "prev")
    (previous / ".lock").write_text("owner")
    monkeypatch.setattr(
        runner,
        "after_previous_classification",
        lambda d: (Path(d) / ".lock").unlink(missing_ok=True),
    )
    assert day2(tmp_path / "today", previous).returncode == 3
    assert read(tmp_path / "today/inputs/previous_run.json")["previous"]["status"] == "unavailable"
    assert (previous / ".lock").read_text() == "owner"
