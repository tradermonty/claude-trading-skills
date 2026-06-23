#!/usr/bin/env python3
"""Pre-commit hook: verify every skill has documentation pages.

Scans skills/*/SKILL.md and checks that corresponding pages exist in
docs/en/skills/, docs/ja/skills/, and docs/zh/skills/. Runs on all files
(pass_filenames: false) since it checks overall repository consistency.
"""

from pathlib import Path

# Directories that contain SKILL.md but are intentional stubs (no docs needed)
SKIP_DIRS: set[str] = set()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def find_skills_without_docs() -> list[str]:
    """Return list of error messages for skills missing documentation."""
    skills_dir = PROJECT_ROOT / "skills"
    docs_en_dir = PROJECT_ROOT / "docs" / "en" / "skills"
    docs_ja_dir = PROJECT_ROOT / "docs" / "ja" / "skills"
    docs_zh_dir = PROJECT_ROOT / "docs" / "zh" / "skills"
    errors = []

    if not skills_dir.is_dir():
        return []

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name

        if skill_name in SKIP_DIRS:
            continue

        en_doc = docs_en_dir / f"{skill_name}.md"
        ja_doc = docs_ja_dir / f"{skill_name}.md"
        zh_doc = docs_zh_dir / f"{skill_name}.md"

        missing = []
        if not en_doc.exists():
            missing.append(f"docs/en/skills/{skill_name}.md")
        if not ja_doc.exists():
            missing.append(f"docs/ja/skills/{skill_name}.md")
        if not zh_doc.exists():
            missing.append(f"docs/zh/skills/{skill_name}.md")

        if missing:
            errors.append(
                f"  skills/{skill_name}/SKILL.md exists but missing: " + ", ".join(missing)
            )

    return errors


def main() -> int:
    errors = find_skills_without_docs()

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
