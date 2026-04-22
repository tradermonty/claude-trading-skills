"""Tests for the regime classifier logic in compute_regime.py.

No network. All tests use synthetic FRED-shaped data.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "macro-indicator-dashboard" / "scripts"))

import compute_regime as cr  # noqa: E402


def _make_series(values, freq="monthly", start_year=2020):
    """Build FRED-like observation list."""
    obs = []
    for i, v in enumerate(values):
        y = start_year + i // 12
        m = (i % 12) + 1
        obs.append({"date": f"{y}-{m:02d}-01", "value": float(v)})
    return {"frequency": freq, "observations": obs, "latest_date": obs[-1]["date"],
            "latest_value": obs[-1]["value"]}


def test_recession_regime():
    """Growth collapse + NFCI crisis => RECESSION."""
    data = {
        "as_of": "2026-04-21",
        "series": {
            "PAYEMS": _make_series([150_000 - i * 200 for i in range(24)]),  # falling
            "UNRATE": _make_series([3.5] * 12 + [3.5 + i * 0.2 for i in range(12)]),  # rising
            "ICSA":   _make_series([300_000 + i * 5000 for i in range(60)], freq="weekly"),
            "INDPRO": _make_series([100 - i * 0.5 for i in range(24)]),
            "CPILFESL": _make_series([100 + i * 0.2 for i in range(24)]),
            "PCEPI":  _make_series([100 + i * 0.2 for i in range(24)]),
            "T5YIE":  _make_series([2.0] * 24, freq="daily"),
            "NFCI":   _make_series([1.5] * 24, freq="weekly"),  # crisis
            "BAMLH0A0HYM2": _make_series([8.0] * 24, freq="daily"),
            "BAMLC0A0CM": _make_series([2.0] * 24, freq="daily"),
            "T10Y3M": _make_series([-0.5] * 24, freq="daily"),  # inverted
            "T10Y2Y": _make_series([-0.4] * 24, freq="daily"),
            "M2SL":   _make_series([100] * 24),
            "RRPONTSYD": _make_series([100] * 24, freq="daily"),
        },
    }
    growth_score, _ = cr.compute_growth_score(data)
    inflation_score, _ = cr.compute_inflation_score(data)
    regime, confidence = cr.classify_regime(growth_score, inflation_score, 1.5, None)
    assert regime == "RECESSION", f"got {regime}"
    assert confidence > 0


def test_goldilocks_regime():
    """Growth strong + inflation falling => GOLDILOCKS."""
    data = {
        "as_of": "2026-04-21",
        "series": {
            "PAYEMS": _make_series([150_000 + i * 300 for i in range(24)]),   # strong growth
            "UNRATE": _make_series([5.0 - i * 0.05 for i in range(24)]),       # falling UR
            "ICSA":   _make_series([220_000 - i * 500 for i in range(60)], freq="weekly"),
            "INDPRO": _make_series([100 + i * 0.5 for i in range(24)]),
            "CPILFESL": _make_series([100 + i * 0.05 for i in range(24)]),     # mild inflation
            "PCEPI":  _make_series([100 + i * 0.05 for i in range(24)]),
            "T5YIE":  _make_series([1.8] * 24, freq="daily"),
            "NFCI":   _make_series([-0.5] * 24, freq="weekly"),                # loose
            "BAMLH0A0HYM2": _make_series([3.0] * 24, freq="daily"),
            "BAMLC0A0CM": _make_series([1.0] * 24, freq="daily"),
            "T10Y3M": _make_series([1.5] * 24, freq="daily"),
            "T10Y2Y": _make_series([1.0] * 24, freq="daily"),
            "M2SL":   _make_series([100 + i * 0.5 for i in range(24)]),
            "RRPONTSYD": _make_series([500] * 24, freq="daily"),
        },
    }
    growth_score, _ = cr.compute_growth_score(data)
    inflation_score, _ = cr.compute_inflation_score(data)
    regime, _ = cr.classify_regime(growth_score, inflation_score, -0.5, None)
    assert regime == "GOLDILOCKS", f"got {regime} (growth={growth_score}, inf={inflation_score})"


def test_risk_on_score_bounds():
    assert 0 <= cr.compute_risk_on_score(-2, 2, -30, -15, -5) <= 100
    assert 0 <= cr.compute_risk_on_score(2, -2, 20, 15, 5) <= 100


def test_exposure_scale_mapping():
    assert cr.score_to_exposure_scale(100) == 1.00
    assert cr.score_to_exposure_scale(85) == 1.00
    assert cr.score_to_exposure_scale(70) == 0.85
    assert cr.score_to_exposure_scale(55) == 0.70
    assert cr.score_to_exposure_scale(40) == 0.50
    assert cr.score_to_exposure_scale(25) == 0.30
    assert cr.score_to_exposure_scale(0) == 0.10
    # monotone check
    last = cr.score_to_exposure_scale(0)
    for s in range(0, 101, 5):
        cur = cr.score_to_exposure_scale(s)
        assert cur >= last - 1e-9
        last = cur


def test_yield_curve_signal_inverted():
    data = {
        "series": {
            "T10Y3M": _make_series([-0.3], freq="daily"),
            "T10Y2Y": _make_series([-0.2], freq="daily"),
        }
    }
    detail, contribution = cr.compute_yield_curve(data)
    assert detail["t10y3m_signal"] == "inverted"
    assert contribution < 0


def test_yield_curve_signal_steep():
    data = {
        "series": {
            "T10Y3M": _make_series([1.8], freq="daily"),
            "T10Y2Y": _make_series([1.2], freq="daily"),
        }
    }
    detail, contribution = cr.compute_yield_curve(data)
    assert detail["t10y3m_signal"] == "steep"
    assert contribution > 0


def test_nfci_signal_classification():
    # very loose
    data = {"series": {"NFCI": _make_series([-0.7], freq="weekly"),
                       "BAMLH0A0HYM2": _make_series([3.0], freq="daily"),
                       "BAMLC0A0CM": _make_series([1.0], freq="daily")}}
    detail, _ = cr.compute_financial_conditions(data)
    assert detail["nfci_signal"] == "very_loose"

    # crisis level
    data = {"series": {"NFCI": _make_series([1.2], freq="weekly"),
                       "BAMLH0A0HYM2": _make_series([9.0], freq="daily"),
                       "BAMLC0A0CM": _make_series([2.8], freq="daily")}}
    detail, _ = cr.compute_financial_conditions(data)
    assert detail["nfci_signal"] == "tight"
    assert detail["hy_oas_signal"] == "stressed"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
