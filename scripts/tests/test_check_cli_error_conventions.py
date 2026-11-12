"""Tests for scripts/check_cli_error_conventions.py (issue #497)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

import scripts.check_cli_error_conventions as cec


def _scan(tmp_path: Path, source: str) -> list[cec.Finding]:
    path = tmp_path / "mod.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return cec.scan_file(path, "skills/x/scripts/mod.py")


def _rules(findings: list[cec.Finding]) -> list[str]:
    return [f.rule for f in findings]


# --- stderr-error-print -----------------------------------------------------


@pytest.mark.parametrize(
    "stmt",
    [
        'print("Error: boom")',
        'print("ERROR: boom")',
        'print("FATAL: boom")',
        'print(f"Error: {x}")',
        'print("  ERROR: indented")',
        'print("[ERROR] bracketed")',
        'print("❌ Error: emoji")',
    ],
)
def test_error_print_to_stdout_flagged(tmp_path, stmt):
    findings = _scan(tmp_path, f"x = 1\n{stmt}\n")
    assert _rules(findings) == [cec.RULE_PRINT]
    assert findings[0].line == 2


@pytest.mark.parametrize(
    "stmt",
    [
        'print("Error: boom", file=sys.stderr)',
        'print("Warning: not an error")',
        'print("Summary")',
        'print(f"{x} Error")',
        "print(message)",
        'print("no args error")',
    ],
)
def test_error_print_negative(tmp_path, stmt):
    assert _scan(tmp_path, f"import sys\nx = message = 1\n{stmt}\n") == []


def test_print_scope_is_enclosing_function(tmp_path):
    findings = _scan(
        tmp_path,
        """
        class A:
            def run(self):
                print("Error: x")
        """,
    )
    assert findings[0].scope == "A.run"


# --- import-error-exit1 -----------------------------------------------------


def test_module_level_import_error_exit1_flagged(tmp_path):
    findings = _scan(
        tmp_path,
        """
        import sys
        try:
            import requests
        except ImportError:
            print("missing", file=sys.stderr)
            sys.exit(1)
        """,
    )
    assert _rules(findings) == [cec.RULE_IMPORT]


def test_module_not_found_and_tuple_flagged(tmp_path):
    findings = _scan(
        tmp_path,
        """
        import sys
        try:
            import numpy
        except (ModuleNotFoundError, ValueError):
            sys.exit(1)
        """,
    )
    assert _rules(findings) == [cec.RULE_IMPORT]


@pytest.mark.parametrize(
    "body",
    [
        "sys.exit(2)",
        "HAS = False",
        "raise",
    ],
)
def test_import_error_other_handlers_ok(tmp_path, body):
    source = f"import sys\ntry:\n    import requests\nexcept ImportError:\n    {body}\n"
    assert _scan(tmp_path, source) == []


def test_function_scope_import_error_exit1_flagged(tmp_path):
    findings = _scan(
        tmp_path,
        """
        import sys
        def load():
            try:
                import requests
            except ImportError:
                sys.exit(1)
        """,
    )
    assert _rules(findings) == [cec.RULE_IMPORT]
    assert findings[0].scope == "load"


@pytest.mark.parametrize(
    "body",
    [
        'sys.exit("requests missing")',
        'raise SystemExit("requests missing")',
        'sys.exit(f"{name} missing")',
        "raise SystemExit(1)",
    ],
)
def test_import_error_string_or_systemexit_exit_flagged(tmp_path, body):
    source = (
        "import sys\nname = 1\ndef f():\n    try:\n        import x\n"
        f"    except ImportError:\n        {body}\n"
    )
    assert _rules(_scan(tmp_path, source)) == [cec.RULE_IMPORT]


@pytest.mark.parametrize(
    "body",
    [
        'print("hint", file=sys.stderr)\n        raise',
        'print("hint", file=sys.stderr)\n        sys.exit(2)',
        "x = None",
    ],
)
def test_function_scope_import_error_ok(tmp_path, body):
    source = (
        "import sys\ndef f():\n    try:\n        import x\n"
        f"    except ImportError:\n        {body}\n"
    )
    assert _scan(tmp_path, source) == []


def test_requests_is_none_guard_is_a_documented_limitation(tmp_path):
    findings = _scan(
        tmp_path,
        """
        import sys
        requests = None
        def f():
            if requests is None:
                sys.exit(1)
        """,
    )
    assert findings == []


# --- network-timeout --------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        "urlopen(req)",
        "urllib.request.urlopen(req)",
        "requests.get(url)",
        "requests.post(url, json=data)",
        "requests.request('GET', url)",
        "session.get(url)",
        "self.session.post(url)",
        "requests.get(url, timeout=None)",
    ],
)
def test_untimed_network_call_flagged(tmp_path, call):
    findings = _scan(tmp_path, f"req = url = data = session = 1\n{call}\n")
    assert _rules(findings) == [cec.RULE_TIMEOUT]


@pytest.mark.parametrize(
    "call",
    [
        "urlopen(req, timeout=10)",
        "requests.get(url, timeout=(3, 30))",
        "session.get(url, params=p, timeout=TIMEOUT)",
        "requests.get(url, **kwargs)",
        "cache.get(key)",
        "d.get('k')",
        "session_state.get('key')",
        "self.session_state.get('key')",
        "session.get()",
    ],
)
def test_timed_or_unrelated_call_ok(tmp_path, call):
    source = f"req = url = session = session_state = p = key = kwargs = TIMEOUT = 1\n{call}\n"
    assert _scan(tmp_path, source) == []


def test_assigned_session_receiver_flagged_whatever_its_name(tmp_path):
    findings = _scan(
        tmp_path,
        """
        import requests
        http = requests.Session()
        http.get()
        """,
    )
    assert _rules(findings) == [cec.RULE_TIMEOUT]


def test_session_named_url_keyword_flagged(tmp_path):
    findings = _scan(tmp_path, "sess = 1\nsess.post(url='http://x')\n")
    assert _rules(findings) == [cec.RULE_TIMEOUT]


# --- allowlist and tree scanning -------------------------------------------


def _project(tmp_path: Path, source: str) -> Path:
    script = tmp_path / "skills" / "demo" / "scripts" / "tool.py"
    script.parent.mkdir(parents=True)
    script.write_text(source, encoding="utf-8")
    tests_dir = script.parent / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_tool.py").write_text('print("Error: ignored in tests")\n', encoding="utf-8")
    return tmp_path


def _allow(root: Path, entries: list[dict]) -> Path:
    path = root / "allow.json"
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


ENTRY = {
    "path": "skills/demo/scripts/tool.py",
    "rule": cec.RULE_PRINT,
    "scope": "main",
    "reason": "intentional",
}
BAD_SOURCE = 'def main():\n    print("Error: x")\n'


def test_tests_directory_excluded_and_finding_reported(tmp_path):
    root = _project(tmp_path, BAD_SOURCE)
    lines, count = cec.run(root, root / "missing.json")
    assert count == 1
    assert lines == [
        "skills/demo/scripts/tool.py:2: stderr-error-print: "
        "error message printed to stdout; add file=sys.stderr"
    ]


def test_allowlist_suppresses_finding_line_independent(tmp_path):
    root = _project(tmp_path, "\n\n\n" + BAD_SOURCE)
    lines, _ = cec.run(root, _allow(root, [ENTRY]))
    assert lines == []


def test_stale_allowlist_entry_fails(tmp_path):
    root = _project(tmp_path, "def main():\n    pass\n")
    lines, _ = cec.run(root, _allow(root, [ENTRY]))
    assert len(lines) == 1
    assert "stale allowlist entry" in lines[0]


def test_allowlist_scope_mismatch_does_not_suppress(tmp_path):
    root = _project(tmp_path, BAD_SOURCE)
    entry = dict(ENTRY, scope="other")
    lines, _ = cec.run(root, _allow(root, [entry]))
    assert any("stderr-error-print" in line for line in lines)
    assert any("stale allowlist entry" in line for line in lines)


@pytest.mark.parametrize("missing", ["path", "rule", "scope", "reason"])
def test_allowlist_requires_reason_and_keys(tmp_path, missing):
    root = _project(tmp_path, BAD_SOURCE)
    entry = {k: v for k, v in ENTRY.items() if k != missing}
    lines, _ = cec.run(root, _allow(root, [entry]))
    assert any(f"missing non-empty '{missing}'" in line for line in lines)


def test_allowlist_blank_reason_rejected(tmp_path):
    root = _project(tmp_path, BAD_SOURCE)
    lines, _ = cec.run(root, _allow(root, [dict(ENTRY, reason="  ")]))
    assert any("reason" in line for line in lines)


def test_main_exit_codes(tmp_path, capsys):
    root = _project(tmp_path, BAD_SOURCE)
    assert cec.main(["--root", str(root), "--allowlist", str(root / "none.json")]) == 1
    assert "stderr-error-print" in capsys.readouterr().err
    allow = _allow(root, [ENTRY])
    assert cec.main(["--root", str(root), "--allowlist", str(allow)]) == 0


def test_repository_is_clean():
    lines, count = cec.run(cec.ROOT, cec.DEFAULT_ALLOWLIST)
    assert lines == []
    assert count > 0
