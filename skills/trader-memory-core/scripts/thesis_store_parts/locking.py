# Source fragment executed in thesis_store's namespace, like persistence.py.
from __future__ import annotations

import errno
import inspect
import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from pathlib import Path

    import thesis_store

    _load_index = thesis_store._load_index
    _build_thesis_for_registration = thesis_store._build_thesis_for_registration
    _read_equity_position_report = thesis_store._read_equity_position_report

_STATE_LOCK_TIMEOUT = 30.0
_LOCK_PLATFORM = os.name
_LOCK_PID = os.getpid()
_STATE_THREADS = {}
_STATE_GUARD = threading.Lock()
_STATE_LOCAL = threading.local()
_OPEN_LOCK_FILES = set()


def _reset_inherited_locks():
    """Discard inherited Python locks/fds after fork; never unlock the parent's fd."""
    global _LOCK_PID, _STATE_THREADS, _STATE_GUARD, _STATE_LOCAL, _OPEN_LOCK_FILES
    if _LOCK_PID == os.getpid():
        return
    for stream in _OPEN_LOCK_FILES:
        stream.close()
    _STATE_THREADS = {}
    _STATE_GUARD = threading.Lock()
    _STATE_LOCAL = threading.local()
    _OPEN_LOCK_FILES = set()
    _LOCK_PID = os.getpid()


def _try_state_file_lock(stream):
    stream.seek(0)
    try:
        if _LOCK_PLATFORM == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
            return False
        raise
    return True


def _release_state_file_lock(stream):
    stream.seek(0)
    if _LOCK_PLATFORM == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _state_lock(state_dir: Path, timeout: float | None = None):
    """Serialize cooperating local writers, including nested calls and aliases."""
    _reset_inherited_locks()
    timeout = _STATE_LOCK_TIMEOUT if timeout is None else timeout
    if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 3600:
        raise ValueError("Invalid state lock timeout")
    deadline = time.monotonic() + timeout
    path = Path(state_dir).resolve()
    with _STATE_GUARD:
        mutex = _STATE_THREADS.setdefault(path, threading.RLock())
    if not mutex.acquire(timeout=max(0, deadline - time.monotonic())):
        raise ValueError("State lock busy; wait for the other writer and retry")
    stream = None
    locked = False
    depths = getattr(_STATE_LOCAL, "depths", None)
    if depths is None:
        depths = _STATE_LOCAL.depths = {}
    try:
        if depths.get(path, 0):
            depths[path] += 1
            try:
                yield path
            finally:
                depths[path] -= 1
            return
        try:
            path.mkdir(parents=True, exist_ok=True)
            stream = (path / ".lock").open("a+b")
            _OPEN_LOCK_FILES.add(stream)
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            while not _try_state_file_lock(stream):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("State lock busy; wait for the other writer and retry")
                time.sleep(min(0.01, remaining))
            locked = True
        except OSError:
            raise ValueError(
                "Cannot acquire state lock; check directory access and retry"
            ) from None
        depths[path] = 1
        try:
            yield path
        finally:
            depths.pop(path, None)
    finally:
        try:
            if locked:
                _release_state_file_lock(stream)
        finally:
            if stream is not None:
                _OPEN_LOCK_FILES.discard(stream)
                stream.close()
            mutex.release()


def _serialize_state_operation(fn, *, preflight=True):
    signature = inspect.signature(fn)

    @wraps(fn)
    def guarded(state_dir, *args, **kwargs):
        bound = signature.bind(state_dir, *args, **kwargs)
        bound.apply_defaults()
        # Preserve source-only rejection before creating a new state directory.
        # Re-run validation inside the locked body before any business writes.
        if not Path(state_dir).exists():
            if fn.__name__ == "register":
                _build_thesis_for_registration(bound.arguments["thesis_data"])
            elif fn.__name__ == "attach_position":
                _read_equity_position_report(
                    bound.arguments["position_report_path"],
                    bound.arguments["expected_entry"],
                    bound.arguments["expected_stop"],
                )
        with _state_lock(state_dir) as path:
            if preflight:
                _load_index(path)
            return fn(path, *args, **kwargs)

    return guarded
