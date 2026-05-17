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
import os
import re
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS_DIR = PROJECT_ROOT / "skills"
DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
DEFAULT_CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"

GITHUB_REPO_URL = "https://github.com/tradermonty/claude-trading-skills"

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
# Doc-page ownership marker
# ---------------------------------------------------------------------------
#
# A rendered page declares ownership via a `generated:` frontmatter key:
#   generated: true   -> generator-owned (drift-checked, --overwrite may rewrite)
#   generated: false  -> hand-maintained (protected; existence/marker only)
#   (key absent)      -> hand-maintained (protected) -- the safe default
# Hand-maintained pages are NEVER content-reverted by --check, and --overwrite
# refuses them unless --force. See docs/README.md "Skill doc ownership".


def _read_generated_marker(path: Path) -> str | None:
    """Return the raw `generated:` value from a page's frontmatter.

    Returns the stripped raw token (e.g. "true", "false", "maybe") if the key
    is present in the leading YAML frontmatter, or ``None`` if the file is
    missing/unreadable, has no frontmatter, or has no ``generated:`` key.

    Uses a line scan rather than ``yaml.safe_load`` for the same reason
    ``parse_skill_md`` keeps a manual fallback: page titles/descriptions can
    contain unquoted colons that break a strict YAML load.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    for line in parts[1].splitlines():
        stripped = line.strip()
        if stripped.startswith("generated:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _doc_is_generated(path: Path) -> bool | None:
    """Ownership of a rendered page.

    ``True``  -> generator-owned (literal ``generated: true``).
    ``False`` -> explicitly hand-maintained (literal ``generated: false``).
    ``None``  -> marker absent / file missing / malformed.

    Callers treat both ``False`` and ``None`` as "protected"; only ``True``
    opts a page into overwrite + content drift checking.
    """
    raw = _read_generated_marker(path)
    if raw is None:
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    return None


def _marker_present_but_invalid(path: Path) -> bool:
    """True if a `generated:` key is present but is neither `true` nor `false`."""
    raw = _read_generated_marker(path)
    return raw is not None and raw not in ("true", "false")


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
# Button generation
# ---------------------------------------------------------------------------


def _generate_buttons(skill_name: str, skill_packages_dir: Path | None, lang: str) -> str:
    """Return markdown download/source buttons for a skill page.

    Args:
        skill_name: The skill slug (e.g., "pead-screener").
        skill_packages_dir: Path to the skill-packages directory, or None.
            Download button is shown only when the .skill file exists.
        lang: "en" or "ja".

    Returns:
        Markdown string with Source button always present, plus Download
        button when .skill package exists.
    """
    buttons = []
    has_package = (
        skill_packages_dir is not None and (skill_packages_dir / f"{skill_name}.skill").exists()
    )

    if has_package:
        dl_url = f"{GITHUB_REPO_URL}/raw/main/skill-packages/{skill_name}.skill"
        if lang == "ja":
            buttons.append(
                f"[スキルパッケージをダウンロード (.skill)]({dl_url})"
                "{: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }"
            )
        else:
            buttons.append(
                f"[Download Skill Package (.skill)]({dl_url})"
                "{: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }"
            )

    src_url = f"{GITHUB_REPO_URL}/tree/main/skills/{skill_name}"
    if lang == "ja":
        buttons.append(f"[GitHubでソースを見る]({src_url}){{: .btn .fs-5 .mb-4 .mb-md-0 }}")
    else:
        buttons.append(f"[View Source on GitHub]({src_url}){{: .btn .fs-5 .mb-4 .mb-md-0 }}")

    return "\n".join(buttons)


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
    skill_packages_dir: Path | None = None,
) -> str:
    """Generate an EN documentation page."""
    fm = skill_data["frontmatter"]
    sections = skill_data["sections"]
    title = _title_case(skill_name)
    description = fm.get("description", "")
    badges = api_badges(api_info)
    buttons = _generate_buttons(skill_name, skill_packages_dir, "en")

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
generated: true
---

# {title}
{{: .no_toc }}

{description}
{{: .fs-6 .fw-300 }}

{badges}

"""
    if buttons:
        page += f"{buttons}\n\n"

    page += f"""<details open markdown="block">
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
    skill_packages_dir: Path | None = None,
) -> str:
    """Generate a JA documentation page (EN content + translation banner)."""
    fm = skill_data["frontmatter"]
    title = _title_case(skill_name)
    description = fm.get("description", "")
    badges_ja = api_badges_ja(api_info)
    buttons = _generate_buttons(skill_name, skill_packages_dir, "ja")

    page = f"""---
layout: default
title: "{title}"
grand_parent: 日本語
parent: スキルガイド
nav_order: {nav_order}
lang_peer: /en/skills/{skill_name}/
permalink: /ja/skills/{skill_name}/
generated: true
---

# {title}
{{: .no_toc }}

{description}
{{: .fs-6 .fw-300 }}

{badges_ja}

"""
    if buttons:
        page += f"{buttons}\n\n"

    page += f"""> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{{{ '/en/skills/{skill_name}/' | relative_url }}}}) for the full guide.
{{: .warning }}

---

[English版ガイドを見る]({{{{ '/en/skills/{skill_name}/' | relative_url }}}}){{: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }}
"""
    return page


def generate_en_full_page(
    skill_name: str,
    skill_data: dict,
    api_info: dict | None,
    cli_example: str | None,
    nav_order: int,
    resources: dict,
    skill_packages_dir: Path | None = None,
) -> str:
    """Generate a 10-section EN documentation skeleton page."""
    fm = skill_data["frontmatter"]
    sections = skill_data["sections"]
    title = _title_case(skill_name)
    description = fm.get("description", "")
    badges = api_badges(api_info)
    buttons = _generate_buttons(skill_name, skill_packages_dir, "en")

    # Auto-fill content
    overview = _extract_section(sections, ["overview", title.lower()])
    if not overview:
        overview = skill_data["body"].split("\n\n")[0] if skill_data["body"] else description

    prerequisites = _extract_section(sections, ["prerequisites", "pre-requisites"])
    if not prerequisites:
        if api_info:
            prerequisites = _generate_prerequisites_from_api(api_info).rstrip()
        else:
            prerequisites = "- **API Key:** None required\n- **Python 3.9+** recommended"

    quick_start = _extract_quick_start(
        _extract_section(sections, ["workflow", "running the script", "how to run"]),
        cli_example,
    )

    refs_list = _format_file_list(
        resources.get("references", []), f"skills/{skill_name}/references/"
    )
    scripts_list = _format_file_list(resources.get("scripts", []), f"skills/{skill_name}/scripts/")
    resources_text = ""
    if refs_list:
        resources_text += f"**References:**\n\n{refs_list}\n\n"
    if scripts_list:
        resources_text += f"**Scripts:**\n\n{scripts_list}\n\n"
    if not resources_text:
        resources_text = (
            "This skill uses built-in Claude capabilities without external scripts or references.\n"
        )

    page = f"""---
layout: default
title: "{title}"
grand_parent: English
parent: Skill Guides
nav_order: {nav_order}
lang_peer: /ja/skills/{skill_name}/
permalink: /en/skills/{skill_name}/
generated: true
---

# {title}
{{: .no_toc }}

{description}
{{: .fs-6 .fw-300 }}

{badges}

"""
    if buttons:
        page += f"{buttons}\n\n"

    page += f"""<details open markdown="block">
  <summary>Table of Contents</summary>
  {{: .text-delta }}
- TOC
{{:toc}}
</details>

---

## 1. Overview

{overview}

---

## 2. Prerequisites

{prerequisites}

---

## 3. Quick Start

{quick_start}

---

## 4. How It Works

<!-- TODO: Describe the internal pipeline/algorithm -->

---

## 5. Usage Examples

<!-- TODO: Add 4-6 real-world usage scenarios -->

---

## 6. Understanding the Output

<!-- TODO: Describe output file format and field definitions -->

---

## 7. Tips & Best Practices

<!-- TODO: Add expert advice for getting the most value -->

---

## 8. Combining with Other Skills

<!-- TODO: Add multi-skill workflow table -->

---

## 9. Troubleshooting

<!-- TODO: Add common errors and fixes -->

---

## 10. Reference

{resources_text}"""

    return page.rstrip() + "\n"


def generate_ja_full_page(
    skill_name: str,
    skill_data: dict,
    api_info: dict | None,
    cli_example: str | None,
    nav_order: int,
    resources: dict,
    skill_packages_dir: Path | None = None,
) -> str:
    """Generate a 10-section JA documentation skeleton page."""
    fm = skill_data["frontmatter"]
    sections = skill_data["sections"]
    title = _title_case(skill_name)
    description = fm.get("description", "")
    badges = api_badges_ja(api_info)
    buttons = _generate_buttons(skill_name, skill_packages_dir, "ja")

    # Auto-fill content (same as EN)
    overview = _extract_section(sections, ["overview", title.lower()])
    if not overview:
        overview = skill_data["body"].split("\n\n")[0] if skill_data["body"] else description

    prerequisites = _extract_section(sections, ["prerequisites", "pre-requisites"])
    if not prerequisites:
        if api_info:
            prerequisites = _generate_prerequisites_from_api(api_info).rstrip()
        else:
            prerequisites = "- **API Key:** None required\n- **Python 3.9+** recommended"

    quick_start = _extract_quick_start(
        _extract_section(sections, ["workflow", "running the script", "how to run"]),
        cli_example,
    )

    refs_list = _format_file_list(
        resources.get("references", []), f"skills/{skill_name}/references/"
    )
    scripts_list = _format_file_list(resources.get("scripts", []), f"skills/{skill_name}/scripts/")
    resources_text = ""
    if refs_list:
        resources_text += f"**References:**\n\n{refs_list}\n\n"
    if scripts_list:
        resources_text += f"**Scripts:**\n\n{scripts_list}\n\n"
    if not resources_text:
        resources_text = (
            "This skill uses built-in Claude capabilities without external scripts or references.\n"
        )

    page = f"""---
layout: default
title: "{title}"
grand_parent: 日本語
parent: スキルガイド
nav_order: {nav_order}
lang_peer: /en/skills/{skill_name}/
permalink: /ja/skills/{skill_name}/
generated: true
---

# {title}
{{: .no_toc }}

{description}
{{: .fs-6 .fw-300 }}

{badges}

"""
    if buttons:
        page += f"{buttons}\n\n"

    page += f"""<details open markdown="block">
  <summary>目次</summary>
  {{: .text-delta }}
- TOC
{{:toc}}
</details>

---

## 1. 概要

{overview}

<!-- TODO: 翻訳 -->

---

## 2. 前提条件

{prerequisites}

<!-- TODO: 翻訳 -->

---

## 3. クイックスタート

{quick_start}

<!-- TODO: 翻訳 -->

---

## 4. 仕組み

<!-- TODO: 翻訳 -->

---

## 5. 使用例

<!-- TODO: 翻訳 -->

---

## 6. 出力の読み方

<!-- TODO: 翻訳 -->

---

## 7. Tips & ベストプラクティス

<!-- TODO: 翻訳 -->

---

## 8. 他スキルとの連携

<!-- TODO: 翻訳 -->

---

## 9. トラブルシューティング

<!-- TODO: 翻訳 -->

---

## 10. リファレンス

{resources_text}"""

    return page.rstrip() + "\n"


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
    # Collapse newlines/whitespace BEFORE truncating so a multi-line YAML
    # block-scalar description (e.g. scenario-analyzer) can never span
    # multiple physical lines and break the markdown table / the row-replace
    # logic. Escape pipes last so the cell stays single-column.
    short_desc = " ".join(short_desc.split())
    if len(short_desc) > 120:
        short_desc = short_desc[:117] + "..."
    short_desc = short_desc.replace("\\", "\\\\").replace("|", "\\|")
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
    """Rebuild an index.md table: header + fresh rows + preserved footer.

    Deterministic, idempotent, and self-healing. Everything between the
    ``|---`` header separator and the *last* table row is discarded and
    rebuilt from ``rows``. The footer is whatever follows the last line that
    starts with ``|`` (its leading blank lines collapsed to exactly one).

    Using "after the last pipe line" — instead of "first non-pipe line after
    the separator" (the previous logic) — is what makes this self-heal a file
    already corrupted by a prior multi-line row: stray non-``|`` continuation
    lines and duplicated row blocks in the old body are all dropped rather
    than mistaken for the footer and re-appended on every run. Combined with
    generate_index_table_row() collapsing newlines, rows can never span
    multiple physical lines again.
    """
    text = index_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    sep_idx = next((i for i, line in enumerate(lines) if line.startswith("|---")), None)
    if sep_idx is None:
        return

    # Last physical line (after the separator) that is a table row.
    last_pipe_idx = sep_idx
    for i in range(sep_idx + 1, len(lines)):
        if lines[i].startswith("|"):
            last_pipe_idx = i

    footer = lines[last_pipe_idx + 1 :]
    while footer and footer[0].strip() == "":
        footer.pop(0)
    footer = (["", *footer]) if footer else []

    new_lines = lines[: sep_idx + 1] + rows + footer
    index_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Catalog page update
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"/(?:en|ja)/skills/([\w-]+)/")


def _extract_catalog_slugs(text: str) -> set[str]:
    """Extract all skill slugs from catalog links and bold names."""
    slugs: set[str] = set()

    # From links like [Name](/en/skills/slug/) or [Name](/ja/skills/slug/)
    for match in _SLUG_RE.finditer(text):
        slugs.add(match.group(1))

    # From bold names in table rows: | **Name** | ... |
    for match in re.finditer(r"\|\s*\*\*([^*]+)\*\*", text):
        slugs.add(_slugify(match.group(1)))

    # From non-linked, non-bold names in table data rows (e.g., "| Name | ...")
    # Skip header rows that contain "Skill" or "スキル"
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 3:
            continue
        name_col = cols[1]
        if not name_col or name_col.startswith("---"):
            continue
        # Skip headers
        if name_col in ("Skill", "スキル", "Badge", "バッジ"):
            continue
        # Already covered by bold or link patterns
        if "**" in name_col or "[" in name_col:
            continue
        slug = _slugify(name_col)
        if slug:
            slugs.add(slug)

    return slugs


def _api_status_en(api_info: dict | None) -> tuple[str, str, str]:
    """Return (fmp, finviz, alpaca) status strings for EN catalog."""
    if not api_info:
        return ("--", "--", "--")
    fmp_raw = api_info.get("fmp", "")
    finviz_raw = api_info.get("finviz", "")
    alpaca_raw = api_info.get("alpaca", "")

    fmp = "Required" if "Required" in fmp_raw else ("Optional" if "Optional" in fmp_raw else "--")
    finviz = (
        "Recommended"
        if "Recommended" in finviz_raw
        else ("Optional" if "Optional" in finviz_raw else "--")
    )
    alpaca = "Required" if "Required" in alpaca_raw else "--"
    return (fmp, finviz, alpaca)


def _api_status_ja(api_info: dict | None) -> tuple[str, str, str]:
    """Return (fmp, finviz, alpaca) status strings for JA catalog."""
    if not api_info:
        return ("-", "-", "-")
    fmp_raw = api_info.get("fmp", "")
    finviz_raw = api_info.get("finviz", "")
    alpaca_raw = api_info.get("alpaca", "")

    fmp = "必須" if "Required" in fmp_raw else ("任意" if "Optional" in fmp_raw else "-")
    finviz = (
        "推奨" if "Recommended" in finviz_raw else ("任意" if "Optional" in finviz_raw else "-")
    )
    alpaca = "必須" if "Required" in alpaca_raw else "-"
    return (fmp, finviz, alpaca)


def update_catalog_api_matrix(
    docs_dir: Path,
    all_skills: list[tuple[str, dict, dict | None]],
) -> None:
    """Add missing skills to the API Requirements Matrix in catalog pages."""
    for lang in ("en", "ja"):
        catalog_path = docs_dir / lang / "skill-catalog.md"
        if not catalog_path.exists():
            continue

        text = catalog_path.read_text(encoding="utf-8")
        lines = text.splitlines()

        # Find the API Requirements Matrix section
        section_heading = "## API Requirements Matrix" if lang == "en" else "## API要件マトリクス"
        section_start = None
        for i, line in enumerate(lines):
            if line.strip() == section_heading:
                section_start = i
                break

        if section_start is None:
            continue

        # Find the table separator within the section
        sep_idx = None
        table_end = None
        for i in range(section_start, len(lines)):
            if lines[i].startswith("|---"):
                sep_idx = i
            elif sep_idx is not None and i > sep_idx and not lines[i].startswith("|"):
                table_end = i
                break

        if sep_idx is None:
            continue
        if table_end is None:
            table_end = len(lines)

        # Extract slugs only from the matrix table rows (not full file)
        matrix_text = "\n".join(lines[sep_idx + 1 : table_end])
        existing_slugs = _extract_catalog_slugs(matrix_text)

        # For JA: find the aggregate row index
        aggregate_idx = None
        if lang == "ja":
            for i in range(sep_idx + 1, table_end):
                if "その他すべてのスキル" in lines[i]:
                    aggregate_idx = i
                    break

        # Collect new rows
        new_rows: list[str] = []
        for skill_name, skill_data, api_info in all_skills:
            slug = _slugify(skill_name)
            if slug in existing_slugs:
                continue

            title = _title_case(skill_name)

            if lang == "en":
                fmp, finviz, alpaca = _api_status_en(api_info)
                new_rows.append(f"| {title} | {fmp} | {finviz} | {alpaca} |")
            else:
                fmp, finviz, alpaca = _api_status_ja(api_info)
                # Skip skills where all values are "-" for JA
                if fmp == "-" and finviz == "-" and alpaca == "-":
                    continue
                new_rows.append(f"| {title} | {fmp} | {finviz} | {alpaca} |")

        if not new_rows:
            continue

        # Create backup
        backup_fd, backup_path = tempfile.mkstemp(suffix=".md.bak")
        os.close(backup_fd)
        try:
            Path(backup_path).write_text(text, encoding="utf-8")

            if lang == "ja" and aggregate_idx is not None:
                # Insert before the aggregate row
                updated_lines = lines[:aggregate_idx] + new_rows + lines[aggregate_idx:]
            else:
                # Append at end of table (before table_end)
                updated_lines = lines[:table_end] + new_rows + lines[table_end:]

            catalog_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
            os.unlink(backup_path)
            print(f"  Updated catalog matrix: {catalog_path} (+{len(new_rows)} rows)")
        except Exception:
            # Restore from backup on failure
            Path(backup_path).replace(catalog_path)
            raise


# ---------------------------------------------------------------------------
# Ownership-aware write/check helpers
# ---------------------------------------------------------------------------


def _compute_nav_orders(skill_dirs: list[Path], overwrite: bool) -> dict[str, int]:
    """Assign nav_order: hand-written keep 1-10, the rest start at NAV_ORDER_START.

    Shared by the write path and ``--check`` so expected output cannot diverge
    from what a real generation would write.
    """
    new_skills: list[str] = []
    for d in skill_dirs:
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        name = d.name
        if name in HAND_WRITTEN and not overwrite:
            continue
        new_skills.append(name)
    new_skills.sort()
    return {name: NAV_ORDER_START + i for i, name in enumerate(new_skills)}


def _render_skill_pages(
    d: Path,
    name: str,
    nav_order: int,
    api_reqs: dict,
    cli_examples: dict,
    skill_packages_dir: Path | None,
    mode: str,
) -> tuple[str, str]:
    """Render (en, ja) page content exactly as the write loop would."""
    skill_data = parse_skill_md(d / "SKILL.md")
    api_info = api_reqs.get(name)
    cli_example = cli_examples.get(name)
    resources = _list_skill_resources(d)
    if mode == "full":
        en = generate_en_full_page(
            name,
            skill_data,
            api_info,
            cli_example,
            nav_order,
            resources,
            skill_packages_dir=skill_packages_dir,
        )
        ja = generate_ja_full_page(
            name,
            skill_data,
            api_info,
            cli_example,
            nav_order,
            resources,
            skill_packages_dir=skill_packages_dir,
        )
    else:
        en = generate_en_page(
            name,
            skill_data,
            api_info,
            cli_example,
            nav_order,
            resources,
            skill_packages_dir=skill_packages_dir,
        )
        ja = generate_ja_page(
            name,
            skill_data,
            api_info,
            nav_order,
            skill_packages_dir=skill_packages_dir,
        )
    return en, ja


def _may_write(path: Path, name: str, args: argparse.Namespace) -> bool:
    """Per-page write decision (EN and JA decided independently).

    HAND_WRITTEN ★ guides are always protected (missing OR existing) unless
    --force; this preserves the existing ``test_skips_hand_written`` contract.
    Brand-new (non-HAND_WRITTEN) pages are created. Existing pages are only
    rewritten when --force, or under --overwrite when the page is explicitly
    generator-owned (``generated: true``). Hand-maintained pages
    (generated:false/absent) are never destroyed without --force.
    """
    if name in HAND_WRITTEN and not args.force:
        return False
    if not path.exists():
        return True
    if not args.overwrite:
        return False
    if args.force:
        return True
    return _doc_is_generated(path) is True


def _check_drift(
    skill_dirs: list[Path],
    en_dir: Path,
    ja_dir: Path,
    api_reqs: dict,
    cli_examples: dict,
    skill_packages_dir: Path | None,
    args: argparse.Namespace,
) -> int:
    """Pure read/compare drift gate (no mkdir, no writes, no index/catalog).

    Mirrors the sibling generators (generate_workflow_docs / generate_skillset_docs):
    print ``DRIFT:``/``OK:`` to stderr and return 1 iff any drift. Existence +
    marker-validity are checked for every page; CONTENT is compared ONLY for
    pages explicitly marked ``generated: true``. Hand-maintained pages
    (generated:false/absent/HAND_WRITTEN) are never content-compared and never
    reverted.
    """
    nav_orders = _compute_nav_orders(skill_dirs, overwrite=False)
    drift = False
    for d in skill_dirs:
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        name = d.name
        en_path = en_dir / f"{name}.md"
        ja_path = ja_dir / f"{name}.md"

        # 1. Existence: every skill must have EN + JA pages.
        for p in (en_path, ja_path):
            if not p.is_file():
                print(f"DRIFT: {p} does not exist", file=sys.stderr)
                drift = True

        # 2. Marker validity: present-but-invalid generated: value.
        for p in (en_path, ja_path):
            if p.is_file() and _marker_present_but_invalid(p):
                print(
                    f"DRIFT: {p} has invalid 'generated:' marker (must be true or false)",
                    file=sys.stderr,
                )
                drift = True

        # 3. Content compare ONLY generator-owned (generated: true) pages.
        # HAND_WRITTEN is always protected regardless of marker (a generated:
        # true stamped via --force must NOT become drift-checked afterwards).
        en_owned = (
            name not in HAND_WRITTEN and en_path.is_file() and _doc_is_generated(en_path) is True
        )
        ja_owned = (
            name not in HAND_WRITTEN and ja_path.is_file() and _doc_is_generated(ja_path) is True
        )
        if not (en_owned or ja_owned):
            continue
        nav_order = nav_orders.get(name, NAV_ORDER_START)
        expected_en, expected_ja = _render_skill_pages(
            d, name, nav_order, api_reqs, cli_examples, skill_packages_dir, args.mode
        )
        if en_owned:
            if en_path.read_text(encoding="utf-8") != expected_en.rstrip("\n") + "\n":
                print(f"DRIFT: {en_path} differs from regenerated output", file=sys.stderr)
                drift = True
            else:
                print(f"OK: {en_path} matches", file=sys.stderr)
        if ja_owned:
            if ja_path.read_text(encoding="utf-8") != expected_ja.rstrip("\n") + "\n":
                print(f"DRIFT: {ja_path} differs from regenerated output", file=sys.stderr)
                drift = True
            else:
                print(f"OK: {ja_path} matches", file=sys.stderr)

    return 1 if drift else 0


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
    parser.add_argument(
        "--skill-packages-dir",
        type=Path,
        default=PROJECT_ROOT / "skill-packages",
        help="Path to skill-packages directory for download buttons",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "full"],
        default="auto",
        help="Generation mode: 'auto' (6-section) or 'full' (10-section skeleton)",
    )
    parser.add_argument(
        "--catalog-category",
        type=str,
        default=None,
        help='Category for catalog insertion, e.g. "4. Portfolio & Execution"',
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite hand-maintained pages (generated:false/absent or HAND_WRITTEN). "
        "Never used in CI/pre-commit.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare regenerated output against on-disk files; exit non-zero if they differ.",
    )
    args = parser.parse_args(argv)

    # Parse CLAUDE.md
    api_reqs = parse_api_requirements(args.claude_md)
    cli_examples = parse_cli_examples(args.claude_md)

    # Resolve skill-packages-dir (None if it doesn't exist)
    skill_packages_dir = args.skill_packages_dir if args.skill_packages_dir.is_dir() else None

    # Discover skills
    skill_dirs = sorted(args.skills_dir.iterdir())
    if args.skill:
        skill_dirs = [args.skills_dir / args.skill]

    en_dir = args.docs_dir / "en" / "skills"
    ja_dir = args.docs_dir / "ja" / "skills"

    # --check is a pure read/compare gate: return BEFORE any mkdir/write so it
    # never touches the tree or runs the index/catalog updaters.
    if args.check:
        return _check_drift(
            skill_dirs, en_dir, ja_dir, api_reqs, cli_examples, skill_packages_dir, args
        )

    en_dir.mkdir(parents=True, exist_ok=True)
    ja_dir.mkdir(parents=True, exist_ok=True)

    # Assign nav_orders (shared with --check via _compute_nav_orders).
    nav_orders = _compute_nav_orders(skill_dirs, args.overwrite)

    generated_en = 0
    generated_ja = 0
    skipped = 0

    for d in skill_dirs:
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue

        name = d.name
        en_path = en_dir / f"{name}.md"
        ja_path = ja_dir / f"{name}.md"

        # Per-page ownership guard (EN and JA decided independently).
        write_en = _may_write(en_path, name, args)
        write_ja = _may_write(ja_path, name, args)
        if not write_en and not write_ja:
            skipped += 1
            continue

        nav_order = nav_orders.get(name, NAV_ORDER_START)
        en_content, ja_content = _render_skill_pages(
            d, name, nav_order, api_reqs, cli_examples, skill_packages_dir, args.mode
        )

        if write_en:
            en_path.write_text(en_content, encoding="utf-8")
            generated_en += 1
        elif args.overwrite:
            print(f"  Protected, EN skipped: {name} (use --force)", file=sys.stderr)

        if write_ja:
            ja_path.write_text(ja_content, encoding="utf-8")
            generated_ja += 1
        elif args.overwrite:
            print(f"  Protected, JA skipped: {name} (use --force)", file=sys.stderr)

        wrote = []
        if write_en:
            wrote.append("EN")
        if write_ja:
            wrote.append("JA")
        print(f"  Generated: {name} ({' + '.join(wrote)}, mode={args.mode})")

    print(f"\nDone: {generated_en} EN + {generated_ja} JA generated, {skipped} skipped")

    # Update index pages with current skill table
    update_index_pages(args.skills_dir, args.docs_dir, api_reqs)

    # Update catalog pages with API matrix
    all_skills_for_catalog: list[tuple[str, dict, dict | None]] = []
    for d in sorted(args.skills_dir.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        data = parse_skill_md(d / "SKILL.md")
        all_skills_for_catalog.append((d.name, data, api_reqs.get(d.name)))

    update_catalog_api_matrix(args.docs_dir, all_skills_for_catalog)

    if args.catalog_category:
        print(
            f"\nWarning: --catalog-category '{args.catalog_category}' was specified "
            "but category table insertion is not yet implemented.\n"
            "Please add the skill to the category table manually in "
            "docs/en/skill-catalog.md and docs/ja/skill-catalog.md."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
