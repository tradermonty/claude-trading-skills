"""set-screening-audit replaces a run's audit bundle all-or-nothing (Issue #642)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
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
    # Each failed restore names the backup file that holds the prior bytes.
    assert "universe-audit-results.jsonl: restore denied" in err
    assert "backup-0.tmp" in err
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


def _staging_dirs(run: Path) -> list[Path]:
    return [path for path in run.iterdir() if ".set-screening-audit" in path.name]


def _lost_names(run: Path, before: dict[str, bytes]) -> list[str]:
    """Names whose prior bytes are neither live nor in a kept backup."""
    backups = [
        path.read_bytes() for staging in _staging_dirs(run) for path in staging.glob("backup-*")
    ]
    lost = []
    for name, data in before.items():
        live = run / name
        if not (live.is_file() and live.read_bytes() == data) and data not in backups:
            lost.append(name)
    return lost


def test_interrupt_during_restore_keeps_prior_bytes(attached_run, replacement, monkeypatch):
    args = replacement.args(attached_run)
    before = _snapshot(attached_run)
    real_replace = os.replace
    run_state = attached_run / "run_state.json"

    events = attached_run / "events.ndjson"

    def replace(source, target):
        if Path(target) == run_state:
            raise OSError("disk full")
        if Path(target) == events and Path(source).name.startswith("backup-"):
            raise KeyboardInterrupt()  # the first restore that really moves a file
        return real_replace(source, target)

    monkeypatch.setattr(RUN_STATE.os, "replace", replace)

    with pytest.raises(KeyboardInterrupt):
        RUN_STATE.main(args)

    assert _lost_names(attached_run, before) == []
    # The interrupt must not skip the remaining files.
    for name, data in before.items():
        if name != "events.ndjson":
            assert (attached_run / name).read_bytes() == data
    assert len(_staging_dirs(attached_run)) == 1


@pytest.mark.parametrize("target", COMMITTED_TARGETS)
def test_interrupt_after_rename_restores_snapshot(attached_run, replacement, monkeypatch, target):
    args = replacement.args(attached_run)
    before = _snapshot(attached_run)
    real_replace = os.replace
    live = attached_run / target
    armed = {"value": True}

    def replace(source, destination):
        result = real_replace(source, destination)
        if armed["value"] and Path(destination) == live:
            armed["value"] = False
            raise KeyboardInterrupt()
        return result

    monkeypatch.setattr(RUN_STATE.os, "replace", replace)

    with pytest.raises(KeyboardInterrupt):
        RUN_STATE.main(args)

    assert _snapshot(attached_run) == before


def test_interrupt_after_rename_of_new_file_removes_it(tmp_path, monkeypatch):
    run = tmp_path / "run"
    _init(run)
    before = _snapshot(run)
    real_replace = os.replace
    live = run / UNIVERSE_TARGET

    def replace(source, destination):
        result = real_replace(source, destination)
        if Path(destination) == live:
            raise KeyboardInterrupt()
        return result

    monkeypatch.setattr(RUN_STATE.os, "replace", replace)
    args = _attach_args(
        run,
        ASSETS / "broad-screen-audit.example.json",
        ASSETS / "universe-audit-results.example.jsonl",
        ASSETS / "broad-screen-results.example.jsonl",
    )

    with pytest.raises(KeyboardInterrupt):
        RUN_STATE.main(args)

    assert _snapshot(run) == before


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "manage_run_state.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_controlled_error(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 1
    assert result.stderr.startswith("ERROR: ")
    assert "Traceback" not in result.stderr


def test_infinite_count_is_a_controlled_error(attached_run, replacement):
    # json.loads accepts the bare token Infinity; int(inf) raises OverflowError.
    replacement.audit["universe"]["row_count"] = 987654321
    text = json.dumps(replacement.audit).replace("987654321", "Infinity", 1)
    replacement.audit_path.write_text(text, encoding="utf-8")
    assert "Infinity" in text
    before = _snapshot(attached_run)

    args = _attach_args(
        attached_run, replacement.audit_path, replacement.universe, replacement.candidate
    )
    result = _run_cli(args)

    _assert_controlled_error(result)
    assert _snapshot(attached_run) == before


def test_deeply_nested_audit_is_a_controlled_error(attached_run, replacement):
    replacement.audit_path.write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
    before = _snapshot(attached_run)

    args = _attach_args(
        attached_run, replacement.audit_path, replacement.universe, replacement.candidate
    )
    result = _run_cli(args)

    _assert_controlled_error(result)
    assert _snapshot(attached_run) == before


def test_list_budget_is_a_controlled_error_through_cli(attached_run, replacement):
    replacement.audit["deep_dive_plan"]["max_deep_dive_candidates"] = [1]
    before = _snapshot(attached_run)

    result = _run_cli(replacement.args(attached_run))

    _assert_controlled_error(result)
    assert "malformed" in result.stderr
    assert _snapshot(attached_run) == before


@pytest.mark.parametrize(
    "artifact_name", ["UNIVERSE-AUDIT-RESULTS.JSONL", "BROAD-SCREEN-AUDIT.JSON"]
)
def test_case_only_name_collision_is_rejected(attached_run, replacement, capsys, artifact_name):
    # On a case-insensitive filesystem these names would overwrite each other.
    enrichment = replacement.dir / artifact_name
    enrichment.write_bytes(b"[]\n")
    replacement.audit["enrichment"]["artifact_path"] = artifact_name
    replacement.audit["enrichment"]["artifact_sha256"] = _sha(enrichment)
    before = _snapshot(attached_run)
    capsys.readouterr()

    assert RUN_STATE.main(replacement.args(attached_run)) == 1

    assert "collides" in capsys.readouterr().err
    assert _snapshot(attached_run) == before


def test_replaced_files_keep_their_mode(attached_run, replacement):
    for target in COMMITTED_TARGETS:
        (attached_run / target).chmod(0o600)

    assert RUN_STATE.main(replacement.args(attached_run)) == 0

    for target in COMMITTED_TARGETS:
        assert stat.S_IMODE((attached_run / target).stat().st_mode) == 0o600, target


def test_new_files_keep_default_mode(tmp_path):
    run = tmp_path / "run"
    _init(run)
    reference = tmp_path / "reference"
    reference.write_text("x", encoding="utf-8")
    args = _attach_args(
        run,
        ASSETS / "broad-screen-audit.example.json",
        ASSETS / "universe-audit-results.example.jsonl",
        ASSETS / "broad-screen-results.example.jsonl",
    )

    assert RUN_STATE.main(args) == 0

    expected = stat.S_IMODE(reference.stat().st_mode)
    assert stat.S_IMODE((run / UNIVERSE_TARGET).stat().st_mode) == expected


@pytest.mark.skipif(not hasattr(os, "chflags"), reason="needs BSD file flags")
def test_immutable_live_file_leaves_no_staging(attached_run, replacement, capsys):
    args = replacement.args(attached_run)
    before = _snapshot(attached_run)
    events = attached_run / "events.ndjson"
    os.chflags(events, stat.UF_IMMUTABLE)
    capsys.readouterr()
    try:
        assert RUN_STATE.main(args) == 1
        assert _snapshot(attached_run) == before
        # copyfile does not carry the flag, so the backups can be removed.
        assert _staging_dirs(attached_run) == []
    finally:
        os.chflags(events, 0)
        for staging in _staging_dirs(attached_run):
            for path in staging.rglob("*"):
                os.chflags(path, 0)


def test_unremovable_staging_is_reported_without_implying_cleanup(
    attached_run, replacement, monkeypatch, capsys
):
    real_rmtree = shutil.rmtree
    monkeypatch.setattr(RUN_STATE.shutil, "rmtree", lambda *args, **kwargs: None)
    capsys.readouterr()

    assert RUN_STATE.main(replacement.args(attached_run)) == 0

    leftovers = _staging_dirs(attached_run)
    assert len(leftovers) == 1
    err = capsys.readouterr().err
    assert "warning" in err.lower()
    assert str(leftovers[0]) in err
    real_rmtree(leftovers[0])


def _share_artifact(item: Replacement, generation_path: str, generation_file: Path) -> Path:
    shared = item.dir / "shared-artifact.jsonl"
    shared.write_bytes(b"[]\n")
    item.audit["enrichment"].update({"artifact_path": shared.name, "artifact_sha256": _sha(shared)})
    generation = dict(item.audit["candidate_pool"].get("generation_audit") or {})
    generation.update(artifact_path=generation_path, artifact_sha256=_sha(generation_file))
    item.audit["candidate_pool"]["generation_audit"] = generation
    return shared


def test_enrichment_and_generation_may_share_one_file(attached_run, replacement):
    # Same file and same SHA under two labels is one artifact, not a collision.
    shared = replacement.dir / "shared-artifact.jsonl"
    shared.write_bytes(b"[]\n")
    _share_artifact(replacement, shared.name, shared)

    assert RUN_STATE.main(replacement.args(attached_run)) == 0

    state = json.loads((attached_run / "run_state.json").read_text(encoding="utf-8"))
    audit = state["screening_audit"]
    assert audit["enrichment"]["artifact_path"] == "audit/shared-artifact.jsonl"
    generation = audit["candidate_pool"]["generation_audit"]
    assert generation["artifact_path"] == "audit/shared-artifact.jsonl"
    assert (attached_run / "audit/shared-artifact.jsonl").read_bytes() == b"[]\n"


def test_same_name_with_different_content_is_rejected(attached_run, replacement, capsys):
    other = replacement.dir / "other" / "shared-artifact.jsonl"
    other.parent.mkdir()
    other.write_bytes(b"[1]\n")
    _share_artifact(replacement, "other/shared-artifact.jsonl", other)
    before = _snapshot(attached_run)
    capsys.readouterr()

    assert RUN_STATE.main(replacement.args(attached_run)) == 1

    assert "shared-artifact.jsonl" in capsys.readouterr().err
    assert _snapshot(attached_run) == before


def test_verification_hashes_the_staged_copy(attached_run, replacement, monkeypatch):
    original = replacement.universe.read_bytes()
    real_copyfile = shutil.copyfile

    def copy_then_change_source(source, destination, **kwargs):
        result = real_copyfile(source, destination, **kwargs)
        if Path(source) == replacement.universe:
            replacement.universe.write_bytes(b"changed after copy\n")
        return result

    args = replacement.args(attached_run)
    monkeypatch.setattr(RUN_STATE.shutil, "copyfile", copy_then_change_source)

    assert RUN_STATE.main(args) == 0

    assert (attached_run / UNIVERSE_TARGET).read_bytes() == original


def test_success_updates_timestamp_and_status(attached_run, replacement):
    state_path = attached_run / "run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "complete"
    state["updated_at"] = "2000-01-01T00:00:00+00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    assert RUN_STATE.main(replacement.args(attached_run)) == 0

    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert after["status"] == "partial"
    assert after["updated_at"] > "2000-01-01T00:00:00+00:00"


@pytest.mark.parametrize("changed_audit", [False, True], ids=["same-audit", "new-evidence"])
def test_verified_checkpoint_rejects_audit_reattachment(
    attached_run, replacement, tmp_path, capsys, changed_audit
):
    example = json.loads((ASSETS / "candidate-input.example.json").read_text(encoding="utf-8"))
    candidate = tmp_path / "ACME.json"
    candidate.write_text(json.dumps(example["candidates"][0]), encoding="utf-8")
    assert (
        RUN_STATE.main(
            [
                "save-candidate",
                "--run-dir",
                str(attached_run),
                "--candidate",
                str(candidate),
                "--stage",
                "verified",
            ]
        )
        == 0
    )
    assert RUN_STATE.main(["status", "--run-dir", str(attached_run), "--strict"]) == 0
    before = _snapshot(attached_run)
    args = (
        replacement.args(attached_run)
        if changed_audit
        else _attach_args(
            attached_run,
            ASSETS / "broad-screen-audit.example.json",
            ASSETS / "universe-audit-results.example.jsonl",
            ASSETS / "broad-screen-results.example.jsonl",
        )
    )
    capsys.readouterr()

    assert RUN_STATE.main(args) == 1

    error = capsys.readouterr().err
    assert "ERROR:" in error
    assert "verified candidates" in error
    assert "new run" in error
    assert _snapshot(attached_run) == before
    assert not _staging_dirs(attached_run)
    assert RUN_STATE.main(["status", "--run-dir", str(attached_run), "--strict"]) == 0


def test_draft_checkpoint_allows_audit_replacement(attached_run, replacement, tmp_path):
    example = json.loads((ASSETS / "candidate-input.example.json").read_text(encoding="utf-8"))
    candidate = tmp_path / "ACME.json"
    candidate.write_text(json.dumps(example["candidates"][0]), encoding="utf-8")
    assert (
        RUN_STATE.main(
            [
                "save-candidate",
                "--run-dir",
                str(attached_run),
                "--candidate",
                str(candidate),
                "--stage",
                "draft",
            ]
        )
        == 0
    )
    saved = (attached_run / "candidates" / "ACME.json").read_bytes()

    assert RUN_STATE.main(replacement.args(attached_run)) == 0

    assert (attached_run / "candidates" / "ACME.json").read_bytes() == saved
    state = json.loads((attached_run / "run_state.json").read_text(encoding="utf-8"))
    assert state["candidates"]["ACME"]["stage"] == "draft"
    assert "ACME" in state["unprocessed_candidates"]
    assert state["screening_funnel"]["deep_dive_completed_count"] == 0
    assert RUN_STATE.main(["status", "--run-dir", str(attached_run), "--strict"]) == 0


def _save(run: Path, candidate: Path, stage: str, *extra: str) -> int:
    return RUN_STATE.main(
        [
            "save-candidate",
            "--run-dir",
            str(run),
            "--candidate",
            str(candidate),
            "--stage",
            stage,
            *extra,
        ]
    )


def _candidate_file(tmp_path: Path, symbol: str = "ACME") -> Path:
    example = json.loads((ASSETS / "candidate-input.example.json").read_text(encoding="utf-8"))
    data = dict(example["candidates"][0])
    data["identity"] = {**data["identity"], "symbol": symbol}
    candidate = tmp_path / f"{symbol}.json"
    candidate.write_text(json.dumps(data), encoding="utf-8")
    return candidate


def _pending_audit(item: Replacement) -> None:
    item.audit["candidate_pool_status"] = "sufficient_pending_enrichment"
    item.audit["selection_outcome"] = "selected_pending_enrichment"


def test_pending_pool_workflow_is_recoverable(tmp_path, capsys):
    run = tmp_path / "run"
    _init(run)
    pending = Replacement(tmp_path)
    _pending_audit(pending)
    assert RUN_STATE.main(pending.args(run)) == 0
    candidate = _candidate_file(tmp_path)

    assert _save(run, candidate, "draft") == 0
    before = _snapshot(run)
    capsys.readouterr()
    assert _save(run, candidate, "verified") == 1
    error = capsys.readouterr().err
    assert "ERROR:" in error
    assert "sufficient_pending_enrichment" in error
    assert "draft" in error
    assert _snapshot(run) == before

    args = _attach_args(
        run,
        ASSETS / "broad-screen-audit.example.json",
        ASSETS / "universe-audit-results.example.jsonl",
        ASSETS / "broad-screen-results.example.jsonl",
    )
    assert RUN_STATE.main(args) == 0
    for symbol in ("ACME", "CYCLE", "STALE"):
        assert _save(run, _candidate_file(tmp_path, symbol), "verified") == 0
    assert RUN_STATE.main(["set-status", "--run-dir", str(run), "complete"]) == 0


def test_verified_candidate_cannot_be_downgraded_to_draft(attached_run, tmp_path, capsys):
    candidate = _candidate_file(tmp_path)
    assert _save(attached_run, candidate, "verified") == 0
    before = _snapshot(attached_run)
    capsys.readouterr()

    assert _save(attached_run, candidate, "draft") == 1

    error = capsys.readouterr().err
    assert "ERROR:" in error
    assert "downgrade" in error
    assert _snapshot(attached_run) == before


def test_reattach_guard_blocks_verified_candidate_outside_selection(
    attached_run, replacement, tmp_path, capsys
):
    outside = _candidate_file(tmp_path, "OUTSIDE")
    assert _save(attached_run, outside, "verified", "--allow-unselected") == 0
    before = _snapshot(attached_run)
    capsys.readouterr()

    assert RUN_STATE.main(replacement.args(attached_run)) == 1

    assert "verified candidates" in capsys.readouterr().err
    assert _snapshot(attached_run) == before
