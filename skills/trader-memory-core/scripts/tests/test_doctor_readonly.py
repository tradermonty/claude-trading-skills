"""Doctor inspects snapshots without creating state or requiring write access."""

import errno
import json
import os
from pathlib import Path

import pytest
import thesis_store as store
from test_thesis_store import _make_thesis_data


def snapshot_bytes(path):
    return {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()}


def test_validate_missing_directory_does_not_create_state(tmp_path):
    missing = tmp_path / "missing" / "state"
    assert isinstance(store.validate_state(missing), dict)
    assert not missing.parent.exists()


@pytest.mark.parametrize("broken", [False, True])
def test_doctor_inspects_chmod_readonly_snapshot_without_lock(tmp_path, capsys, broken):
    state = tmp_path / "snapshot"
    tid = store.register(state, _make_thesis_data())
    (state / ".lock").unlink()
    if broken:
        (state / store.INDEX_FILE).unlink()
    before = snapshot_bytes(state)
    state.chmod(0o555)
    try:
        if os.access(state, os.W_OK):
            pytest.skip(
                "Effective identity can write chmod-555 directories; simulated errno cases cover this platform"
            )
        code = store.main(["--state-dir", str(state), "doctor"])
        report = json.loads(capsys.readouterr().out)
        assert code == int(broken)
        assert report["ok"] is (not broken)
        assert report["missing_in_index"] == ([tid] if broken else [])
        assert snapshot_bytes(state) == before
        assert not (state / ".lock").exists()
    finally:
        state.chmod(0o755)


@pytest.mark.parametrize("error", [errno.EACCES, errno.EPERM, errno.EROFS])
def test_readonly_lock_open_falls_back_to_diagnostics(tmp_path, monkeypatch, error):
    state = tmp_path / "state"
    store.register(state, _make_thesis_data())
    (state / ".lock").unlink()
    before = snapshot_bytes(state)
    original_open = Path.open
    attempts = []

    def readonly_open(path, *args, **kwargs):
        if path == state / ".lock":
            attempts.append(path)
            raise OSError(error, "synthetic read-only lock location")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", readonly_open)
    assert store.validate_state(state)["ok"] is True
    assert attempts == [state / ".lock"]
    assert snapshot_bytes(state) == before


def test_doctor_does_not_recreate_directory_removed_after_access_check(tmp_path, monkeypatch):
    state = tmp_path / "disappearing"
    state.mkdir()
    original_access = os.access

    def access(path, mode, *args, **kwargs):
        if Path(path) == state and mode == os.W_OK:
            state.rmdir()
            return True
        return original_access(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "access", access)
    with pytest.raises(ValueError, match="Cannot acquire state lock"):
        store.validate_state(state)
    assert not state.exists()


def test_writable_doctor_still_coordinates_with_writers(tmp_path, monkeypatch):
    original_try = store._try_state_file_lock
    locked = []

    def lock(stream):
        locked.append(True)
        return original_try(stream)

    monkeypatch.setattr(store, "_try_state_file_lock", lock)
    assert store.validate_state(tmp_path)["ok"] is True
    assert locked == [True]
    assert (tmp_path / ".lock").is_file()


def test_doctor_does_not_hide_writer_contention(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_STATE_LOCK_TIMEOUT", 0)
    monkeypatch.setattr(store, "_try_state_file_lock", lambda _: False)
    with pytest.raises(ValueError, match="State lock busy"):
        store.validate_state(tmp_path)


def test_doctor_does_not_hide_unrelated_lock_io_error(tmp_path, monkeypatch):
    original_open = Path.open

    def broken_open(path, *args, **kwargs):
        if path == tmp_path / ".lock":
            raise OSError(errno.EIO, "synthetic storage failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_open)
    with pytest.raises(ValueError, match="Cannot acquire state lock"):
        store.validate_state(tmp_path)


@pytest.mark.parametrize("error", [errno.EACCES, errno.EPERM, errno.EROFS])
def test_writers_never_use_readonly_lock_fallback(tmp_path, monkeypatch, error):
    tid = store.register(tmp_path, _make_thesis_data())
    before = snapshot_bytes(tmp_path)
    original_open = Path.open

    def readonly_open(path, *args, **kwargs):
        mode = kwargs.get("mode", args[0] if args else "r")
        if path == tmp_path / ".lock" and any(flag in mode for flag in "wa+"):
            raise OSError(error, "synthetic lock permission failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", readonly_open)
    with pytest.raises(ValueError, match="Cannot acquire state lock"):
        store.update(tmp_path, tid, {"thesis_statement": "must not be written"})
    assert snapshot_bytes(tmp_path) == before
