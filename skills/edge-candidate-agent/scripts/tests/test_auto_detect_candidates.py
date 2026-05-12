"""Unit tests for auto_detect_candidates.py (pandas-independent parts)."""

from datetime import date
from pathlib import Path
from subprocess import CompletedProcess

import auto_detect_candidates as adc
import pytest


def test_infer_entry_family_from_text_detects_breakout() -> None:
    text = "AI leaders are breaking out to new highs with base contraction"
    assert adc.infer_entry_family_from_text(text) == "pivot_breakout"


def test_infer_entry_family_from_text_detects_gap() -> None:
    text = "Post-earnings gap and follow-through looks strong"
    assert adc.infer_entry_family_from_text(text) == "gap_up_continuation"


def test_normalize_hints_and_hint_boost() -> None:
    hints = adc.normalize_hints(
        [
            {
                "title": "Earnings continuation",
                "preferred_entry_family": "gap_up_continuation",
                "symbols": ["NVDA", "msft"],
            }
        ]
    )
    boost, titles = adc.hint_match_boost("NVDA", "gap_up_continuation", hints)
    assert boost > 0
    assert titles == ["Earnings continuation"]


def test_score_functions_clamp_to_valid_range() -> None:
    breakout = adc.score_breakout_candidate(
        {
            "rs_rank_pct": 1.5,
            "rel_volume": 8.0,
            "close_pos": 1.2,
            "atr_pct": 0.03,
            "close": 120.0,
            "high20_prev": 100.0,
        },
        regime_label="RiskOn",
    )
    gap = adc.score_gap_candidate(
        {
            "gap": 0.2,
            "rel_volume": 8.0,
            "close_pos": 1.2,
            "close": 100.0,
            "ma50": 90.0,
            "ma200": 80.0,
            "atr_pct": 0.04,
        },
        regime_label="RiskOn",
    )
    assert 0.0 <= breakout <= 100.0
    assert 0.0 <= gap <= 100.0


def test_build_ticket_payload_exportable_contains_validation() -> None:
    payload = adc.build_ticket_payload(
        candidate={
            "symbol": "NVDA",
            "entry_family": "pivot_breakout",
            "hypothesis_type": "breakout",
            "priority_score": 88.5,
            "close": 120.0,
            "rel_volume": 2.2,
            "gap": 0.01,
            "close_pos": 0.75,
            "rs_rank_pct": 0.92,
            "conditions": ["close > high20_prev"],
            "trend_filter": ["price > sma_200"],
        },
        as_of_date=date(2026, 2, 20),
        regime_label="RiskOn",
        rank=1,
        market_summary={"pct_above_ma50": 0.65, "avg_pair_corr_20": 0.28, "vol_trend": 0.9},
    )
    assert payload["entry_family"] == "pivot_breakout"
    assert payload["validation"]["method"] == "full_sample"
    assert "entry" in payload


def test_build_ticket_payload_research_only_sets_flag() -> None:
    payload = adc.build_ticket_payload(
        candidate={
            "symbol": "MARKET_BASKET",
            "entry_family": None,
            "hypothesis_type": "regime_shift",
            "priority_score": 72.0,
            "description": "Regime inflection candidate",
        },
        as_of_date=date(2026, 2, 20),
        regime_label="Neutral",
        rank=1,
        market_summary={"pct_above_ma50": 0.48, "avg_pair_corr_20": 0.41, "vol_trend": 1.02},
    )
    assert payload["research_only"] is True
    assert "validation" not in payload
    assert payload["hypothesis_type"] == "regime_shift"


def test_generate_llm_hints_parses_yaml(monkeypatch) -> None:
    stdout = """
hints:
  - title: Momentum leaders
    preferred_entry_family: pivot_breakout
    symbols: [NVDA]
"""

    def fake_run(*args, **kwargs):
        return CompletedProcess(args=args[0], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(adc.subprocess, "run", fake_run)
    hints = adc.generate_llm_hints(
        llm_command="fake-llm-cli",
        as_of_date=date(2026, 2, 20),
        market_summary={"risk_on_score": 70},
        anomalies=[],
    )
    assert len(hints) == 1
    assert hints[0]["entry_family"] == "pivot_breakout"


def test_infer_entry_family_from_text_detects_panic_reversal() -> None:
    text = "Capitulation selloff with oversold reversal signal"
    assert adc.infer_entry_family_from_text(text) == "panic_reversal"


def test_infer_entry_family_from_text_detects_news_reaction() -> None:
    text = "Binary event catalyst with news reaction signal"
    assert adc.infer_entry_family_from_text(text) == "news_reaction"


def test_build_ticket_payload_news_reaction_observation() -> None:
    payload = adc.build_ticket_payload(
        candidate={
            "symbol": "AAPL",
            "entry_family": "news_reaction",
            "hypothesis_type": "news_reaction",
            "priority_score": 75.0,
            "close": 180.0,
            "rel_volume": 3.5,
            "gap": 0.08,
            "close_pos": 0.65,
            "rs_rank_pct": 0.50,
            "reaction_1d": -0.09,
            "conditions": ["abs_reaction_1d >= 0.06"],
            "trend_filter": ["validate_follow_through_d2"],
        },
        as_of_date=date(2026, 2, 20),
        regime_label="Neutral",
        rank=1,
        market_summary={"pct_above_ma50": 0.50},
    )
    assert payload["entry_family"] == "news_reaction"
    assert payload["observation"]["abs_reaction_1d"] == 0.09
    assert payload["observation"]["reaction_direction"] == "down"


def test_build_ticket_payload_panic_reversal_hypothesis() -> None:
    payload = adc.build_ticket_payload(
        candidate={
            "symbol": "TSLA",
            "entry_family": "panic_reversal",
            "hypothesis_type": "panic_reversal",
            "priority_score": 80.0,
            "close": 200.0,
            "rel_volume": 2.5,
            "gap": -0.08,
            "close_pos": 0.30,
            "rs_rank_pct": 0.20,
            "conditions": ["ret_1d <= -0.07"],
            "trend_filter": ["price > sma_200 * 0.85"],
        },
        as_of_date=date(2026, 2, 20),
        regime_label="RiskOff",
        rank=1,
        market_summary={"pct_above_ma50": 0.30},
    )
    assert payload["entry_family"] == "panic_reversal"
    assert "rebound probability" in payload["hypothesis"]


def test_scan_news_reaction_candidates_canonical_conditions() -> None:
    """Verify scanner emits canonical threshold conditions, not raw values."""
    pytest.importorskip("pandas")
    import pandas as pd

    news = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "timestamp": pd.to_datetime(["2026-02-20", "2026-02-20"], utc=True),
            "reaction_1d": [0.12, -0.08],
        }
    )
    candidates, available = adc.scan_news_reaction_candidates(
        news_table=news,
        target_date=date(2026, 2, 20),
        tradable=None,
        top_n=4,
    )
    assert available is True
    assert len(candidates) == 2
    # All candidates must use canonical thresholds, not observed values
    for c in candidates:
        assert c["entry_family"] == "news_reaction"
        assert "abs_reaction_1d >= 0.06" in c["conditions"]
        assert "rel_volume >= 2.0" in c["conditions"]
        # Must NOT contain raw observed value like "reaction_1d=0.12"
        for cond in c["conditions"]:
            assert not cond.startswith("reaction_1d=")


def test_scan_news_reaction_candidates_with_tradable_join() -> None:
    """Verify tradable join enriches candidates with OHLCV columns."""
    pytest.importorskip("pandas")
    import pandas as pd

    news = pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "timestamp": pd.to_datetime(["2026-02-20"], utc=True),
            "reaction_1d": [0.10],
        }
    )
    tradable = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "rel_volume": [3.0, 1.5],
            "close_pos": [0.8, 0.4],
            "atr_pct": [0.025, 0.020],
        }
    )
    candidates, _ = adc.scan_news_reaction_candidates(
        news_table=news,
        target_date=date(2026, 2, 20),
        tradable=tradable,
        top_n=4,
    )
    assert len(candidates) == 1
    assert candidates[0]["symbol"] == "AAPL"
    assert candidates[0]["entry_family"] == "news_reaction"


def test_load_ohlcv_table_reads_csv(tmp_path: Path) -> None:
    """_load_ohlcv_table sniffs .csv extension and uses pd.read_csv."""
    pytest.importorskip("pandas")
    import pandas as pd

    csv_path = tmp_path / "tiny.csv"
    pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL"],
            "timestamp": ["2026-02-19", "2026-02-20"],
            "open": [180.0, 181.0],
            "high": [182.0, 183.0],
            "low": [179.0, 180.5],
            "close": [181.0, 182.5],
            "volume": [1_000_000, 1_100_000],
        }
    ).to_csv(csv_path, index=False)

    df = adc._load_ohlcv_table(csv_path)
    assert list(df.columns) == ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 2


def test_load_ohlcv_table_rejects_unknown_extension(tmp_path: Path) -> None:
    """_load_ohlcv_table raises AutoDetectError for unsupported extensions."""
    pytest.importorskip("pandas")
    bogus = tmp_path / "ohlcv.xlsx"
    bogus.write_text("not really xlsx")
    with pytest.raises(adc.AutoDetectError, match="unsupported OHLCV format"):
        adc._load_ohlcv_table(bogus)


def test_load_ohlcv_table_rejects_no_extension(tmp_path: Path) -> None:
    """_load_ohlcv_table raises AutoDetectError for files without extensions."""
    pytest.importorskip("pandas")
    bogus = tmp_path / "ohlcv"
    bogus.write_text("symbol,timestamp\n")
    with pytest.raises(adc.AutoDetectError, match="unsupported OHLCV format"):
        adc._load_ohlcv_table(bogus)


def test_generate_llm_hints_raises_on_failure(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return CompletedProcess(args=args[0], returncode=1, stdout="", stderr="failure")

    monkeypatch.setattr(adc.subprocess, "run", fake_run)
    with pytest.raises(adc.AutoDetectError, match="LLM ideas command failed"):
        adc.generate_llm_hints(
            llm_command="fake-llm-cli",
            as_of_date=date(2026, 2, 20),
            market_summary={"risk_on_score": 70},
            anomalies=[],
        )
