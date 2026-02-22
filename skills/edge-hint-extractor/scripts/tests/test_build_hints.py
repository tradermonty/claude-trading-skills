"""Unit tests for build_hints.py."""

from datetime import date
from subprocess import CompletedProcess

import build_hints as bh


def test_build_rule_hints_generates_market_and_news_hints() -> None:
    hints = bh.build_rule_hints(
        market_summary={"regime_label": "RiskOn", "pct_above_ma50": 0.66, "vol_trend": 1.12},
        anomalies=[
            {"symbol": "CPRT", "metric": "gap", "z": -3.2},
            {"symbol": "NVDA", "metric": "rel_volume", "z": 3.1},
        ],
        news_rows=[
            {"symbol": "TSLA", "timestamp": "2026-02-20T21:00:00Z", "reaction_1d": -0.12},
        ],
        max_anomaly_hints=5,
        news_threshold=0.06,
    )

    titles = [hint["title"] for hint in hints]
    assert any("Breadth-supported breakout regime" in title for title in titles)
    assert any("Participation spike in NVDA" in title for title in titles)
    assert any("News shock reversal in TSLA" in title for title in titles)


def test_generate_llm_hints_parses_hints_dict(monkeypatch) -> None:
    stdout = """
hints:
  - title: LLM momentum idea
    observation: strong leaders pushing highs
    preferred_entry_family: pivot_breakout
    symbols: [NVDA]
"""

    def fake_run(*args, **kwargs):
        return CompletedProcess(args=args[0], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(bh.subprocess, "run", fake_run)
    hints = bh.generate_llm_hints(
        llm_command="fake-llm-cli",
        payload={"as_of": date(2026, 2, 20).isoformat()},
    )

    assert len(hints) == 1
    assert hints[0]["preferred_entry_family"] == "pivot_breakout"
    assert hints[0]["symbols"] == ["NVDA"]
