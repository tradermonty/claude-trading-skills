from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
EXPECTED_RESOURCES = (
    "references/technical_analysis_framework.md",
    "assets/analysis_template.md",
    "references/contrarian-confirmation-checklist.md",
    "scripts/check_weekly_price_action.py",
)


def _skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter() -> dict:
    text = _skill_text()
    assert text.startswith("---\n")
    _prefix, raw_yaml, _body = text.split("---", 2)
    metadata = yaml.safe_load(raw_yaml)
    assert isinstance(metadata, dict)
    return metadata


def test_frontmatter_identifies_chart_only_technical_skill() -> None:
    metadata = _frontmatter()

    assert metadata["name"] == "technical-analyst"
    assert "weekly price charts" in metadata["description"]
    assert "without consideration of news or fundamental factors" in metadata["description"]


def test_required_framework_and_template_are_present_and_named() -> None:
    text = _skill_text()

    for rel_path in EXPECTED_RESOURCES:
        assert (SKILL_DIR / rel_path).is_file()
        assert rel_path in text


def test_prompt_contract_requires_chart_input_and_probabilistic_output() -> None:
    text = _skill_text()

    assert "Chart Images" in text
    assert "Pure Chart Analysis" in text
    assert "Probabilistic Scenarios" in text
    assert "[SYMBOL]_technical_analysis_[YYYY-MM-DD].md" in text


# --- Contrarian Confirmation Mode (Shapiro Step 3) -- additive section ------
# The section must exist between "Example Usage Scenarios" and "Resources"
# so none of the existing section anchors above are disturbed, and it must
# name its output contract fields and filename pattern so a reader (or a
# downstream skill like contrarian-setup-gate, #241) can rely on them.


def test_contrarian_confirmation_section_present_and_positioned() -> None:
    text = _skill_text()

    assert "## Contrarian Confirmation Mode (Shapiro Step 3)" in text
    examples_idx = text.index("## Example Usage Scenarios")
    contrarian_idx = text.index("## Contrarian Confirmation Mode (Shapiro Step 3)")
    resources_idx = text.index("## Resources")
    assert examples_idx < contrarian_idx < resources_idx


def test_contrarian_confirmation_output_contract_fields_named() -> None:
    text = _skill_text()

    for token in (
        "CONFIRMED",
        "NOT_CONFIRMED",
        "INSUFFICIENT_DATA",
        "weekly_key_reversal",
        "failed_extreme",
        "failed_breakout",
        "continuation",
        "verdict_reason",
        "swing_levels",
        "stop_reference",
        "handoff",
    ):
        assert token in text, f"expected output-contract token {token!r} in SKILL.md"


def test_contrarian_confirmation_output_filename_pattern_documented() -> None:
    text = _skill_text()

    assert "ta_confirmation_<SYMBOL>_<as-of>.json" in text
    assert "ta_confirmation_<SYMBOL>_<as-of>.md" in text


def test_contrarian_confirmation_cli_invocation_documented() -> None:
    text = _skill_text()

    assert "check_weekly_price_action.py" in text


def test_contrarian_confirmation_guardrails_documented() -> None:
    text = _skill_text()

    assert "INSUFFICIENT_DATA" in text
    assert "never a trade" in text.lower() or "not a trade" in text.lower()


def test_existing_workflow_identity_phrases_untouched() -> None:
    # No-regression guard (plan DoD): the pre-existing chart-only workflow
    # identity phrases must survive verbatim alongside the new section.
    text = _skill_text()

    assert "Chart Images" in text
    assert "Pure Chart Analysis" in text
    assert "Probabilistic Scenarios" in text
