#!/usr/bin/env python3
"""Bootstrap data/skills-index.yaml from existing repo state.

Sources of truth (in priority order):
  1. skills/<name>/SKILL.md frontmatter -> name, description (full)
  2. docs/en/skill-catalog.md tables    -> category, short description, badges
  3. docs/en/skills/<name>.md           -> has_doc_page=True if file is non-stub
  4. CLAUDE.md API matrix               -> required/optional/none per API

Run from repo root:
  python3 scripts/bootstrap_skills_index.py [--write]

Default is dry-run: prints YAML to stdout. Use --write to overwrite the
`skills:` block in data/skills-index.yaml while preserving the header.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO / "skills"
INDEX_PATH = REPO / "data" / "skills-index.yaml"
EN_CATALOG = REPO / "docs" / "en" / "skill-catalog.md"
EN_SKILLS_DIR = REPO / "docs" / "en" / "skills"

CATEGORY_TITLE_TO_ID = {
    "stock screening": "stock-screening",
    "market analysis": "market-analysis",
    "theme & strategy": "theme-strategy",
    "portfolio & execution": "portfolio-execution",
    "dividend investing": "dividend-investing",
    "edge research pipeline": "edge-research",
    "quality & workflow": "quality-workflow",
}

BADGE_TO_API = {
    "FMP Required": ("fmp", "required"),
    "FMP Optional": ("fmp", "optional"),
    "FINVIZ Elite Required": ("finviz", "required"),
    "FINVIZ Optional": ("finviz", "optional"),
    "FINVIZ Elite Optional": ("finviz", "optional"),
    "Alpaca Required": ("alpaca", "required"),
    "Alpaca Optional": ("alpaca", "optional"),
}


def parse_skill_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def parse_catalog_tables(catalog: Path) -> dict[str, dict]:
    """Extract per-skill metadata from the EN catalog: category + description + badges."""
    out: dict[str, dict] = {}
    text = catalog.read_text(encoding="utf-8")
    current_category: str | None = None

    section_re = re.compile(r"^##\s+\d+\.\s+(.+?)\s*$")
    row_re = re.compile(
        r"^\|\s*\*\*\[?([^\]\*\|]+?)\]?"  # title text inside ** ** with optional [ ]
        r"(?:\([^)]*\))?"  # optional Jekyll/markdown link target
        r"\*\*\s*"  # closing **
        r"\|\s*(.*?)\s*"  # description
        r"\|\s*(.*?)\s*\|\s*$"  # badges html
    )

    for line in text.splitlines():
        sec = section_re.match(line)
        if sec:
            cat_title = sec.group(1).lower().strip()
            current_category = CATEGORY_TITLE_TO_ID.get(cat_title)
            continue
        if not current_category:
            continue
        m = row_re.match(line)
        if not m:
            continue
        title, desc, badges_html = m.groups()
        title = title.strip()
        # Title -> name slug (best-effort; bootstrap will reconcile against directory list)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        apis: dict[str, str] = {}
        for badge_text, (api_id, level) in BADGE_TO_API.items():
            if badge_text in badges_html:
                apis[api_id] = level
        out[slug] = {
            "title": title,
            "category": current_category,
            "description": desc.replace("|", "/").strip(),
            "apis": apis,
        }
    return out


def is_full_doc_page(path: Path) -> bool:
    """A doc page is "full" if it has more than ~30 lines of content (not a stub)."""
    if not path.exists():
        return False
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return len(lines) > 30


def first_sentence(s: str, max_chars: int = 220) -> str:
    s = s.strip()
    # Trim at the first sentence boundary or max_chars
    m = re.search(r"\.\s+|$", s)
    candidate = s[: m.end()].rstrip()
    if len(candidate) > max_chars:
        candidate = candidate[:max_chars].rsplit(" ", 1)[0] + "..."
    return candidate.rstrip(".") or s[:max_chars]


def reconcile(name: str, fm: dict, catalog_meta: dict[str, dict]) -> dict:
    """Combine SKILL.md frontmatter + catalog metadata into one entry."""
    title = name.replace("-", " ").title()
    description = ""
    category: str | None = None
    apis: dict[str, str] = {}

    # Try matching the catalog by slug or normalized title
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    match = None
    for slug, meta in catalog_meta.items():
        if norm(meta["title"]) == norm(name) or slug == name:
            match = meta
            break
    if match:
        title = match["title"]
        category = match["category"]
        description = match["description"]
        apis = dict(match["apis"])

    # Fall back to SKILL.md description if catalog didn't have one
    if not description and fm.get("description"):
        description = first_sentence(fm["description"])

    entry: dict = {
        "name": name,
        "title": title,
        "category": category or "quality-workflow",  # safe default; user fixes
        "description": description or f"(no description; please fill in from {name}/SKILL.md)",
    }
    if apis:
        entry["apis"] = apis
    if is_full_doc_page(EN_SKILLS_DIR / f"{name}.md"):
        entry["has_doc_page"] = True
    return entry


def collect_skills() -> list[dict]:
    catalog_meta = parse_catalog_tables(EN_CATALOG) if EN_CATALOG.exists() else {}
    skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())
    entries = []
    for d in skill_dirs:
        fm = parse_skill_frontmatter(d / "SKILL.md")
        name = fm.get("name", d.name)
        if name != d.name:
            print(
                f"WARNING: SKILL.md name '{name}' != dir '{d.name}' for {d}",
                file=sys.stderr,
            )
            name = d.name
        entries.append(reconcile(name, fm, catalog_meta))
    return entries


def write_index(entries: list[dict]) -> str:
    """Render entries to YAML, preserving the header of the existing index file."""
    if not INDEX_PATH.exists():
        raise SystemExit(f"Index file missing: {INDEX_PATH}")
    src = INDEX_PATH.read_text(encoding="utf-8")
    # Replace the trailing `skills: []` (or any existing `skills:` block) with new content.
    skills_yaml = yaml.safe_dump(
        {"skills": entries}, sort_keys=False, allow_unicode=True, width=100
    )
    # Strip the leading 'skills:' line so we can splice inline
    new_block = skills_yaml
    pattern = re.compile(r"\nskills:[ \t]*(?:\[\][^\n]*|[^\n]*\n(?:[ \t-].*\n?)*).*\Z", re.DOTALL)
    if not pattern.search(src):
        raise SystemExit("Could not find `skills:` block in index file")
    return pattern.sub("\n" + new_block.rstrip() + "\n", src)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true", help="Overwrite data/skills-index.yaml")
    args = p.parse_args()

    entries = collect_skills()
    rendered = write_index(entries)
    if args.write:
        INDEX_PATH.write_text(rendered, encoding="utf-8")
        print(f"Wrote {len(entries)} skills -> {INDEX_PATH}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
        print(
            f"\n# (dry-run, {len(entries)} skills) — use --write to persist",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
