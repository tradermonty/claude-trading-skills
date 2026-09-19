#!/usr/bin/env python3
"""Pre-commit hook: verify every skill has documentation pages.

Scans skills/*/SKILL.md and checks that corresponding pages exist in
docs/en/skills/ and docs/ja/skills/. Also flags orphan skill directories
(a skills/*/ dir without SKILL.md, e.g. issue #432 residue) so they fail
CI instead of hiding from SKILL.md-based discovery. Runs on all files
(pass_filenames: false) since it checks overall repository consistency.
"""

from pathlib import Path

# Directories that contain SKILL.md but are intentional stubs (no docs needed)
SKIP_DIRS: set[str] = set()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def find_skills_without_docs(
    root: Path | None = None,
) -> list[str]:
    """Return list of error messages for skills missing documentation."""
    project_root = root or PROJECT_ROOT
    skills_dir = project_root / "skills"
    docs_en_dir = project_root / "docs" / "en" / "skills"
    docs_ja_dir = project_root / "docs" / "ja" / "skills"

    errors = []

    if not skills_dir.is_dir():
        return []

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name

        if skill_name in SKIP_DIRS:
            continue

        en_doc = docs_en_dir / f"{skill_name}.md"
        ja_doc = docs_ja_dir / f"{skill_name}.md"

        missing = []
        if not en_doc.exists():
            missing.append(f"docs/en/skills/{skill_name}.md")
        if not ja_doc.exists():
            missing.append(f"docs/ja/skills/{skill_name}.md")

        if missing:
            errors.append(
                f"  skills/{skill_name}/SKILL.md exists but missing: " + ", ".join(missing)
            )

    return errors


def find_orphan_skill_dirs(root: Path | None = None) -> list[str]:
    """Return error messages for skills/*/ dirs without SKILL.md (issue #432).

    SKILL.md-based discovery (packaging, dep checks, this hook's doc scan)
    silently ignores such dirs, so flag them explicitly.
    """
    skills_dir = (root or PROJECT_ROOT) / "skills"
    errors = []

    if not skills_dir.is_dir():
        return []

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in SKIP_DIRS:
            continue
        if not (entry / "SKILL.md").is_file():
            errors.append(
                f"  skills/{entry.name}/ has no SKILL.md "
                "(orphan dir: complete it as a skill or delete it)"
            )

    return errors


def main() -> int:
    errors = find_skills_without_docs() + find_orphan_skill_dirs()

    if errors:
        print("ERROR: Skills with missing documentation pages:")
        print("\n".join(errors))
        print(
            "\nRun: python3 scripts/generate_skill_docs.py --skill <name>"
            " to generate missing pages."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
