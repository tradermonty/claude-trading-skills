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
    write_readme(tmp_path, name="README.md", sentinel="catalog-en")
    write_readme(tmp_path, name="README.ja.md", sentinel="catalog-ja")

    rc = main(["--project-root", str(tmp_path)])
    assert rc == 0

    rc = main(["--project-root", str(tmp_path), "--check"])
    assert rc == 0


def test_main_check_fails_on_drift(tmp_path: Path) -> None:
    write_minimal_index(tmp_path, [make_skill("a-skill", category="market-regime")])
    write_readme(tmp_path, name="README.md", sentinel="catalog-en")
    write_readme(tmp_path, name="README.ja.md", sentinel="catalog-ja")

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

    rc = main(["--project-root", str(tmp_path)])
    assert rc == 1


def test_main_fails_on_missing_index(tmp_path: Path) -> None:
    write_readme(tmp_path, name="README.md", sentinel="catalog-en")
    write_readme(tmp_path, name="README.ja.md", sentinel="catalog-ja")

    with pytest.raises(FileNotFoundError):
        main(["--project-root", str(tmp_path)])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
