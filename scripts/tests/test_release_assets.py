"""Release assets must be complete, byte-verified, and fail closed."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from package_skills import package_skill  # noqa: E402
from release_assets import ReleaseError, prepare, verify  # noqa: E402


@pytest.fixture
def source(tmp_path: Path) -> Path:
    for name in ("alpha", "bravo"):
        skill = tmp_path / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        package_skill(skill, tmp_path / "skill-packages")
    (tmp_path / "docs/dev").mkdir(parents=True)
    (tmp_path / "docs/dev/release-compatibility.md").write_text(
        "| Release | Assets | Workflows | Rule |\n"
        "| --- | --- | --- | --- |\n"
        "| v1.2.3 | v1.2.3 | v1.2.3 | Same tag |\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [1.2.3] - 2026-10-10\n\n"
        "### Skills\n- Added alpha.\n\n"
        "### Workflows\n- None.\n\n"
        "### Breaking metadata\n- None.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_prepare_and_verify_complete_assets(source: Path) -> None:
    staged = source / "dist"
    assets = prepare(source, "v1.2.3", staged)
    assert [path.name for path in assets] == ["alpha.skill", "bravo.skill"]
    assert (staged / "SHA256SUMS").read_text().count(".skill\n") == 2
    assert "Added alpha" in (staged / "RELEASE_NOTES.md").read_text()
    downloaded = source / "downloaded"
    downloaded.mkdir()
    for name in ("alpha.skill", "bravo.skill", "SHA256SUMS"):
        shutil.copyfile(staged / name, downloaded / name)
    verify(staged, downloaded)
    (downloaded / "alpha.skill").write_bytes(b"modified but could have same name and size")
    with pytest.raises(ReleaseError, match="differs"):
        verify(staged, downloaded)


@pytest.mark.parametrize("tag", ["v1.2.3-rc1", "v01.2.3", "v1.2", "1.2.3", "v1.2.3/path"])
def test_prepare_rejects_nonstable_or_unsafe_tag(source: Path, tag: str) -> None:
    with pytest.raises(ReleaseError, match="stable SemVer"):
        prepare(source, tag, source / "dist")


def test_prepare_requires_matching_release_metadata(source: Path) -> None:
    compat = source / "docs/dev/release-compatibility.md"
    compat.write_text("| v1.2.3 | v1.2.3 | v1.2.2 | Cross-version |\n")
    with pytest.raises(ReleaseError, match="same-tag"):
        prepare(source, "v1.2.3", source / "dist")
    compat.write_text("| v1.2.3 | v1.2.3 | v1.2.3 | Same tag |\n")
    changelog = source / "CHANGELOG.md"
    changelog.write_text(
        changelog.read_text().replace("### Breaking metadata\n- None.", "### Breaking metadata\n")
    )
    with pytest.raises(ReleaseError, match="Breaking metadata"):
        prepare(source, "v1.2.3", source / "dist")


def test_prepare_rejects_commented_release_template(source: Path) -> None:
    changelog = source / "CHANGELOG.md"
    changelog.write_text("<!--\n" + changelog.read_text() + "\n-->\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="exactly one"):
        prepare(source, "v1.2.3", source / "dist")


def test_prepare_rejects_missing_or_stale_archive(source: Path) -> None:
    (source / "skill-packages/bravo.skill").unlink()
    with pytest.raises(ReleaseError, match="package set"):
        prepare(source, "v1.2.3", source / "dist")
    package_skill(source / "skills/bravo", source / "skill-packages")
    (source / "skills/bravo/SKILL.md").write_text("changed\n")
    with pytest.raises(ReleaseError, match="differs from source"):
        prepare(source, "v1.2.3", source / "dist")


def test_verify_rejects_missing_asset_and_bad_manifest(source: Path) -> None:
    staged = source / "dist"
    prepare(source, "v1.2.3", staged)
    downloaded = source / "downloaded"
    downloaded.mkdir()
    shutil.copyfile(staged / "alpha.skill", downloaded / "alpha.skill")
    shutil.copyfile(staged / "SHA256SUMS", downloaded / "SHA256SUMS")
    with pytest.raises(ReleaseError, match="asset set"):
        verify(staged, downloaded)
    shutil.copyfile(staged / "bravo.skill", downloaded / "bravo.skill")
    (staged / "SHA256SUMS").write_text("0" * 64 + "  alpha.skill\n")
    with pytest.raises(ReleaseError, match="exactly once"):
        verify(staged, downloaded)
