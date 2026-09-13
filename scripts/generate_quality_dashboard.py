"""Generate `docs/en/quality-dashboard.md` and `docs/ja/quality-dashboard.md`.

The dashboard summarises the catalog's quality posture for the docs site. It
must read **only committed artifacts** so regeneration is deterministic in CI;
runtime/CI-derived metrics resolve from the committed snapshot
`docs/assets/quality-dashboard-sources.json`, and anything the snapshot does not
carry renders as the canonical string "not-yet-measured" rather than being
omitted.

Usage:
    python3 scripts/generate_quality_dashboard.py            # regenerate both pages
    python3 scripts/generate_quality_dashboard.py --check    # drift gate (exit 1 on drift)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from generate_catalog_from_index import _find_integration

NOT_YET_MEASURED = "not-yet-measured"

DEFAULT_SNAPSHOT_PATH = "docs/assets/quality-dashboard-sources.json"
PROVIDERS = ("fmp", "finviz", "alpaca")
# Mirror generate_catalog_from_index.py semantics: an integration that is
# listed but `not_required` is shown as "Not used" in the catalog, so it must
# not count as a provider dependency here.
USED_REQUIREMENTS = frozenset({"required", "recommended", "optional"})


# ---------------------------------------------------------------------------
# Input loaders (committed artifacts only)
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_index(project_root: Path) -> dict[str, Any]:
    return _read_yaml(project_root / "skills-index.yaml")


def load_policy(project_root: Path) -> dict[str, Any]:
    return _read_yaml(project_root / "config/ci-test-policy.yaml")


def load_replay_coverage(project_root: Path) -> dict[str, Any]:
    return _read_yaml(project_root / "examples/workflows/replay-coverage.yaml")


def load_snapshot(project_root: Path) -> dict[str, Any]:
    path = project_root / DEFAULT_SNAPSHOT_PATH
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def _parse_date(value: Any) -> date | None:
    """Parse an ISO date/datetime into a date; return None when not parseable."""
    if not isinstance(value, str):
        return None
    head = value[:10]
    if len(head) != 10 or head[4] != "-" or head[7] != "-":
        return None
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def _has_tests(project_root: Path, skill_id: str) -> bool:
    tests_dir = project_root / "skills" / skill_id / "scripts" / "tests"
    if not tests_dir.is_dir():
        return False
    return any(p.suffix == ".py" for p in tests_dir.iterdir())


def compute_metrics(project_root: Path) -> dict[str, Any]:
    """Return all dashboard metrics, resolved from committed sources + snapshot."""
    index = load_index(project_root)
    policy = load_policy(project_root)
    replay = load_replay_coverage(project_root)
    snapshot = load_snapshot(project_root)

    skills = index.get("skills") or []

    production = sum(1 for s in skills if s.get("status") == "production")
    beta = sum(1 for s in skills if s.get("status") == "beta")
    other_status = len(skills) - production - beta
    knowledge_only = sum(1 for s in skills if s.get("knowledge_only") is True)
    executable = len(skills) - knowledge_only

    has_tests_map = {
        s.get("id", ""): _has_tests(project_root, s.get("id", ""))
        for s in skills
        if s.get("knowledge_only") is not True
    }
    executable_with_tests = sum(1 for v in has_tests_map.values() if v)
    executable_without_tests = executable - executable_with_tests

    provider_counts = {"fmp": 0, "finviz": 0, "alpaca": 0, "none": 0}
    for s in skills:
        uses_any = False
        for p in PROVIDERS:
            entry = _find_integration(s, p)
            if entry is not None and entry.get("requirement", "unknown") in USED_REQUIREMENTS:
                provider_counts[p] += 1
                uses_any = True
        if not uses_any:
            provider_counts["none"] += 1

    covered = replay.get("covered") or {}
    deferred = replay.get("deferred") or {}
    replay_total = len(covered) + len(deferred)
    replay_covered = len(covered)

    allowed_failures = policy.get("allowed_failures") or {}
    agg = policy.get("aggregate_coverage") or {}
    agg_target = agg.get("target")
    agg_floor = (agg.get("waiver") or {}).get("floor")

    as_of = snapshot.get("as_of", NOT_YET_MEASURED)
    as_of_date = _parse_date(as_of)

    per_skill_coverage = snapshot.get("per_skill_coverage_pct") or {}
    beta_since_raw = snapshot.get("beta_since") or {}

    days_in_beta: dict[str, Any] = {}
    for s in skills:
        sid = s.get("id", "")
        if s.get("status") != "beta":
            continue
        since = beta_since_raw.get(sid)
        since_date = _parse_date(since)
        if as_of_date is not None and since_date is not None:
            days_in_beta[sid] = (as_of_date - since_date).days
        else:
            days_in_beta[sid] = NOT_YET_MEASURED

    def snapshot_value(key: str) -> Any:
        if key in snapshot:
            return snapshot[key]
        return NOT_YET_MEASURED

    drift = snapshot.get("drift_status") or {}

    skills_meta = []
    for s in skills:
        sid = s.get("id", "")
        is_knowledge = s.get("knowledge_only") is True
        skills_meta.append(
            {
                "id": sid,
                "display_name": s.get("display_name", sid),
                "status": s.get("status", ""),
                "knowledge_only": is_knowledge,
                "has_tests": has_tests_map.get(sid, False),
            }
        )

    return {
        "as_of": as_of,
        "skills_meta": skills_meta,
        "total_skills": len(skills),
        "production": production,
        "beta": beta,
        "other_status": other_status,
        "knowledge_only": knowledge_only,
        "executable": executable,
        "executable_with_tests": executable_with_tests,
        "executable_without_tests": executable_without_tests,
        "has_tests": has_tests_map,
        "provider_counts": provider_counts,
        "replay_workflows_total": replay_total,
        "replay_workflows_covered": replay_covered,
        "replay_deferred_count": len(deferred),
        "allowed_failures_count": len(allowed_failures),
        "aggregate_coverage_target": agg_target,
        "aggregate_coverage_floor": agg_floor,
        "per_skill_coverage": per_skill_coverage,
        "days_in_beta": days_in_beta,
        "dual_axis_score_distribution": snapshot_value("dual_axis_score_distribution"),
        "open_high_severity_issues": snapshot_value("open_high_severity_issues"),
        "last_successful_ci_timestamp": snapshot_value("last_successful_ci_timestamp"),
        "drift_status": {
            "package": drift.get("package", NOT_YET_MEASURED),
            "docs": drift.get("docs", NOT_YET_MEASURED),
            "navigator": drift.get("navigator", NOT_YET_MEASURED),
        },
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt_pct(value: Any) -> str:
    if value is NOT_YET_MEASURED or value is None or not isinstance(value, (int, float)):
        return "not yet measured"
    return f"{value:.1f}%"


def _fmt_days(value: Any) -> str:
    if value is NOT_YET_MEASURED or value is None or not isinstance(value, (int, float)):
        return "not yet measured"
    return f"{value} days"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _frontmatter(lang: str) -> str:
    if lang == "en":
        return (
            "---\n"
            "layout: page\n"
            "parent: English\n"
            "title: Quality Dashboard\n"
            "nav_order: 3\n"
            "permalink: /en/quality-dashboard/\n"
            "lang_peer: /ja/quality-dashboard/\n"
            "generated: true\n"
            "---\n"
        )
    return (
        "---\n"
        "layout: page\n"
        "parent: 日本語\n"
        "title: 品質ダッシュボード\n"
        "nav_order: 3\n"
        "permalink: /ja/quality-dashboard/\n"
        "lang_peer: /en/quality-dashboard/\n"
        "generated: true\n"
        "---\n"
    )


L = {
    "en": {
        "title": "Quality Dashboard",
        "notice": "Auto-generated by `scripts/generate_quality_dashboard.py`. Do not edit by hand.",
        "as_of": "Snapshot as of:",
        "lifecycle": "Lifecycle",
        "coverage": "Test coverage",
        "replay": "End-to-end replay",
        "deps": "Dependencies",
        "beta_pipeline": "Beta pipeline",
        "per_skill": "Per-skill status",
        "runtime": "Runtime metrics (snapshot)",
        "total": "Total",
        "production": "production",
        "beta": "beta",
        "knowledge_only": "Knowledge-only",
        "executable": "Executable",
        "with_tests": "With tests",
        "without_tests": "Without tests",
        "agg_target": "Aggregate coverage target",
        "agg_floor": "Aggregate coverage floor",
        "agg_waiver": "Aggregate waiver floor",
        "allowed_failures": "Allowed failures",
        "target_zero": "target 0",
        "covered_workflows": "Workflows covered by E2E replay",
        "provider": "Provider",
        "count": "Count",
        "none_provider": "none (offline / pure calculation)",
        "beta_skill": "Skill",
        "beta_days": "Days in beta",
        "skill": "Skill",
        "status": "Status",
        "exec_col": "Executable",
        "tests_col": "Tests",
        "coverage_col": "Coverage",
        "yes": "yes",
        "no": "no",
        "other": "other",
        "metric": "Metric",
        "value": "Value",
        "dual_axis": "Dual-axis score distribution",
        "issues": "Open high-severity issues",
        "last_ci": "Last successful CI",
        "pkg_drift": "Package drift",
        "docs_drift": "Docs drift",
        "nav_drift": "Navigator drift",
    },
    "ja": {
        "title": "品質ダッシュボード",
        "notice": "本セクションは `scripts/generate_quality_dashboard.py` により自動生成されます。手動編集しないでください。",
        "as_of": "スナップショット基準日:",
        "lifecycle": "ライフサイクル",
        "coverage": "テストカバレッジ",
        "replay": "E2E リプレイ",
        "deps": "依存関係",
        "beta_pipeline": "ベータパイプライン",
        "per_skill": "スキル別ステータス",
        "runtime": "ランタイム指標（スナップショット）",
        "total": "合計",
        "production": "本番",
        "beta": "ベータ",
        "knowledge_only": "知識のみ",
        "executable": "実行可能",
        "with_tests": "テストあり",
        "without_tests": "テストなし",
        "agg_target": "全体カバレッジ目標",
        "agg_floor": "全体カバレッジ下限",
        "agg_waiver": "全体カバレッジ免除下限",
        "allowed_failures": "許容失敗",
        "target_zero": "目標 0",
        "covered_workflows": "E2E リプレイでカバーされたワークフロー",
        "provider": "プロバイダ",
        "count": "件数",
        "none_provider": "なし（オフライン / 純粋計算）",
        "beta_skill": "スキル",
        "beta_days": "ベータ経過日数",
        "skill": "スキル",
        "status": "ステータス",
        "exec_col": "実行可能",
        "tests_col": "テスト",
        "coverage_col": "カバレッジ",
        "yes": "はい",
        "no": "いいえ",
        "other": "その他",
        "metric": "指標",
        "value": "値",
        "dual_axis": "Dual-axis スコア分布",
        "issues": "高深刻度の未解決 Issue",
        "last_ci": "直近の成功 CI",
        "pkg_drift": "パッケージ差分",
        "docs_drift": "ドキュメント差分",
        "nav_drift": "ナビゲータ差分",
    },
}


def render_page(metrics: dict[str, Any], lang: str) -> str:
    t = L[lang]
    buf: list[str] = []
    buf.append(_frontmatter(lang))
    buf.append("")
    buf.append(f"# {t['title']}")
    buf.append("")
    buf.append(f"> {t['notice']}")
    buf.append("")
    buf.append(f"{t['as_of']} `{_escape(str(metrics['as_of']))}`")
    buf.append("")

    # Lifecycle
    buf.append(f"## {t['lifecycle']}")
    buf.append("")
    buf.append(
        "| {total} | {production} | {beta} | {knowledge_only} | {executable} | {with_tests} | {without_tests} |".format(
            total=t["total"],
            production=t["production"],
            beta=t["beta"],
            knowledge_only=t["knowledge_only"],
            executable=t["executable"],
            with_tests=t["with_tests"],
            without_tests=t["without_tests"],
        )
    )
    buf.append("|---:|---:|---:|---:|---:|---:|---:|")
    buf.append(
        "| {total} | {production} | {beta} | {knowledge_only} | {executable} | {with_tests} | {without_tests} |".format(
            total=metrics["total_skills"],
            production=metrics["production"],
            beta=metrics["beta"],
            knowledge_only=metrics["knowledge_only"],
            executable=metrics["executable"],
            with_tests=metrics["executable_with_tests"],
            without_tests=metrics["executable_without_tests"],
        )
    )
    buf.append("")

    # Test coverage
    buf.append(f"## {t['coverage']}")
    buf.append("")
    buf.append(f"- {t['agg_target']}: {_fmt_pct(metrics['aggregate_coverage_target'])}")
    buf.append(f"- {t['agg_floor']}: {_fmt_pct(metrics['aggregate_coverage_floor'])}")
    buf.append(
        f"- {t['allowed_failures']}: {metrics['allowed_failures_count']} ({t['target_zero']})"
    )
    buf.append("")

    # End-to-end replay
    buf.append(f"## {t['replay']}")
    buf.append("")
    buf.append(
        f"- {t['covered_workflows']}: "
        f"{metrics['replay_workflows_covered']} / {metrics['replay_workflows_total']}"
    )
    buf.append("")

    # Dependencies
    buf.append(f"## {t['deps']}")
    buf.append("")
    buf.append(f"| {t['provider']} | {t['count']} |")
    buf.append("|---|---:|")
    for p in PROVIDERS:
        buf.append(f"| {p.upper()} | {metrics['provider_counts'][p]} |")
    buf.append(f"| {t['none_provider']} | {metrics['provider_counts']['none']} |")
    buf.append("")

    # Beta pipeline
    buf.append(f"## {t['beta_pipeline']}")
    buf.append("")
    buf.append(f"| {t['beta_skill']} | {t['beta_days']} |")
    buf.append("|---|---:|")
    beta_days = metrics["days_in_beta"]
    for sid, days in sorted(beta_days.items()):
        buf.append(f"| `{sid}` | {_fmt_days(days)} |")
    buf.append("")

    # Per-skill status
    buf.append(f"## {t['per_skill']}")
    buf.append("")
    buf.append(
        "| {skill} | {status} | {exec_col} | {tests_col} | {coverage_col} |".format(
            skill=t["skill"],
            status=t["status"],
            exec_col=t["exec_col"],
            tests_col=t["tests_col"],
            coverage_col=t["coverage_col"],
        )
    )
    buf.append("|---|---|---|---|---|")
    for row in sorted(metrics["skills_meta"], key=lambda r: r["id"]):
        coverage = _fmt_pct(metrics["per_skill_coverage"].get(row["id"], NOT_YET_MEASURED))
        status = row["status"]
        if status == "production":
            status_disp = t["production"]
        elif status == "beta":
            status_disp = t["beta"]
        else:
            status_disp = f"{t['other']} ({status})"
        exec_disp = t["no"] if row["knowledge_only"] else t["yes"]
        test_disp = t["yes"] if row["has_tests"] else t["no"]
        name = _escape(row["display_name"])
        buf.append(
            f"| **{name}** (`{row['id']}`) | {status_disp} | {exec_disp} | {test_disp} | {coverage} |"
        )
    buf.append("")

    # Runtime metrics
    buf.append(f"## {t['runtime']}")
    buf.append("")
    buf.append(f"| {t['metric']} | {t['value']} |")
    buf.append("|---|---|")
    rows = [
        (t["as_of"], metrics["as_of"]),
        (t["dual_axis"], metrics["dual_axis_score_distribution"]),
        (t["issues"], metrics["open_high_severity_issues"]),
        (t["last_ci"], metrics["last_successful_ci_timestamp"]),
        (t["pkg_drift"], metrics["drift_status"]["package"]),
        (t["docs_drift"], metrics["drift_status"]["docs"]),
        (t["nav_drift"], metrics["drift_status"]["navigator"]),
    ]
    for label, value in rows:
        buf.append(f"| {label} | {_escape(str(value))} |")
    buf.append("")

    return "\n".join(buf)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _page_path(project_root: Path, lang: str) -> Path:
    return project_root / "docs" / lang / "quality-dashboard.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the quality dashboard docs pages.")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Repository root (defaults to the repo containing this script).",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "ja", "all"),
        default="all",
        help="Which page(s) to regenerate (default: both).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when the generated content differs from the on-disk pages.",
    )
    args = parser.parse_args(argv)

    root = Path(args.project_root) if args.project_root else Path(__file__).resolve().parents[1]
    if not (root / "skills-index.yaml").exists():
        print(f"error: skills-index.yaml not found under {root}", file=sys.stderr)
        return 1

    metrics = compute_metrics(root)
    langs = ("en", "ja") if args.lang == "all" else (args.lang,)

    drift: list[str] = []
    for lang in langs:
        # Normalize to exactly one trailing newline so the on-disk page matches
        # the generator output byte-for-byte (end-of-file-fixer strips extras).
        page = render_page(metrics, lang).rstrip("\n") + "\n"
        path = _page_path(root, lang)
        if args.check:
            if not path.exists():
                print(f"error: missing generated page: {path}", file=sys.stderr)
                drift.append(str(path))
            elif path.read_text(encoding="utf-8") != page:
                print(f"error: drift detected in {path}", file=sys.stderr)
                drift.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page, encoding="utf-8")

    if drift:
        return 1
    if args.check:
        print("quality-dashboard: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
