"""Tests for scripts/generate_catalog_from_index.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_catalog_from_index import (  # noqa: E402
    SENTINEL_RE,
    SentinelError,
    main,
    render_api_matrix,
    render_catalog_en,
    render_catalog_ja,
    rewrite_file,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_skill(skill_id: str, category: str = "core-portfolio", **overrides) -> dict:
    base = {
        "id": skill_id,
        "display_name": skill_id.replace("-", " ").title(),
        "category": category,
        "status": "production",
        "summary": f"Summary for {skill_id}.",
        "integrations": [
            {
                "id": "local_calculation",
                "type": "calculation",
                "requirement": "not_required",
            }
        ],
        "timeframe": "weekly",
        "difficulty": "intermediate",
    }
    base.update(overrides)
    return base


def write_minimal_index(project_root: Path, skills: list[dict]) -> None:
    payload = {
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
        "skills": skills,
    }
    (project_root / "skills-index.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def write_readme(project_root: Path, name: str = "README.md", sentinel: str = "catalog-en") -> None:
    body = f"""# Test repo

Some pre-existing content above.

## Detailed Skill Catalog

<!-- skills-index:start name="{sentinel}" -->
PLACEHOLDER — will be regenerated.
<!-- skills-index:end name="{sentinel}" -->

Some pre-existing content below that must remain untouched.
"""
    (project_root / name).write_text(body, encoding="utf-8")


def write_claude_md(project_root: Path) -> None:
    """Create a minimal CLAUDE.md with the api-matrix sentinel."""
    body = """# CLAUDE.md

Some setup text.

#### API Requirements by Skill

<!-- skills-index:start name="api-matrix" -->
PLACEHOLDER — will be regenerated.
<!-- skills-index:end name="api-matrix" -->

More text below the matrix.
"""
    (project_root / "CLAUDE.md").write_text(body, encoding="utf-8")


def write_all_targets(project_root: Path) -> None:
    """Create README.md + README.ja.md + README.zh.md + CLAUDE.md with sentinels."""
    write_readme(project_root, name="README.md", sentinel="catalog-en")
    write_readme(project_root, name="README.ja.md", sentinel="catalog-ja")
    write_readme(project_root, name="README.zh.md", sentinel="catalog-zh")
    write_claude_md(project_root)


# ---------------------------------------------------------------------------
# Renderer content
# ---------------------------------------------------------------------------


def test_render_en_groups_by_category() -> None:
    skills = [
        make_skill("a-skill", category="market-regime"),
        make_skill("b-skill", category="core-portfolio"),
    ]
    out = render_catalog_en(skills)
    assert "### Market Regime" in out
    assert "### Core Portfolio" in out
    assert "`a-skill`" in out
    assert "`b-skill`" in out


def test_render_ja_uses_japanese_headers() -> None:
    skills = [make_skill("a-skill", category="market-regime")]
    out = render_catalog_ja(skills)
    assert "### 相場環境" in out
    assert "サマリ" in out


def test_render_skips_empty_categories() -> None:
    """Only categories with at least one skill are rendered."""
    skills = [make_skill("a-skill", category="market-regime")]
    out = render_catalog_en(skills)
    assert "### Market Regime" in out
    # No other categories should appear since no skills are in them
    assert "### Core Portfolio" not in out
    assert "### Meta" not in out


def test_render_includes_integrations_with_badges() -> None:
    skills = [
        make_skill(
            "a-skill",
            integrations=[
                {"id": "fmp", "type": "market_data", "requirement": "required"},
                {"id": "finviz", "type": "screener", "requirement": "optional"},
            ],
        )
    ]
    out = render_catalog_en(skills)
    assert "`fmp` **required**" in out
    assert "`finviz` optional" in out


def test_render_escapes_pipe_in_summary() -> None:
    """A literal '|' in summary must be backslash-escaped or it breaks the table."""
    skills = [
        make_skill(
            "pipe-skill",
            category="market-regime",
            summary="Use a|b notation to separate options.",
        )
    ]
    out = render_catalog_en(skills)
    # The escaped form must be present
    assert "a\\|b" in out
    # The bare form must NOT survive (would break the table)
    assert "a|b" not in out.replace("a\\|b", "")


def test_render_escapes_newline_in_summary() -> None:
    """Newlines in summary must collapse to spaces so the table row stays on one line."""
    skills = [
        make_skill(
            "nl-skill",
            category="market-regime",
            summary="Line one.\nLine two.",
        )
    ]
    out = render_catalog_en(skills)
    # The row containing this skill must not contain an embedded newline mid-row
    rows = [line for line in out.splitlines() if "nl-skill" in line]
    assert len(rows) == 1
    assert "Line one. Line two." in rows[0]


def test_render_is_deterministic_when_skill_order_varies() -> None:
    """Within a category, skills should be sorted by id."""
    skills = [
        make_skill("zz-skill", category="market-regime"),
        make_skill("aa-skill", category="market-regime"),
    ]
    out = render_catalog_en(skills)
    pos_aa = out.find("aa-skill")
    pos_zz = out.find("zz-skill")
    assert 0 < pos_aa < pos_zz, "aa-skill should appear before zz-skill"


# ---------------------------------------------------------------------------
# API matrix renderer
# ---------------------------------------------------------------------------


def test_render_api_matrix_includes_header_columns() -> None:
    """API matrix must preserve the 3-column FMP/FINVIZ/Alpaca + Notes shape."""
    skills = [make_skill("a-skill")]
    out = render_api_matrix(skills)
    assert "| Skill | FMP API | FINVIZ Elite | Alpaca | Notes |" in out


def test_render_api_matrix_required_recommended_optional() -> None:
    """Requirement values must map to the canonical cell strings."""
    skills = [
        make_skill(
            "fmp-required",
            integrations=[{"id": "fmp", "type": "market_data", "requirement": "required"}],
        ),
        make_skill(
            "finviz-rec",
            integrations=[{"id": "finviz", "type": "screener", "requirement": "recommended"}],
        ),
        make_skill(
            "alpaca-opt",
            integrations=[{"id": "alpaca", "type": "broker", "requirement": "optional"}],
        ),
    ]
    out = render_api_matrix(skills)
    assert "**Fmp Required**" in out  # display_name title-cased from id
    # required maps to ✅ Required
    fmp_row = [line for line in out.splitlines() if "Fmp Required" in line][0]
    assert "✅ Required" in fmp_row
    finviz_row = [line for line in out.splitlines() if "Finviz Rec" in line][0]
    assert "🟡 Optional (Recommended)" in finviz_row
    alpaca_row = [line for line in out.splitlines() if "Alpaca Opt" in line][0]
    # alpaca optional → 🟡 Optional
    assert "🟡 Optional" in alpaca_row
    assert "🟡 Optional (Recommended)" not in alpaca_row


def test_render_api_matrix_absent_integration_renders_not_used() -> None:
    """A skill without FMP/FINVIZ/Alpaca should show ❌ Not used."""
    skills = [
        make_skill(
            "no-paid",
            integrations=[
                {
                    "id": "local_calculation",
                    "type": "calculation",
                    "requirement": "not_required",
                }
            ],
        )
    ]
    out = render_api_matrix(skills)
    row = [line for line in out.splitlines() if "No Paid" in line][0]
    # All three paid columns should be ❌ Not used
    assert row.count("❌ Not used") == 3


def test_render_api_matrix_excludes_deprecated_skills() -> None:
    """Deprecated skills must not appear in the user-facing matrix."""
    skills = [
        make_skill("active-skill"),
        make_skill("dead-skill", status="deprecated"),
    ]
    out = render_api_matrix(skills)
    assert "Active Skill" in out
    assert "Dead Skill" not in out


def test_render_api_matrix_notes_uses_integration_note() -> None:
    skills = [
        make_skill(
            "skill-with-note",
            integrations=[
                {
                    "id": "fmp",
                    "type": "market_data",
                    "requirement": "required",
                    "note": "Specific FMP usage description.",
                }
            ],
        )
    ]
    out = render_api_matrix(skills)
    assert "Specific FMP usage description." in out


def test_render_api_matrix_notes_falls_back_to_other_integrations() -> None:
    """When no paid integration has a note, Notes should describe non-paid ones."""
    skills = [
        make_skill(
            "csv-skill",
            integrations=[
                {
                    "id": "public_csv",
                    "type": "local_file",
                    "requirement": "required",
                    "note": "Public CSV breadth data.",
                }
            ],
        )
    ]
    out = render_api_matrix(skills)
    assert "Public CSV breadth data." in out


def test_render_api_matrix_escapes_pipe_in_notes() -> None:
    skills = [
        make_skill(
            "pipe-note",
            integrations=[
                {
                    "id": "fmp",
                    "type": "market_data",
                    "requirement": "required",
                    "note": "Use a|b notation",
                }
            ],
        )
    ]
    out = render_api_matrix(skills)
    assert "a\\|b" in out
    # The bare form must not appear (would break the table)
    assert "a|b" not in out.replace("a\\|b", "")


def test_render_api_matrix_sorted_by_display_name() -> None:
    skills = [
        make_skill("zebra-skill"),  # display_name "Zebra Skill"
        make_skill("alpha-skill"),  # display_name "Alpha Skill"
    ]
    out = render_api_matrix(skills)
    pos_alpha = out.find("Alpha Skill")
    pos_zebra = out.find("Zebra Skill")
    assert 0 < pos_alpha < pos_zebra


# ---------------------------------------------------------------------------
# rewrite_file — sentinel-region preservation
# ---------------------------------------------------------------------------


def test_rewrite_preserves_text_outside_sentinels(tmp_path: Path) -> None:
    write_readme(tmp_path)
    skills = [make_skill("a-skill", category="market-regime")]

    _current, regenerated = rewrite_file(tmp_path / "README.md", skills)

    assert "Some pre-existing content above." in regenerated
    assert "Some pre-existing content below that must remain untouched." in regenerated
    assert "PLACEHOLDER" not in regenerated  # placeholder was replaced
    assert "a-skill" in regenerated


def test_rewrite_idempotent(tmp_path: Path) -> None:
    write_readme(tmp_path)
    skills = [make_skill("a-skill", category="market-regime")]

    _c, first = rewrite_file(tmp_path / "README.md", skills)
    (tmp_path / "README.md").write_text(first, encoding="utf-8")
    _c, second = rewrite_file(tmp_path / "README.md", skills)
    assert first == second


def test_rewrite_raises_on_unknown_sentinel_name(tmp_path: Path) -> None:
    write_readme(tmp_path, sentinel="bogus-name")
    skills = [make_skill("a-skill", category="market-regime")]
    with pytest.raises(SentinelError):
        rewrite_file(tmp_path / "README.md", skills)


def test_sentinel_regex_matches_paired_markers() -> None:
    text = (
        '<!-- skills-index:start name="catalog-en" -->\n'
        "old content\n"
        '<!-- skills-index:end name="catalog-en" -->'
    )
    m = SENTINEL_RE.search(text)
    assert m is not None
    assert m.group(2) == "catalog-en"


def test_sentinel_regex_requires_matching_names() -> None:
    """Mismatched start/end names must not match (regex uses backreference)."""
    text = (
        '<!-- skills-index:start name="catalog-en" -->\n'
        "content\n"
        '<!-- skills-index:end name="catalog-ja" -->'
    )
    m = SENTINEL_RE.search(text)
    assert m is None


# ---------------------------------------------------------------------------
# main() end-to-end with --check
# ---------------------------------------------------------------------------


def test_main_writes_then_check_passes(tmp_path: Path) -> None:
    write_minimal_index(tmp_path, [make_skill("a-skill", category="market-regime")])
    write_all_targets(tmp_path)

    rc = main(["--project-root", str(tmp_path)])
    assert rc == 0

    rc = main(["--project-root", str(tmp_path), "--check"])
    assert rc == 0


def test_main_check_fails_on_drift(tmp_path: Path) -> None:
    write_minimal_index(tmp_path, [make_skill("a-skill", category="market-regime")])
    write_all_targets(tmp_path)

    # Generate first
    main(["--project-root", str(tmp_path)])

    # Tamper inside the sentinel region (the only place generator owns)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    # Insert a manual edit between sentinels
    tampered = readme.replace("Summary for a-skill.", "Manually edited summary.")
    (tmp_path / "README.md").write_text(tampered, encoding="utf-8")

    rc = main(["--project-root", str(tmp_path), "--check"])
    assert rc == 1


def test_main_fails_on_missing_sentinel(tmp_path: Path) -> None:
    """README.md present but without the required sentinel name → error."""
    write_minimal_index(tmp_path, [make_skill("a-skill", category="market-regime")])
    # README.md has WRONG sentinel name (catalog-ja in the english file).
    write_readme(tmp_path, name="README.md", sentinel="catalog-ja")
    write_readme(tmp_path, name="README.ja.md", sentinel="catalog-ja")
    write_claude_md(tmp_path)  # CLAUDE.md is required; create it correctly

    rc = main(["--project-root", str(tmp_path)])
    assert rc == 1


def test_main_fails_on_missing_index(tmp_path: Path) -> None:
    write_all_targets(tmp_path)

    with pytest.raises(FileNotFoundError):
        main(["--project-root", str(tmp_path)])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
