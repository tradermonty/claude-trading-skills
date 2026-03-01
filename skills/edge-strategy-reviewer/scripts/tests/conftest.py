"""Test configuration for edge-strategy-reviewer scripts."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def well_formed_breakout_draft() -> dict:
    """A well-formed breakout draft that should PASS all criteria."""
    return {
        "id": "draft_edge_concept_breakout_behavior_riskon_core",
        "concept_id": "edge_concept_breakout_behavior_riskon",
        "name": "Participation-backed trend breakout (core)",
        "variant": "core",
        "export_ready_v1": True,
        "entry_family": "pivot_breakout",
        "hypothesis_type": "breakout",
        "mechanism_tag": "behavior",
        "regime": "RiskOn",
        "thesis": "Price breakouts above 20-day highs with above-average volume indicate institutional participation and momentum continuation.",
        "entry": {
            "conditions": [
                "close > high20_prev",
                "rel_volume >= 2",
                "close > ma50 > ma200",
            ],
            "trend_filter": [
                "price > sma_200",
                "price > sma_50",
                "sma_50 > sma_200",
            ],
        },
        "exit": {
            "stop_loss_pct": 0.07,
            "take_profit_rr": 3.0,
        },
        "risk": {
            "risk_per_trade": 0.01,
            "max_positions": 5,
            "max_sector_exposure": 0.3,
        },
        "invalidation_signals": [
            "Breakout fails within 3 days",
            "Volume dries up below average",
            "Broad market enters risk-off regime",
        ],
        "validation_plan": {
            "period": "2016-01-01 to latest",
            "entry_timing": "next_open",
            "hold_days": [5, 20, 60],
            "success_criteria": [
                "expected_value_after_costs > 0",
                "stable across regimes and subperiods",
            ],
        },
    }


@pytest.fixture()
def empty_thesis_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with empty thesis -- should fail C1."""
    d = dict(well_formed_breakout_draft)
    d["thesis"] = ""
    return d


@pytest.fixture()
def generic_thesis_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with generic thesis (short, no domain terms) -- should warn C1."""
    d = dict(well_formed_breakout_draft)
    d["thesis"] = "Buy stocks that are going up soon"
    return d


@pytest.fixture()
def excessive_conditions_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with 11 conditions+trend_filter -- should warn C2."""
    d = dict(well_formed_breakout_draft)
    d["entry"] = {
        "conditions": [
            "close > high20_prev",
            "rel_volume >= 2",
            "close > ma50",
            "close > ma200",
            "RSI > 50",
            "MACD > 0",
            "ADX > 25",
            "close > vwap",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
        ],
    }
    return d


@pytest.fixture()
def extreme_conditions_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with 13 conditions+trend_filter -- should fail C2."""
    d = dict(well_formed_breakout_draft)
    d["entry"] = {
        "conditions": [
            "close > high20_prev",
            "rel_volume >= 2",
            "close > ma50",
            "close > ma200",
            "RSI > 50",
            "MACD > 0",
            "ADX > 25",
            "close > vwap",
            "stochastic > 80",
            "OBV rising",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
        ],
    }
    return d


@pytest.fixture()
def precise_threshold_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with precise decimal thresholds -- should get C2 penalty."""
    d = dict(well_formed_breakout_draft)
    d["entry"] = {
        "conditions": [
            "RSI > 33.5",
            "volume > 1.73 * avg_volume",
            "close > ma50 * 1.025",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
        ],
    }
    return d


@pytest.fixture()
def restrictive_conditions_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with regime + many conditions -- should warn C3 (est ~20/yr)."""
    d = dict(well_formed_breakout_draft)
    d["regime"] = "RiskOn"
    d["entry"] = {
        "conditions": [
            "close > high20_prev",
            "rel_volume >= 2",
            "close > ma50",
            "close > ma200",
            "RSI > 50",
            "MACD > 0",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
        ],
    }
    return d


@pytest.fixture()
def extreme_restriction_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with extreme restriction -- should fail C3."""
    d = dict(well_formed_breakout_draft)
    d["regime"] = "RiskOn"
    d["entry"] = {
        "conditions": [
            "sector == Technology",
            "close > high20_prev",
            "rel_volume >= 1.5",
            "close > ma50",
            "close > ma200",
            "RSI > 50",
            "MACD > 0",
            "ADX > 25",
            "close > vwap",
            "stochastic > 80",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
            "sma_20 > sma_50",
        ],
    }
    return d


@pytest.fixture()
def single_regime_no_validation_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with single regime and no cross-regime validation -- should warn C4."""
    d = dict(well_formed_breakout_draft)
    d["regime"] = "RiskOn"
    d["validation_plan"] = {
        "period": "2016-01-01 to latest",
        "entry_timing": "next_open",
        "hold_days": [5, 20, 60],
        "success_criteria": [
            "expected_value_after_costs > 0",
        ],
    }
    return d


@pytest.fixture()
def unreasonable_stop_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with stop_loss > 15% -- should fail C5."""
    d = dict(well_formed_breakout_draft)
    d["exit"] = {
        "stop_loss_pct": 0.20,
        "take_profit_rr": 3.0,
    }
    return d


@pytest.fixture()
def low_rr_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with take_profit_rr < 1.5 -- should fail C5."""
    d = dict(well_formed_breakout_draft)
    d["exit"] = {
        "stop_loss_pct": 0.07,
        "take_profit_rr": 1.0,
    }
    return d


@pytest.fixture()
def high_risk_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with risk_per_trade > 1.5% -- should warn C6."""
    d = dict(well_formed_breakout_draft)
    d["risk"] = {
        "risk_per_trade": 0.018,
        "max_positions": 5,
        "max_sector_exposure": 0.3,
    }
    return d


@pytest.fixture()
def extreme_risk_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with risk_per_trade > 2% -- should fail C6."""
    d = dict(well_formed_breakout_draft)
    d["risk"] = {
        "risk_per_trade": 0.025,
        "max_positions": 5,
        "max_sector_exposure": 0.3,
    }
    return d


@pytest.fixture()
def no_volume_filter_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with no volume filter in conditions -- should warn C7."""
    d = dict(well_formed_breakout_draft)
    d["entry"] = {
        "conditions": [
            "close > high20_prev",
            "close > ma50 > ma200",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
        ],
    }
    return d


@pytest.fixture()
def wrong_family_export_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with export_ready_v1=true but non-exportable family -- should fail C7."""
    d = dict(well_formed_breakout_draft)
    d["export_ready_v1"] = True
    d["entry_family"] = "mean_reversion"
    return d


@pytest.fixture()
def empty_invalidation_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with empty invalidation_signals -- should fail C8."""
    d = dict(well_formed_breakout_draft)
    d["invalidation_signals"] = []
    return d


@pytest.fixture()
def insufficient_invalidation_draft(well_formed_breakout_draft: dict) -> dict:
    """Draft with only 1 invalidation signal -- should warn C8."""
    d = dict(well_formed_breakout_draft)
    d["invalidation_signals"] = ["Breakout fails quickly"]
    return d


@pytest.fixture()
def research_probe_draft() -> dict:
    """A research probe draft that should PASS but not be export eligible."""
    return {
        "id": "draft_edge_concept_news_reaction_research_probe",
        "concept_id": "edge_concept_news_reaction",
        "name": "Event overreaction and drift (research_probe)",
        "variant": "research_probe",
        "export_ready_v1": False,
        "entry_family": "research_only",
        "hypothesis_type": "news_reaction",
        "mechanism_tag": "behavior",
        "regime": "Neutral",
        "thesis": "Stocks with large negative earnings surprises show post-event drift as institutional investors slowly adjust positions over multiple days.",
        "entry": {
            "conditions": [
                "earnings_surprise < -0.10",
                "volume > 2 * avg_volume_50",
            ],
            "trend_filter": [
                "price > sma_200",
            ],
        },
        "exit": {
            "stop_loss_pct": 0.05,
            "take_profit_rr": 2.2,
        },
        "risk": {
            "risk_per_trade": 0.005,
            "max_positions": 3,
            "max_sector_exposure": 0.3,
        },
        "invalidation_signals": [
            "Price recovers within 1 day",
            "Volume normalizes immediately",
        ],
        "validation_plan": {
            "period": "2016-01-01 to latest",
            "entry_timing": "next_open",
            "hold_days": [5, 20],
            "success_criteria": [
                "expected_value_after_costs > 0",
                "stable across regimes and subperiods",
            ],
        },
    }
