#!/usr/bin/env python3
"""Regenerate README catalog sections from skills-index.yaml.

The generator rewrites ONLY the content between paired sentinel comments:

    <!-- skills-index:start name="catalog-en" -->
    ...generated content...
    <!-- skills-index:end name="catalog-en" -->

Anything outside the markers is untouched. Each marker pair maps to one
region renderer keyed by `name`. Currently:

    catalog-en  → README.md  Detailed Skill Catalog (English)
    catalog-ja  → README.ja.md Detailed Skill Catalog (Japanese)

Idempotent — same input always produces byte-identical output. Use
`--check` to detect drift in CI.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Sentinels
# ---------------------------------------------------------------------------

SENTINEL_RE = re.compile(
    r'(<!-- skills-index:start name="([^"]+)" -->\n)(.*?)(\n<!-- skills-index:end name="\2" -->)',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Localized labels
# ---------------------------------------------------------------------------

CATEGORY_LABELS_EN = {
    "market-regime": "Market Regime",
    "core-portfolio": "Core Portfolio",
    "swing-opportunity": "Swing Opportunity",
    "trade-planning": "Trade Planning",
    "trade-memory": "Trade Memory",
    "strategy-research": "Strategy Research",
    "advanced-satellite": "Advanced Satellite",
    "meta": "Meta / Development Tooling",
}

CATEGORY_LABELS_JA = {
    "market-regime": "相場環境（Market Regime）",
    "core-portfolio": "コアポートフォリオ（Core Portfolio）",
    "swing-opportunity": "スイング候補（Swing Opportunity）",
    "trade-planning": "トレード計画（Trade Planning）",
    "trade-memory": "トレード記録（Trade Memory）",
    "strategy-research": "戦略リサーチ（Strategy Research）",
    "advanced-satellite": "アドバンスト・サテライト（Advanced Satellite）",
    "meta": "メタ / 開発ツール（Meta）",
}

CATEGORY_LABELS_ZH = {
    "market-regime": "市场环境（Market Regime）",
    "core-portfolio": "核心组合（Core Portfolio）",
    "swing-opportunity": "波段机会（Swing Opportunity）",
    "trade-planning": "交易计划（Trade Planning）",
    "trade-memory": "交易记忆（Trade Memory）",
    "strategy-research": "策略研究（Strategy Research）",
    "advanced-satellite": "进阶卫星（Advanced Satellite）",
    "meta": "元 / 开发工具（Meta）",
}

INTEGRATION_BADGES = {
    "required": "**required**",
    "recommended": "_recommended_",
    "optional": "optional",
    "not_required": "—",
    "unknown": "_unknown_",
}


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------


def load_index(project_root: Path) -> dict[str, Any]:
    path = project_root / "skills-index.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def group_by_category(skills: list[dict]) -> dict[str, list[dict]]:
    """Return {category: [skills sorted by id]}."""
    buckets: dict[str, list[dict]] = {}
    for s in skills:
        cat = s.get("category", "meta")
        buckets.setdefault(cat, []).append(s)
    for items in buckets.values():
        items.sort(key=lambda x: x.get("id", ""))
    return buckets


def _primary_integrations(skill: dict) -> str:
    """Return a one-line summary of the skill's integrations."""
    integs = skill.get("integrations") or []
    if not integs:
        return "—"
    parts = []
    for i in integs:
        iid = i.get("id", "?")
        req = i.get("requirement", "unknown")
        badge = INTEGRATION_BADGES.get(req, req)
        parts.append(f"`{iid}` {badge}")
    return ", ".join(parts)


def _escape_table_cell(text: str) -> str:
    """Escape characters that would break a Markdown table cell.

    Pipes (|) terminate columns and must be backslash-escaped. Newlines
    inside a cell are collapsed to spaces so a multi-line summary does
    not span multiple table rows.
    """
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


# ---------------------------------------------------------------------------
# Rendering — one renderer per `name` sentinel
# ---------------------------------------------------------------------------


def render_catalog_en(skills: list[dict]) -> str:
    buf = io.StringIO()
    buf.write(
        "<!-- This section is auto-generated from skills-index.yaml by "
        "scripts/generate_catalog_from_index.py. Do not edit by hand — "
        "edit the index and re-run the generator. -->\n\n"
    )
    buckets = group_by_category(skills)
    for cat in [
        "market-regime",
        "core-portfolio",
        "swing-opportunity",
        "trade-planning",
        "trade-memory",
        "strategy-research",
        "advanced-satellite",
        "meta",
    ]:
        items = buckets.get(cat, [])
        if not items:
            continue
        buf.write(f"### {CATEGORY_LABELS_EN[cat]}\n\n")
        buf.write("| Skill | Summary | Integrations | Status |\n")
        buf.write("|---|---|---|---|\n")
        for s in items:
            sid = s.get("id", "")
            display_name = _escape_table_cell(s.get("display_name", sid))
            summary = _escape_table_cell(s.get("summary") or "")
            status = _escape_table_cell(s.get("status", ""))
            integs = _primary_integrations(s)
            buf.write(f"| **{display_name}** (`{sid}`) | {summary} | {integs} | {status} |\n")
        buf.write("\n")
    return buf.getvalue().rstrip("\n")


def render_catalog_ja(skills: list[dict]) -> str:
    buf = io.StringIO()
    buf.write(
        "<!-- 本セクションは skills-index.yaml から "
        "scripts/generate_catalog_from_index.py で自動生成されます。"
        "手動編集せず、index を更新して generator を再実行してください。 -->\n\n"
    )
    buckets = group_by_category(skills)
    for cat in [
        "market-regime",
        "core-portfolio",
        "swing-opportunity",
        "trade-planning",
        "trade-memory",
        "strategy-research",
        "advanced-satellite",
        "meta",
    ]:
        items = buckets.get(cat, [])
        if not items:
            continue
        buf.write(f"### {CATEGORY_LABELS_JA[cat]}\n\n")
        buf.write("| スキル | サマリ | 依存 | ステータス |\n")
        buf.write("|---|---|---|---|\n")
        for s in items:
            sid = s.get("id", "")
            display_name = _escape_table_cell(s.get("display_name", sid))
            summary = _escape_table_cell(s.get("summary") or "")
            status = _escape_table_cell(s.get("status", ""))
            integs = _primary_integrations(s)
            buf.write(f"| **{display_name}** (`{sid}`) | {summary} | {integs} | {status} |\n")
        buf.write("\n")
    return buf.getvalue().rstrip("\n")


def render_catalog_zh(skills: list[dict]) -> str:
    buf = io.StringIO()
    buf.write(
        "<!-- 本节由 scripts/generate_catalog_from_index.py 从 skills-index.yaml "
        "自动生成。请勿手动编辑——请修改 index 并重新运行生成器。 -->\n\n"
    )
    buckets = group_by_category(skills)
    for cat in [
        "market-regime",
        "core-portfolio",
        "swing-opportunity",
        "trade-planning",
        "trade-memory",
        "strategy-research",
        "advanced-satellite",
        "meta",
    ]:
        items = buckets.get(cat, [])
        if not items:
            continue
        buf.write(f"### {CATEGORY_LABELS_ZH[cat]}\n\n")
        buf.write("| 技能 | 概要 | 依赖 | 状态 |\n")
        buf.write("|---|---|---|---|\n")
        for s in items:
            sid = s.get("id", "")
            display_name = _escape_table_cell(s.get("display_name", sid))
            summary = _escape_table_cell(s.get("summary") or "")
            status = _escape_table_cell(s.get("status", ""))
            integs = _primary_integrations(s)
            buf.write(f"| **{display_name}** (`{sid}`) | {summary} | {integs} | {status} |\n")
        buf.write("\n")
    return buf.getvalue().rstrip("\n")


def _find_integration(skill: dict, integration_id: str) -> dict | None:
    """Return the integrations[] entry with id == integration_id, or None."""
    for i in skill.get("integrations") or []:
        if i.get("id") == integration_id:
            return i
    return None


API_MATRIX_CELL_BY_REQUIREMENT = {
    "required": "✅ Required",
    "recommended": "🟡 Optional (Recommended)",
    "optional": "🟡 Optional",
    "not_required": "❌ Not used",
    "unknown": "❓ Unknown",
}


def _api_matrix_cell(skill: dict, integration_id: str) -> str:
    """Render the cell for one paid-API column (FMP/FINVIZ/Alpaca)."""
    entry = _find_integration(skill, integration_id)
    if entry is None:
        return "❌ Not used"
    req = entry.get("requirement", "unknown")
    return API_MATRIX_CELL_BY_REQUIREMENT.get(req, f"❓ {req}")


def _api_matrix_notes(skill: dict) -> str:
    """Build the Notes column.

    Prefer the strongest paid-API integration's `note`. Otherwise list non-paid
    integration ids that explain the skill's data source (csv, image, web, etc.).
    """
    paid_ids = ("fmp", "finviz", "alpaca")
    # Prefer the highest-priority paid integration with a note.
    for iid in paid_ids:
        entry = _find_integration(skill, iid)
        if entry and entry.get("note"):
            return _escape_table_cell(str(entry["note"]))
    # Fallback: combine non-paid integration ids + notes.
    parts = []
    for i in skill.get("integrations") or []:
        if i.get("id") in paid_ids:
            continue
        note = i.get("note") or ""
        if note:
            parts.append(_escape_table_cell(str(note)))
    if parts:
        return "; ".join(parts)
    return "—"


def render_api_matrix(skills: list[dict]) -> str:
    """Render the CLAUDE.md API Requirements by Skill table.

    Preserves the historical 3-column shape (FMP / FINVIZ / Alpaca + Notes) so
    existing setup instructions still apply. Skills are sorted by display_name.
    """
    buf = io.StringIO()
    buf.write(
        "<!-- This table is auto-generated from skills-index.yaml by "
        "scripts/generate_catalog_from_index.py. Do not edit by hand — "
        "edit the index and re-run the generator. -->\n\n"
    )
    buf.write("| Skill | FMP API | FINVIZ Elite | Alpaca | Notes |\n")
    buf.write("|-------|---------|--------------|--------|-------|\n")
    for s in sorted(skills, key=lambda x: x.get("display_name", x.get("id", ""))):
        # Skip deprecated skills from the user-facing API matrix.
        if s.get("status") == "deprecated":
            continue
        display_name = _escape_table_cell(s.get("display_name", s.get("id", "")))
        fmp_cell = _api_matrix_cell(s, "fmp")
        finviz_cell = _api_matrix_cell(s, "finviz")
        alpaca_cell = _api_matrix_cell(s, "alpaca")
        notes = _api_matrix_notes(s)
        buf.write(
            f"| **{display_name}** | {fmp_cell} | {finviz_cell} | {alpaca_cell} | {notes} |\n"
        )
    return buf.getvalue().rstrip("\n")


RENDERERS = {
    "catalog-en": render_catalog_en,
    "catalog-ja": render_catalog_ja,
    "catalog-zh": render_catalog_zh,
    "api-matrix": render_api_matrix,
}


# ---------------------------------------------------------------------------
# File rewriting
# ---------------------------------------------------------------------------


class SentinelError(RuntimeError):
    """Raised when a target file is missing required sentinel markers."""


def rewrite_file(path: Path, skills: list[dict]) -> tuple[str, str]:
    """Return (current, regenerated) so callers can write or compare.

    Raises SentinelError if a sentinel marker references a name without a
    registered renderer, or if any expected renderer name is never found.
    """
    current = path.read_text(encoding="utf-8")
    seen_names: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        opening, name, _body, closing = match.groups()
        if name not in RENDERERS:
            raise SentinelError(f"{path}: sentinel name {name!r} has no registered renderer")
        seen_names.add(name)
        new_body = RENDERERS[name](skills)
        return f"{opening}{new_body}{closing}"

    regenerated = SENTINEL_RE.sub(_replace, current)
    return current, regenerated


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


TARGETS = [
    ("README.md", {"catalog-en"}),
    ("README.ja.md", {"catalog-ja"}),
    ("README.zh.md", {"catalog-zh"}),
    ("CLAUDE.md", {"api-matrix"}),
]


def find_target_paths(project_root: Path) -> list[Path]:
    return [project_root / rel for rel, _names in TARGETS]


def expected_names(project_root: Path, path: Path) -> set[str]:
    rel = path.relative_to(project_root).as_posix()
    for target_rel, names in TARGETS:
        if target_rel == rel:
            return names
    return set()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate README catalog sections from skills-index.yaml."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the repository root (default: cwd)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any target file would change.",
    )
    args = parser.parse_args(argv)

    index = load_index(args.project_root)
    skills = index.get("skills") or []

    drift = False
    for rel, expected in TARGETS:
        path = args.project_root / rel
        if not path.is_file():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 1
        try:
            current, regenerated = rewrite_file(path, skills)
        except SentinelError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        # Verify all expected sentinel names were actually present.
        present = {m.group(2) for m in SENTINEL_RE.finditer(current)}
        missing = expected - present
        if missing:
            print(
                f"ERROR: {path} missing sentinel names: {sorted(missing)}",
                file=sys.stderr,
            )
            return 1

        if args.check:
            if current != regenerated:
                print(f"DRIFT: {path} differs from regenerated output", file=sys.stderr)
                drift = True
            else:
                print(f"OK: {path} matches", file=sys.stderr)
        else:
            if current != regenerated:
                path.write_text(regenerated, encoding="utf-8")
                print(f"Wrote {path}", file=sys.stderr)
            else:
                print(f"Unchanged: {path}", file=sys.stderr)

    return 1 if (args.check and drift) else 0


if __name__ == "__main__":
    raise SystemExit(main())
