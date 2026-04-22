"""Tests for check_alerts.detect_alerts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "macro-indicator-dashboard" / "scripts"))

import check_alerts as ca  # noqa: E402


def _fixture(regime="SLOWDOWN", risk_on=50, nfci=0.0, t10y3m=1.0, sahm=0.0):
    return {
        "regime": regime,
        "risk_on_score": risk_on,
        "indicators": {
            "financial_conditions": {"nfci": nfci},
            "yield_curve": {"t10y3m": t10y3m},
            "growth": {"sahm_proxy_pp": sahm},
        },
    }


def test_no_alerts_when_stable():
    prev = _fixture()
    cur = _fixture()
    assert ca.detect_alerts(cur, prev) == []


def test_regime_change_alert():
    prev = _fixture(regime="GOLDILOCKS", risk_on=70)
    cur = _fixture(regime="SLOWDOWN", risk_on=55)
    alerts = ca.detect_alerts(cur, prev)
    assert any(a["type"] == "regime_change" for a in alerts)


def test_risk_on_swing_high():
    prev = _fixture(risk_on=70)
    cur = _fixture(risk_on=40)  # -30 move
    alerts = ca.detect_alerts(cur, prev)
    swing = [a for a in alerts if a["type"] == "risk_on_swing"]
    assert len(swing) == 1
    assert swing[0]["level"] == "high"


def test_risk_on_swing_medium():
    prev = _fixture(risk_on=60)
    cur = _fixture(risk_on=43)  # -17 move
    alerts = ca.detect_alerts(cur, prev)
    swing = [a for a in alerts if a["type"] == "risk_on_swing"]
    assert len(swing) == 1
    assert swing[0]["level"] == "medium"


def test_risk_on_swing_no_alert_below_threshold():
    prev = _fixture(risk_on=60)
    cur = _fixture(risk_on=50)  # -10 move, below threshold
    alerts = ca.detect_alerts(cur, prev)
    assert not any(a["type"] == "risk_on_swing" for a in alerts)


def test_nfci_sign_flip():
    prev = _fixture(nfci=-0.3)
    cur = _fixture(nfci=0.2)
    alerts = ca.detect_alerts(cur, prev)
    assert any(a["type"] == "nfci_sign_flip" for a in alerts)


def test_yield_curve_sign_flip():
    prev = _fixture(t10y3m=0.1)
    cur = _fixture(t10y3m=-0.1)
    alerts = ca.detect_alerts(cur, prev)
    assert any(a["type"] == "yield_curve_sign_flip" for a in alerts)


def test_sahm_trigger():
    prev = _fixture(sahm=0.3)
    cur = _fixture(sahm=0.55)
    alerts = ca.detect_alerts(cur, prev)
    sahm_alerts = [a for a in alerts if a["type"] == "sahm_trigger"]
    assert len(sahm_alerts) == 1
    assert sahm_alerts[0]["level"] == "critical"


def test_sahm_no_trigger_below_threshold():
    prev = _fixture(sahm=0.3)
    cur = _fixture(sahm=0.45)
    alerts = ca.detect_alerts(cur, prev)
    assert not any(a["type"] == "sahm_trigger" for a in alerts)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
