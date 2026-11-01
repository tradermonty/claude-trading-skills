"""Release assets must be complete, byte-verified, and fail closed."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from package_skills import package_skill  # noqa: E402
from release_assets import ReleaseError, latest_flag, main, prepare, verify  # noqa: E402


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
    compat.write_text(
        "| Release | Assets | Workflows | Rule |\n| --- | --- | --- | --- |\n| v1.2.3 | v1.2.3 | v1.2.3 | Same tag |\n"
    )
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


HEADER = "| Release | Assets | Workflows | Rule |\n| --- | --- | --- | --- |\n"
ROW = "| v1.2.3 | v1.2.3 | v1.2.3 | Same tag |\n"


@pytest.mark.parametrize(
    "content",
    [
        ROW,
        "```\n" + HEADER + ROW + "```\n",
        "~~~markdown\n" + HEADER + ROW + "~~~\n",
        "```\n" + HEADER + ROW,
        HEADER + "\n" + ROW,
        HEADER + ROW + ROW,
        HEADER.replace("---", "--") + ROW,
        HEADER + ROW.replace("v1.2.3 | Same", "v1.2.2 | Same"),
        "<!--\n" + HEADER + ROW + "-->\n",
        HEADER + "<!-- " + ROW.strip() + " -->\n",
        "".join("    " + line + "\n" for line in (HEADER + ROW).splitlines()),
    ],
)
def test_compatibility_rejects_fake_or_invalid_table(source: Path, content: str) -> None:
    (source / "docs/dev/release-compatibility.md").write_text(content)
    with pytest.raises(ReleaseError, match="same-tag"):
        prepare(source, "v1.2.3", source / "dist")


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_compatibility_ignores_fenced_fake_rows(source: Path, fence: str) -> None:
    (source / "docs/dev/release-compatibility.md").write_text(
        fence + "\n" + HEADER + ROW + fence + "\n" + HEADER + ROW
    )
    prepare(source, "v1.2.3", source / "dist")


def test_compatibility_allows_escaped_pipe_in_earlier_row(source: Path) -> None:
    (source / "docs/dev/release-compatibility.md").write_text(
        HEADER + "| v1.2.2 | v1.2.2 | v1.2.2 | a \\| b |\n" + ROW
    )
    prepare(source, "v1.2.3", source / "dist")


@pytest.mark.parametrize("bad_date", ["20261010", "2026-W41-1", "2026-10-10T00:00"])
def test_changelog_date_must_be_yyyy_mm_dd(source: Path, bad_date: str) -> None:
    changelog = source / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().replace("2026-10-10", bad_date))
    with pytest.raises(ReleaseError, match="YYYY-MM-DD"):
        prepare(source, "v1.2.3", source / "dist")


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("## [1.2.3] -", "## [v1.2.3] -", "## [1.2.3] - YYYY-MM-DD"),
        ("## [1.2.3] -", "## [1.2.3]", "## [1.2.3] - YYYY-MM-DD"),
        ("### Skills", "#### Skills", "### Skills"),
    ],
)
def test_changelog_near_miss_explains_format(
    source: Path, old: str, new: str, expected: str
) -> None:
    changelog = source / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().replace(old, new))
    with pytest.raises(ReleaseError) as error:
        prepare(source, "v1.2.3", source / "dist")
    assert expected in str(error.value)


def test_non_utf8_changelog_blocks_cli_without_traceback(source: Path, capsys) -> None:
    (source / "CHANGELOG.md").write_bytes(b"\xff")
    assert (
        main(
            [
                "prepare",
                "--root",
                str(source),
                "--tag",
                "v1.2.3",
                "--output-dir",
                str(source / "dist"),
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert "CHANGELOG.md must be UTF-8" in output.err
    assert "Traceback" not in output.err
    assert not (source / "dist").exists()


@pytest.mark.parametrize(
    ("tag", "published", "expected"),
    [
        ("v1.0.0", [], "--latest"),
        ("v1.0.1", ["v1.1.0"], "--latest=false"),
        ("v1.1.0", ["v1.0.0"], "--latest"),
        ("v1.10.0", ["v1.9.0"], "--latest"),
        ("v1.9.1", ["v1.10.0"], "--latest=false"),
        ("v10.0.0", ["v9.9.9"], "--latest"),
        ("v9.9.9", ["v10.0.0"], "--latest=false"),
        ("v1.2.0", ["v1.2.0-rc1", "latest", "", "  v1.0.0  ", "v1.1.0"], "--latest"),
        ("v1.0.5", ["v1.2.0-rc1", "  v1.0.0  "], "--latest"),
        ("v1.0.5", ["  v1.1.0\n"], "--latest=false"),
    ],
)
def test_latest_flag_uses_numeric_semver_order(
    tag: str, published: list[str], expected: str
) -> None:
    assert latest_flag(tag, published) == expected


def test_latest_flag_rejects_already_published_and_invalid_tag() -> None:
    with pytest.raises(ReleaseError, match="already"):
        latest_flag("v1.0.0", ["v1.0.0"])
    with pytest.raises(ReleaseError, match="stable SemVer"):
        latest_flag("v1.0.0-rc1", [])


def test_latest_flag_cli_prints_only_token(tmp_path: Path, capsys) -> None:
    listing = tmp_path / "published.txt"
    listing.write_text("v1.1.0\nv1.0.0\n", encoding="utf-8")
    args = ["latest-flag", "--published-tags-file", str(listing), "--tag"]
    assert main([*args, "v1.0.1"]) == 0
    assert capsys.readouterr().out == "--latest=false\n"
    assert main([*args, "v1.2.0"]) == 0
    assert capsys.readouterr().out == "--latest\n"


def test_latest_flag_cli_errors_without_traceback(tmp_path: Path, capsys) -> None:
    listing = tmp_path / "published.txt"
    listing.write_text("", encoding="utf-8")
    assert main(["latest-flag", "--tag", "v1.0", "--published-tags-file", str(listing)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Release blocked:" in captured.err
    assert "Traceback" not in captured.err
    missing = tmp_path / "missing.txt"
    assert main(["latest-flag", "--tag", "v1.0.0", "--published-tags-file", str(missing)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Release blocked:" in captured.err
    assert "Traceback" not in captured.err
    non_utf8 = tmp_path / "non_utf8.txt"
    non_utf8.write_bytes(b"v1.0.0\n\xff\xfe\n")
    assert main(["latest-flag", "--tag", "v1.1.0", "--published-tags-file", str(non_utf8)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Release blocked:" in captured.err
    assert "Traceback" not in captured.err
