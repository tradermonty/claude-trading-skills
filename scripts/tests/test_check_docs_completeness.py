"""Tests for the docs-completeness pre-commit hook (issue #432 hardening)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
HOOKS_DIR = SCRIPTS_DIR / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import check_docs_completeness as hook  # noqa: E402


def _make_skill(root: Path, name: str, *, with_docs: bool = True) -> None:
    (root / "skills" / name).mkdir(parents=True)
    (root / "skills" / name / "SKILL.md").write_text(
        "---\nname: placeholder\nd: x\n---\n", encoding="utf-8"
    )
    if with_docs:
        for lang in ("en", "ja"):
            d = root / "docs" / lang / "skills"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.md").write_text("# doc\n", encoding="utf-8")


def test_no_orphan_no_errors(tmp_path):
    _make_skill(tmp_path, "demo-skill")
    assert hook.find_orphan_skill_dirs(tmp_path) == []
    assert hook.find_skills_without_docs(tmp_path) == []


def test_orphan_dir_without_skill_md_flagged(tmp_path):
    (tmp_path / "skills" / "orphan-dir" / "scripts").mkdir(parents=True)
    (tmp_path / "skills" / "orphan-dir" / "scripts" / "note.txt").write_text("x", encoding="utf-8")
    errors = hook.find_orphan_skill_dirs(tmp_path)
    assert len(errors) == 1
    assert "orphan-dir" in errors[0]
    assert "SKILL.md" in errors[0]


def test_files_and_dotdirs_ignored(tmp_path):
    (tmp_path / "skills").mkdir(parents=True)
    (tmp_path / "skills" / ".DS_Store").write_text("x", encoding="utf-8")
    (tmp_path / "skills" / ".hidden").mkdir()
    (tmp_path / "skills" / "__pycache__").mkdir()
    assert hook.find_orphan_skill_dirs(tmp_path) == []


def test_missing_docs_still_flagged(tmp_path):
    _make_skill(tmp_path, "undoc-skill", with_docs=False)
    errors = hook.find_skills_without_docs(tmp_path)
    assert len(errors) == 1
    assert "undoc-skill" in errors[0]


def test_missing_skills_dir_returns_empty(tmp_path):
    assert hook.find_orphan_skill_dirs(tmp_path / "nonexistent") == []
    assert hook.find_skills_without_docs(tmp_path / "nonexistent") == []


def test_main_passes_on_real_repo():
    assert hook.main() == 0


def test_main_fails_on_orphan(tmp_path, monkeypatch, capsys):
    (tmp_path / "skills" / "orphan-dir").mkdir(parents=True)
    monkeypatch.setattr(hook, "PROJECT_ROOT", tmp_path)
    assert hook.main() == 1
    assert "orphan-dir" in capsys.readouterr().out
