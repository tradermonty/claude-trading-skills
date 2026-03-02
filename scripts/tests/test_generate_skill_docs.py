"""Tests for scripts/generate_skill_docs.py."""

from __future__ import annotations

# Import from parent scripts/ directory
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generate_skill_docs import (
    HAND_WRITTEN,
    _slugify,
    _split_sections,
    _title_case,
    api_badges,
    api_badges_ja,
    generate_en_page,
    generate_index_table_row,
    generate_ja_page,
    main,
    parse_api_requirements,
    parse_cli_examples,
    parse_skill_md,
    update_index_pages,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_skill(tmp_path):
    """Create a minimal skill directory with SKILL.md."""
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: test-skill
        description: A test skill for unit testing the doc generator.
        ---

        # Test Skill

        ## Overview

        This is a test skill that does testing things.

        ## When to Use

        Use when testing the documentation generator.

        ## Prerequisites

        - Python 3.9+
        - No API key required

        ## Workflow

        ### Step 1: Run the test

        ```bash
        python3 scripts/test_runner.py --output-dir reports/
        ```

        ### Step 2: Review results

        Check the output in reports/ directory.
        """)
    )
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "methodology.md").write_text("# Methodology\n")

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "test_runner.py").write_text("#!/usr/bin/env python3\n")

    return tmp_path


@pytest.fixture
def tmp_claude_md(tmp_path):
    """Create a minimal CLAUDE.md with API requirements table."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        textwrap.dedent("""\
        # CLAUDE.md

        #### API Requirements by Skill

        | Skill | FMP API | FINVIZ Elite | Alpaca | Notes |
        |-------|---------|--------------|--------|-------|
        | **Test Skill** | ✅ Required | ❌ Not used | ❌ Not used | Test notes |
        | **Free Skill** | ❌ Not required | ❌ Not used | ❌ Not used | No API needed |
        | **Optional Skill** | 🟡 Optional | 🟡 Optional (Recommended) | ❌ Not used | Both optional |
        | **Alpaca Skill** | ❌ Not required | ❌ Not used | ✅ Required | Needs Alpaca |

        ### Running Helper Scripts

        **Test Skill:** ⚠️ Requires FMP API key
        ```bash
        python3 skills/test-skill/scripts/test_runner.py --output-dir reports/
        ```
        """)
    )
    return claude_md


# ---------------------------------------------------------------------------
# Tests: SKILL.md parser
# ---------------------------------------------------------------------------


class TestParseSkillMd:
    def test_parses_frontmatter(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        assert data["frontmatter"]["name"] == "test-skill"
        assert "unit testing" in data["frontmatter"]["description"]

    def test_parses_sections(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        assert "overview" in data["sections"]
        assert "when to use" in data["sections"]
        assert "workflow" in data["sections"]

    def test_no_frontmatter_returns_empty(self, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text("# Just a title\n\nSome content.")
        data = parse_skill_md(md)
        assert data["frontmatter"] == {}


class TestSplitSections:
    def test_basic_split(self):
        body = "## Overview\n\nHello world.\n\n## Workflow\n\nDo stuff."
        sections = _split_sections(body)
        assert "overview" in sections
        assert "Hello world." in sections["overview"]
        assert "workflow" in sections
        assert "Do stuff." in sections["workflow"]

    def test_empty_body(self):
        assert _split_sections("") == {}


# ---------------------------------------------------------------------------
# Tests: CLAUDE.md parsers
# ---------------------------------------------------------------------------


class TestParseApiRequirements:
    def test_parses_table(self, tmp_claude_md):
        reqs = parse_api_requirements(tmp_claude_md)
        assert "test-skill" in reqs
        assert "Required" in reqs["test-skill"]["fmp"]

    def test_free_skill(self, tmp_claude_md):
        reqs = parse_api_requirements(tmp_claude_md)
        assert "free-skill" in reqs
        assert "Not required" in reqs["free-skill"]["fmp"]

    def test_optional_skill(self, tmp_claude_md):
        reqs = parse_api_requirements(tmp_claude_md)
        assert "optional-skill" in reqs
        assert "Optional" in reqs["optional-skill"]["fmp"]

    def test_alpaca_skill(self, tmp_claude_md):
        reqs = parse_api_requirements(tmp_claude_md)
        assert "alpaca-skill" in reqs
        assert "Required" in reqs["alpaca-skill"]["alpaca"]


class TestParseCLIExamples:
    def test_extracts_code_block(self, tmp_claude_md):
        examples = parse_cli_examples(tmp_claude_md)
        assert "test-skill" in examples
        assert "test_runner.py" in examples["test-skill"]


# ---------------------------------------------------------------------------
# Tests: Badge generation
# ---------------------------------------------------------------------------


class TestApiBadges:
    def test_no_api(self):
        assert "badge-free" in api_badges(None)

    def test_fmp_required(self):
        badges = api_badges({"fmp": "✅ Required", "finviz": "❌", "alpaca": "❌"})
        assert "badge-api" in badges
        assert "FMP Required" in badges

    def test_optional_shows_both(self):
        badges = api_badges({"fmp": "🟡 Optional", "finviz": "🟡 Optional", "alpaca": "❌"})
        assert "badge-free" in badges
        assert "badge-optional" in badges

    def test_alpaca_required(self):
        badges = api_badges({"fmp": "❌", "finviz": "❌", "alpaca": "✅ Required"})
        assert "Alpaca Required" in badges


class TestApiBadgesJa:
    def test_no_api_ja(self):
        assert "API不要" in api_badges_ja(None)

    def test_fmp_required_ja(self):
        badges = api_badges_ja({"fmp": "✅ Required", "finviz": "❌", "alpaca": "❌"})
        assert "FMP必須" in badges
        assert "badge-api" in badges

    def test_optional_ja(self):
        badges = api_badges_ja({"fmp": "🟡 Optional", "finviz": "🟡 Optional", "alpaca": "❌"})
        assert "API不要" in badges
        assert "FMP任意" in badges
        assert "FINVIZ任意" in badges

    def test_alpaca_required_ja(self):
        badges = api_badges_ja({"fmp": "❌", "finviz": "❌", "alpaca": "✅ Required"})
        assert "Alpaca必須" in badges


# ---------------------------------------------------------------------------
# Tests: Index table row generation
# ---------------------------------------------------------------------------


class TestGenerateIndexTableRow:
    def test_en_row_basic(self):
        row = generate_index_table_row("test-skill", "A test skill", None, "en")
        assert "Test Skill" in row
        assert "/en/skills/test-skill/" in row
        assert "No API" in row
        assert "★" not in row

    def test_hand_written_gets_star(self):
        hw = next(iter(HAND_WRITTEN))
        row = generate_index_table_row(hw, "desc", None, "en")
        assert "★" in row

    def test_ja_row_uses_ja_badges(self):
        api = {"fmp": "✅ Required", "finviz": "❌", "alpaca": "❌"}
        row = generate_index_table_row("test-skill", "desc", api, "ja")
        assert "FMP必須" in row
        assert "/ja/skills/test-skill/" in row

    def test_long_description_truncated(self):
        long_desc = "A" * 200
        row = generate_index_table_row("x", long_desc, None, "en")
        assert "..." in row
        assert len(row) < 300


# ---------------------------------------------------------------------------
# Tests: Title and slug helpers
# ---------------------------------------------------------------------------


class TestTitleCase:
    def test_basic(self):
        assert _title_case("earnings-trade-analyzer") == "Earnings Trade Analyzer"

    def test_acronyms(self):
        assert _title_case("us-stock-analysis") == "US Stock Analysis"
        assert _title_case("vcp-screener") == "VCP Screener"
        assert _title_case("pead-screener") == "PEAD Screener"

    def test_slugify(self):
        assert _slugify("Test Skill") == "test-skill"
        assert _slugify("**Bold Name**") == "bold-name"


# ---------------------------------------------------------------------------
# Tests: Page generation
# ---------------------------------------------------------------------------


class TestGenerateEnPage:
    def test_contains_frontmatter(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_en_page(
            "test-skill", data, None, None, 11, {"references": [], "scripts": []}
        )
        assert "layout: default" in page
        assert 'title: "Test Skill"' in page
        assert "nav_order: 11" in page
        assert "grand_parent: English" in page

    def test_contains_overview(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_en_page(
            "test-skill", data, None, None, 11, {"references": [], "scripts": []}
        )
        assert "testing things" in page

    def test_contains_workflow(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_en_page(
            "test-skill", data, None, None, 11, {"references": [], "scripts": []}
        )
        assert "test_runner.py" in page

    def test_api_badges_included(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        api = {"fmp": "✅ Required", "finviz": "❌", "alpaca": "❌"}
        page = generate_en_page(
            "test-skill", data, api, None, 11, {"references": [], "scripts": []}
        )
        assert "badge-api" in page

    def test_resources_listed(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        resources = {"references": ["methodology.md"], "scripts": ["test_runner.py"]}
        page = generate_en_page("test-skill", data, None, None, 11, resources)
        assert "methodology.md" in page
        assert "test_runner.py" in page


class TestGenerateJaPage:
    def test_contains_ja_frontmatter(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_ja_page("test-skill", data, None, 11)
        assert "grand_parent: 日本語" in page
        assert "parent: スキルガイド" in page

    def test_contains_translation_banner(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_ja_page("test-skill", data, None, 11)
        assert "not yet been translated" in page

    def test_links_to_en_version(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_ja_page("test-skill", data, None, 11)
        assert "/en/skills/test-skill/" in page


# ---------------------------------------------------------------------------
# Tests: End-to-end main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_generates_pages(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)

        result = main(
            [
                "--skills-dir",
                str(tmp_skill / "skills"),
                "--docs-dir",
                str(docs_dir),
                "--claude-md",
                str(tmp_claude_md),
            ]
        )
        assert result == 0
        assert (docs_dir / "en" / "skills" / "test-skill.md").exists()
        assert (docs_dir / "ja" / "skills" / "test-skill.md").exists()

    def test_skips_hand_written(self, tmp_skill, tmp_claude_md):
        # Create a skill that matches HAND_WRITTEN
        hw_skill = tmp_skill / "skills" / "backtest-expert"
        hw_skill.mkdir()
        (hw_skill / "SKILL.md").write_text("---\nname: backtest-expert\ndescription: test\n---\n")

        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)

        main(
            [
                "--skills-dir",
                str(tmp_skill / "skills"),
                "--docs-dir",
                str(docs_dir),
                "--claude-md",
                str(tmp_claude_md),
            ]
        )
        # backtest-expert should not be generated (hand-written)
        assert not (docs_dir / "en" / "skills" / "backtest-expert.md").exists()

    def test_overwrite_regenerates(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en_path = docs_dir / "en" / "skills" / "test-skill.md"
        en_path.parent.mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        en_path.write_text("old content")

        main(
            [
                "--skills-dir",
                str(tmp_skill / "skills"),
                "--docs-dir",
                str(docs_dir),
                "--claude-md",
                str(tmp_claude_md),
                "--overwrite",
            ]
        )
        assert "old content" not in en_path.read_text()
        assert "Test Skill" in en_path.read_text()

    def test_main_updates_index(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en_index = docs_dir / "en" / "skills" / "index.md"
        ja_index = docs_dir / "ja" / "skills" / "index.md"
        en_index.parent.mkdir(parents=True)
        ja_index.parent.mkdir(parents=True)
        en_index.write_text(
            "## Guides\n\n| Skill | Desc | API |\n|---|---|---|\n| old | old | old |\n\nFooter\n"
        )
        ja_index.write_text(
            "## ガイド\n\n| スキル | 概要 | API |\n|---|---|---|\n| old | old | old |\n\nFooter\n"
        )

        main(
            [
                "--skills-dir",
                str(tmp_skill / "skills"),
                "--docs-dir",
                str(docs_dir),
                "--claude-md",
                str(tmp_claude_md),
            ]
        )
        en_content = en_index.read_text()
        assert "Test Skill" in en_content
        assert "old | old" not in en_content
        assert "Footer" in en_content

        ja_content = ja_index.read_text()
        assert "Test Skill" in ja_content

    def test_skips_dir_without_skill_md(self, tmp_skill, tmp_claude_md):
        # Create a directory without SKILL.md
        (tmp_skill / "skills" / "empty-skill").mkdir()

        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)

        main(
            [
                "--skills-dir",
                str(tmp_skill / "skills"),
                "--docs-dir",
                str(docs_dir),
                "--claude-md",
                str(tmp_claude_md),
            ]
        )
        assert not (docs_dir / "en" / "skills" / "empty-skill.md").exists()


# ---------------------------------------------------------------------------
# Tests: Index page update
# ---------------------------------------------------------------------------


class TestUpdateIndexPages:
    def test_replaces_table_rows(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en_index = docs_dir / "en" / "skills" / "index.md"
        en_index.parent.mkdir(parents=True)
        en_index.write_text(
            "# Title\n\n| Skill | Desc | API |\n|---|---|---|\n| stale | stale | stale |\n\nFooter\n"
        )

        api_reqs = parse_api_requirements(tmp_claude_md)
        update_index_pages(tmp_skill / "skills", docs_dir, api_reqs)

        content = en_index.read_text()
        assert "stale" not in content
        assert "Test Skill" in content
        assert "Footer" in content

    def test_preserves_header_and_footer(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en_index = docs_dir / "en" / "skills" / "index.md"
        en_index.parent.mkdir(parents=True)
        en_index.write_text(
            "---\ntitle: Index\n---\n\n# Heading\n\n"
            "| Skill | Desc | API |\n|---|---|---|\n| old | row | here |\n\n"
            "★ = detailed guide\n"
        )

        api_reqs = parse_api_requirements(tmp_claude_md)
        update_index_pages(tmp_skill / "skills", docs_dir, api_reqs)

        content = en_index.read_text()
        assert "title: Index" in content
        assert "# Heading" in content
        assert "★ = detailed guide" in content
        assert "old | row" not in content

    def test_skips_missing_index(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        # No index.md created — should not raise
        api_reqs = parse_api_requirements(tmp_claude_md)
        update_index_pages(tmp_skill / "skills", docs_dir, api_reqs)
