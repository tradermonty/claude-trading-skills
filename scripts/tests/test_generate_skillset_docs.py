"""Tests for scripts/generate_skillset_docs.py.

Verify the generator produces stable, schema-aware output and that
--check correctly detects drift. Mirrors test_generate_workflow_docs.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_skillset_docs import (  # noqa: E402
    load_skillsets,
    main,
    render_page,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_skillset(skillsets_dir: Path, ss: dict) -> None:
    ss_id = ss["id"]
    (skillsets_dir / f"{ss_id}.yaml").write_text(
        yaml.safe_dump(ss, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def make_skillset(skillsets_dir: Path, **overrides) -> dict:
    """Create a minimal but complete skillset YAML and return the dict."""
    base = {
        "schema_version": 1,
        "id": "sample-skillset",
        "display_name": "Sample Skillset",
        "category": "sample-skillset",
        "timeframe": "daily",
        "difficulty": "beginner",
        "api_profile": "no-api-basic",
        "target_users": ["part-time-swing-trader"],
        "when_to_use": "When the test demands it.",
        "when_not_to_use": "When you are unsure.",
        "required_skills": ["alpha"],
        "recommended_skills": ["beta"],
        "optional_skills": ["gamma"],
        "related_workflows": ["sample-workflow"],
    }
    base.update(overrides)
    _write_skillset(skillsets_dir, base)
    return base


@pytest.fixture
def skillsets_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skillsets"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_skillsets_returns_sorted_list(skillsets_dir: Path) -> None:
    make_skillset(skillsets_dir, id="zebra")
    make_skillset(skillsets_dir, id="alpha")
    skillsets = load_skillsets(skillsets_dir)
    assert [s["id"] for s in skillsets] == ["alpha", "zebra"]


def test_load_skillsets_skips_files_without_id(skillsets_dir: Path) -> None:
    (skillsets_dir / "broken.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "no_id_here": True}), encoding="utf-8"
    )
    make_skillset(skillsets_dir, id="good")
    skillsets = load_skillsets(skillsets_dir)
    assert [s["id"] for s in skillsets] == ["good"]


def test_load_skillsets_ignores_non_yaml(skillsets_dir: Path) -> None:
    """A README.md alongside the manifests must not be loaded."""
    (skillsets_dir / "README.md").write_text("# Skillsets\n", encoding="utf-8")
    make_skillset(skillsets_dir, id="only")
    skillsets = load_skillsets(skillsets_dir)
    assert [s["id"] for s in skillsets] == ["only"]


# ---------------------------------------------------------------------------
# Render — content checks
# ---------------------------------------------------------------------------


def test_render_includes_summary_table(skillsets_dir: Path) -> None:
    make_skillset(skillsets_dir, id="alpha", timeframe="weekly", api_profile="mixed")
    skillsets = load_skillsets(skillsets_dir)
    page = render_page(skillsets, "en")
    assert "## Available skillsets" in page
    assert "`alpha`" in page
    assert "weekly" in page
    assert "mixed" in page
    # Anchor link present
    assert "[`alpha`](#alpha)" in page


def test_render_includes_when_to_use_and_target_users(skillsets_dir: Path) -> None:
    make_skillset(
        skillsets_dir,
        id="meta-test",
        when_to_use="Use it in spring.",
        when_not_to_use="Never in winter.",
        target_users=["growth-investor", "long-term-investor"],
    )
    skillsets = load_skillsets(skillsets_dir)
    page = render_page(skillsets, "en")
    assert "**When to use:** Use it in spring." in page
    assert "**When NOT to use:** Never in winter." in page
    assert "**Target users:** `growth-investor`, `long-term-investor`" in page


def test_render_skill_lists(skillsets_dir: Path) -> None:
    """Required present; empty recommended still prints heading with (none)."""
    make_skillset(
        skillsets_dir,
        id="lists-test",
        required_skills=["alpha", "beta"],
        recommended_skills=[],
        optional_skills=["gamma"],
    )
    skillsets = load_skillsets(skillsets_dir)
    page = render_page(skillsets, "en")
    assert "**Required skills:** `alpha`, `beta`" in page
    assert "**Recommended skills:** (none)" in page
    assert "**Optional skills:** `gamma`" in page


def test_render_japanese_uses_japanese_labels(skillsets_dir: Path) -> None:
    make_skillset(skillsets_dir, id="ja-test")
    skillsets = load_skillsets(skillsets_dir)
    page = render_page(skillsets, "ja")
    # Page title and frontmatter
    assert "title: スキルセット" in page
    assert "# スキルセット" in page
    # Localized section headings
    assert "使用するとき" in page
    assert "必須スキル" in page
    assert "対象ユーザー" in page
    assert "関連ワークフロー" in page


def test_render_collapses_folded_scalar(skillsets_dir: Path) -> None:
    """A multiline (YAML >- folded) when_to_use must render on one line so the
    markdown does not break (the scenario-analyzer table-break hazard)."""
    make_skillset(
        skillsets_dir,
        id="folded",
        when_to_use="First line\nsecond line\nthird line",
    )
    skillsets = load_skillsets(skillsets_dir)
    page = render_page(skillsets, "en")
    assert "**When to use:** First line second line third line" in page
    # No raw newline survived inside the rendered value
    assert "First line\nsecond" not in page


def test_render_related_workflows_multiple(skillsets_dir: Path) -> None:
    make_skillset(
        skillsets_dir,
        id="multi-wf",
        related_workflows=["wf-a", "wf-b"],
    )
    skillsets = load_skillsets(skillsets_dir)
    page = render_page(skillsets, "en")
    assert "**Related workflows:** `wf-a`, `wf-b`" in page
    # Summary table also lists both
    assert "`wf-a`, `wf-b`" in page


# ---------------------------------------------------------------------------
# Idempotency / drift
# ---------------------------------------------------------------------------


def test_render_is_idempotent(skillsets_dir: Path) -> None:
    make_skillset(skillsets_dir, id="alpha")
    make_skillset(skillsets_dir, id="beta")
    skillsets = load_skillsets(skillsets_dir)
    a = render_page(skillsets, "en")
    b = render_page(skillsets, "en")
    assert a == b
    # Ends with exactly one trailing newline (end-of-file-fixer lockstep)
    assert a.endswith("\n")
    assert not a.endswith("\n\n")


def test_check_mode_passes_when_files_match(tmp_path: Path) -> None:
    """End-to-end: write files then re-run with --check; should exit 0."""
    skillsets_dir = tmp_path / "skillsets"
    skillsets_dir.mkdir()
    make_skillset(skillsets_dir, id="alpha")

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert rc == 0
    assert (tmp_path / "out.md").is_file()

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
            "--check",
        ]
    )
    assert rc == 0


def test_check_mode_fails_when_files_drift(tmp_path: Path) -> None:
    skillsets_dir = tmp_path / "skillsets"
    skillsets_dir.mkdir()
    make_skillset(skillsets_dir, id="alpha")

    main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )

    (tmp_path / "out.md").write_text("intentionally wrong content", encoding="utf-8")

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
            "--check",
        ]
    )
    assert rc == 1


def test_check_mode_fails_when_target_missing(tmp_path: Path) -> None:
    skillsets_dir = tmp_path / "skillsets"
    skillsets_dir.mkdir()
    make_skillset(skillsets_dir, id="alpha")

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
            "--check",
        ]
    )
    assert rc == 1


# ---------------------------------------------------------------------------
# CLI argument validation
# ---------------------------------------------------------------------------


def test_main_rejects_output_with_lang_all(tmp_path: Path) -> None:
    skillsets_dir = tmp_path / "skillsets"
    skillsets_dir.mkdir()
    make_skillset(skillsets_dir, id="alpha")

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "all",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert rc == 2


def test_main_fails_when_skillsets_dir_missing(tmp_path: Path) -> None:
    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert rc == 1


def test_main_fails_when_no_manifests(tmp_path: Path) -> None:
    (tmp_path / "skillsets").mkdir()
    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert rc == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
