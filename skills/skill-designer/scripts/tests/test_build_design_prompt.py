"""Tests for build_design_prompt.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import build_design_prompt as bdp
import pytest
from build_design_prompt import (
    REFERENCES_DIR,
    build_prompt,
    list_existing_skills,
    load_references,
)


def _make_idea(title: str = "test-skill", description: str = "A test skill") -> dict:
    return {"title": title, "description": description, "category": "testing"}


def test_build_prompt_uses_skill_name():
    """Prompt uses the --skill-name value for directory and frontmatter name."""
    refs = load_references(REFERENCES_DIR)
    prompt = build_prompt(_make_idea(), "my-custom-name", refs, [])

    assert "skills/my-custom-name/" in prompt
    assert "`my-custom-name`" in prompt
    assert "name:` field MUST be exactly `my-custom-name`" in prompt


def test_build_prompt_includes_refs():
    """All three reference file contents are embedded in the prompt."""
    refs = load_references(REFERENCES_DIR)

    # All 3 references should be loaded
    assert len(refs) == 3
    assert "skill-structure-guide.md" in refs
    assert "quality-checklist.md" in refs
    assert "skill-template.md" in refs

    prompt = build_prompt(_make_idea(), "test-skill", refs, [])

    # Each reference content should appear in the prompt
    assert "--- BEGIN skill-structure-guide.md ---" in prompt
    assert "--- BEGIN quality-checklist.md ---" in prompt
    assert "--- BEGIN skill-template.md ---" in prompt


def test_build_prompt_frontmatter_name_matches():
    """Prompt instructs Claude to set name: matching the skill_name."""
    refs = load_references(REFERENCES_DIR)
    prompt = build_prompt(_make_idea(), "exact-name-here", refs, ["existing-a", "existing-b"])

    # Should instruct the frontmatter name to match
    assert "exact-name-here" in prompt
    # Should list existing skills for deduplication
    assert "existing-a" in prompt
    assert "existing-b" in prompt


def test_load_references_skips_missing_files(tmp_path):
    (tmp_path / "quality-checklist.md").write_text("QC body", encoding="utf-8")
    refs = load_references(tmp_path)
    assert refs == {"quality-checklist.md": "QC body"}


def test_list_existing_skills_filters_and_sorts(tmp_path):
    skills = tmp_path / "skills"
    for name in ("zeta", "alpha", "nomd"):
        (skills / name).mkdir(parents=True)
    (skills / "zeta" / "SKILL.md").write_text("x")
    (skills / "alpha" / "SKILL.md").write_text("x")
    (skills / "stray.txt").write_text("x")
    assert list_existing_skills(tmp_path) == ["alpha", "zeta"]


def test_list_existing_skills_respects_limit(tmp_path):
    for name in ("a", "b", "c"):
        (tmp_path / "skills" / name).mkdir(parents=True)
        (tmp_path / "skills" / name / "SKILL.md").write_text("x")
    assert list_existing_skills(tmp_path, limit=2) == ["a", "b"]


def test_list_existing_skills_no_skills_dir(tmp_path):
    assert list_existing_skills(tmp_path) == []


def test_build_prompt_defaults_and_none_marker():
    prompt = build_prompt({}, "s", {}, [])
    assert "- **Title**: unnamed" in prompt
    assert "- **Category**: general" in prompt
    assert "- **Description**: \n" in prompt
    assert "## Existing Skills (do not duplicate)\n\n- (none)" in prompt
    assert "--- BEGIN" not in prompt


def test_build_prompt_embeds_reference_content_and_idea():
    prompt = build_prompt(_make_idea("T", "D"), "s", {"r.md": "REF BODY"}, ["x"])
    assert "--- BEGIN r.md ---\nREF BODY\n--- END r.md ---" in prompt
    assert "- **Title**: T" in prompt
    assert "- **Description**: D" in prompt
    assert "- x" in prompt


def _run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["build_design_prompt.py", *argv])
    return bdp.main()


def test_main_prints_prompt(tmp_path, monkeypatch, capsys):
    idea = tmp_path / "idea.json"
    idea.write_text(json.dumps(_make_idea("My Idea", "Desc")), encoding="utf-8")
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("x")
    rc = _run_main(
        monkeypatch,
        ["--idea-json", str(idea), "--skill-name", "new-skill", "--project-root", str(tmp_path)],
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "named 'new-skill'" in out
    assert "- **Title**: My Idea" in out
    assert "- foo" in out
    assert "--- BEGIN skill-template.md ---" in out


def test_main_missing_idea_file(tmp_path, monkeypatch, capsys):
    rc = _run_main(monkeypatch, ["--idea-json", str(tmp_path / "nope.json"), "--skill-name", "s"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "idea JSON not found" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "idea JSON is not valid JSON"),
        ("[1, 2]", "idea JSON must be an object"),
    ],
)
def test_main_rejects_unusable_idea_json(tmp_path, monkeypatch, capsys, content, message):
    idea = tmp_path / "idea.json"
    idea.write_text(content, encoding="utf-8")
    rc = _run_main(monkeypatch, ["--idea-json", str(idea), "--skill-name", "s"])
    captured = capsys.readouterr()
    assert rc == 1
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_main_missing_references(tmp_path, monkeypatch, capsys):
    idea = tmp_path / "idea.json"
    idea.write_text("{}", encoding="utf-8")
    (tmp_path / "refs").mkdir()
    (tmp_path / "refs" / "skill-template.md").write_text("only one")
    monkeypatch.setattr(bdp, "REFERENCES_DIR", tmp_path / "refs")
    rc = _run_main(monkeypatch, ["--idea-json", str(idea), "--skill-name", "s"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "reference files missing" in captured.err
    missing_part = captured.err.split("missing:")[1]
    assert "skill-structure-guide.md" in missing_part
    assert "quality-checklist.md" in missing_part
    assert "skill-template.md" not in missing_part
    assert captured.out == ""


def test_script_entrypoint_exit_code(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(bdp.__file__)),
            "--idea-json",
            str(tmp_path / "x.json"),
            "--skill-name",
            "s",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "idea JSON not found" in result.stderr
