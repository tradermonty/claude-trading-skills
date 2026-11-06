"""set-screening-audit replaces a run's audit bundle all-or-nothing (Issue #642)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import bundle_run_artifacts as BUNDLE  # noqa: E402
import manage_run_state as RUN_STATE  # noqa: E402
import prepublish_audit as PREPUBLISH  # noqa: E402

ASSETS = SCRIPTS_DIR.parent / "assets"
UNIVERSE_TARGET = "audit/universe-audit-results.jsonl"
CANDIDATE_TARGET = "audit/broad-screen-results.jsonl"
COMMITTED_TARGETS = [
    UNIVERSE_TARGET,
    CANDIDATE_TARGET,
    "audit/broad-screen-audit.json",
    "events.ndjson",
    "run_state.json",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(run: Path) -> dict[str, bytes]:
    return {
        path.relative_to(run).as_posix(): path.read_bytes()
        for path in sorted(run.rglob("*"))
        if path.is_file()
    }


def _attach_args(run: Path, audit: Path, universe: Path, candidate: Path) -> list[str]:
    return [
        "set-screening-audit",
        "--run-dir",
        str(run),
        "--audit",
        str(audit),
        "--universe-artifact",
        str(universe),
        "--candidate-artifact",
        str(candidate),
    ]


def _init(run: Path) -> None:
    example = json.loads((ASSETS / "candidate-input.example.json").read_text(encoding="utf-8"))
    args = [
        "init",
        "--run-dir",
        str(run),
        "--analysis-as-of",
        example["analysis_as_of"],
        "--price-as-of",
        example["price_basis"]["as_of"],
        "--session",
        "regular_close",
        "--price-source-id",
        "quote-20260821",
        "--config",
        str(ASSETS / "screening-config.example.json"),
        "--market-context",
        str(ASSETS / "market-context.example.json"),
        "--global-sources",
        str(ASSETS / "global-sources.example.json"),
    ]
    assert RUN_STATE.main(args) == 0


class Replacement:
    """An editable copy of the bundled audit whose universe bytes differ from the example."""

    def __init__(self, root: Path) -> None:
        self.dir = root / "replacement"
        shutil.copytree(ASSETS, self.dir)
        self.audit_path = self.dir / "broad-screen-audit.example.json"
        self.audit = json.loads(self.audit_path.read_text(encoding="utf-8"))
        self.universe = self.dir / "universe-audit-results.example.jsonl"
        self.candidate = self.dir / "broad-screen-results.example.jsonl"
        self.universe.write_bytes(self.universe.read_bytes() + b"\n")
        self.audit["universe"]["artifact_sha256"] = _sha(self.universe)

    def args(self, run: Path) -> list[str]:
        self.audit_path.write_text(json.dumps(self.audit), encoding="utf-8")
        return _attach_args(run, self.audit_path, self.universe, self.candidate)


@pytest.fixture
def attached_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    _init(run)
    args = _attach_args(
        run,
        ASSETS / "broad-screen-audit.example.json",
        ASSETS / "universe-audit-results.example.jsonl",
        ASSETS / "broad-screen-results.example.jsonl",
    )
    assert RUN_STATE.main(args) == 0
    assert RUN_STATE.main(["status", "--run-dir", str(run), "--strict"]) == 0
    return run


@pytest.fixture
def replacement(tmp_path: Path) -> Replacement:
    return Replacement(tmp_path)


def _bad_candidate_sha(item: Replacement) -> None:
    item.audit["candidate_pool"]["artifact_sha256"] = "0" * 64


def _selected_wrong_type(item: Replacement) -> None:
    item.audit["selected_symbols"] = "ACME"


def _plan_mismatch(item: Replacement) -> None:
    item.audit["deep_dive_plan"]["selected_symbols"] = ["OTHER"]


def _plan_symbol_not_text(item: Replacement) -> None:
    item.audit["deep_dive_plan"]["selected_symbols"] = [1]


def _plan_budget_not_numeric(item: Replacement) -> None:
    item.audit["deep_dive_plan"]["max_deep_dive_candidates"] = "many"


def _funnel_count_not_numeric(item: Replacement) -> None:
    item.audit["universe"]["row_count"] = "many"


def _bad_enrichment_sha(item: Replacement) -> None:
    item.audit["enrichment"]["artifact_sha256"] = "0" * 64


def _bad_pool_status(item: Replacement) -> None:
    item.audit["candidate_pool_status"] = "unknown"


REJECTIONS = {
    "bad-second-artifact-sha": (_bad_candidate_sha, "candidate-pool artifact SHA-256"),
    "selected-symbols-wrong-type": (_selected_wrong_type, "selected_symbols"),
    "deep-dive-plan-mismatch": (_plan_mismatch, "deep_dive_plan.selected_symbols"),
    "deep-dive-symbol-not-text": (_plan_symbol_not_text, "malformed"),
    "deep-dive-budget-not-numeric": (_plan_budget_not_numeric, "malformed"),
    "funnel-count-not-numeric": (_funnel_count_not_numeric, "malformed"),
    "bad-enrichment-sha": (_bad_enrichment_sha, "enrichment artifact SHA-256"),
    "bad-pool-status": (_bad_pool_status, "candidate_pool_status"),
}


@pytest.mark.parametrize("name", REJECTIONS)
def test_rejected_replacement_changes_nothing(attached_run, replacement, capsys, name):
    mutate, message = REJECTIONS[name]
    mutate(replacement)
    before = _snapshot(attached_run)
    capsys.readouterr()

    assert RUN_STATE.main(replacement.args(attached_run)) == 1

    assert message in capsys.readouterr().err
    assert _snapshot(attached_run) == before
    assert RUN_STATE.main(["status", "--run-dir", str(attached_run), "--strict"]) == 0


def test_rejected_replacement_keeps_stored_hashes_valid(attached_run, replacement):
    _bad_candidate_sha(replacement)

    assert RUN_STATE.main(replacement.args(attached_run)) == 1

    state = json.loads((attached_run / "run_state.json").read_text(encoding="utf-8"))
    audit = state["screening_audit"]
    assert _sha(attached_run / UNIVERSE_TARGET) == audit["universe"]["artifact_sha256"]
    assert _sha(attached_run / CANDIDATE_TARGET) == audit["candidate_pool"]["artifact_sha256"]


def test_unreadable_audit_is_a_controlled_error(attached_run, replacement, capsys):
    replacement.audit_path.write_bytes(b"\xff\xfe not utf-8")
    before = _snapshot(attached_run)
    capsys.readouterr()

    args = _attach_args(
        attached_run, replacement.audit_path, replacement.universe, replacement.candidate
    )
    assert RUN_STATE.main(args) == 1

    assert "malformed" in capsys.readouterr().err
    assert _snapshot(attached_run) == before


def test_copy_failure_preserves_checkpoint(attached_run, replacement, monkeypatch, capsys):
    real_copyfile = shutil.copyfile

    def fail_on_candidate(source, destination, **kwargs):
        if Path(source) == replacement.candidate:
            raise PermissionError("cannot read candidate artifact")
        return real_copyfile(source, destination, **kwargs)

    args = replacement.args(attached_run)
    before = _snapshot(attached_run)
    monkeypatch.setattr(RUN_STATE.shutil, "copyfile", fail_on_candidate)
    capsys.readouterr()

    assert RUN_STATE.main(args) == 1

    assert "cannot read candidate artifact" in capsys.readouterr().err
    assert _snapshot(attached_run) == before


def _fail_replace_once(monkeypatch, destination: Path, error: BaseException) -> None:
    real_replace = os.replace
    armed = {"value": True}

    def replace(source, target):
        if armed["value"] and Path(target) == destination:
            armed["value"] = False
            raise error
        return real_replace(source, target)

    monkeypatch.setattr(RUN_STATE.os, "replace", replace)


@pytest.mark.parametrize("target", COMMITTED_TARGETS)
def test_commit_failure_restores_every_file(attached_run, replacement, monkeypatch, capsys, target):
    args = replacement.args(attached_run)
    before = _snapshot(attached_run)
    _fail_replace_once(monkeypatch, attached_run / target, OSError("disk full"))
    capsys.readouterr()

    assert RUN_STATE.main(args) == 1

    err = capsys.readouterr().err
    assert "disk full" in err
    assert "restored" in err
    assert _snapshot(attached_run) == before
    assert not [path for path in attached_run.iterdir() if ".set-screening-audit" in path.name]


def test_commit_failure_on_first_attach_removes_new_files(tmp_path, monkeypatch):
    run = tmp_path / "run"
    _init(run)
    before = _snapshot(run)
    _fail_replace_once(monkeypatch, run / "run_state.json", OSError("disk full"))
    args = _attach_args(
        run,
        ASSETS / "broad-screen-audit.example.json",
        ASSETS / "universe-audit-results.example.jsonl",
        ASSETS / "broad-screen-results.example.jsonl",
    )

    assert RUN_STATE.main(args) == 1

    assert _snapshot(run) == before


def test_interrupt_during_commit_restores_and_propagates(attached_run, replacement, monkeypatch):
    args = replacement.args(attached_run)
    before = _snapshot(attached_run)
    _fail_replace_once(monkeypatch, attached_run / "run_state.json", KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        RUN_STATE.main(args)

    assert _snapshot(attached_run) == before


def test_blocked_target_fails_cleanly_through_real_cli(attached_run, replacement):
    # A real mid-commit failure: both artifacts are replaced before this path is reached.
    audit_file = attached_run / "audit" / "broad-screen-audit.json"
    audit_file.unlink()
    audit_file.mkdir()
    args = replacement.args(attached_run)
    before = _snapshot(attached_run)

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "manage_run_state.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stderr.startswith("ERROR: ")
    assert "Traceback" not in result.stderr
    assert _snapshot(attached_run) == before


def test_failed_rollback_reports_and_keeps_backups(attached_run, replacement, monkeypatch, capsys):
    args = replacement.args(attached_run)
    original_universe = (attached_run / UNIVERSE_TARGET).read_bytes()
    real_replace = os.replace
    run_state = attached_run / "run_state.json"
    universe = attached_run / UNIVERSE_TARGET

    def replace(source, target):
        if Path(target) == run_state:
            raise OSError("disk full")
        if Path(target) == universe and Path(source).name.startswith("backup-"):
            raise OSError("restore denied")
        return real_replace(source, target)

    monkeypatch.setattr(RUN_STATE.os, "replace", replace)
    capsys.readouterr()

    assert RUN_STATE.main(args) == 1

    err = capsys.readouterr().err
    assert "restore denied" in err
    kept = [path for path in attached_run.iterdir() if ".set-screening-audit" in path.name]
    assert len(kept) == 1
    assert str(kept[0]) in err
    backups = [path.read_bytes() for path in kept[0].glob("backup-*")]
    assert original_universe in backups
    # Kept backups must never leak into a published audit bundle.
    assert not [path for path in kept[0].rglob("*") if BUNDLE._include(path, attached_run)]


@pytest.mark.parametrize(
    "artifact_name",
    ["universe-audit-results.jsonl", "broad-screen-audit.json"],
    ids=["other-artifact", "audit-document"],
)
def test_artifact_name_collision_is_rejected(attached_run, replacement, capsys, artifact_name):
    # Letting one artifact overwrite another would break the stored SHA of the first.
    enrichment = replacement.dir / artifact_name
    enrichment.write_bytes(b"[]\n")
    replacement.audit["enrichment"]["artifact_path"] = artifact_name
    replacement.audit["enrichment"]["artifact_sha256"] = _sha(enrichment)
    before = _snapshot(attached_run)
    capsys.readouterr()

    assert RUN_STATE.main(replacement.args(attached_run)) == 1

    assert artifact_name in capsys.readouterr().err
    assert _snapshot(attached_run) == before


def test_valid_replacement_stores_matching_hashes(attached_run, replacement):
    events_before = (attached_run / "events.ndjson").read_bytes()

    assert RUN_STATE.main(replacement.args(attached_run)) == 0

    state = json.loads((attached_run / "run_state.json").read_text(encoding="utf-8"))
    audit = state["screening_audit"]
    saved = json.loads((attached_run / "audit/broad-screen-audit.json").read_text(encoding="utf-8"))
    assert saved == audit
    assert (attached_run / UNIVERSE_TARGET).read_bytes() == replacement.universe.read_bytes()
    assert _sha(attached_run / UNIVERSE_TARGET) == audit["universe"]["artifact_sha256"]
    errors: list[str] = []
    for label in ("universe", "candidate_pool", "enrichment"):
        PREPUBLISH._verify_artifact(audit[label], attached_run, label, errors)
    assert errors == []
    events = (attached_run / "events.ndjson").read_bytes()
    assert events.startswith(events_before)
    assert json.loads(events[len(events_before) :])["event"] == "screening_audit_attached"
    assert RUN_STATE.main(["status", "--run-dir", str(attached_run), "--strict"]) == 0
    assert not [path for path in attached_run.iterdir() if ".set-screening-audit" in path.name]


def test_reattaching_from_the_runs_own_artifacts_succeeds(attached_run):
    # Source and destination are the same file; staging must not trip over that.
    args = _attach_args(
        attached_run,
        ASSETS / "broad-screen-audit.example.json",
        attached_run / UNIVERSE_TARGET,
        attached_run / CANDIDATE_TARGET,
    )
    assert RUN_STATE.main(args) == 0
    assert RUN_STATE.main(["status", "--run-dir", str(attached_run), "--strict"]) == 0
