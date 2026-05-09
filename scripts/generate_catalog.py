#!/usr/bin/env python3
"""Generate the catalog markdown sections from data/skills-index.yaml.

Replaces content between marker comments in docs/{en,ja}/skill-catalog.md:

    <!-- BEGIN AUTO: catalog-categories -->
    ... rendered category tables ...
    <!-- END AUTO: catalog-categories -->

    <!-- BEGIN AUTO: api-matrix -->
    ... rendered API requirements matrix ...
    <!-- END AUTO: api-matrix -->

If the markers are missing, --check fails with a non-zero exit; --write
emits a sibling `*.generated.md` file for manual diffing.

Modes:
  --check   exit 1 if any catalog file would change (CI guard)
  --write   write changes (or .generated.md when no markers exist)
  default   print rendered markdown to stdout (preview)

Usage:
  python3 scripts/generate_catalog.py                # preview EN
  python3 scripts/generate_catalog.py --lang ja      # preview JA
  python3 scripts/generate_catalog.py --check
  python3 scripts/generate_catalog.py --write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO / "data" / "skills-index.yaml"
CATALOG_PATHS = {
    "en": REPO / "docs" / "en" / "skill-catalog.md",
    "ja": REPO / "docs" / "ja" / "skill-catalog.md",
}

CATEGORIES_BEGIN = "<!-- BEGIN AUTO: catalog-categories -->"
CATEGORIES_END = "<!-- END AUTO: catalog-categories -->"
API_MATRIX_BEGIN = "<!-- BEGIN AUTO: api-matrix -->"
API_MATRIX_END = "<!-- END AUTO: api-matrix -->"


def load_index() -> dict:
    with INDEX_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def badge(api_id: str, level: str, apis_meta: dict) -> str:
    meta = apis_meta[api_id]
    if level == "required":
        return f'<span class="badge badge-api">{meta["badge_required"]}</span>'
    if level == "optional":
        return f'<span class="badge badge-optional">{meta["badge_optional"]}</span>'
    return ""


def render_skill_badges(skill: dict, apis_meta: dict) -> str:
    apis = skill.get("apis") or {}
    if skill.get("workflow"):
        return '<span class="badge badge-workflow">Workflow</span>'
    badges: list[str] = []
    has_required = any(level == "required" for level in apis.values())
    if not has_required:
        badges.append('<span class="badge badge-free">No API</span>')
    for api_id in ("fmp", "finviz", "alpaca"):
        if api_id in apis:
            badges.append(badge(api_id, apis[api_id], apis_meta))
    return " ".join(badges)


def render_skill_link(skill: dict, lang: str) -> str:
    title = skill["title"]
    if skill.get("has_doc_page"):
        return f"**[{title}]({{{{ '/{lang}/skills/{skill['name']}/' | relative_url }}}})**"
    return f"**{title}**"


def render_categories(index: dict, lang: str) -> str:
    apis_meta = index["apis"]
    categories = sorted(index["categories"], key=lambda c: c["order"])
    skills_by_cat: dict[str, list[dict]] = {c["id"]: [] for c in categories}
    for s in index["skills"]:
        if s["category"] not in skills_by_cat:
            raise SystemExit(f"Skill {s['name']} has unknown category {s['category']!r}")
        skills_by_cat[s["category"]].append(s)

    parts: list[str] = []
    for idx, cat in enumerate(categories, 1):
        parts.append(f"## {idx}. {cat['title']}\n")
        parts.append("| Skill | Description | API Requirements |")
        parts.append("|-------|-------------|-----------------|")
        for s in sorted(skills_by_cat[cat["id"]], key=lambda x: x["title"]):
            link = render_skill_link(s, lang)
            desc = s["description"].replace("|", "/").replace("\n", " ").strip()
            badges = render_skill_badges(s, apis_meta)
            parts.append(f"| {link} | {desc} | {badges} |")
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_api_matrix(index: dict) -> str:
    apis_meta = index["apis"]
    api_ids = list(apis_meta.keys())
    headers = ["Skill"] + [apis_meta[a]["title"] for a in api_ids]
    parts = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for s in sorted(index["skills"], key=lambda x: x["title"]):
        row = [s["title"]]
        apis = s.get("apis") or {}
        for a in api_ids:
            level = apis.get(a)
            if level == "required":
                row.append("Required")
            elif level == "optional":
                row.append("Optional")
            else:
                row.append("--")
        parts.append("| " + " | ".join(row) + " |")
    parts.append("")
    parts.append(
        '"--" means not required. "Optional" means functionality is enhanced but the skill works without it.'
    )
    return "\n".join(parts) + "\n"


def splice(src: str, begin: str, end: str, payload: str) -> tuple[str, bool]:
    """Replace content between marker comments. Returns (new_src, did_splice)."""
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(src):
        return src, False
    replacement = f"{begin}\n\n{payload.strip()}\n\n{end}"
    return pattern.sub(replacement, src), True


def update_catalog(lang: str, index: dict) -> tuple[str, str, bool, bool]:
    path = CATALOG_PATHS[lang]
    src = path.read_text(encoding="utf-8") if path.exists() else ""
    cats_payload = render_categories(index, lang)
    api_payload = render_api_matrix(index)
    new, ok1 = splice(src, CATEGORIES_BEGIN, CATEGORIES_END, cats_payload)
    new, ok2 = splice(new, API_MATRIX_BEGIN, API_MATRIX_END, api_payload)
    return src, new, ok1, ok2


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lang", choices=["en", "ja"], default="en")
    p.add_argument("--check", action="store_true", help="Exit 1 if catalog would change")
    p.add_argument("--write", action="store_true", help="Write updates back to catalog files")
    p.add_argument("--all-langs", action="store_true", help="Process all languages")
    args = p.parse_args()

    index = load_index()
    langs = ["en", "ja"] if args.all_langs else [args.lang]

    any_diff = False
    for lang in langs:
        path = CATALOG_PATHS[lang]
        src, new, ok_cats, ok_api = update_catalog(lang, index)
        if not (ok_cats and ok_api):
            generated = path.with_suffix(".generated.md")
            payload = (
                f"# Generated catalog ({lang})\n\n"
                f"Markers missing in {path.name}. "
                f"Insert these markers at the appropriate spots:\n\n"
                f"  {CATEGORIES_BEGIN} ... {CATEGORIES_END}\n"
                f"  {API_MATRIX_BEGIN} ... {API_MATRIX_END}\n\n"
                f"## Categories block\n\n{render_categories(index, lang)}\n\n"
                f"## API matrix block\n\n{render_api_matrix(index)}\n"
            )
            if args.write:
                generated.write_text(payload, encoding="utf-8")
                print(f"[{lang}] markers missing -> wrote preview to {generated}", file=sys.stderr)
            else:
                if args.check:
                    print(f"[{lang}] markers missing in {path}", file=sys.stderr)
                    any_diff = True
                else:
                    sys.stdout.write(payload)
            continue

        if new != src:
            any_diff = True
            if args.write:
                path.write_text(new, encoding="utf-8")
                print(f"[{lang}] updated {path}", file=sys.stderr)
            elif args.check:
                print(f"[{lang}] catalog drift detected in {path}", file=sys.stderr)
            else:
                sys.stdout.write(new)
        else:
            print(f"[{lang}] no changes", file=sys.stderr)

    if args.check and any_diff:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
