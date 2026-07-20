"""Regression checks for hand-maintained crypto-regime documentation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JA_PAGE = ROOT / "docs" / "ja" / "skills" / "crypto-regime-analyzer.md"


def test_crypto_regime_ja_page_is_a_real_translation() -> None:
    text = JA_PAGE.read_text(encoding="utf-8")

    assert "generated: false" in text
    assert "not yet been translated into Japanese" not in text
    assert "## 1. 概要" in text
    assert "## 5. ワークフロー" in text
    assert "暗号資産市場" in text
