"""Guard the FMP plan-gating documentation (Issue #707).

The canonical FMP plans note must name the endpoints observed as plan-gated,
and the dividend screeners' docs must point readers at it instead of claiming
the stock-screener endpoint works on the free plan.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

NOTE_PAGES = {
    "docs/en/getting-started.md": "Plan-gated endpoints (as of 2026-11):",
    "docs/ja/getting-started.md": "プラン限定エンドポイント（2026-11 時点）:",
}
PRICING_PAGE = "site.financialmodelingprep.com/pricing-plans"
NOTE_REFERENCE = "docs/en/getting-started.md#fmp-plans"

SKILL_AND_REFERENCE_FILES = (
    "skills/value-dividend-screener/SKILL.md",
    "skills/value-dividend-screener/references/performance_and_cost.md",
    "skills/value-dividend-screener/references/fmp_api_guide.md",
    "skills/dividend-growth-pullback-screener/SKILL.md",
    "skills/dividend-growth-pullback-screener/references/fmp_api_guide.md",
)

RENDERED_PAGES = {
    "docs/en/skills/value-dividend-screener.md": "{{ '/en/getting-started/' | relative_url }}#fmp-plans",
    "docs/ja/skills/value-dividend-screener.md": "{{ '/ja/getting-started/' | relative_url }}#fmp-plans",
    "docs/en/skills/dividend-growth-pullback-screener.md": "{{ '/en/getting-started/' | relative_url }}#fmp-plans",
    "docs/ja/skills/dividend-growth-pullback-screener.md": "{{ '/ja/getting-started/' | relative_url }}#fmp-plans",
}

FORBIDDEN = (
    "ideal for free-tier API users",
    "Free tier (250 calls/day) is sufficient for FMP-only mode",
    "stays within free tier limits",
    "sufficient for two-stage screening",
    "無料ティアのAPIユーザーに最適",
    "無料枠内に収まる",
    "FMP無料枠",
)


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _note_section(relative_path: str) -> str:
    lines = _text(relative_path).splitlines()
    for index, line in enumerate(lines):
        if index == 0 or line.strip() != "{: #fmp-plans }":
            continue
        heading = re.match(r"(#+)\s", lines[index - 1])
        if not heading:
            continue
        level = len(heading.group(1))
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            next_heading = re.match(r"(#+)\s", lines[next_index])
            if next_heading and len(next_heading.group(1)) <= level:
                end = next_index
                break
        return "\n".join(lines[index - 1 : end])
    raise AssertionError(f"{relative_path} has no #fmp-plans note section")


def test_note_names_the_plan_gated_endpoints() -> None:
    for path, phrase in NOTE_PAGES.items():
        section = _note_section(path)
        assert phrase in section, f"{path} must name the plan-gated caveat"
        assert PRICING_PAGE in section
        assert "HTTP 402" in section
        assert "13F" in section
        for paragraph in re.split(r"\n\s*\n", section):
            if "13F" in paragraph:
                assert "402" not in paragraph and "403" not in paragraph, (
                    f"{path} must not claim 13F returned 402/403: {paragraph!r}"
                )


def test_skill_and_reference_files_point_to_the_note() -> None:
    for path in SKILL_AND_REFERENCE_FILES:
        assert NOTE_REFERENCE in _text(path), f"{path} must reference {NOTE_REFERENCE}"


def test_rendered_pages_point_to_the_note() -> None:
    for path, anchor in RENDERED_PAGES.items():
        text = _text(path)
        assert anchor in text, f"{path} must link to its language's FMP plans note"


def test_old_free_tier_sufficiency_claims_are_gone() -> None:
    for path in (*SKILL_AND_REFERENCE_FILES, *RENDERED_PAGES):
        text = _text(path)
        for phrase in FORBIDDEN:
            assert phrase not in text, f"{path} still contains stale claim: {phrase!r}"
