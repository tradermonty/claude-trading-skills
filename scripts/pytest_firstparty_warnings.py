"""Fail pytest sessions with unexpected deprecations from production source files.

Skills commonly use flat imports, so warning module names are insufficient.
Dependency and test-only warnings remain visible without failing this gate.
"""

from pathlib import Path

import pytest

_findings = []
_root = None
_pending = []


def pytest_configure(config):
    global _root
    _findings.clear()
    _root = Path(config.rootpath).resolve()
    for message in _pending:
        _record(message)
    _pending.clear()


def pytest_warning_recorded(warning_message, when, nodeid, location):
    if not issubclass(warning_message.category, DeprecationWarning):
        return
    if _root is None:
        _pending.append(warning_message)
        return
    _record(warning_message)


def _record(warning_message):
    path = Path(warning_message.filename).resolve()
    try:
        relative = path.relative_to(_root)
    except ValueError:
        return
    if relative.parts[0] not in {"skills", "scripts"} or "tests" in relative.parts:
        return
    _findings.append((relative, warning_message.lineno, str(warning_message.message)))


def pytest_unconfigure(config):
    global _root
    _root = None
    _pending.clear()


def pytest_sessionfinish(session, exitstatus):
    if _findings and exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    if _findings:
        terminalreporter.section("First-party deprecations (fatal)", red=True)
        for path, line, message in _findings:
            terminalreporter.write_line(f"{path}:{line}: {message}")
