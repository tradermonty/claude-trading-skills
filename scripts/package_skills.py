#!/usr/bin/env python3
"""Build distributable .skill archives from source skill directories.

Distribution packages intentionally exclude tests and local build artifacts.
Those files are useful in the repository, but they add weight and trigger
security-scanner noise when users install .skill archives in Claude Web App.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS_DIR = PROJECT_ROOT / "skills"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "skill-packages"
FIXED_ZIP_DATE = (2026, 1, 1, 0, 0, 0)

EXCLUDED_DIR_NAMES = {"tests", "__pycache__"}
EXCLUDED_FILE_NAMES = {".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def should_include(relative_path: Path) -> bool:
    """Return True when a source path should be included in a .skill archive."""
    if any(part in EXCLUDED_DIR_NAMES for part in relative_path.parts):
        return False
    if relative_path.name in EXCLUDED_FILE_NAMES:
        return False
    if relative_path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def iter_package_files(skill_dir: Path) -> list[Path]:
    """List packageable files for a skill in deterministic archive order."""
    return sorted(
        (
            path
            for path in skill_dir.rglob("*")
            if path.is_file() and should_include(path.relative_to(skill_dir))
        ),
        key=lambda path: path.relative_to(skill_dir).as_posix(),
    )


def _zip_info(archive_name: str, source_path: Path) -> ZipInfo:
    info = ZipInfo(archive_name, FIXED_ZIP_DATE)
    info.compress_type = ZIP_DEFLATED
    mode = source_path.stat().st_mode
    info.external_attr = (mode & 0o777) << 16
    return info


def package_skill(skill_dir: Path, output_dir: Path, *, dry_run: bool = False) -> Path:
    """Create one .skill archive and return its path."""
    skill_dir = skill_dir.resolve()
    output_dir = output_dir.resolve()

    if not skill_dir.is_dir():
        raise FileNotFoundError(f"Skill directory not found: {skill_dir}")
    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(f"Missing SKILL.md in {skill_dir}")

    files = iter_package_files(skill_dir)
    if not files:
        raise ValueError(f"No packageable files found in {skill_dir}")

    output_path = output_dir / f"{skill_dir.name}.skill"
    if dry_run:
        return output_path

    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with ZipFile(tmp_path, "w") as archive:
            for source_path in files:
                rel = source_path.relative_to(skill_dir)
                archive_name = f"{skill_dir.name}/{rel.as_posix()}"
                archive.writestr(_zip_info(archive_name, source_path), source_path.read_bytes())
        os.replace(tmp_path, output_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return output_path


def _source_logical_contents(skill_dir: Path) -> dict[str, tuple[bytes, bool]]:
    """Logical archive contents from source: name -> (uncompressed bytes, exec bit)."""
    skill_dir = skill_dir.resolve()
    contents: dict[str, tuple[bytes, bool]] = {}
    for source_path in iter_package_files(skill_dir):
        rel = source_path.relative_to(skill_dir)
        name = f"{skill_dir.name}/{rel.as_posix()}"
        contents[name] = (source_path.read_bytes(), bool(source_path.stat().st_mode & 0o111))
    return contents


def _archive_logical_contents(archive_path: Path) -> dict[str, tuple[bytes, bool]]:
    """Logical contents of a committed .skill: name -> (uncompressed bytes, exec bit).

    Compares logical content (not raw ZIP_DEFLATED bytes) so the gate does not
    flap when the local and CI zlib versions compress the same input differently.
    """
    contents: dict[str, tuple[bytes, bool]] = {}
    with ZipFile(archive_path) as archive:
        for info in archive.infolist():
            exec_bit = bool((info.external_attr >> 16) & 0o111)
            contents[info.filename] = (archive.read(info.filename), exec_bit)
    return contents


def check_skill(skill_dir: Path, output_dir: Path) -> bool:
    """Return True when the committed .skill matches what packaging would produce."""
    archive_path = output_dir.resolve() / f"{skill_dir.resolve().name}.skill"
    if not archive_path.is_file():
        return False
    return _source_logical_contents(skill_dir) == _archive_logical_contents(archive_path)


def discover_skill_dirs(skills_dir: Path) -> list[Path]:
    """Return source skill directories that contain SKILL.md."""
    return sorted(
        (path.parent for path in skills_dir.glob("*/SKILL.md")),
        key=lambda path: path.name,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build .skill archives while excluding tests and local build artifacts."
    )
    parser.add_argument(
        "--skill",
        action="append",
        help="Skill name to package. May be repeated. Defaults to all skills.",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=DEFAULT_SKILLS_DIR,
        help="Source skills directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated .skill archives.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print archives that would be generated without writing files.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify committed .skill archives match source (logical content); exit 1 on drift.",
    )
    return parser.parse_args()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    skills_dir = args.skills_dir.resolve()
    output_dir = args.output_dir.resolve()

    if args.skill:
        skill_dirs = [skills_dir / skill for skill in args.skill]
    else:
        skill_dirs = discover_skill_dirs(skills_dir)

    if not skill_dirs:
        raise SystemExit(f"No skills found in {skills_dir}")

    if args.check:
        drift = False
        for skill_dir in skill_dirs:
            archive_path = output_dir / f"{skill_dir.name}.skill"
            if check_skill(skill_dir, output_dir):
                print(f"OK: {_display_path(archive_path)} matches source")
            else:
                print(f"DRIFT: {_display_path(archive_path)} is stale; re-run package_skills.py")
                drift = True
        return 1 if drift else 0

    for skill_dir in skill_dirs:
        output_path = package_skill(skill_dir, output_dir, dry_run=args.dry_run)
        verb = "would write" if args.dry_run else "wrote"
        print(f"{verb}: {_display_path(output_path)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
