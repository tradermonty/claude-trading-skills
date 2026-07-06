"""Tests for validate_workflows.py — Skill Integration Tester."""

import json
from pathlib import Path

from validate_workflows import (
    HANDOFF_CONTRACTS,
    SKILL_CONTRACTS,
    check_naming_conventions,
    check_skill_exists,
    create_dry_run_fixtures,
    generate_report,
    parse_frontmatter_name,
    parse_workflows,
    resolve_skill_name,
    validate_handoff,
    validate_workflow,
)

# ── Sample CLAUDE.md content for testing ─────────────────────────────

SAMPLE_CLAUDE_MD = """\
## Multi-Skill Workflows

Skills are designed to be combined for comprehensive analysis:

**Daily Market Monitoring:**
1. Economic Calendar Fetcher \u2192 Check today's events
2. Earnings Calendar \u2192 Identify reporting companies
3. Market News Analyst \u2192 Review overnight developments

**Earnings Momentum Trading:**
1. Earnings Trade Analyzer \u2192 Score recent earnings reactions
2. PEAD Screener (Mode B) \u2192 Feed analyzer output and screen
3. Technical Analyst \u2192 Confirm weekly chart setups
"""


# ── parse_workflows ──────────────────────────────────────────────────


class TestParseWorkflows:
    def test_finds_named_workflows(self):
        workflows = parse_workflows(SAMPLE_CLAUDE_MD)
        assert "Daily Market Monitoring" in workflows
        assert "Earnings Momentum Trading" in workflows

    def test_extracts_correct_step_count(self):
        workflows = parse_workflows(SAMPLE_CLAUDE_MD)
        assert len(workflows["Daily Market Monitoring"]) == 3
        assert len(workflows["Earnings Momentum Trading"]) == 3

    def test_extracts_skill_display_and_action(self):
        workflows = parse_workflows(SAMPLE_CLAUDE_MD)
        step = workflows["Daily Market Monitoring"][0]
        assert step["skill_display"] == "Economic Calendar Fetcher"
        assert step["action"] == "Check today's events"

    def test_strips_parenthetical_from_skill_name(self):
        workflows = parse_workflows(SAMPLE_CLAUDE_MD)
        step = workflows["Earnings Momentum Trading"][1]
        assert step["skill_display"] == "PEAD Screener"

    def test_returns_empty_for_no_workflows(self):
        assert parse_workflows("No workflows here") == {}


# ── resolve_skill_name ───────────────────────────────────────────────


class TestResolveSkillName:
    def test_known_mapping(self):
        assert resolve_skill_name("Economic Calendar Fetcher") == "economic-calendar-fetcher"

    def test_case_insensitive(self):
        assert resolve_skill_name("SECTOR ANALYST") == "sector-analyst"

    def test_unknown_name_algorithmic_fallback(self):
        assert resolve_skill_name("My Custom Skill") == "my-custom-skill"


# ── check_skill_exists ──────────────────────────────────────────────


class TestCheckSkillExists:
    def test_exists_when_skill_md_present(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\n", encoding="utf-8")
        assert check_skill_exists("my-skill", tmp_path)

    def test_not_exists_when_missing(self, tmp_path):
        assert not check_skill_exists("nonexistent", tmp_path)


# ── parse_frontmatter_name ──────────────────────────────────────────


class TestParseFrontmatterName:
    def test_extracts_name(self, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text("---\nname: foo-bar\ndescription: X\n---\nBody", encoding="utf-8")
        assert parse_frontmatter_name(md) == "foo-bar"

    def test_returns_none_for_no_frontmatter(self, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text("No frontmatter here", encoding="utf-8")
        assert parse_frontmatter_name(md) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        assert parse_frontmatter_name(tmp_path / "missing.md") is None


# ── check_naming_conventions ─────────────────────────────────────────


class TestCheckNamingConventions:
    def test_valid_skill_no_violations(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\n", encoding="utf-8")
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run_check.py").write_text("", encoding="utf-8")
        assert check_naming_conventions("my-skill", tmp_path) == []

    def test_detects_non_snake_case_script(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\n", encoding="utf-8")
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "RunAnalysis.py").write_text("", encoding="utf-8")
        violations = check_naming_conventions("my-skill", tmp_path)
        assert any("snake_case" in v for v in violations)

    def test_detects_name_mismatch(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: wrong-name\n---\n", encoding="utf-8")
        violations = check_naming_conventions("my-skill", tmp_path)
        assert any("does not match" in v for v in violations)


# ── validate_handoff ─────────────────────────────────────────────────


class TestValidateHandoff:
    def _make_skill(self, skills_dir, name):
        d = skills_dir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")

    def test_known_valid_contract(self, tmp_path):
        self._make_skill(tmp_path, "earnings-trade-analyzer")
        self._make_skill(tmp_path, "pead-screener")
        result = validate_handoff("earnings-trade-analyzer", "pead-screener", tmp_path)
        assert result["status"] == "valid"

    def test_missing_producer_is_broken(self, tmp_path):
        self._make_skill(tmp_path, "pead-screener")
        result = validate_handoff("nonexistent", "pead-screener", tmp_path)
        assert result["status"] == "broken"

    def test_unknown_pair_is_no_contract(self, tmp_path):
        self._make_skill(tmp_path, "skill-a")
        self._make_skill(tmp_path, "skill-b")
        result = validate_handoff("skill-a", "skill-b", tmp_path)
        assert result["status"] == "no_contract"


# ── validate_workflow ────────────────────────────────────────────────


class TestValidateWorkflow:
    def test_all_steps_exist(self, tmp_path):
        for name in ("skill-a", "skill-b"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        steps = [
            {"skill_display": "skill-a", "action": "do A"},
            {"skill_display": "skill-b", "action": "do B"},
        ]
        result = validate_workflow("Test", steps, tmp_path)
        assert result["status"] != "broken"

    def test_missing_step_marks_broken(self, tmp_path):
        d = tmp_path / "skill-a"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: skill-a\n---\n", encoding="utf-8")
        steps = [
            {"skill_display": "skill-a", "action": "do A"},
            {"skill_display": "nonexistent", "action": "do B"},
        ]
        result = validate_workflow("Test", steps, tmp_path)
        assert result["status"] == "broken"


# ── generate_report ──────────────────────────────────────────────────


class TestGenerateReport:
    def _make_result(self, status="valid"):
        return {
            "workflow": "Test",
            "step_count": 1,
            "steps": [
                {
                    "index": 1,
                    "skill_display": "A",
                    "skill_name": "a",
                    "action": "do",
                    "exists": True,
                    "is_meta": False,
                    "has_contract": False,
                }
            ],
            "handoffs": [],
            "naming_violations": [],
            "status": status,
        }

    def test_creates_json_and_md_files(self, tmp_path):
        json_p, md_p = generate_report([self._make_result()], False, [], tmp_path)
        assert json_p.is_file()
        assert md_p.is_file()

    def test_json_report_schema(self, tmp_path):
        json_p, _ = generate_report([self._make_result()], False, [], tmp_path)
        data = json.loads(json_p.read_text())
        assert data["schema_version"] == "1.0"
        assert data["summary"]["total_workflows"] == 1
        assert data["summary"]["valid"] == 1
        assert data["summary"]["broken"] == 0

    def test_dry_run_includes_fixtures(self, tmp_path):
        json_p, _ = generate_report(
            [self._make_result()],
            True,
            ["/tmp/fixture.json"],
            tmp_path,
        )
        data = json.loads(json_p.read_text())
        assert data["dry_run"] is True
        assert "/tmp/fixture.json" in data["fixtures_created"]


# ── create_dry_run_fixtures ──────────────────────────────────────────


class TestCreateDryRunFixtures:
    def test_creates_fixture_files(self, tmp_path):
        workflows = {
            "Test": [
                {
                    "skill_display": "Earnings Calendar",
                    "action": "check",
                },
            ],
        }
        fixtures = create_dry_run_fixtures(workflows, tmp_path)
        assert len(fixtures) > 0
        data = json.loads(Path(fixtures[0]).read_text())
        assert data["_fixture"] is True
        assert data["_skill"] == "earnings-calendar"
        assert data["schema_version"] == "1.0"

    def test_skips_unknown_skills(self, tmp_path):
        workflows = {
            "Test": [
                {
                    "skill_display": "Unknown Skill XYZ",
                    "action": "do",
                },
            ],
        }
        fixtures = create_dry_run_fixtures(workflows, tmp_path)
        assert len(fixtures) == 0

    def test_deduplicates_across_workflows(self, tmp_path):
        workflows = {
            "WF1": [
                {
                    "skill_display": "Earnings Calendar",
                    "action": "a",
                },
            ],
            "WF2": [
                {
                    "skill_display": "Earnings Calendar",
                    "action": "b",
                },
            ],
        }
        fixtures = create_dry_run_fixtures(workflows, tmp_path)
        assert len(fixtures) == 1


# ── Contract data integrity ──────────────────────────────────────────


class TestContractIntegrity:
    def test_all_handoff_producers_have_contracts(self):
        """Every producer in HANDOFF_CONTRACTS must exist in SKILL_CONTRACTS."""
        for (producer, _consumer), _contract in HANDOFF_CONTRACTS.items():
            assert producer in SKILL_CONTRACTS, (
                f"Handoff producer '{producer}' missing from SKILL_CONTRACTS"
            )

    def test_handoff_required_fields_subset_of_output(self):
        """Required fields in handoff must be subset of producer output."""
        for (producer, consumer), contract in HANDOFF_CONTRACTS.items():
            producer_fields = set(SKILL_CONTRACTS[producer]["output_fields"])
            required = set(contract["required_fields"])
            missing = required - producer_fields
            assert not missing, (
                f"Handoff {producer}\u2192{consumer}: "
                f"required fields {missing} not in producer output"
            )
