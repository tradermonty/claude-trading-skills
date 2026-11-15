"""Tests for scripts/check_price_bar_defaults.py (issue #655)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

import scripts.check_price_bar_defaults as lint

REL = "skills/x/scripts/mod.py"


def _scan(source: str) -> list[lint.Finding]:
    return lint.scan_source(textwrap.dedent(source), REL)


def _summary(findings):
    return [(f.line, f.field, f.scope) for f in findings]


# --- rules ------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr,field",
    [
        ('bar.get("close", 0)', "close"),
        ('bar.get("open", 0.0)', "open"),
        ('row.get("high", 0)', "high"),
        ('row.get("low", 0.0)', "low"),
        ('d.get("volume", 0)', "volume"),
        ('d.get("adjClose", 0)', "adjClose"),
        ('d.get("close") or 0', "close"),
        ('d.get("volume") or 0.0', "volume"),
        ('float(d.get("close", None) or 0.0)', "close"),
        ('s.get("close", default=0)', "close"),
        ('s.get("volume", default=0.0)', "volume"),
        ('bar.get("close", False)', "close"),
        ('s.get("low", default=False)', "low"),
        ('bar.get("high") or False', "high"),
    ],
)
def test_zero_default_rules_flag(expr, field):
    findings = _scan(f"x = {expr}\n")
    assert _summary(findings) == [(1, field, "<module>")]


@pytest.mark.parametrize(
    "expr",
    [
        'bar.get("close")',
        'bar.get("close", 1)',
        'bar.get("close", None)',
        'bar.get("close", True)',
        's.get("close", default=None)',
        's.get("close", other=0)',
        'bar.get("close", -0.0)',
        'bar.get("price", 0)',
        'bar.get("Close", 0)',
        "bar.get(key, 0)",
        'bar["close"] or 0',
        'a.get("close") or b or 0',
        'bar.get("close") or 1',
        'bar.get("close") and 0',
        'get("close", 0)',
    ],
)
def test_zero_default_rules_do_not_flag(expr):
    assert _scan(f"x = {expr}\n") == []


def test_nested_default_is_flagged_on_inner_field():
    findings = _scan('x = d.get("close", d.get("adjClose", 0))\n')
    assert _summary(findings) == [(1, "adjClose", "<module>")]


def test_get_zero_or_zero_counts_once():
    findings = _scan('x = float(d.get("close", 0.0) or 0.0)\n')
    assert _summary(findings) == [(1, "close", "<module>")]
    findings = _scan('x = float(d.get("close", default=0) or 0)\n')
    assert _summary(findings) == [(1, "close", "<module>")]


def test_scopes_use_qualnames():
    findings = _scan(
        """
        class Calc:
            def run(self, bar):
                return bar.get("close", 0)

        def outer(bars):
            def inner(b):
                return b.get("volume", 0)
            return [inner(b) for b in bars]

        async def fetch(bar):
            return bar.get("low") or 0
        """
    )
    assert _summary(findings) == [
        (4, "close", "Calc.run"),
        (8, "volume", "outer.inner"),
        (12, "low", "fetch"),
    ]


# --- allowlist + repo scan ---------------------------------------------------


def _repo(tmp_path: Path, source: str, entries: list[dict] | None) -> tuple[Path, Path]:
    script = tmp_path / "skills" / "demo" / "scripts" / "calc.py"
    script.parent.mkdir(parents=True)
    script.write_text(textwrap.dedent(source), encoding="utf-8")
    tests_dir = tmp_path / "skills" / "demo" / "scripts" / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text('x = {}.get("close", 0)\n', encoding="utf-8")
    allowlist = tmp_path / "allow.json"
    if entries is not None:
        allowlist.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return tmp_path, allowlist


SOURCE = """
def f(bars):
    a = bars[0].get("close", 0)
    b = bars[1].get("close", 0)
    return a + b
"""

ENTRY = {
    "path": "skills/demo/scripts/calc.py",
    "scope": "f",
    "field": "close",
    "count": 2,
    "reason": "pending #655 migration: demo",
}


def test_tests_directory_is_excluded_and_exact_count_passes(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, [ENTRY])
    problems, files, total = lint.run(root, allowlist)
    assert problems == []
    assert files == 1
    assert total == 2


def test_unallowlisted_finding_fails(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, [])
    problems, _, _ = lint.run(root, allowlist)
    assert len(problems) == 2
    assert problems[0].startswith("skills/demo/scripts/calc.py:3: close")


def test_missing_allowlist_file_means_empty(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, None)
    problems, _, _ = lint.run(root, allowlist)
    assert len(problems) == 2


def test_more_findings_than_allowlisted_count_fails(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, [dict(ENTRY, count=1)])
    problems, _, _ = lint.run(root, allowlist)
    assert any("expected 1 finding(s), found 2" in p for p in problems)


def test_fewer_findings_than_allowlisted_count_fails(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, [dict(ENTRY, count=3)])
    problems, _, _ = lint.run(root, allowlist)
    assert any("expected 3 finding(s), found 2" in p for p in problems)


def test_stale_entry_with_no_findings_fails(tmp_path):
    stale = dict(ENTRY, scope="g", count=1)
    root, allowlist = _repo(tmp_path, SOURCE, [ENTRY, stale])
    problems, _, _ = lint.run(root, allowlist)
    assert any("expected 1 finding(s), found 0" in p for p in problems)


def test_scope_must_match(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, [dict(ENTRY, scope="<module>")])
    problems, _, _ = lint.run(root, allowlist)
    assert any("calc.py:3: close" in p for p in problems)
    assert any("found 0" in p for p in problems)


def test_module_scope_entry(tmp_path):
    source = 'X = {}.get("volume", 0)\n'
    entry = dict(ENTRY, scope="<module>", field="volume", count=1)
    root, allowlist = _repo(tmp_path, source, [entry])
    assert lint.run(root, allowlist)[0] == []


@pytest.mark.parametrize(
    "bad,message",
    [
        ({"scope": "f", "field": "close", "count": 2, "reason": "r"}, "'path'"),
        (dict(ENTRY, reason=" "), "'reason'"),
        (dict(ENTRY, count=0), "'count'"),
        (dict(ENTRY, count=True), "'count'"),
        (dict(ENTRY, field="price"), "unknown field"),
    ],
)
def test_invalid_entries_fail(tmp_path, bad, message):
    root, allowlist = _repo(tmp_path, SOURCE, [bad])
    problems, _, _ = lint.run(root, allowlist)
    assert any(message in p for p in problems)


def test_duplicate_key_fails(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, [ENTRY, ENTRY])
    problems, _, _ = lint.run(root, allowlist)
    assert any("duplicate" in p for p in problems)


def test_invalid_json_fails(tmp_path):
    root, allowlist = _repo(tmp_path, SOURCE, [])
    allowlist.write_text("{not json", encoding="utf-8")
    problems, _, _ = lint.run(root, allowlist)
    assert problems and "invalid JSON" in problems[0]


def test_main_exit_codes(tmp_path, capsys):
    root, allowlist = _repo(tmp_path, SOURCE, [ENTRY])
    assert lint.main(["--root", str(root), "--allowlist", str(allowlist)]) == 0
    assert "OK" in capsys.readouterr().out
    allowlist.write_text(json.dumps({"entries": []}), encoding="utf-8")
    assert lint.main(["--root", str(root), "--allowlist", str(allowlist)]) == 1
    assert "zero-default" in capsys.readouterr().err


def test_repository_is_clean():
    problems, files, total = lint.run(lint.ROOT, lint.DEFAULT_ALLOWLIST)
    assert problems == []
    assert files > 0
    assert total == sum(e["count"] for e in lint.load_allowlist(lint.DEFAULT_ALLOWLIST)[0])


def test_ftd_detector_has_no_allowlist_entries():
    entries, errors = lint.load_allowlist(lint.DEFAULT_ALLOWLIST)
    assert errors == []
    assert not [e for e in entries if e["path"].startswith("skills/ftd-detector/")]
