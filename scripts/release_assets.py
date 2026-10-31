#!/usr/bin/env python3
"""Prepare and verify immutable skill assets for a tag-driven GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from package_skills import check_skill, discover_skill_dirs

ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
SKILL_RE = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
HEX_RE = re.compile(r"[0-9a-f]{64}\Z")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
REQUIRED_NOTES = ("Skills", "Workflows", "Breaking metadata")


class ReleaseError(ValueError):
    """Release input is incomplete or unsafe to publish."""


def validate_tag(tag: str) -> str:
    if not TAG_RE.fullmatch(tag):
        raise ReleaseError("Release tag must be stable SemVer vMAJOR.MINOR.PATCH")
    return tag[1:]


def _version(tag: str) -> tuple[int, int, int]:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ReleaseError("Release tag must be stable SemVer vMAJOR.MINOR.PATCH")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def latest_flag(tag: str, published_tags: Iterable[str]) -> str:
    """Return the `gh release edit` flag that keeps `latest` on the highest stable SemVer."""
    candidate = _version(tag)
    published = [entry.strip() for entry in published_tags]
    if tag in published:
        raise ReleaseError(f"Release already published for {tag}")
    stable = [_version(entry) for entry in published if TAG_RE.fullmatch(entry)]
    if not stable or candidate > max(stable):
        return "--latest"
    return "--latest=false"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_metadata(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseError(f"{path.name} must be UTF-8 text") from exc


def _notes(changelog: Path, version: str) -> str:
    content = _read_metadata(changelog)
    lines = COMMENT_RE.sub("", content).splitlines()
    marker = f"## [{version}] - "
    matches = [index for index, line in enumerate(lines) if line.startswith(marker)]
    if len(matches) != 1:
        raise ReleaseError(
            f"CHANGELOG needs exactly one release heading: ## [{version}] - YYYY-MM-DD"
        )
    start = matches[0]
    # Python 3.11+ fromisoformat also accepts 20261010 and 2026-W41-1.
    heading_date = lines[start][len(marker) :]
    try:
        if not DATE_RE.fullmatch(heading_date):
            raise ValueError(heading_date)
        date.fromisoformat(heading_date)
    except ValueError as exc:
        raise ReleaseError(
            f"CHANGELOG release heading must be ## [{version}] - YYYY-MM-DD with a valid ISO date"
        ) from exc
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    section = lines[start:end]
    for heading in REQUIRED_NOTES:
        indexes = [i for i, line in enumerate(section) if line == f"### {heading}"]
        if len(indexes) != 1:
            raise ReleaseError(
                f"CHANGELOG release needs one nonempty '{heading}' section headed exactly ### {heading}"
            )
        next_heading = next(
            (i for i in range(indexes[0] + 1, len(section)) if section[i].startswith("### ")),
            len(section),
        )
        if not any(line.strip() for line in section[indexes[0] + 1 : next_heading]):
            raise ReleaseError(f"CHANGELOG '{heading}' section is empty")
    return f"# Release v{version}\n\n" + "\n".join(section).strip() + "\n"


def _check_compatibility(path: Path, tag: str) -> None:
    rows = []
    fence = None
    awaiting_separator = False
    in_table = False
    # Rows hidden in HTML comments or indented code blocks are not rendered.
    for line in COMMENT_RE.sub("", _read_metadata(path)).splitlines():
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})(.*)$", stripped)
        if fence is not None:
            if (
                fence_match
                and fence_match[1][0] == fence[0]
                and len(fence_match[1]) >= len(fence)
                and not fence_match[2].strip()
            ):
                fence = None
            continue
        if fence_match:
            fence = fence_match[1]
            awaiting_separator = in_table = False
            continue
        indented = len(line) - len(line.lstrip(" ")) >= 4 or line.startswith("\t")
        if indented or not stripped.startswith("|") or not stripped.endswith("|"):
            awaiting_separator = in_table = False
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped[1:-1])]
        if len(cells) == 4 and cells[0] == "Release":
            awaiting_separator = True
            in_table = False
            continue
        if awaiting_separator:
            in_table = len(cells) == 4 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)
            awaiting_separator = False
            continue
        if in_table:
            if len(cells) != 4:
                in_table = False
            elif cells[0] == tag:
                rows.append(cells)
    if len(rows) != 1 or rows[0][1:3] != [tag, tag]:
        raise ReleaseError(
            f"Compatibility table needs one same-tag {tag} row after a Release header and separator"
        )


def prepare(root: Path, tag: str, output_dir: Path) -> list[Path]:
    version = validate_tag(tag)
    root = root.resolve()
    output_dir = output_dir.resolve()
    notes = _notes(root / "CHANGELOG.md", version)
    _check_compatibility(root / "docs/dev/release-compatibility.md", tag)
    skills_dir = root / "skills"
    packages_dir = root / "skill-packages"
    skills = discover_skill_dirs(skills_dir)
    if not skills:
        raise ReleaseError("No source skills found")
    names = [skill.name for skill in skills]
    if any(not SKILL_RE.fullmatch(name) for name in names):
        raise ReleaseError("Unsafe skill name")
    expected = {f"{name}.skill" for name in names}
    actual = {path.name for path in packages_dir.glob("*.skill")}
    if expected != actual:
        raise ReleaseError("Committed package set does not match source skills")
    if any(path.is_symlink() or not path.is_file() for path in packages_dir.glob("*.skill")):
        raise ReleaseError("Skill assets must be regular files")
    for skill in skills:
        if not check_skill(skill, packages_dir):
            raise ReleaseError(f"Committed package differs from source: {skill.name}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ReleaseError("Release output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for name in sorted(expected):
        target = output_dir / name
        shutil.copyfile(packages_dir / name, target)
        assets.append(target)
    sums = "".join(f"{_sha256(path)}  {path.name}\n" for path in assets)
    (output_dir / "SHA256SUMS").write_text(sums, encoding="utf-8")
    (output_dir / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    return assets


def verify(local_dir: Path, downloaded_dir: Path) -> None:
    local_dir = local_dir.resolve()
    downloaded_dir = downloaded_dir.resolve()
    names = {path.name for path in local_dir.glob("*.skill")}
    if not names:
        raise ReleaseError("No local skill assets")
    expected_files = names | {"SHA256SUMS"}
    remote_files = {path.name for path in downloaded_dir.iterdir()}
    if remote_files != expected_files:
        raise ReleaseError("Downloaded Release asset set differs from staged assets")
    manifest = (local_dir / "SHA256SUMS").read_text(encoding="utf-8")
    rows = manifest.splitlines()
    if len(rows) != len(names):
        raise ReleaseError("SHA256SUMS does not cover every skill asset exactly once")
    parsed = {}
    for row in rows:
        digest, separator, name = row.partition("  ")
        if not separator or not HEX_RE.fullmatch(digest) or name not in names or name in parsed:
            raise ReleaseError("Malformed or duplicate SHA256SUMS entry")
        parsed[name] = digest
    if set(parsed) != names or [row.partition("  ")[2] for row in rows] != sorted(names):
        raise ReleaseError("SHA256SUMS must list every asset in sorted order")
    for name in sorted(expected_files):
        local = local_dir / name
        remote = downloaded_dir / name
        if local.is_symlink() or remote.is_symlink() or not remote.is_file():
            raise ReleaseError(f"Unsafe Release asset: {name}")
        if _sha256(local) != _sha256(remote):
            raise ReleaseError(f"Uploaded Release asset differs: {name}")
        if name in parsed and _sha256(local) != parsed[name]:
            raise ReleaseError(f"SHA256SUMS mismatch: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prep = subparsers.add_parser("prepare")
    prep.add_argument("--tag", required=True)
    prep.add_argument("--root", type=Path, default=ROOT)
    prep.add_argument("--output-dir", required=True, type=Path)
    check = subparsers.add_parser("verify")
    check.add_argument("--local-dir", required=True, type=Path)
    check.add_argument("--downloaded-dir", required=True, type=Path)
    flag = subparsers.add_parser("latest-flag")
    flag.add_argument("--tag", required=True)
    flag.add_argument("--published-tags-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            assets = prepare(args.root, args.tag, args.output_dir)
            print(f"Prepared {len(assets)} skill assets and SHA256SUMS")
        elif args.command == "latest-flag":
            try:
                listing = args.published_tags_file.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ReleaseError(f"Published tags file must be UTF-8: {exc}") from exc
            print(latest_flag(args.tag, listing.splitlines()))
        else:
            verify(args.local_dir, args.downloaded_dir)
            print("Uploaded Release assets match staged bytes and SHA256SUMS")
    except (OSError, ReleaseError) as exc:
        print(f"Release blocked: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
