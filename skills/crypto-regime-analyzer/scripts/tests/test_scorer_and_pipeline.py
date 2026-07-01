"""Tests for the composite scorer and end-to-end offline analysis."""

from crypto_regime_analyzer import run_analysis
from scorer import COMPONENT_WEIGHTS, calculate_composite_score


def _comp(score, available=True):
    return {"score": score, "signal": "test", "data_available": available}


def test_all_components_full_weights():
    components = {cid: _comp(80) for cid in COMPONENT_WEIGHTS}
    result = calculate_composite_score(components)
    assert result["score"] == 80.0
    assert result["zone"] == "RISK_ON"
    assert result["components_available"] == 6
    assert abs(sum(result["effective_weights"].values()) - 1.0) < 1e-6


def test_weight_redistribution_on_missing_component():
    components = {cid: _comp(60) for cid in COMPONENT_WEIGHTS}
    components["funding"] = _comp(0, available=False)
    result = calculate_composite_score(components)
    assert result["score"] == 60.0  # missing weight redistributed, others equal
    assert result["components_available"] == 5
    assert "funding" not in result["effective_weights"]


def test_zone_boundaries():
    for score, zone in [
        (85, "RISK_ON"),
        (70, "CONSTRUCTIVE"),
        (50, "NEUTRAL"),
        (30, "DEFENSIVE"),
        (10, "RISK_OFF"),
    ]:
        components = {cid: _comp(score) for cid in COMPONENT_WEIGHTS}
        assert calculate_composite_score(components)["zone"] == zone


def test_no_data_returns_unknown():
    components = {cid: _comp(50, available=False) for cid in COMPONENT_WEIGHTS}
    result = calculate_composite_score(components)
    assert result["score"] is None
    assert result["zone"] == "UNKNOWN"


def test_end_to_end_bull_snapshot(trending_series, universe):
    series = universe(n_up=8, n_down=1)
    series["BTC"] = trending_series(n=400, daily_pct=0.3)
    snapshot = {
        "as_of": "2026-07-01T00:00:00Z",
        "series": series,
        "dominance_series": [58 - i * 0.1 for i in range(40)],  # falling dom
        "funding": {"BTCUSDT": 0.0001, "ETHUSDT": 0.00009},
    }
    analysis = run_analysis(snapshot)
    assert analysis["composite"]["components_available"] == 6
    assert analysis["composite"]["zone"] in ("RISK_ON", "CONSTRUCTIVE")
    assert analysis["metadata"]["universe_size"] == 10


def test_end_to_end_bear_snapshot(trending_series, universe):
    series = universe(n_up=1, n_down=8)
    series["BTC"] = trending_series(n=400, daily_pct=-0.3)
    snapshot = {
        "as_of": "2026-07-01T00:00:00Z",
        "series": series,
        "dominance_series": [55 - i * 0.1 for i in range(40)],  # falling dom, BTC down
        "funding": {"BTCUSDT": 0.0005, "ETHUSDT": 0.0004},
    }
    analysis = run_analysis(snapshot)
    assert analysis["composite"]["zone"] in ("DEFENSIVE", "RISK_OFF")


def test_end_to_end_degrades_without_dominance_and_funding(trending_series, universe):
    series = universe(n_up=8, n_down=1)
    series["BTC"] = trending_series(n=400, daily_pct=0.3)
    snapshot = {"series": series, "dominance_series": [], "funding": {}}
    analysis = run_analysis(snapshot)
    assert analysis["composite"]["components_available"] == 4
    assert analysis["composite"]["score"] is not None
