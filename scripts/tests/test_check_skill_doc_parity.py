"""Tests for the EN/JA skill-doc parity checker (issue #433)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import check_skill_doc_parity as parity  # noqa: E402


def test_extract_commands_joins_continuations(tmp_path):
    page = tmp_path / "en.md"
    page.write_text(
        "```bash\npython3 run.py \\\n  --spec a.json \\\n  --out b.json\n```\n",
        encoding="utf-8",
    )
    counter, _ = parity._extract_commands(page)
    assert counter == {"python3 run.py --spec a.json --out b.json": 1}


def test_full_line_comments_ignored_and_inline_stripped(tmp_path):
    page = tmp_path / "en.md"
    page.write_text(
        "```bash\n# install step\npython3 run.py --out b.json # write result\n```\n",
        encoding="utf-8",
    )
    counter, _ = parity._extract_commands(page)
    assert counter == {"python3 run.py --out b.json": 1}


def test_quoted_hash_not_stripped(tmp_path):
    page = tmp_path / "en.md"
    page.write_text('```bash\npython3 log.py -m "fix #123"\n```\n', encoding="utf-8")
    counter, _ = parity._extract_commands(page)
    assert counter == {'python3 log.py -m "fix #123"': 1}


def test_non_command_lines_ignored(tmp_path):
    page = tmp_path / "en.md"
    page.write_text(
        '```bash\nSet fees before reading any result.\n{"a": 1}\n```\n',
        encoding="utf-8",
    )
    counter, notes = parity._extract_commands(page)
    assert counter == Counter()
    assert len(notes) == 1


def test_json_and_text_fences_out_of_scope(tmp_path):
    page = tmp_path / "en.md"
    page.write_text(
        '```json\n{"a": 1}\n```\n```text\nsome output\n```\n',
        encoding="utf-8",
    )
    counter, _ = parity._extract_commands(page)
    assert counter == Counter()


def test_shebang_and_prompts(tmp_path):
    page = tmp_path / "en.md"
    page.write_text(
        "```bash\n#!/bin/bash\n$ python3 run.py\n> python3 other.py\n```\n",
        encoding="utf-8",
    )
    counter, _ = parity._extract_commands(page)
    assert counter == {"python3 run.py": 1, "python3 other.py": 1}


def test_missing_command_reported_with_counts(monkeypatch, tmp_path):
    en_dir = tmp_path / "en"
    ja_dir = tmp_path / "ja"
    en_dir.mkdir()
    ja_dir.mkdir()
    monkeypatch.setattr(parity, "EN_DIR", en_dir)
    monkeypatch.setattr(parity, "JA_DIR", ja_dir)
    (en_dir / "en-skill.md").write_text("```bash\npython3 run.py --x 1\n```\n", encoding="utf-8")
    (ja_dir / "en-skill.md").write_text("no fences\n", encoding="utf-8")
    violations = parity.check_skill("en-skill")
    assert len(violations) == 1
    assert "missing x1" in violations[0]
    assert "python3 run.py --x 1" in violations[0]


def test_ja_extras_allowed(monkeypatch, tmp_path):
    en_dir = tmp_path / "en"
    ja_dir = tmp_path / "ja"
    en_dir.mkdir()
    ja_dir.mkdir()
    monkeypatch.setattr(parity, "EN_DIR", en_dir)
    monkeypatch.setattr(parity, "JA_DIR", ja_dir)
    (en_dir / "pair.md").write_text("```bash\npython3 run.py\n```\n", encoding="utf-8")
    # JA has the EN command plus an extra example
    (ja_dir / "pair.md").write_text(
        "```bash\npython3 run.py\n```\n```bash\npython3 extra.py\n```\n",
        encoding="utf-8",
    )
    assert parity.check_skill("pair") == []


def test_untranslated_banner_skips(monkeypatch, tmp_path):
    en_dir = tmp_path / "en"
    ja_dir = tmp_path / "ja"
    en_dir.mkdir()
    ja_dir.mkdir()
    monkeypatch.setattr(parity, "EN_DIR", en_dir)
    monkeypatch.setattr(parity, "JA_DIR", ja_dir)
    (en_dir / "stub.md").write_text("```bash\npython3 run.py\n```\n", encoding="utf-8")
    (ja_dir / "stub.md").write_text(parity.UNTRANSLATED_BANNER + "\n", encoding="utf-8")
    assert parity.check_skill("stub") == []


def test_banner_wording_drift_not_skipped(monkeypatch, tmp_path):
    en_dir = tmp_path / "en"
    ja_dir = tmp_path / "ja"
    en_dir.mkdir()
    ja_dir.mkdir()
    monkeypatch.setattr(parity, "EN_DIR", en_dir)
    monkeypatch.setattr(parity, "JA_DIR", ja_dir)
    (en_dir / "s.md").write_text("```bash\npython3 run.py\n```\n", encoding="utf-8")
    (ja_dir / "s.md").write_text("not yet translated to Japanese\n", encoding="utf-8")
    assert len(parity.check_skill("s")) == 1


def test_full_repo_check_is_green():
    violations, _ = parity.check_all()
    effective = [v for v in violations if not _allowlisted(v)]
    assert effective == []


def _allowlisted(violation: str) -> bool:
    import re

    m = re.match(r"\s*\[(.*?)\] missing x\d+: (.*)", violation)
    if not m:
        return False
    return parity.is_allowlisted(m.group(1), m.group(2))


def test_allowlist_helper_matches_main_filter():
    # The test helper must stay consistent with the checker's own filter.
    assert parity.is_allowlisted("vcp-screener", "python3 missing.py") is False


def test_flipped_pages_have_no_violations():
    for skill in (
        "manifoldbt-backtester",
        "mt5-robot-tester",
        "residual-edge-analyzer",
        "us-undervalued-growth-screener",
    ):
        assert parity.check_skill(skill) == [], skill
