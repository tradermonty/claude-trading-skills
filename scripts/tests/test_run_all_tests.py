from __future__ import annotations

from pathlib import Path

from scripts.ci_test_matrix import TestEntry
from scripts.run_all_tests import execute


def _entry(entry_id: str, *, allowed_failure: bool = False) -> TestEntry:
    return TestEntry(
        id=entry_id,
        test_paths=("tests",),
        coverage_source="skills/example/scripts",
        allowed_failure=allowed_failure,
    )


def test_execute_reports_blocking_and_known_failures(monkeypatch, tmp_path):
    entries = {
        "passing": _entry("passing"),
        "known": _entry("known", allowed_failure=True),
        "broken": _entry("broken"),
    }
    monkeypatch.setattr("scripts.run_all_tests.install", lambda entry: None)
    monkeypatch.setattr(
        "scripts.run_all_tests.run",
        lambda entry, root, coverage_dir: 0 if entry.id == "passing" else 1,
    )
    output: list[str] = []

    assert execute(entries, root=tmp_path, emit=output.append) == 1
    assert "KNOWN FAILURE: known is non-blocking" in output
    assert "FAILED: broken" in output
    assert "=== Summary: 1/3 passed, 1 known failure(s) ===" in output


def test_execute_succeeds_with_only_allowed_failure(monkeypatch, tmp_path: Path):
    entries = {"known": _entry("known", allowed_failure=True)}
    monkeypatch.setattr("scripts.run_all_tests.install", lambda entry: None)
    monkeypatch.setattr("scripts.run_all_tests.run", lambda entry, root, coverage_dir: 1)

    assert execute(entries, root=tmp_path, emit=lambda _: None) == 0
