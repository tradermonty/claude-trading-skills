#!/usr/bin/env python3
"""Run every versioned CI test row without requiring a POSIX shell."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

if __package__:
    from .ci_test_matrix import MatrixError, TestEntry, build_entries, install, run
else:
    from ci_test_matrix import MatrixError, TestEntry, build_entries, install, run

ROOT = Path(__file__).resolve().parents[1]


def execute(
    entries: dict[str, TestEntry],
    *,
    root: Path = ROOT,
    emit: Callable[[str], None] = print,
) -> int:
    failures: list[str] = []
    known_failures: list[str] = []
    for entry in entries.values():
        emit(f"--- {entry.id} ---")
        try:
            install(entry)
            returncode = run(entry, root, None)
        except (MatrixError, OSError, subprocess.CalledProcessError) as exc:
            emit(f"ERROR: {exc}")
            returncode = 1
        if returncode != 0:
            if entry.allowed_failure:
                known_failures.append(entry.id)
                emit(f"KNOWN FAILURE: {entry.id} is non-blocking")
            else:
                failures.append(entry.id)
        emit("")
    passed = len(entries) - len(failures) - len(known_failures)
    emit(f"=== Summary: {passed}/{len(entries)} passed, {len(known_failures)} known failure(s) ===")
    if failures:
        emit(f"FAILED: {' '.join(failures)}")
        return 1
    return 0


def main() -> int:
    try:
        entries = build_entries(ROOT)
    except (MatrixError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return execute(entries)


if __name__ == "__main__":
    raise SystemExit(main())
