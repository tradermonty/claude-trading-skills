"""Regression checks for hand-maintained FXMacroData documentation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JA_PAGE = ROOT / "docs" / "ja" / "skills" / "fxmacrodata-calendar.md"


def test_fxmacrodata_ja_page_is_a_real_translation() -> None:
    text = JA_PAGE.read_text(encoding="utf-8")

    assert "generated: false" in text
    assert "not yet been translated into Japanese" not in text
    assert "## 1. 概要" in text
    assert "## 4. ワークフロー" in text
    assert "経済指標" in text
