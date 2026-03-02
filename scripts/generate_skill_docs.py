#!/usr/bin/env python3
"""Generate Jekyll documentation pages from SKILL.md files.

Reads each skill's SKILL.md (YAML frontmatter + body) and CLAUDE.md
(API requirements table) to produce EN and JA pages under docs/.

Usage:
    python3 scripts/generate_skill_docs.py                  # all missing skills
    python3 scripts/generate_skill_docs.py --skill pead-screener
    python3 scripts/generate_skill_docs.py --overwrite       # regenerate all
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS_DIR = PROJECT_ROOT / "skills"
DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
DEFAULT_CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"

# Existing hand-written guides; skip by default (--overwrite to regenerate).
HAND_WRITTEN = frozenset(
    {
        "backtest-expert",
        "canslim-screener",
        "finviz-screener",
        "market-breadth-analyzer",
        "market-news-analyst",
        "position-sizer",
        "theme-detector",
        "us-market-bubble-detector",
        "us-stock-analysis",
        "vcp-screener",
    }
)

# Starting nav_order for auto-generated pages (existing use 1-10).
NAV_ORDER_START = 11

# ---------------------------------------------------------------------------
# SKILL.md parser
# ---------------------------------------------------------------------------


def parse_skill_md(path: Path) -> dict:
    """Parse SKILL.md into {frontmatter: dict, body: str, sections: dict}."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"frontmatter": {}, "body": text, "sections": {}}

    import yaml

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        # Fallback: extract name and description manually when YAML
        # has unquoted colons in values.
        fm = {}
        for line in parts[1].strip().splitlines():
            if line.startswith("name:"):
                fm["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                fm["description"] = line.split(":", 1)[1].strip()
    body = parts[2].strip()
    sections = _split_sections(body)
    return {"frontmatter": fm, "body": body, "sections": sections}


def _split_sections(body: str) -> dict[str, str]:
    """Split markdown body into {heading_lower: content} by ## headings."""
    sections: dict[str, str] = {}
    current_key = ""
    lines: list[str] = []

    for line in body.splitlines():
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(lines).strip()
            current_key = line.lstrip("# ").strip().lower()
            lines = []
        else:
            lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(lines).strip()

    return sections


# ---------------------------------------------------------------------------
# CLAUDE.md API requirements parser
# ---------------------------------------------------------------------------


def parse_api_requirements(claude_md: Path) -> dict[str, dict]:
    """Return {skill_name: {fmp: str, finviz: str, alpaca: str, notes: str}}.

    Parses the markdown table under '#### API Requirements by Skill'.
    """
    text = claude_md.read_text(encoding="utf-8")
    table_match = re.search(
        r"####\s+API Requirements by Skill.*?\n((?:\|.*\n)+)",
        text,
        re.DOTALL,
    )
    if not table_match:
        return {}

    result: dict[str, dict] = {}
    for line in table_match.group(1).strip().splitlines():
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 6:
            continue
        # cols: ['', 'Skill', 'FMP API', 'FINVIZ Elite', 'Alpaca', 'Notes', '']
        raw_name = cols[1]
        # Extract name: strip ** bold markers and lowercase / slugify
        name = re.sub(r"\*\*", "", raw_name).strip()
        if name in ("Skill", "-------", ""):
            continue
        slug = _slugify(name)
        result[slug] = {
            "fmp": cols[2],
            "finviz": cols[3],
            "alpaca": cols[4],
            "notes": cols[5] if len(cols) > 5 else "",
        }
    return result


def _slugify(name: str) -> str:
    """Convert a display name to a directory slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ---------------------------------------------------------------------------
# CLI usage examples from CLAUDE.md
# ---------------------------------------------------------------------------


def parse_cli_examples(claude_md: Path) -> dict[str, str]:
    """Return {skill_slug: code_block_text} from 'Running Helper Scripts'."""
    text = claude_md.read_text(encoding="utf-8")
    # Find the section
    match = re.search(r"### Running Helper Scripts\n(.*?)(?=\n###\s|\n##\s|\Z)", text, re.DOTALL)
    if not match:
        return {}

    result: dict[str, str] = {}
    section = match.group(1)
    # Split by bold skill labels like **Economic Calendar Fetcher:**
    # Note: the colon is inside the bold markers: **Name:**
    parts = re.split(r"\*\*([^*]+?):\*\*", section)
    for i in range(1, len(parts) - 1, 2):
        label = parts[i].strip()
        content = parts[i + 1].strip()
        slug = _slugify(label)
        # Extract the first code block
        code_match = re.search(r"```bash\n(.*?)```", content, re.DOTALL)
        if code_match:
            result[slug] = code_match.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Badge generation
# ---------------------------------------------------------------------------


def api_badges(api_info: dict | None) -> str:
    """Return Jekyll badge spans from API info dict."""
    if not api_info:
        return '<span class="badge badge-free">No API</span>'

    badges = []
    fmp = api_info.get("fmp", "")
    finviz = api_info.get("finviz", "")
    alpaca = api_info.get("alpaca", "")

    has_required = False
    if "Required" in fmp:
        badges.append('<span class="badge badge-api">FMP Required</span>')
        has_required = True
    elif "Optional" in fmp:
        badges.append('<span class="badge badge-optional">FMP Optional</span>')

    if "Required" in finviz:
        badges.append('<span class="badge badge-api">FINVIZ Required</span>')
        has_required = True
    elif "Optional" in finviz or "Recommended" in finviz:
        badges.append('<span class="badge badge-optional">FINVIZ Optional</span>')

    if "Required" in alpaca:
        badges.append('<span class="badge badge-api">Alpaca Required</span>')
        has_required = True

    if not badges:
        badges.append('<span class="badge badge-free">No API</span>')
    elif not has_required:
        badges.insert(0, '<span class="badge badge-free">No API</span>')

    return " ".join(badges)


def api_badges_ja(api_info: dict | None) -> str:
    """Return Japanese Jekyll badge spans from API info dict."""
    if not api_info:
        return '<span class="badge badge-free">API不要</span>'

    badges = []
    fmp = api_info.get("fmp", "")
    finviz = api_info.get("finviz", "")
    alpaca = api_info.get("alpaca", "")

    has_required = False
    if "Required" in fmp:
        badges.append('<span class="badge badge-api">FMP必須</span>')
        has_required = True
    elif "Optional" in fmp:
        badges.append('<span class="badge badge-optional">FMP任意</span>')

    if "Required" in finviz:
        badges.append('<span class="badge badge-api">FINVIZ必須</span>')
        has_required = True
    elif "Optional" in finviz or "Recommended" in finviz:
        badges.append('<span class="badge badge-optional">FINVIZ任意</span>')

    if "Required" in alpaca:
        badges.append('<span class="badge badge-api">Alpaca必須</span>')
        has_required = True

    if not badges:
        badges.append('<span class="badge badge-free">API不要</span>')
    elif not has_required:
        badges.insert(0, '<span class="badge badge-free">API不要</span>')

    return " ".join(badges)


# ---------------------------------------------------------------------------
# Page generation
# ---------------------------------------------------------------------------


def generate_en_page(
    skill_name: str,
    skill_data: dict,
    api_info: dict | None,
    cli_example: str | None,
    nav_order: int,
    resources: dict,
) -> str:
    """Generate an EN documentation page."""
    fm = skill_data["frontmatter"]
    sections = skill_data["sections"]
    title = _title_case(skill_name)
    description = fm.get("description", "")
    badges = api_badges(api_info)

    # Build sections
    overview = _extract_section(sections, ["overview", title.lower()])
    if not overview:
        # Fallback: use the first paragraph of the body
        overview = skill_data["body"].split("\n\n")[0] if skill_data["body"] else description

    prerequisites = _extract_section(sections, ["prerequisites", "pre-requisites"])
    workflow = _extract_section(sections, ["workflow", "running the script", "how to run"])
    when_to_use = _extract_section(sections, ["when to use", "when to use this skill"])

    # Build Quick Start from workflow step 1
    quick_start = _extract_quick_start(workflow, cli_example)

    # Resources
    refs_list = _format_file_list(
        resources.get("references", []), f"skills/{skill_name}/references/"
    )
    scripts_list = _format_file_list(resources.get("scripts", []), f"skills/{skill_name}/scripts/")

    page = f"""---
layout: default
title: "{title}"
grand_parent: English
parent: Skill Guides
nav_order: {nav_order}
lang_peer: /ja/skills/{skill_name}/
permalink: /en/skills/{skill_name}/
---

# {title}
{{: .no_toc }}

{description}
{{: .fs-6 .fw-300 }}

{badges}

<details open markdown="block">
  <summary>Table of Contents</summary>
  {{: .text-delta }}
- TOC
{{:toc}}
</details>

---

## 1. Overview

{overview}

"""
    if when_to_use:
        page += f"""---

## 2. When to Use

{when_to_use}

"""

    page += f"""---

## {"3" if when_to_use else "2"}. Prerequisites

"""
    if prerequisites:
        page += f"{prerequisites}\n\n"
    elif api_info:
        page += _generate_prerequisites_from_api(api_info)
    else:
        page += "- **API Key:** None required\n- **Python 3.9+** recommended\n\n"

    page += f"""---

## {"4" if when_to_use else "3"}. Quick Start

{quick_start}

---

## {"5" if when_to_use else "4"}. Workflow

"""
    if workflow:
        page += f"{workflow}\n\n"
    else:
        page += "See the skill's SKILL.md for the complete workflow.\n\n"

    page += f"""---

## {"6" if when_to_use else "5"}. Resources

"""
    if refs_list:
        page += f"**References:**\n\n{refs_list}\n\n"
    if scripts_list:
        page += f"**Scripts:**\n\n{scripts_list}\n\n"
    if not refs_list and not scripts_list:
        page += "This skill uses built-in Claude capabilities without external scripts or references.\n\n"

    return page.rstrip() + "\n"


def generate_ja_page(
    skill_name: str,
    skill_data: dict,
    api_info: dict | None,
    nav_order: int,
) -> str:
    """Generate a JA documentation page (EN content + translation banner)."""
    fm = skill_data["frontmatter"]
    title = _title_case(skill_name)
    description = fm.get("description", "")
    badges_ja = api_badges(api_info)

    return f"""---
layout: default
title: "{title}"
grand_parent: 日本語
parent: スキルガイド
nav_order: {nav_order}
lang_peer: /en/skills/{skill_name}/
permalink: /ja/skills/{skill_name}/
---

# {title}
{{: .no_toc }}

{description}
{{: .fs-6 .fw-300 }}

{badges_ja}

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{{{ '/en/skills/{skill_name}/' | relative_url }}}}) for the full guide.
{{: .warning }}

---

[English版ガイドを見る]({{{{ '/en/skills/{skill_name}/' | relative_url }}}}){{: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _title_case(slug: str) -> str:
    """Convert slug to title case, preserving known acronyms."""
    acronyms = {
        "us": "US",
        "vcp": "VCP",
        "canslim": "CANSLIM",
        "pead": "PEAD",
        "ftd": "FTD",
        "etf": "ETF",
        "mcp": "MCP",
        "sop": "SOP",
        "esg": "ESG",
    }
    words = slug.split("-")
    return " ".join(acronyms.get(w, w.capitalize()) for w in words)


def _extract_section(sections: dict, keys: list[str]) -> str:
    """Find a section by trying multiple heading keys."""
    for key in keys:
        for sec_key, content in sections.items():
            if key in sec_key:
                return content
    return ""


def _extract_quick_start(workflow: str, cli_example: str | None) -> str:
    """Extract a quick start section from workflow or CLI example."""
    if cli_example:
        return f"```bash\n{cli_example}\n```"
    if workflow:
        # Extract the first code block from workflow
        code_match = re.search(r"```(?:bash)?\n(.*?)```", workflow, re.DOTALL)
        if code_match:
            return f"```bash\n{code_match.group(1).strip()}\n```"
        # Extract the first step
        lines = workflow.strip().splitlines()
        quick = []
        for line in lines[:10]:
            quick.append(line)
            if line.strip() == "" and len(quick) > 3:
                break
        return "\n".join(quick).strip()
    return "Invoke this skill by describing your analysis needs to Claude."


def _generate_prerequisites_from_api(api_info: dict) -> str:
    """Generate prerequisites text from API info."""
    lines = []
    fmp = api_info.get("fmp", "")
    finviz = api_info.get("finviz", "")
    alpaca = api_info.get("alpaca", "")
    notes = api_info.get("notes", "")

    if "Required" in fmp:
        lines.append("- **FMP API key** required (`FMP_API_KEY` environment variable)")
    elif "Optional" in fmp:
        lines.append("- **FMP API key** optional but recommended")

    if "Required" in finviz:
        lines.append("- **FINVIZ Elite** subscription required")
    elif "Optional" in finviz or "Recommended" in finviz:
        lines.append("- **FINVIZ Elite** optional (improves performance)")

    if "Required" in alpaca:
        lines.append("- **Alpaca API** account required (paper trading is free)")

    if notes:
        lines.append(f"- {notes}")

    if not lines:
        lines.append("- No API key required")

    lines.append("- Python 3.9+ recommended")
    return "\n".join(lines) + "\n\n"


def _format_file_list(files: list[str], prefix: str) -> str:
    """Format a list of files as markdown."""
    if not files:
        return ""
    return "\n".join(f"- `{prefix}{f}`" for f in sorted(files))


def _list_skill_resources(skill_dir: Path) -> dict:
    """List references and scripts files for a skill."""
    result: dict[str, list[str]] = {"references": [], "scripts": []}

    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        result["references"] = [
            f.name for f in refs_dir.iterdir() if f.is_file() and not f.name.startswith(".")
        ]

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        result["scripts"] = [
            f.name
            for f in scripts_dir.iterdir()
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("test_")
        ]

    return result


# ---------------------------------------------------------------------------
# Index page update
# ---------------------------------------------------------------------------


def generate_index_table_row(
    skill_name: str,
    description: str,
    api_info: dict | None,
    lang: str,
) -> str:
    """Generate a single table row for the index page."""
    title = _title_case(skill_name)
    star = " ★" if skill_name in HAND_WRITTEN else ""
    link = f"{{{{ '/{lang}/skills/{skill_name}/' | relative_url }}}}"
    badges = api_badges_ja(api_info) if lang == "ja" else api_badges(api_info)
    short_desc = description.split(".")[0].strip() if description else title
    if len(short_desc) > 120:
        short_desc = short_desc[:117] + "..."
    return f"| [{title}]({link}){star} | {short_desc} | {badges} |"


def update_index_pages(
    skills_dir: Path,
    docs_dir: Path,
    api_reqs: dict[str, dict],
) -> None:
    """Regenerate the Available Guides table in both EN and JA index.md."""
    # Collect all skills with SKILL.md
    all_skills: list[tuple[str, dict, dict | None]] = []
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        data = parse_skill_md(d / "SKILL.md")
        all_skills.append((d.name, data, api_reqs.get(d.name)))

    for lang in ("en", "ja"):
        index_path = docs_dir / lang / "skills" / "index.md"
        if not index_path.exists():
            continue

        rows = []
        for name, skill_data, api_info in all_skills:
            row = generate_index_table_row(
                name,
                skill_data["frontmatter"].get("description", ""),
                api_info,
                lang,
            )
            rows.append(row)

        _replace_table_rows(index_path, rows)
        print(f"  Updated index: {index_path} ({len(rows)} skills)")


def _replace_table_rows(index_path: Path, rows: list[str]) -> None:
    """Replace table data rows in an index.md file, preserving header/footer."""
    text = index_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the separator line (|---|...) that follows the table header
    sep_idx = None
    table_end = None
    for i, line in enumerate(lines):
        if line.startswith("|---"):
            sep_idx = i
        elif sep_idx is not None and i > sep_idx and not line.startswith("|"):
            table_end = i
            break

    if sep_idx is None:
        return
    if table_end is None:
        table_end = len(lines)

    new_lines = lines[: sep_idx + 1] + rows + lines[table_end:]
    index_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate skill documentation pages")
    parser.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--claude-md", type=Path, default=DEFAULT_CLAUDE_MD)
    parser.add_argument("--skill", type=str, help="Generate for a single skill")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing pages")
    args = parser.parse_args(argv)

    # Parse CLAUDE.md
    api_reqs = parse_api_requirements(args.claude_md)
    cli_examples = parse_cli_examples(args.claude_md)

    # Discover skills
    skill_dirs = sorted(args.skills_dir.iterdir())
    if args.skill:
        skill_dirs = [args.skills_dir / args.skill]

    en_dir = args.docs_dir / "en" / "skills"
    ja_dir = args.docs_dir / "ja" / "skills"
    en_dir.mkdir(parents=True, exist_ok=True)
    ja_dir.mkdir(parents=True, exist_ok=True)

    # Assign nav_orders: existing hand-written keep 1-10, new start at 11+
    new_skills = []
    for d in skill_dirs:
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        name = d.name
        if name in HAND_WRITTEN and not args.overwrite:
            continue
        new_skills.append(name)

    new_skills.sort()
    nav_orders = {name: NAV_ORDER_START + i for i, name in enumerate(new_skills)}

    generated_en = 0
    generated_ja = 0
    skipped = 0

    for d in skill_dirs:
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue

        name = d.name

        if name in HAND_WRITTEN and not args.overwrite:
            skipped += 1
            continue

        en_path = en_dir / f"{name}.md"
        ja_path = ja_dir / f"{name}.md"

        if en_path.exists() and not args.overwrite:
            skipped += 1
            continue

        skill_data = parse_skill_md(d / "SKILL.md")
        api_info = api_reqs.get(name)
        cli_example = cli_examples.get(name)
        nav_order = nav_orders.get(name, NAV_ORDER_START)
        resources = _list_skill_resources(d)

        # Generate EN page
        en_content = generate_en_page(name, skill_data, api_info, cli_example, nav_order, resources)
        en_path.write_text(en_content, encoding="utf-8")
        generated_en += 1

        # Generate JA page
        ja_content = generate_ja_page(name, skill_data, api_info, nav_order)
        ja_path.write_text(ja_content, encoding="utf-8")
        generated_ja += 1

        print(f"  Generated: {name} (EN + JA)")

    print(f"\nDone: {generated_en} EN + {generated_ja} JA generated, {skipped} skipped")

    # Update index pages with current skill table
    update_index_pages(args.skills_dir, args.docs_dir, api_reqs)

    return 0


if __name__ == "__main__":
    sys.exit(main())
