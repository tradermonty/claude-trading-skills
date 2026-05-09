#!/usr/bin/env python3
"""Validate data/skills-index.yaml against the actual repo state.

Checks:
  1. Every skills/<name>/SKILL.md has an entry in the index.
  2. Every index entry has a matching skills/<name>/SKILL.md.
  3. Every entry's `category` is a known category id.
  4. Every entry's `use_cases` keys exist in top-level `use_cases`.
  5. SKILL.md frontmatter `name` matches the directory name.
  6. apis values are in {required, optional}.

Exit 0 = clean, exit 1 = errors.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO / "skills"
INDEX_PATH = REPO / "data" / "skills-index.yaml"

ALLOWED_API_LEVELS = {"required", "optional"}


def parse_skill_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def main() -> int:
    if not INDEX_PATH.exists():
        print(f"FATAL: {INDEX_PATH} not found", file=sys.stderr)
        return 1
    index = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))

    errors: list[str] = []
    warnings: list[str] = []

    cat_ids = {c["id"] for c in index.get("categories", [])}
    api_ids = set(index.get("apis", {}).keys())
    use_case_ids = set((index.get("use_cases") or {}).keys())

    index_names: dict[str, dict] = {}
    for s in index.get("skills") or []:
        name = s.get("name")
        if not name:
            errors.append(f"Skill entry missing `name`: {s}")
            continue
        if name in index_names:
            errors.append(f"Duplicate skill name in index: {name}")
        index_names[name] = s

        if s.get("category") not in cat_ids:
            errors.append(f"{name}: unknown category {s.get('category')!r}")
        for uc in s.get("use_cases") or []:
            if uc not in use_case_ids:
                errors.append(f"{name}: unknown use_case {uc!r}")
        for api_id, level in (s.get("apis") or {}).items():
            if api_id not in api_ids:
                errors.append(f"{name}: unknown api {api_id!r}")
            if level not in ALLOWED_API_LEVELS:
                errors.append(f"{name}: invalid api level {level!r} (use required|optional)")
        if not s.get("description"):
            warnings.append(f"{name}: empty description")

    repo_names: set[str] = set()
    for d in sorted(SKILLS_DIR.iterdir()):
        sm = d / "SKILL.md"
        if not sm.exists():
            continue
        repo_names.add(d.name)
        fm = parse_skill_frontmatter(sm)
        if fm.get("name") and fm["name"] != d.name:
            errors.append(f"{d.name}: SKILL.md frontmatter name={fm['name']!r} != dir")

    missing_in_index = sorted(repo_names - set(index_names))
    extra_in_index = sorted(set(index_names) - repo_names)
    for name in missing_in_index:
        errors.append(f"Skill in repo but not in index: {name}")
    for name in extra_in_index:
        errors.append(f"Skill in index but not in repo: {name}")

    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  WARN: {w}")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  FAIL: {e}")
        return 1
    print(f"OK: {len(repo_names)} skills in repo, {len(index_names)} in index, no errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
