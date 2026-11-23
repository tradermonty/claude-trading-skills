"""Synthetic local persistence regressions; independent processes never touch real state."""

import json
import multiprocessing
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import thesis_store as store
from test_equity_long_only import active, corrupt_short
from test_thesis_store import _make_thesis_data

WRITERS = (
    "register",
    "update",
    "record_lessons",
    "transition",
    "link_report",
    "mark_reviewed",
    "attach_position",
    "attach_futures_position",
    "open_position",
    "close",
    "trim",
    "terminate",
    "rebuild_index",
)


def business_bytes(state):
    return {
        p.name: p.read_bytes()
        for p in state.iterdir()
        if p.name == "_index.json" or p.suffix == ".yaml"
    }


@pytest.mark.parametrize("manual", [False, True])
def test_legacy_shorts_survive_doctor_rebuild_and_queries(tmp_path, manual):
    tid = active(tmp_path)
    corrupt_short(tmp_path, tid, manual)
    before = (tmp_path / f"{tid}.yaml").read_bytes()
    assert store.validate_state(tmp_path)["ok"]
    store.rebuild_index(tmp_path)
    assert tid in store._load_index(tmp_path)["theses"]
    assert any(r["thesis_id"] == tid for r in store.query(tmp_path))
    assert any(r["thesis_id"] == tid for r in store.list_active(tmp_path))
    assert any(r["thesis_id"] == tid for r in store.list_review_due(tmp_path, "2099-01-01"))
    assert (tmp_path / f"{tid}.yaml").read_bytes() == before
    assert store.validate_state(tmp_path)["ok"]


@pytest.mark.parametrize("name", WRITERS[:-1])
@pytest.mark.parametrize(
    "broken", ["{", "[]", '{"version":1,"theses":[]}', '{"version":1,"theses":{"bad":null}}']
)
def test_all_writers_preflight_bad_index_before_business_writes(tmp_path, name, broken):
    tid = store.register(tmp_path, _make_thesis_data())
    (tmp_path / "_index.json").write_text(broken)
    before = business_bytes(tmp_path)
    operations = {
        "register": lambda: store.register(tmp_path, _make_thesis_data(ticker="MSFT")),
        "update": lambda: store.update(tmp_path, tid, {"thesis_statement": "changed"}),
        "record_lessons": lambda: store.record_lessons(tmp_path, tid, "synthetic lesson"),
        "transition": lambda: store.transition(tmp_path, tid, "ENTRY_READY", "ready"),
        "link_report": lambda: store.link_report(tmp_path, tid, "test", "fake.md", "2026-01-01"),
        "mark_reviewed": lambda: store.mark_reviewed(tmp_path, tid, review_date="2026-01-01"),
        "attach_position": lambda: store.attach_position(tmp_path, tid, "fake.json"),
        "attach_futures_position": lambda: store.attach_futures_position(
            tmp_path, tid, "fake.json"
        ),
        "open_position": lambda: store.open_position(tmp_path, tid, 100, "2026-01-01", shares=1),
        "close": lambda: store.close(tmp_path, tid, "manual", 110, "2026-01-01"),
        "trim": lambda: store.trim(tmp_path, tid, 1, 110, "2026-01-01", "manual"),
        "terminate": lambda: store.terminate(tmp_path, tid, "INVALIDATED", "manual"),
    }
    with pytest.raises(ValueError, match="index.*rebuild|rebuild.*index"):
        operations[name]()
    assert business_bytes(tmp_path) == before


def test_explicit_rebuild_can_recover_corrupt_index(tmp_path):
    tid = store.register(tmp_path, _make_thesis_data())
    (tmp_path / "_index.json").write_text("{")
    store.rebuild_index(tmp_path)
    assert tid in store._load_index(tmp_path)["theses"]
    assert store.validate_state(tmp_path)["ok"]


def _register_worker(state, number, duplicate, start, output):
    # Imported in a fresh interpreter by multiprocessing spawn.
    original = store._load_index

    def delayed_load(path):
        result = original(path)
        time.sleep(0.04)
        return result

    store._load_index = delayed_load
    original_find = store._find_by_fingerprint

    def delayed_find(path, fingerprint):
        result = original_find(path, fingerprint)
        time.sleep(0.15)
        return result

    store._find_by_fingerprint = delayed_find
    try:
        start.wait(timeout=20)
        data = _make_thesis_data(ticker="SAME" if duplicate else f"SYM{number}")
        tid = store.register(Path(state), data)
        output.put(("ok", tid))
    except Exception as e:
        output.put(("error", repr(e)))


@pytest.mark.parametrize("duplicate", [False, True])
def test_spawned_registration_has_no_lost_entries_or_duplicate_origins(tmp_path, duplicate):
    ctx = multiprocessing.get_context("spawn")
    start, output = ctx.Barrier(9), ctx.Queue()
    processes = [
        ctx.Process(target=_register_worker, args=(str(tmp_path), n, duplicate, start, output))
        for n in range(8)
    ]
    try:
        for p in processes:
            p.start()
        start.wait(timeout=30)
        results = [output.get(timeout=40) for _ in processes]
        for p in processes:
            p.join(10)
            assert p.exitcode == 0
    finally:
        for p in processes:
            if p.is_alive():
                p.terminate()
            p.join(5)
        output.close()
    assert all(status == "ok" for status, _ in results), results
    expected = 1 if duplicate else 8
    assert len(set(tid for _, tid in results)) == expected
    assert len(list(tmp_path.glob("th_*.yaml"))) == expected
    assert len(store._load_index(tmp_path)["theses"]) == expected
    assert store.validate_state(tmp_path)["ok"]


def test_writer_registry_covers_public_mutators():
    assert set(store._STATE_WRITERS) == set(WRITERS)
    for name in WRITERS:
        assert getattr(store, name).__wrapped__


def test_thread_updates_are_serialized_and_lock_released_after_error(tmp_path):
    tid = store.register(tmp_path, _make_thesis_data())
    with pytest.raises(ValueError):
        store.transition(tmp_path, tid, "ACTIVE", "forbidden direct transition")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda n: store.register(tmp_path, _make_thesis_data(ticker=f"TH{n}")), range(12)
            )
        )
    assert len(store._load_index(tmp_path)["theses"]) == 13
    assert store.validate_state(tmp_path)["ok"]


def test_nested_writer_and_alias_lock_are_reentrant(tmp_path):
    tid = active(tmp_path)
    store.close(tmp_path, tid, "manual", 110, "2026-01-02T00:00:00+00:00")
    alias = tmp_path.parent / (tmp_path.name + "-alias")
    alias.symlink_to(tmp_path, target_is_directory=True)
    with store._state_lock(tmp_path):
        updated, action = store.record_lessons(alias, tid, "Synthetic nested update")
    assert action == "new"
    assert updated["outcome"]["lessons_learned"] == "Synthetic nested update"
    assert store.validate_state(tmp_path)["ok"]


def test_lock_contention_timeout_is_value_error_and_preserves_state(tmp_path):
    store.register(tmp_path, _make_thesis_data())
    before = business_bytes(tmp_path)
    held, release = threading.Event(), threading.Event()

    def holder():
        with store._state_lock(tmp_path):
            held.set()
            assert release.wait(10)

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert held.wait(10)
        with pytest.raises(ValueError, match="lock"):
            with store._state_lock(tmp_path, timeout=0.05):
                pass
    finally:
        release.set()
        thread.join(10)
    assert business_bytes(tmp_path) == before


def _hold_lock_worker(state, held):
    with store._state_lock(Path(state)):
        held.set()
        time.sleep(20)


def test_os_lock_timeout_and_process_exit_release(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    held = ctx.Event()
    proc = ctx.Process(target=_hold_lock_worker, args=(str(tmp_path), held))
    proc.start()
    try:
        assert held.wait(20)
        with pytest.raises(ValueError, match="lock"):
            with store._state_lock(tmp_path, timeout=0.05):
                pass
        proc.terminate()
        proc.join(10)
        with store._state_lock(tmp_path, timeout=2):
            pass
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(10)


def _mixed_worker(state, tid, mode, start, output):
    try:
        start.wait(timeout=20)
        state = Path(state)
        if mode == "review":
            store.mark_reviewed(state, tid, review_date="2026-01-02", outcome="WARN")
        elif mode == "rebuild":
            store.rebuild_index(state)
        else:
            store.register(state, _make_thesis_data(ticker=mode))
        output.put("ok")
    except Exception as exc:
        output.put(repr(exc))


def test_rebuild_and_other_process_writers_share_the_lock(tmp_path):
    tid = store.register(tmp_path, _make_thesis_data())
    ctx = multiprocessing.get_context("spawn")
    start, output = ctx.Barrier(5), ctx.Queue()
    procs = [
        ctx.Process(target=_mixed_worker, args=(str(tmp_path), tid, mode, start, output))
        for mode in ("review", "rebuild", "MIXA", "MIXB")
    ]
    try:
        for p in procs:
            p.start()
        start.wait(timeout=30)
        results = [output.get(timeout=30) for _ in procs]
        for p in procs:
            p.join(10)
            assert p.exitcode == 0
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
            p.join(5)
        output.close()
    assert results == ["ok"] * 4
    assert len(store._load_index(tmp_path)["theses"]) == 3
    assert store.get(tmp_path, tid)["monitoring"]["last_review_date"] == "2026-01-02"
    assert store.validate_state(tmp_path)["ok"]


def test_windows_byte_lock_contract(monkeypatch, tmp_path):
    import errno
    import os
    from types import SimpleNamespace

    calls = []

    def locking(fd, mode, count):
        calls.append((mode, count, os.lseek(fd, 0, os.SEEK_CUR)))
        if mode == 1 and len(calls) == 1:
            raise OSError(errno.EACCES, "busy")

    monkeypatch.setitem(
        sys.modules, "msvcrt", SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    )
    monkeypatch.setattr(store, "_LOCK_PLATFORM", "nt")
    with store._state_lock(tmp_path, timeout=1):
        assert (tmp_path / ".lock").read_bytes() == b"\0"
    assert calls == [(1, 1, 0), (1, 1, 0), (2, 1, 0)]
    assert (tmp_path / ".lock").read_bytes() == b"\0"


def test_windows_contention_timeout_releases_handles(monkeypatch, tmp_path):
    import errno
    from types import SimpleNamespace

    def busy(*args):
        raise OSError(errno.EACCES, "busy")

    monkeypatch.setitem(
        sys.modules, "msvcrt", SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=busy)
    )
    monkeypatch.setattr(store, "_LOCK_PLATFORM", "nt")
    with pytest.raises(ValueError, match="lock"):
        with store._state_lock(tmp_path, timeout=0.02):
            pass
    assert not store._OPEN_LOCK_FILES


def test_cli_corrupt_index_fails_before_yaml_mutation(tmp_path, capsys):
    tid = store.register(tmp_path, _make_thesis_data())
    (tmp_path / "_index.json").write_text("{")
    before = business_bytes(tmp_path)
    # main raises ValueError; the script-level handler normalizes it to stderr.
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            store.__file__,
            "--state-dir",
            str(tmp_path),
            "transition",
            tid,
            "ENTRY_READY",
            "--reason",
            "ready",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1
    assert "rebuild-index" in result.stderr
    assert "Traceback" not in result.stderr
    assert business_bytes(tmp_path) == before


def _fork_lock_probe(state, output):
    try:
        with store._state_lock(Path(state), timeout=0.05):
            output.put("unexpected acquisition")
    except ValueError:
        output.put("busy")


@pytest.mark.skipif("fork" not in multiprocessing.get_all_start_methods(), reason="POSIX fork only")
def test_forked_child_does_not_reuse_parent_reentrant_depth(tmp_path):
    ctx = multiprocessing.get_context("fork")
    output = ctx.Queue()
    with store._state_lock(tmp_path):
        proc = ctx.Process(target=_fork_lock_probe, args=(str(tmp_path), output))
        proc.start()
        try:
            assert output.get(timeout=10) == "busy"
            proc.join(10)
            assert proc.exitcode == 0
        finally:
            if proc.is_alive():
                proc.terminate()
            proc.join(5)
    output.close()
    with store._state_lock(tmp_path, timeout=1):
        pass


@pytest.mark.parametrize("manual", [False, True])
def test_legacy_short_real_cli_doctor_and_rebuild(tmp_path, manual, capsys):
    tid = active(tmp_path)
    corrupt_short(tmp_path, tid, manual)
    before = (tmp_path / f"{tid}.yaml").read_bytes()
    assert store.main(["--state-dir", str(tmp_path), "doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert store.main(["--state-dir", str(tmp_path), "rebuild-index"]) == 0
    capsys.readouterr()
    assert tid in store._load_index(tmp_path)["theses"]
    assert (tmp_path / f"{tid}.yaml").read_bytes() == before
