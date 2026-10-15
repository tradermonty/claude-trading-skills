#!/usr/bin/env python3
"""Build a Claude CLI prompt for designing a new skill from an idea specification.

Reads the idea JSON, embeds all three reference files, lists existing skills,
and outputs a complete prompt to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"
REFERENCE_FILES = [
    "skill-structure-guide.md",
    "quality-checklist.md",
    "skill-template.md",
]
MAX_EXISTING_SKILLS = 20


def load_references(refs_dir: Path) -> dict[str, str]:
    """Load all reference files. Returns dict of filename -> content."""
    refs = {}
    for name in REFERENCE_FILES:
        path = refs_dir / name
        if path.exists():
            refs[name] = path.read_text(encoding="utf-8")
    return refs


def list_existing_skills(project_root: Path, limit: int = MAX_EXISTING_SKILLS) -> list[str]:
    """List existing skill directory names (up to limit)."""
    skills_dir = project_root / "skills"
    if not skills_dir.is_dir():
        return []
    names = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            names.append(child.name)
            if len(names) >= limit:
                break
    return names


def build_prompt(idea: dict, skill_name: str, refs: dict[str, str], existing: list[str]) -> str:
    """Build the complete design prompt."""
    title = idea.get("title", "unnamed")
    description = idea.get("description", "")
    category = idea.get("category", "general")

    existing_list = "\n".join(f"- {s}" for s in existing) if existing else "- (none)"

    ref_sections = ""
    for name, content in refs.items():
        ref_sections += f"\n\n--- BEGIN {name} ---\n{content}\n--- END {name} ---"

    prompt = f"""Design and create a complete Claude skill named '{skill_name}'.

## Idea Specification

- **Title**: {title}
- **Description**: {description}
- **Category**: {category}

## Requirements

1. Create the skill directory at `skills/{skill_name}/`
2. The YAML frontmatter `name:` field MUST be exactly `{skill_name}`
3. Follow the structure guide, quality checklist, and template below
4. Create all required files:
   - `skills/{skill_name}/SKILL.md` (with YAML frontmatter)
   - At least one file in `skills/{skill_name}/references/`
   - At least one script in `skills/{skill_name}/scripts/` (unless this is a knowledge-only skill)
   - Test directory `skills/{skill_name}/scripts/tests/` with conftest.py and at least 3 tests
5. Scripts must use `--output-dir reports/` as default output location
6. Do NOT duplicate functionality of existing skills listed below
7. Use imperative verb forms in SKILL.md workflow steps
8. All scripts must use relative paths (no hardcoded absolute paths)

## Existing Skills (do not duplicate)

{existing_list}

## Reference Documents
{ref_sections}

## Instructions

Create all the files for the skill now. Start with SKILL.md, then references, then scripts, then tests.
Ensure the skill scores well on all 5 quality categories (metadata, workflow, execution safety, artifacts, tests).
"""
    return prompt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Claude CLI prompt for skill design")
    parser.add_argument("--idea-json", required=True, help="Path to idea JSON file")
    parser.add_argument("--skill-name", required=True, help="Normalized skill directory name")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()

    # Load idea
    idea_path = Path(args.idea_json)
    if not idea_path.exists():
        print(f"Error: idea JSON not found: {idea_path}", file=sys.stderr)
        return 1

    try:
        idea = json.loads(idea_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: idea JSON is not valid JSON: {idea_path}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(idea, dict):
        print(f"Error: idea JSON must be an object: {idea_path}", file=sys.stderr)
        return 1

    # Load references — all 3 are required (no silent degrade on partial miss)
    refs = load_references(REFERENCES_DIR)
    missing = [f for f in REFERENCE_FILES if f not in refs]
    if missing:
        print(
            f"Error: reference files missing: {missing}. All 3 are required.",
            file=sys.stderr,
        )
        return 1

    # List existing skills
    existing = list_existing_skills(project_root)

    # Build and output prompt
    prompt = build_prompt(idea, args.skill_name, refs, existing)
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
