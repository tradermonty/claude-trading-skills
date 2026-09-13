"""Tests for scripts/generate_quality_dashboard.py.

Verify the dashboard generator produces stable, schema-aware output built
only from committed artifacts, renders runtime metrics as "not yet measured"
rather than omitting them, and that --check correctly detects drift.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_quality_dashboard import (  # noqa: E402
    NOT_YET_MEASURED,
    compute_metrics,
    load_snapshot,
    main,
    render_page,
)

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

INDEX_YAML = """\
schema_version: 1
skills:
- id: alpha
  display_name: Alpha
  category: market-regime
  status: production
  integrations:
  - id: fmp
    type: api
    requirement: required
- id: beta-skill
  display_name: Beta Skill
  category: market-regime
  status: beta
  integrations:
  - id: finviz
    type: api
    requirement: recommended
- id: meta-skill
  display_name: Meta Skill
  category: market-regime
  status: production
  knowledge_only: true
  integrations: []
"""

POLICY_YAML = """\
schema_version: 1
aggregate_coverage:
  target: 75
  waiver:
    floor: 72
    target: 75
    expires_on: "2026-10-31"
    issue: 293
coverage:
  default_target: 70
allowed_failures: {}
"""

REPLAY_YAML = """\
schema_version: 1
covered:
  a:
    spec: a/replay.yaml
    variants:
    - required-only
  b:
    spec: b/replay.yaml
    variants:
    - full-path
deferred:
  c:
    issue: 294
    reason: Test deferral.
"""

SNAPSHOT_JSON = """\
{
  "schema_version": 1,
  "as_of": "2026-09-12T00:00:00Z",
  "per_skill_coverage_pct": { "alpha": 78.4 },
  "beta_since": { "beta-skill": "2026-01-10" },
  "dual_axis_score_distribution": "not-yet-measured",
  "open_high_severity_issues": "not-yet-measured",
  "last_successful_ci_timestamp": "not-yet-measured",
  "drift_status": { "package": "clean", "docs": "clean", "navigator": "clean" }
}
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_project(root: Path, *, snapshot: bool = False, has_alpha_tests: bool = True) -> Path:
    """Create a minimal project tree and return the project root."""
    for rel, content in (
        ("skills-index.yaml", INDEX_YAML),
        ("config/ci-test-policy.yaml", POLICY_YAML),
        ("examples/workflows/replay-coverage.yaml", REPLAY_YAML),
    ):
        _write(root / rel, content)

    if has_alpha_tests:
        _write(
            root / "skills/alpha/scripts/tests/test_alpha.py",
            "def test_alpha():\n    assert True\n",
        )
    if snapshot:
        _write(root / "docs/assets/quality-dashboard-sources.json", SNAPSHOT_JSON)
    return root


# ---------------------------------------------------------------------------
# Loaders / metrics
# ---------------------------------------------------------------------------


def test_load_snapshot_returns_empty_dict_when_missing(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert load_snapshot(root) == {}


def test_load_snapshot_parses_values(tmp_path: Path) -> None:
    root = make_project(tmp_path, snapshot=True)
    snap = load_snapshot(root)
    assert snap["as_of"] == "2026-09-12T00:00:00Z"
    assert snap["per_skill_coverage_pct"]["alpha"] == 78.4
    assert snap["drift_status"]["package"] == "clean"


def test_compute_metrics_counts_lifecycle_and_executable(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    assert m["total_skills"] == 3
    assert m["production"] == 2
    assert m["beta"] == 1
    assert m["knowledge_only"] == 1
    assert m["executable"] == 2
    assert m["executable_with_tests"] == 1
    assert m["executable_without_tests"] == 1


def test_compute_metrics_provider_counts(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    assert m["provider_counts"] == {
        "fmp": 1,
        "finviz": 1,
        "alpaca": 0,
        "other_external": 0,
        "offline": 1,
    }


def test_compute_metrics_replay_coverage(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    assert m["replay_workflows_total"] == 3
    assert m["replay_workflows_covered"] == 2


def test_compute_metrics_allowed_failures_from_policy(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    assert m["allowed_failures_count"] == 0
    assert m["aggregate_coverage_target"] == 75
    assert m["aggregate_coverage_floor"] == 72


def test_missing_aggregate_metrics_render_not_yet_measured(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    _write(root / "config/ci-test-policy.yaml", "allowed_failures: {}\n")
    m = compute_metrics(root)
    assert m["aggregate_coverage_target"] is None
    assert m["aggregate_coverage_floor"] is None
    page = render_page(m, "en")
    assert "not yet measured" in page
    assert "None%" not in page


def test_render_page_has_single_trailing_newline(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    page = render_page(m, "en")
    assert page.endswith("\n")
    assert not page.endswith("\n\n")


# ---------------------------------------------------------------------------
# "not yet measured" fallback
# ---------------------------------------------------------------------------


def test_unknown_metrics_render_not_yet_measured_never_omitted(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    page = render_page(m, "en")
    assert "not yet measured" in page
    assert NOT_YET_MEASURED in page
    for label in (
        "Snapshot as of:",
        "Dual-axis score distribution",
        "Open high-severity issues",
        "Last successful CI",
        "Package drift",
        "Docs drift",
        "Navigator drift",
    ):
        assert label in page


def test_snapshot_metrics_render_values(tmp_path: Path) -> None:
    root = make_project(tmp_path, snapshot=True)
    m = compute_metrics(root)
    assert m["as_of"] == "2026-09-12T00:00:00Z"
    assert m["per_skill_coverage"]["alpha"] == 78.4
    assert m["days_in_beta"]["beta-skill"] == 245
    assert m["drift_status"]["package"] == "clean"

    page = render_page(m, "en")
    assert "2026-09-12T00:00:00Z" in page
    assert "78.4%" in page
    assert "day".lower() in page.lower()
    assert "clean" in page


# ---------------------------------------------------------------------------
# Rendering — content
# ---------------------------------------------------------------------------


def test_provider_counts_split_external_from_offline(tmp_path: Path) -> None:
    """A skill using an external source other than FMP/FINVIZ/Alpaca (e.g.
    CoinGecko or WebSearch) must count as "other external", not "offline".
    Only skills with no external data source may count as offline."""
    custom_index = """\
schema_version: 1
skills:
- id: ext-coingecko
  display_name: Ext CoinGecko
  category: market-regime
  status: production
  integrations:
  - id: coingecko
    type: market_data
    requirement: required
- id: ext-websearch
  display_name: Ext WebSearch
  category: market-regime
  status: production
  integrations:
  - id: websearch
    type: web
    requirement: optional
- id: offline-calc
  display_name: Offline Calc
  category: market-regime
  status: production
  integrations:
  - id: local_calculation
    type: calculation
    requirement: not_required
- id: paid-fmp
  display_name: Paid FMP
  category: market-regime
  status: production
  integrations:
  - id: fmp
    type: api
    requirement: required
"""
    root = make_project(tmp_path)
    _write(root / "skills-index.yaml", custom_index)
    m = compute_metrics(root)
    assert m["provider_counts"]["fmp"] == 1
    assert m["provider_counts"]["finviz"] == 0
    assert m["provider_counts"]["alpaca"] == 0
    assert m["provider_counts"]["other_external"] == 2
    assert m["provider_counts"]["offline"] == 1


def test_public_csv_counts_as_external(tmp_path: Path) -> None:
    """A skill that fetches a public CSV over the network (public_csv, type web)
    must count as an external provider, never as offline."""
    custom_index = """\
schema_version: 1
skills:
- id: breadth
  display_name: Breadth
  category: market-regime
  status: production
  integrations:
  - id: public_csv
    type: web
    requirement: required
    note: TraderMonty public CSV; no API key required
- id: pure-math
  display_name: Pure Math
  category: market-regime
  status: production
  integrations:
  - id: local_calculation
    type: calculation
    requirement: not_required
"""
    root = make_project(tmp_path)
    _write(root / "skills-index.yaml", custom_index)
    m = compute_metrics(root)
    assert m["provider_counts"]["other_external"] == 1
    assert m["provider_counts"]["offline"] == 1
    assert m["provider_counts"]["fmp"] == 0


def test_render_english_includes_summary_and_skill_table(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    page = render_page(m, "en")
    assert "## Lifecycle" in page
    assert "## Test coverage" in page
    assert "## End-to-end replay" in page
    assert "## Dependencies" in page
    assert "## Per-skill status" in page
    assert "`alpha`" in page
    assert "production" in page
    assert "beta" in page


def test_render_japanese_frontmatter_and_labels(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    page = render_page(m, "ja")
    assert "parent: 日本語" in page
    assert "nav_order: 3" in page
    assert "permalink: /ja/quality-dashboard/" in page
    assert "lang_peer: /en/quality-dashboard/" in page
    assert "本セクションは" in page
    assert "ライフサイクル" in page
    assert "テストカバレッジ" in page
    assert "依存関係" in page
    assert "Alpha" in page
    assert "production" not in page.replace("`production`", "").replace("production ", "")


def test_render_english_frontmatter(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    page = render_page(m, "en")
    assert "parent: English" in page
    assert "nav_order: 3" in page
    assert "permalink: /en/quality-dashboard/" in page
    assert "lang_peer: /ja/quality-dashboard/" in page
    assert "generated: true" in page


def test_render_metadata_never_omits_absolute_path(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    m = compute_metrics(root)
    for page in (render_page(m, "en"), render_page(m, "ja")):
        assert "/Users/" not in page


# ---------------------------------------------------------------------------
# CLI / drift
# ---------------------------------------------------------------------------


def _run_main(root: Path, *, check: bool = False) -> int:
    args = ["--project-root", str(root)]
    if check:
        args.append("--check")
    return main(args)


def test_main_generates_both_pages(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    rc = _run_main(root)
    assert rc == 0
    assert (root / "docs/en/quality-dashboard.md").is_file()
    assert (root / "docs/ja/quality-dashboard.md").is_file()


def test_check_passes_when_files_match(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert _run_main(root) == 0
    assert _run_main(root, check=True) == 0


def test_check_fails_when_files_drift(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    _run_main(root)
    (root / "docs/en/quality-dashboard.md").write_text(
        "intentionally wrong content", encoding="utf-8"
    )
    assert _run_main(root, check=True) == 1


def test_check_fails_when_target_missing(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert _run_main(root, check=True) == 1


# ---------------------------------------------------------------------------
# Determinism / date-leak resistance
# ---------------------------------------------------------------------------


def test_regeneration_is_byte_stable(tmp_path: Path) -> None:
    root = make_project(tmp_path, snapshot=True)
    _run_main(root)
    en1 = (root / "docs/en/quality-dashboard.md").read_text(encoding="utf-8")
    _run_main(root)
    en2 = (root / "docs/en/quality-dashboard.md").read_text(encoding="utf-8")
    assert en1 == en2


def test_page_does_not_leak_system_date(tmp_path: Path) -> None:
    """The page must never embed the machine's current date (date.today() leak)."""
    root = make_project(tmp_path, snapshot=True)
    # Use a snapshot as_of far from the system date so a leaked date.today()
    # would be detectable (the default 2026-09-12 coincides with the env date).
    snap = root / "docs/assets/quality-dashboard-sources.json"
    snap.write_text(
        SNAPSHOT_JSON.replace("2026-09-12T00:00:00Z", "2040-06-15T00:00:00Z"),
        encoding="utf-8",
    )
    _run_main(root)
    page = (root / "docs/en/quality-dashboard.md").read_text(encoding="utf-8")
    assert "2040-06-15T00:00:00Z" in page
    assert date.today().isoformat() not in page


def test_distinct_snapshot_dates_recompute_days_in_beta_only(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path, snapshot=True)
    _run_main(root)

    snap = root / "docs/assets/quality-dashboard-sources.json"
    snap.write_text(
        SNAPSHOT_JSON.replace("2026-09-12T00:00:00Z", "2026-09-19T00:00:00Z"),
        encoding="utf-8",
    )
    _run_main(root)
    page = (root / "docs/en/quality-dashboard.md").read_text(encoding="utf-8")
    # Deterministic sections must be unchanged; only the as_of label and the
    # diff-derived metric reflect the new snapshot date.
    assert "2026-09-19T00:00:00Z" in page
    assert "2026-09-12T00:00:00Z" not in page


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
