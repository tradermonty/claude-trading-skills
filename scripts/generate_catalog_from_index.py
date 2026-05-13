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
            display_name = s.get("display_name", sid)
            summary = (s.get("summary") or "").replace("\n", " ").strip()
            status = s.get("status", "")
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
            display_name = s.get("display_name", sid)
            summary = (s.get("summary") or "").replace("\n", " ").strip()
            status = s.get("status", "")
            integs = _primary_integrations(s)
            buf.write(f"| **{display_name}** (`{sid}`) | {summary} | {integs} | {status} |\n")
        buf.write("\n")
    return buf.getvalue().rstrip("\n")


RENDERERS = {
    "catalog-en": render_catalog_en,
    "catalog-ja": render_catalog_ja,
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
