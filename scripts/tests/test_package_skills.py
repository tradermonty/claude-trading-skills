"""Tests for scripts/package_skills.py."""

from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZipFile

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from package_skills import discover_skill_dirs, package_skill, should_include  # noqa: E402


def test_should_include_excludes_tests_and_local_artifacts() -> None:
    assert should_include(Path("SKILL.md"))
    assert should_include(Path("scripts/run.py"))
    assert not should_include(Path("scripts/tests/test_run.py"))
    assert not should_include(Path("tests/test_skill.py"))
    assert not should_include(Path("scripts/__pycache__/run.cpython-311.pyc"))
    assert not should_include(Path("assets/.DS_Store"))


def test_package_skill_excludes_tests_and_build_artifacts(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "demo-skill"
    (skill_dir / "scripts" / "tests").mkdir(parents=True)
    (skill_dir / "references").mkdir()
    (skill_dir / "assets").mkdir()
    (skill_dir / "scripts" / "__pycache__").mkdir()

    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo.\n---\n")
    (skill_dir / "scripts" / "run.py").write_text("print('ok')\n")
    (skill_dir / "scripts" / "tests" / "test_run.py").write_text("def test_run(): pass\n")
    (skill_dir / "scripts" / "__pycache__" / "run.cpython-311.pyc").write_bytes(b"pyc")
    (skill_dir / "references" / "guide.md").write_text("# Guide\n")
    (skill_dir / "assets" / ".DS_Store").write_bytes(b"junk")

    output_path = package_skill(skill_dir, tmp_path / "skill-packages")

    with ZipFile(output_path) as archive:
        names = set(archive.namelist())

    assert "demo-skill/SKILL.md" in names
    assert "demo-skill/scripts/run.py" in names
    assert "demo-skill/references/guide.md" in names
    assert all("/tests/" not in name for name in names)
    assert all("__pycache__" not in name for name in names)
    assert all(not name.endswith(".DS_Store") for name in names)


def test_discover_skill_dirs_sorts_skills_with_skill_md(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    for name in ["z-skill", "a-skill"]:
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: x\ndescription: x\n---\n")
    (skills_dir / "not-a-skill").mkdir()

    assert [path.name for path in discover_skill_dirs(skills_dir)] == ["a-skill", "z-skill"]
