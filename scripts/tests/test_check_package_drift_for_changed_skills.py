"""Tests for scripts/check_package_drift_for_changed_skills.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import check_package_drift_for_changed_skills as checker  # noqa: E402
from check_package_drift_for_changed_skills import (
    check_changed_package_drift,  # noqa: E402
    packaged_skills_for_changed_paths,  # noqa: E402
)
from package_skills import package_skill  # noqa: E402


def _make_skill(project_root: Path, skill_name: str, *, package: bool = True) -> Path:
    skill_dir = project_root / "skills" / skill_name
    (skill_dir / "scripts" / "tests").mkdir(parents=True)
    (skill_dir / "references").mkdir()
    (skill_dir / "schemas").mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: Demo skill.\n---\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / "scripts" / "tests" / "test_run.py").write_text(
        "def test_run(): pass\n",
        encoding="utf-8",
    )
    (skill_dir / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (skill_dir / "schemas" / "input.schema.json").write_text("{}\n", encoding="utf-8")
    if package:
        package_skill(skill_dir, project_root / "skill-packages")
    return skill_dir


def _check(project_root: Path, changed_paths: list[str]) -> int:
    return check_changed_package_drift(
        changed_paths,
        skills_dir=project_root / "skills",
        output_dir=project_root / "skill-packages",
        project_root=project_root,
    )


def test_no_args_checks_all_skills_and_passes_when_archives_match(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_skill(tmp_path, "demo")

    assert _check(tmp_path, []) == 0
    assert capsys.readouterr().out == "OK: skill-packages/demo.skill matches source\n"


def test_no_args_fails_when_archive_is_stale(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    skill_dir = _make_skill(tmp_path, "demo")
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Changed.\n---\n",
        encoding="utf-8",
    )

    assert _check(tmp_path, []) == 1
    assert capsys.readouterr().out == (
        "DRIFT: skill-packages/demo.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill demo\n"
    )


def test_no_args_fails_when_archive_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_skill(tmp_path, "demo", package=False)

    assert _check(tmp_path, []) == 1
    assert capsys.readouterr().out == (
        "DRIFT: skill-packages/demo.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill demo\n"
    )


def test_skill_source_change_fails_when_archive_is_stale(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    skill_dir = _make_skill(tmp_path, "demo")
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Changed.\n---\n",
        encoding="utf-8",
    )

    assert _check(tmp_path, ["skills/demo/SKILL.md"]) == 1
    assert capsys.readouterr().out == (
        "DRIFT: skill-packages/demo.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill demo\n"
    )


def test_skill_source_change_passes_when_archive_is_synced(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_skill(tmp_path, "demo")

    assert _check(tmp_path, ["skills/demo/SKILL.md"]) == 0
    assert capsys.readouterr().out == "OK: skill-packages/demo.skill matches source\n"


def test_package_excluded_script_tests_only_change_is_ignored(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    skill_dir = _make_skill(tmp_path, "demo")
    (skill_dir / "scripts" / "run.py").write_text("print('stale')\n", encoding="utf-8")

    assert _check(tmp_path, ["skills/demo/scripts/tests/test_run.py"]) == 0
    assert capsys.readouterr().out == ""


def test_archive_change_targets_matching_skill(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    skill_dir = _make_skill(tmp_path, "demo")
    (skill_dir / "references" / "guide.md").write_text("# Changed\n", encoding="utf-8")

    assert _check(tmp_path, ["skill-packages/demo.skill"]) == 1
    assert capsys.readouterr().out == (
        "DRIFT: skill-packages/demo.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill demo\n"
    )


def test_packaged_schema_change_fails_when_archive_is_stale(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    skill_dir = _make_skill(tmp_path, "demo")
    (skill_dir / "schemas" / "input.schema.json").write_text(
        '{"changed": true}\n',
        encoding="utf-8",
    )

    assert _check(tmp_path, ["skills/demo/schemas/input.schema.json"]) == 1
    assert capsys.readouterr().out == (
        "DRIFT: skill-packages/demo.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill demo\n"
    )


def test_skill_source_change_fails_when_archive_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_skill(tmp_path, "demo", package=False)

    assert _check(tmp_path, ["skills/demo/SKILL.md"]) == 1
    assert capsys.readouterr().out == (
        "DRIFT: skill-packages/demo.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill demo\n"
    )


def test_multiple_skill_changes_check_only_changed_skills_and_missing_archives(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    changed_skill = _make_skill(tmp_path, "changed")
    unchanged_skill = _make_skill(tmp_path, "unchanged")
    _make_skill(tmp_path, "unpacked", package=False)
    (changed_skill / "SKILL.md").write_text(
        "---\nname: changed\ndescription: Changed.\n---\n",
        encoding="utf-8",
    )
    (unchanged_skill / "SKILL.md").write_text(
        "---\nname: unchanged\ndescription: Also stale, but not changed.\n---\n",
        encoding="utf-8",
    )

    assert packaged_skills_for_changed_paths(
        [
            "skills/changed/SKILL.md",
            "skills/unpacked/SKILL.md",
            "skills/changed/scripts/tests/test_run.py",
        ],
        skills_dir=tmp_path / "skills",
        output_dir=tmp_path / "skill-packages",
        project_root=tmp_path,
    ) == ["changed", "unpacked"]
    assert _check(tmp_path, ["skills/changed/SKILL.md", "skills/unpacked/SKILL.md"]) == 1
    assert capsys.readouterr().out == (
        "DRIFT: skill-packages/changed.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill changed\n"
        "DRIFT: skill-packages/unpacked.skill is stale; "
        "re-run python3 scripts/package_skills.py --skill unpacked\n"
    )


def test_main_empty_argv_invokes_no_arg_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_paths: list[str] = []

    def fake_check(changed_paths: list[str]) -> int:
        captured_paths.extend(changed_paths)
        return 7

    monkeypatch.setattr(checker, "check_changed_package_drift", fake_check)

    assert checker.main([]) == 7
    assert captured_paths == []
