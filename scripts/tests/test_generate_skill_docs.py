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
    _doc_is_generated,
    _extract_catalog_slugs,
    _generate_buttons,
    _marker_present_but_invalid,
    _slugify,
    _split_sections,
    _title_case,
    api_badges,
    api_badges_ja,
    generate_en_full_page,
    generate_en_page,
    generate_index_table_row,
    generate_ja_full_page,
    generate_ja_page,
    main,
    parse_api_requirements,
    parse_cli_examples,
    parse_skill_md,
    update_catalog_api_matrix,
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

    def test_overwrite_skips_protected_absent_marker(self, tmp_skill, tmp_claude_md):
        # BEHAVIOR CHANGE (Follow-up B): a page with no `generated:` marker is
        # hand-maintained/protected. --overwrite (without --force) must NOT
        # destroy it. (Previously this test asserted --overwrite regenerated a
        # markerless page; the ownership guard intentionally flips that.)
        docs_dir = tmp_skill / "docs"
        en_path = docs_dir / "en" / "skills" / "test-skill.md"
        en_path.parent.mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        en_path.write_text("old hand-maintained content")

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
        assert en_path.read_text() == "old hand-maintained content"

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
# Tests: ownership guard + --check (Follow-up B)
# ---------------------------------------------------------------------------


def _base_args(tmp_skill, tmp_claude_md):
    return [
        "--skills-dir",
        str(tmp_skill / "skills"),
        "--docs-dir",
        str(tmp_skill / "docs"),
        "--claude-md",
        str(tmp_claude_md),
    ]


class TestOwnershipGuardAndCheck:
    def test_new_page_stamped_generated_true(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        main(_base_args(tmp_skill, tmp_claude_md))
        en = docs_dir / "en" / "skills" / "test-skill.md"
        ja = docs_dir / "ja" / "skills" / "test-skill.md"
        assert _doc_is_generated(en) is True
        assert _doc_is_generated(ja) is True

    def test_overwrite_skips_protected_generated_false(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        body = "---\ntitle: x\ngenerated: false\n---\nhand body\n"
        en.write_text(body)
        main(_base_args(tmp_skill, tmp_claude_md) + ["--overwrite"])
        assert en.read_text() == body

    def test_overwrite_rewrites_generated_true(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        en.write_text("---\ntitle: x\ngenerated: true\n---\nstale generated body\n")
        main(_base_args(tmp_skill, tmp_claude_md) + ["--overwrite"])
        out = en.read_text()
        assert "stale generated body" not in out
        assert "Test Skill" in out
        assert _doc_is_generated(en) is True

    def test_force_overrides_protection(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        en.write_text("hand body, no marker")
        main(_base_args(tmp_skill, tmp_claude_md) + ["--overwrite", "--force"])
        out = en.read_text()
        assert "hand body, no marker" not in out
        assert "Test Skill" in out

    def test_hand_written_missing_not_generated_normal(self, tmp_skill, tmp_claude_md):
        hw = tmp_skill / "skills" / "backtest-expert"
        hw.mkdir()
        (hw / "SKILL.md").write_text("---\nname: backtest-expert\ndescription: t\n---\n")
        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        main(_base_args(tmp_skill, tmp_claude_md))
        assert not (docs_dir / "en" / "skills" / "backtest-expert.md").exists()

    def test_hand_written_missing_generated_with_force(self, tmp_skill, tmp_claude_md):
        hw = tmp_skill / "skills" / "backtest-expert"
        hw.mkdir()
        (hw / "SKILL.md").write_text("---\nname: backtest-expert\ndescription: t\n---\n")
        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        main(_base_args(tmp_skill, tmp_claude_md) + ["--force"])
        assert (docs_dir / "en" / "skills" / "backtest-expert.md").exists()

    def test_hand_written_existing_protected_under_overwrite(self, tmp_skill, tmp_claude_md):
        hw = tmp_skill / "skills" / "backtest-expert"
        hw.mkdir()
        (hw / "SKILL.md").write_text("---\nname: backtest-expert\ndescription: t\n---\n")
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "backtest-expert.md"
        en.parent.mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        en.write_text("hand-written guide body")
        main(_base_args(tmp_skill, tmp_claude_md) + ["--overwrite"])
        assert en.read_text() == "hand-written guide body"

    def test_mixed_ownership_en_owned_ja_protected(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        ja = docs_dir / "ja" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        ja.parent.mkdir(parents=True)
        en.write_text("---\ntitle: x\ngenerated: true\n---\nstale en\n")
        ja_body = "---\ntitle: x\n---\n# 手動翻訳された日本語ページ\n"
        ja.write_text(ja_body)
        main(_base_args(tmp_skill, tmp_claude_md) + ["--overwrite"])
        assert "stale en" not in en.read_text()
        assert "Test Skill" in en.read_text()
        assert ja.read_text() == ja_body  # JA hand-translation byte-unchanged

    def test_brand_new_one_side_non_hand_written(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        ja = docs_dir / "ja" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        ja.parent.mkdir(parents=True)
        ja_body = "---\ntitle: x\n---\n# 既存の手動翻訳\n"
        ja.write_text(ja_body)
        # EN missing, JA exists & protected, NORMAL run (no --overwrite)
        main(_base_args(tmp_skill, tmp_claude_md))
        assert en.exists()
        assert _doc_is_generated(en) is True
        assert ja.read_text() == ja_body  # JA untouched

    def test_check_protects_hand_written_even_with_generated_true(self, tmp_skill, tmp_claude_md):
        # A HAND_WRITTEN page is ALWAYS protected, even if it carries
        # generated: true (e.g. stamped earlier via --force). --check must NOT
        # content-compare it.
        hw = tmp_skill / "skills" / "backtest-expert"
        hw.mkdir()
        (hw / "SKILL.md").write_text("---\nname: backtest-expert\ndescription: t\n---\n")
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "backtest-expert.md"
        ja = docs_dir / "ja" / "skills" / "backtest-expert.md"
        en.parent.mkdir(parents=True)
        ja.parent.mkdir(parents=True)
        en.write_text("---\ntitle: x\ngenerated: true\n---\nwildly divergent hand body\n")
        ja.write_text("---\ntitle: x\ngenerated: true\n---\n手動の全く違う本文\n")
        # tmp_skill always creates skills/test-skill too; give it protected
        # pages so existence checks don't trip (focus is the HW assertion).
        (docs_dir / "en" / "skills" / "test-skill.md").write_text("protected en\n")
        (docs_dir / "ja" / "skills" / "test-skill.md").write_text("protected ja\n")
        rc = main(_base_args(tmp_skill, tmp_claude_md) + ["--check"])
        assert rc == 0

    def test_check_passes_when_protected_body_differs(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        ja = docs_dir / "ja" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        ja.parent.mkdir(parents=True)
        en.write_text("wildly different EN, no marker\n")
        ja.write_text("全く違う日本語、マーカーなし\n")
        rc = main(_base_args(tmp_skill, tmp_claude_md) + ["--check"])
        assert rc == 0

    def test_check_fails_on_generated_true_drift(self, tmp_skill, tmp_claude_md, capsys):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        ja = docs_dir / "ja" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        ja.parent.mkdir(parents=True)
        en.write_text("---\ntitle: x\ngenerated: true\n---\nstale owned body\n")
        ja.write_text("---\ntitle: x\n---\nhand ja\n")
        rc = main(_base_args(tmp_skill, tmp_claude_md) + ["--check"])
        assert rc == 1
        assert "DRIFT:" in capsys.readouterr().err

    def test_check_fails_on_missing_page(self, tmp_skill, tmp_claude_md, capsys):
        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        # neither EN nor JA exists for test-skill
        rc = main(_base_args(tmp_skill, tmp_claude_md) + ["--check"])
        assert rc == 1
        assert "does not exist" in capsys.readouterr().err

    def test_check_reports_invalid_marker(self, tmp_skill, tmp_claude_md, capsys):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        ja = docs_dir / "ja" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        ja.parent.mkdir(parents=True)
        en.write_text("---\ntitle: x\ngenerated: maybe\n---\nbody\n")
        ja.write_text("---\ntitle: x\n---\nbody\n")
        rc = main(_base_args(tmp_skill, tmp_claude_md) + ["--check"])
        assert rc == 1
        assert "invalid 'generated:' marker" in capsys.readouterr().err

    def test_check_passes_clean_after_generate(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        (docs_dir / "en" / "skills").mkdir(parents=True)
        (docs_dir / "ja" / "skills").mkdir(parents=True)
        main(_base_args(tmp_skill, tmp_claude_md))
        rc = main(_base_args(tmp_skill, tmp_claude_md) + ["--check"])
        assert rc == 0

    def test_check_performs_no_writes(self, tmp_skill, tmp_claude_md):
        docs_dir = tmp_skill / "docs"
        en = docs_dir / "en" / "skills" / "test-skill.md"
        ja = docs_dir / "ja" / "skills" / "test-skill.md"
        en.parent.mkdir(parents=True)
        ja.parent.mkdir(parents=True)
        en.write_text("protected en\n")
        ja.write_text("protected ja\n")
        before = (en.read_text(), ja.read_text(), en.stat().st_mtime_ns)
        main(_base_args(tmp_skill, tmp_claude_md) + ["--check"])
        assert (en.read_text(), ja.read_text(), en.stat().st_mtime_ns) == before
        # No index/catalog created as a side effect of --check
        assert not (docs_dir / "en" / "skills" / "index.md").exists()

    def test_doc_is_generated_helper(self, tmp_path):
        true_p = tmp_path / "t.md"
        true_p.write_text("---\ntitle: a: b\ngenerated: true\n---\nx")
        false_p = tmp_path / "f.md"
        false_p.write_text("---\ngenerated: false\n---\nx")
        absent_p = tmp_path / "a.md"
        absent_p.write_text("---\ntitle: x\n---\nx")
        invalid_p = tmp_path / "i.md"
        invalid_p.write_text("---\ngenerated: maybe\n---\nx")
        missing_p = tmp_path / "nope.md"
        assert _doc_is_generated(true_p) is True
        assert _doc_is_generated(false_p) is False
        assert _doc_is_generated(absent_p) is None
        assert _doc_is_generated(invalid_p) is None
        assert _doc_is_generated(missing_p) is None
        assert _marker_present_but_invalid(invalid_p) is True
        assert _marker_present_but_invalid(true_p) is False
        assert _marker_present_but_invalid(absent_p) is False


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


# ---------------------------------------------------------------------------
# Tests: JA badge bug fix (Step 1)
# ---------------------------------------------------------------------------


class TestGenerateJaPageBadges:
    def test_ja_badges_used(self, tmp_skill):
        """Verify JA page uses api_badges_ja (FMP必須) not api_badges (FMP Required)."""
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        api = {"fmp": "✅ Required", "finviz": "❌", "alpaca": "❌"}
        page = generate_ja_page("test-skill", data, api, 11)
        assert "FMP必須" in page
        assert "FMP Required" not in page


# ---------------------------------------------------------------------------
# Tests: Buttons (Step 2)
# ---------------------------------------------------------------------------


class TestButtons:
    def test_buttons_en_with_package(self, tmp_path):
        """When .skill file exists, both Download and Source buttons appear."""
        pkg_dir = tmp_path / "skill-packages"
        pkg_dir.mkdir()
        (pkg_dir / "my-skill.skill").write_text("zip content")

        result = _generate_buttons("my-skill", pkg_dir, "en")
        assert "Download Skill Package (.skill)" in result
        assert "skill-packages/my-skill.skill" in result
        assert "View Source on GitHub" in result
        assert "skills/my-skill" in result
        assert ".btn .btn-primary" in result

    def test_buttons_en_without_package(self, tmp_path):
        """When .skill file does not exist, only Source button appears."""
        pkg_dir = tmp_path / "skill-packages"
        pkg_dir.mkdir()
        # No .skill file created

        result = _generate_buttons("my-skill", pkg_dir, "en")
        assert "Download Skill Package" not in result
        assert "View Source on GitHub" in result

    def test_buttons_ja(self, tmp_path):
        """JA buttons use Japanese text."""
        pkg_dir = tmp_path / "skill-packages"
        pkg_dir.mkdir()
        (pkg_dir / "my-skill.skill").write_text("zip content")

        result = _generate_buttons("my-skill", pkg_dir, "ja")
        assert "スキルパッケージをダウンロード (.skill)" in result
        assert "GitHubでソースを見る" in result

    def test_buttons_none_still_shows_source(self):
        """When skill_packages_dir is None, Source button still appears."""
        result = _generate_buttons("my-skill", None, "en")
        assert "View Source on GitHub" in result
        assert "Download Skill Package" not in result

    def test_buttons_none_ja_still_shows_source(self):
        """When skill_packages_dir is None, JA Source button still appears."""
        result = _generate_buttons("my-skill", None, "ja")
        assert "GitHubでソースを見る" in result
        assert "スキルパッケージをダウンロード" not in result


# ---------------------------------------------------------------------------
# Tests: Full page generation (Step 3)
# ---------------------------------------------------------------------------


class TestGenerateEnFullPage:
    def test_full_page_has_10_sections(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_en_full_page(
            "test-skill",
            data,
            None,
            None,
            11,
            {"references": ["methodology.md"], "scripts": ["test_runner.py"]},
        )
        for heading in [
            "## 1. Overview",
            "## 2. Prerequisites",
            "## 3. Quick Start",
            "## 4. How It Works",
            "## 5. Usage Examples",
            "## 6. Understanding the Output",
            "## 7. Tips & Best Practices",
            "## 8. Combining with Other Skills",
            "## 9. Troubleshooting",
            "## 10. Reference",
        ]:
            assert heading in page, f"Missing heading: {heading}"

    def test_full_page_has_todo_markers(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_en_full_page(
            "test-skill",
            data,
            None,
            None,
            11,
            {"references": [], "scripts": []},
        )
        # Sections 4-9 should have TODO comments
        assert "<!-- TODO: Describe the internal pipeline/algorithm -->" in page
        assert "<!-- TODO: Add 4-6 real-world usage scenarios -->" in page
        assert "<!-- TODO: Describe output file format and field definitions -->" in page
        assert "<!-- TODO: Add expert advice for getting the most value -->" in page
        assert "<!-- TODO: Add multi-skill workflow table -->" in page
        assert "<!-- TODO: Add common errors and fixes -->" in page

    def test_full_page_auto_fills_overview(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_en_full_page(
            "test-skill",
            data,
            None,
            None,
            11,
            {"references": [], "scripts": []},
        )
        assert "testing things" in page

    def test_full_page_has_buttons(self, tmp_path, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "test-skill.skill").write_text("zip")

        page = generate_en_full_page(
            "test-skill",
            data,
            None,
            None,
            11,
            {"references": [], "scripts": []},
            skill_packages_dir=pkg_dir,
        )
        assert "Download Skill Package" in page
        assert "View Source on GitHub" in page


class TestGenerateJaFullPage:
    def test_ja_full_page_has_ja_headings(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_ja_full_page(
            "test-skill",
            data,
            None,
            None,
            11,
            {"references": ["methodology.md"], "scripts": ["test_runner.py"]},
        )
        for heading in [
            "## 1. 概要",
            "## 2. 前提条件",
            "## 3. クイックスタート",
            "## 4. 仕組み",
            "## 5. 使用例",
            "## 6. 出力の読み方",
            "## 7. Tips & ベストプラクティス",
            "## 8. 他スキルとの連携",
            "## 9. トラブルシューティング",
            "## 10. リファレンス",
        ]:
            assert heading in page, f"Missing JA heading: {heading}"

    def test_ja_full_page_has_ja_badges(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        api = {"fmp": "✅ Required", "finviz": "❌", "alpaca": "❌"}
        page = generate_ja_full_page(
            "test-skill",
            data,
            api,
            None,
            11,
            {"references": [], "scripts": []},
        )
        assert "FMP必須" in page
        assert "FMP Required" not in page

    def test_ja_full_page_has_todo_translation(self, tmp_skill):
        data = parse_skill_md(tmp_skill / "skills" / "test-skill" / "SKILL.md")
        page = generate_ja_full_page(
            "test-skill",
            data,
            None,
            None,
            11,
            {"references": [], "scripts": []},
        )
        assert "<!-- TODO: 翻訳 -->" in page


# ---------------------------------------------------------------------------
# Tests: Catalog API matrix (Step 4)
# ---------------------------------------------------------------------------


class TestExtractCatalogSlugs:
    def test_extracts_linked_slugs(self):
        text = "| [Name](/en/skills/my-skill/) | desc |\n| [Other](/ja/skills/other-one/) | x |"
        slugs = _extract_catalog_slugs(text)
        assert "my-skill" in slugs
        assert "other-one" in slugs

    def test_extracts_bold_names(self):
        text = "| **Theme Detector** | desc | badge |\n| **VCP Screener** | desc | badge |"
        slugs = _extract_catalog_slugs(text)
        assert "theme-detector" in slugs
        assert "vcp-screener" in slugs


class TestUpdateCatalogApiMatrix:
    def _make_en_catalog(self, docs_dir):
        """Create a minimal EN catalog with an API Requirements Matrix."""
        en_dir = docs_dir / "en"
        en_dir.mkdir(parents=True, exist_ok=True)
        catalog = en_dir / "skill-catalog.md"
        catalog.write_text(
            textwrap.dedent("""\
            # Skill Catalog

            ## API Requirements Matrix

            | Skill | FMP | FINVIZ Elite | Alpaca |
            |-------|-----|-------------|--------|
            | Existing Skill | Required | -- | -- |

            "--" means not required.
            """)
        )
        return catalog

    def _make_ja_catalog(self, docs_dir):
        """Create a minimal JA catalog with an API要件マトリクス."""
        ja_dir = docs_dir / "ja"
        ja_dir.mkdir(parents=True, exist_ok=True)
        catalog = ja_dir / "skill-catalog.md"
        catalog.write_text(
            textwrap.dedent("""\
            # スキル一覧

            ## API要件マトリクス

            | スキル | FMP | FINVIZ Elite | Alpaca |
            |--------|-----|-------------|--------|
            | Existing Skill | 必須 | - | - |
            | その他すべてのスキル | - | - | - |

            「-」は不要を意味します。
            """)
        )
        return catalog

    def test_adds_missing_skill_to_en_matrix(self, tmp_path):
        docs_dir = tmp_path / "docs"
        catalog = self._make_en_catalog(docs_dir)

        all_skills = [
            (
                "new-skill",
                {"frontmatter": {"name": "new-skill", "description": "A new skill"}},
                {"fmp": "✅ Required", "finviz": "❌ Not used", "alpaca": "❌ Not used"},
            ),
        ]
        update_catalog_api_matrix(docs_dir, all_skills)
        content = catalog.read_text()
        assert "New Skill" in content
        assert "Existing Skill" in content

    def test_skips_existing_skill_in_matrix(self, tmp_path):
        docs_dir = tmp_path / "docs"
        catalog = self._make_en_catalog(docs_dir)

        all_skills = [
            (
                "existing-skill",
                {"frontmatter": {"name": "existing-skill", "description": "Already there"}},
                {"fmp": "✅ Required", "finviz": "❌ Not used", "alpaca": "❌ Not used"},
            ),
        ]
        update_catalog_api_matrix(docs_dir, all_skills)
        content = catalog.read_text()
        # Should still have exactly one "Existing Skill" row
        assert content.count("Existing Skill") == 1

    def test_ja_inserts_before_aggregate_row(self, tmp_path):
        docs_dir = tmp_path / "docs"
        catalog = self._make_ja_catalog(docs_dir)

        all_skills = [
            (
                "new-skill",
                {"frontmatter": {"name": "new-skill", "description": "A new skill"}},
                {"fmp": "✅ Required", "finviz": "❌ Not used", "alpaca": "❌ Not used"},
            ),
        ]
        update_catalog_api_matrix(docs_dir, all_skills)
        content = catalog.read_text()
        lines = content.splitlines()
        # Find "New Skill" and "その他すべてのスキル"
        new_idx = None
        agg_idx = None
        for i, line in enumerate(lines):
            if "New Skill" in line:
                new_idx = i
            if "その他すべてのスキル" in line:
                agg_idx = i
        assert new_idx is not None, "New Skill row not found"
        assert agg_idx is not None, "Aggregate row not found"
        assert new_idx < agg_idx, "New skill should appear before aggregate row"

    def test_skill_in_category_but_not_in_matrix_gets_added(self, tmp_path):
        """A skill linked in a category table but missing from matrix should be added."""
        docs_dir = tmp_path / "docs"
        en_dir = docs_dir / "en"
        en_dir.mkdir(parents=True)
        catalog = en_dir / "skill-catalog.md"
        catalog.write_text(
            textwrap.dedent("""\
            # Skill Catalog

            ## 1. Screening

            | Skill | Description | API Requirements |
            |-------|-------------|-----------------|
            | **[My Skill](/en/skills/my-skill/)** | Already in category | badge |

            ## API Requirements Matrix

            | Skill | FMP | FINVIZ Elite | Alpaca |
            |-------|-----|-------------|--------|
            | Other Skill | -- | -- | -- |

            "--" means not required.
            """)
        )
        all_skills = [
            (
                "my-skill",
                {"frontmatter": {"name": "my-skill", "description": "desc"}},
                {"fmp": "✅ Required", "finviz": "❌ Not used", "alpaca": "❌ Not used"},
            ),
        ]
        update_catalog_api_matrix(docs_dir, all_skills)
        content = catalog.read_text()
        # my-skill is in category table but NOT in matrix — should be added to matrix
        assert content.count("My Skill") == 2  # once in category, once in matrix

    def test_ja_skips_all_dash_skill(self, tmp_path):
        docs_dir = tmp_path / "docs"
        catalog = self._make_ja_catalog(docs_dir)

        all_skills = [
            (
                "free-skill",
                {"frontmatter": {"name": "free-skill", "description": "No API needed"}},
                {"fmp": "❌ Not required", "finviz": "❌ Not used", "alpaca": "❌ Not used"},
            ),
        ]
        update_catalog_api_matrix(docs_dir, all_skills)
        content = catalog.read_text()
        # free-skill should not be added to JA because all values are "-"
        assert "Free Skill" not in content
