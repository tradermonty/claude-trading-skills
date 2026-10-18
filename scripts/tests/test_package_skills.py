"""Tests for scripts/package_skills.py."""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from package_skills import (  # noqa: E402
    check_skill,
    discover_skill_dirs,
    package_skill,
    should_include,
)


def test_should_include_excludes_tests_and_local_artifacts() -> None:
    assert should_include(Path("SKILL.md"))
    assert should_include(Path("scripts/run.py"))
    assert not should_include(Path("scripts/tests/test_run.py"))
    assert not should_include(Path("tests/test_skill.py"))
    assert not should_include(Path("scripts/__pycache__/run.cpython-311.pyc"))
    assert not should_include(Path("scripts/.pytest_cache/v/cache/nodeids"))
    assert not should_include(Path("assets/.DS_Store"))


def test_package_skill_excludes_tests_and_build_artifacts(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "demo-skill"
    (skill_dir / "scripts" / "tests").mkdir(parents=True)
    (skill_dir / "references").mkdir()
    (skill_dir / "assets").mkdir()
    (skill_dir / "scripts" / "__pycache__").mkdir()
    (skill_dir / "scripts" / ".pytest_cache" / "v" / "cache").mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo.\n---\n")
    (skill_dir / "requirements.txt").write_text("# stdlib-only\n")
    (skill_dir / "scripts" / "run.py").write_text("print('ok')\n")
    (skill_dir / "scripts" / "tests" / "test_run.py").write_text("def test_run(): pass\n")
    (skill_dir / "scripts" / "__pycache__" / "run.cpython-311.pyc").write_bytes(b"pyc")
    (skill_dir / "scripts" / ".pytest_cache" / "v" / "cache" / "nodeids").write_text("[]\n")
    (skill_dir / "references" / "guide.md").write_text("# Guide\n")
    (skill_dir / "assets" / ".DS_Store").write_bytes(b"junk")

    output_path = package_skill(skill_dir, tmp_path / "skill-packages")

    with ZipFile(output_path) as archive:
        names = set(archive.namelist())

    assert "demo-skill/SKILL.md" in names
    assert "demo-skill/requirements.txt" in names
    assert "demo-skill/scripts/run.py" in names
    assert "demo-skill/references/guide.md" in names
    assert all("/tests/" not in name for name in names)
    assert all("__pycache__" not in name for name in names)
    assert all(".pytest_cache" not in name for name in names)
    assert all(not name.endswith(".DS_Store") for name in names)


def _git_skill_with_executable_script(tmp_path: Path) -> Path:
    """A skill in a fresh git repo whose script is 100755 in the index only."""
    import subprocess

    skill_dir = tmp_path / "skills" / "demo-skill"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo.\n---\n")
    (skill_dir / "requirements.txt").write_text("# stdlib-only\n")
    script = skill_dir / "scripts" / "run.py"
    script.write_text("print('ok')\n")
    script.chmod(0o644)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("add", ".")
    git("update-index", "--chmod=+x", "skills/demo-skill/scripts/run.py")
    return skill_dir


@pytest.mark.skipif(__import__("shutil").which("git") is None, reason="git not installed")
def test_exec_bit_comes_from_git_index_when_filesystem_lacks_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows os.stat never reports +x on .py files; the git index is the truth."""
    import package_skills

    monkeypatch.setattr(package_skills, "FILESYSTEM_TRACKS_EXEC_BIT", False)
    skill_dir = _git_skill_with_executable_script(tmp_path)
    output_dir = tmp_path / "skill-packages"

    output_path = package_skill(skill_dir, output_dir)

    with ZipFile(output_path) as archive:
        modes = {info.filename: info.external_attr >> 16 for info in archive.infolist()}
    assert modes["demo-skill/scripts/run.py"] & 0o111
    assert not modes["demo-skill/SKILL.md"] & 0o111
    assert check_skill(skill_dir, output_dir)


def test_discover_skill_dirs_sorts_skills_with_skill_md(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    for name in ["z-skill", "a-skill"]:
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: x\ndescription: x\n---\n")
    (skills_dir / "not-a-skill").mkdir()

    assert [path.name for path in discover_skill_dirs(skills_dir)] == ["a-skill", "z-skill"]


def test_package_skill_fails_closed_without_dependency_manifest(
    tmp_path: Path, capsys: object
) -> None:
    """Executable skills without requirements.txt cannot be packaged (issue #330)."""
    import pytest

    skill_dir = tmp_path / "skills" / "demo-skill"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo.\n---\n")
    (skill_dir / "scripts" / "run.py").write_text("print('ok')\n")

    with pytest.raises(ValueError, match="requirements.txt"):
        package_skill(skill_dir, tmp_path / "skill-packages")
    assert not check_skill(skill_dir, tmp_path / "skill-packages")
    assert "requirements.txt" in capsys.readouterr().out


def test_package_skill_allows_script_free_skill_without_manifest(tmp_path: Path) -> None:
    """Knowledge-only style skills (no packaged scripts) need no manifest."""
    skill_dir = tmp_path / "skills" / "docs-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: docs-skill\ndescription: Docs.\n---\n")
    (skill_dir / "references" / "guide.md").write_text("# Guide\n")

    output_path = package_skill(skill_dir, tmp_path / "skill-packages")
    assert output_path.is_file()


@pytest.mark.parametrize("bad_name", ["demo-skill/../evil", "other/SKILL.md", "demo-skill\\evil"])
def test_check_skill_rejects_unsafe_zip_member(tmp_path: Path, bad_name: str) -> None:
    skill_dir = tmp_path / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("demo\n")
    output_dir = tmp_path / "packages"
    archive_path = package_skill(skill_dir, output_dir)
    with ZipFile(archive_path, "a") as archive:
        archive.writestr(bad_name, b"bad")
    assert not check_skill(skill_dir, output_dir)


def test_check_skill_rejects_duplicate_zip_member(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("demo\n")
    output_dir = tmp_path / "packages"
    archive_path = package_skill(skill_dir, output_dir)
    with ZipFile(archive_path, "a") as archive:
        archive.writestr("demo-skill/SKILL.md", b"demo\n")
    assert not check_skill(skill_dir, output_dir)


def test_check_skill_rejects_symlink_member(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("demo\n")
    output_dir = tmp_path / "packages"
    archive_path = package_skill(skill_dir, output_dir)
    with ZipFile(archive_path, "a") as archive:
        info = ZipInfo("demo-skill/link")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "../../secret")
    assert not check_skill(skill_dir, output_dir)


def test_check_skill_rejects_special_file_member(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("demo\n")
    output_dir = tmp_path / "packages"
    archive_path = output_dir / "demo-skill.skill"
    output_dir.mkdir()
    with ZipFile(archive_path, "w") as archive:
        info = ZipInfo("demo-skill/SKILL.md")
        info.create_system = 3
        info.external_attr = (stat.S_IFIFO | 0o644) << 16
        archive.writestr(info, b"demo\n")
    assert not check_skill(skill_dir, output_dir)


@pytest.mark.parametrize(
    "name", ["demo-skill/foo\nDRIFT: forged", "demo-skill/foo\rforged", "demo-skill/foo\x1bforged"]
)
def test_control_character_member_reports_single_escaped_drift(
    tmp_path: Path, capsys, name: str
) -> None:
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("demo")
    output = tmp_path / "packages"
    archive_path = package_skill(skill, output)
    with ZipFile(archive_path, "a") as archive:
        archive.writestr(name, b"bad")
    assert not check_skill(skill, output)
    diagnostic = capsys.readouterr().out
    assert len(diagnostic.splitlines()) == 1
    assert repr(name) in diagnostic
    assert diagnostic.startswith("DRIFT:")


@pytest.mark.parametrize("encrypted", [True, False])
def test_unreadable_zip_member_reports_drift(tmp_path: Path, capsys, encrypted: bool) -> None:
    import struct

    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("demo")
    output = tmp_path / "packages"
    archive_path = package_skill(skill, output)
    data = bytearray(archive_path.read_bytes())
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    if encrypted:
        for offset in (local + 6, central + 8):
            flags = struct.unpack_from("<H", data, offset)[0]
            struct.pack_into("<H", data, offset, flags | 1)
    else:
        for offset in (local + 8, central + 10):
            struct.pack_into("<H", data, offset, 99)
    archive_path.write_bytes(data)
    assert not check_skill(skill, output)
    diagnostic = capsys.readouterr().out
    assert "DRIFT:" in diagnostic
    assert "Unreadable archive member: 'demo-skill/SKILL.md'" in diagnostic


def test_corrupt_compressed_member_reports_drift(tmp_path: Path, capsys) -> None:
    import struct

    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("demo " * 50)
    output = tmp_path / "packages"
    archive_path = package_skill(skill, output)
    data = bytearray(archive_path.read_bytes())
    local = data.index(b"PK\x03\x04")
    name_len, extra_len = struct.unpack_from("<HH", data, local + 26)
    # 0xFF starts a deflate block with reserved BTYPE=11, so decompression fails.
    data[local + 30 + name_len + extra_len] = 0xFF
    archive_path.write_bytes(data)
    assert not check_skill(skill, output)
    diagnostic = capsys.readouterr().out
    assert "Unreadable archive member: 'demo-skill/SKILL.md'" in diagnostic
