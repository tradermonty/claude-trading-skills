#!/usr/bin/env python3
"""One-shot migration helper: bootstrap skills-index.yaml from existing repo state.

This script is intentionally placed under `scripts/dev/` to mark it as
non-permanent. After PR1 merges, `skills-index.yaml` is the source of truth
and CLAUDE.md becomes a downstream consumer. Do NOT re-run this as a sync
tool — direct edits to skills-index.yaml are the maintenance path.

What it does:
  1. Scans skills/*/SKILL.md → id, summary (from frontmatter `description`)
  2. Heuristic display_name (Title-cased, with common abbreviations capitalized)
  3. Heuristic category from id keywords (human reviews and corrects)
  4. Parses CLAUDE.md API Requirements Matrix → integrations[]
  5. Emits skills-index.yaml at project root (or stdout under --dry-run)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

# id-keyword → category mapping (first match wins)
CATEGORY_HINTS: list[tuple[list[str], str]] = [
    (
        [
            "breadth",
            "uptrend",
            "regime",
            "distribution-day",
            "macro",
            "market-top",
            "ftd",
            "exposure",
            "downtrend",
            "market-environment",
            "market-news",
            "bubble",
        ],
        "market-regime",
    ),
    (["portfolio", "kanchi", "dividend"], "core-portfolio"),
    (["vcp", "canslim", "breakout", "theme"], "swing-opportunity"),
    (["position-sizer", "technical-analyst"], "trade-planning"),
    (["memory", "postmortem", "journal", "trade-hypothesis"], "trade-memory"),
    (["backtest", "edge-", "scenario", "strategy-pivot", "stanley"], "strategy-research"),
    (
        [
            "parabolic",
            "options",
            "earnings",
            "pead",
            "pair-trade",
            "institutional-flow",
            "finviz",
            "ibd-distribution",
        ],
        "advanced-satellite",
    ),
    (
        [
            "skill-designer",
            "skill-idea",
            "skill-integration",
            "dual-axis",
            "data-quality-checker",
            "downtrend-duration",
            "signal-postmortem-analyzer",
            "us-stock-analysis",
            "sector-analyst",
        ],
        "meta",
    ),
]

# Common abbreviations to capitalize when generating display_name
DISPLAY_NAME_OVERRIDES = {
    "vcp": "VCP",
    "canslim": "CANSLIM",
    "pead": "PEAD",
    "ftd": "FTD",
    "ibd": "IBD",
    "mcp": "MCP",
    "us": "US",
    "etf": "ETF",
    "rsi": "RSI",
    "atr": "ATR",
    "ai": "AI",
    "fmp": "FMP",
    "sop": "SOP",
}

# Skills not in CLAUDE.md API matrix that we know are pure-local
KNOWN_PURE_LOCAL = {
    # Add IDs here only when we are certain — otherwise leave as `unknown`.
}

# ---------------------------------------------------------------------------
# Frontmatter parser (mirrors check_skill_frontmatter.py)
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    return dict(FIELD_RE.findall(match.group(1)))


# ---------------------------------------------------------------------------
# Display name heuristic
# ---------------------------------------------------------------------------


def to_display_name(skill_id: str) -> str:
    parts = skill_id.split("-")
    out = []
    for part in parts:
        out.append(DISPLAY_NAME_OVERRIDES.get(part, part.capitalize()))
    return " ".join(out)


# ---------------------------------------------------------------------------
# Category heuristic
# ---------------------------------------------------------------------------


def guess_category(skill_id: str) -> str | None:
    for keywords, category in CATEGORY_HINTS:
        for kw in keywords:
            if kw in skill_id:
                return category
    return None


# ---------------------------------------------------------------------------
# CLAUDE.md API matrix parser
# ---------------------------------------------------------------------------


MATRIX_HEADER_RE = re.compile(
    r"^\|\s*Skill\s*\|\s*FMP API\s*\|\s*FINVIZ Elite\s*\|\s*Alpaca\s*\|", re.MULTILINE
)
ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|$")


def display_name_to_id(name: str) -> str:
    """Convert "Earnings Trade Analyzer" → "earnings-trade-analyzer"."""
    cleaned = name.replace("**", "").strip()
    return cleaned.lower().replace(" ", "-")


def cell_to_requirement(cell: str) -> str | None:
    """Translate a matrix cell into a requirement value."""
    cell = cell.strip()
    if "Required" in cell and "Not" not in cell:
        return "required"
    if "Optional" in cell and "Recommended" in cell:
        return "recommended"
    if "Optional" in cell:
        return "optional"
    # "Not used" / "Not required" / blank → no entry
    return None


def parse_claude_md_matrix(claude_md: Path) -> dict[str, list[dict]]:
    """Return {skill_id: [integration entries]} parsed from CLAUDE.md."""
    text = claude_md.read_text(encoding="utf-8")
    header = MATRIX_HEADER_RE.search(text)
    if not header:
        return {}

    # Pull lines from the header until the first blank or non-table line
    lines = text[header.start() :].splitlines()
    # Skip header + separator (first 2 lines)
    data_lines = []
    for line in lines[2:]:
        if not line.startswith("|"):
            break
        data_lines.append(line)

    out: dict[str, list[dict]] = {}
    for line in data_lines:
        m = ROW_RE.match(line)
        if not m:
            continue
        name, fmp_cell, finviz_cell, alpaca_cell, notes = m.groups()
        skill_id = display_name_to_id(name)

        integrations: list[dict] = []
        fmp = cell_to_requirement(fmp_cell)
        if fmp:
            integrations.append(
                {
                    "id": "fmp",
                    "type": "market_data",
                    "requirement": fmp,
                    "note": "Financial Modeling Prep API",
                }
            )
        finviz = cell_to_requirement(finviz_cell)
        if finviz:
            integrations.append(
                {
                    "id": "finviz",
                    "type": "screener",
                    "requirement": finviz,
                    "note": "FINVIZ Elite API",
                }
            )
        alpaca = cell_to_requirement(alpaca_cell)
        if alpaca:
            integrations.append(
                {
                    "id": "alpaca",
                    "type": "broker",
                    "requirement": alpaca,
                    "note": "Alpaca brokerage MCP/API",
                }
            )

        # No paid-API entry → infer from notes column
        if not integrations:
            note_lower = notes.lower()
            if "image" in note_lower:
                integrations.append(
                    {
                        "id": "chart_image",
                        "type": "image",
                        "requirement": "required",
                        "note": "Chart screenshot input",
                    }
                )
            elif "websearch" in note_lower or "webfetch" in note_lower:
                integrations.append(
                    {
                        "id": "websearch",
                        "type": "web",
                        "requirement": "required",
                        "note": "Web search / fetch",
                    }
                )
            elif (
                "calculation" in note_lower or "scoring" in note_lower or "validation" in note_lower
            ):
                integrations.append(
                    {
                        "id": "local_calculation",
                        "type": "calculation",
                        "requirement": "not_required",
                        "note": notes.strip() or "Pure local calculation",
                    }
                )
            elif "user provides" in note_lower or "user-provided" in note_lower:
                integrations.append(
                    {
                        "id": "user_input",
                        "type": "local_file",
                        "requirement": "required",
                        "note": notes.strip() or "User-provided data",
                    }
                )
            else:
                # Unable to infer — flag for review
                integrations.append(
                    {
                        "id": "unknown",
                        "type": "unknown",
                        "requirement": "unknown",
                        "note": f"TODO: review; CLAUDE.md row notes: {notes.strip()}",
                    }
                )

        out[skill_id] = integrations

    return out


# ---------------------------------------------------------------------------
# Main bootstrap
# ---------------------------------------------------------------------------


def build_index(project_root: Path) -> dict[str, Any]:
    skills_dir = project_root / "skills"
    claude_md = project_root / "CLAUDE.md"
    matrix = parse_claude_md_matrix(claude_md) if claude_md.is_file() else {}

    skill_entries: list[dict] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        skill_id = child.name
        text = skill_md.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        description = (fm.get("description") or "").strip().strip("'\"")
        # Truncate long descriptions to a one-sentence summary
        summary = description.split(". ")[0].rstrip(".") + "."
        if len(summary) > 240:
            summary = summary[:237].rstrip() + "..."

        category = guess_category(skill_id) or "meta"

        integrations = matrix.get(skill_id)
        if not integrations:
            if skill_id in KNOWN_PURE_LOCAL:
                integrations = [
                    {
                        "id": "local_calculation",
                        "type": "calculation",
                        "requirement": "not_required",
                        "note": "Pure local calculation",
                    }
                ]
            else:
                integrations = [
                    {
                        "id": "unknown",
                        "type": "unknown",
                        "requirement": "unknown",
                        "note": "TODO: review; not found in CLAUDE.md API matrix",
                    }
                ]

        entry = {
            "id": skill_id,
            "display_name": to_display_name(skill_id),
            "category": category,
            "status": "production",
            "summary": summary,
            "timeframe": "unknown",
            "difficulty": "unknown",
            "integrations": integrations,
            "inputs": [],
            "outputs": [],
            "workflows": [],
        }
        skill_entries.append(entry)

    return {
        "schema_version": 1,
        "categories": [
            "market-regime",
            "core-portfolio",
            "swing-opportunity",
            "trade-planning",
            "trade-memory",
            "strategy-research",
            "advanced-satellite",
            "meta",
        ],
        "skills": skill_entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap skills-index.yaml from skills/*/SKILL.md and CLAUDE.md "
            "(one-time migration helper, NOT a sync tool)."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the repository root (default: cwd)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <project-root>/skills-index.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated YAML to stdout instead of writing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing skills-index.yaml. Required for non-dry runs over an existing file.",
    )
    args = parser.parse_args(argv)

    output = args.output or (args.project_root / "skills-index.yaml")
    if not args.dry_run and output.exists() and not args.force:
        print(
            f"ERROR: {output} already exists. Pass --force to overwrite, "
            "or --dry-run to preview without writing.",
            file=sys.stderr,
        )
        return 2

    index = build_index(args.project_root)
    rendered = yaml.safe_dump(index, sort_keys=False, allow_unicode=True, width=100)

    if args.dry_run:
        sys.stdout.write(rendered)
        return 0

    output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output} ({len(index['skills'])} skills).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
