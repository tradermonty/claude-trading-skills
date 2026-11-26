"""Issue #778 follow-up: shipped skills the collector must be able to trace.

downtrend-duration-analyzer used a dynamic importlib loader, so the collector
could not trace its delegated FMP timeout. It must stay free of findings so its
``security_review`` can stay ``passed``. theme-detector may only keep the
documented yfinance gap.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def collector():
    path = ROOT / "scripts" / "backfill_security_review.py"
    spec = importlib.util.spec_from_file_location("shipped_skill_trace_collector", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_downtrend_client_is_statically_traceable(collector):
    result = collector.mechanical_checks("downtrend-duration-analyzer", ROOT)
    assert result["network_timeout_findings"] == []
    assert result["findings"] == []
    assert result["clean"] is True
    assert result["network_applicability"] == "network"


def test_theme_detector_only_has_the_documented_yfinance_gap(collector):
    """The FMP/requests/finviz paths are proven; yfinance stays an honest gap.

    ``yf.download`` carries an explicit timeout and ``Ticker.info`` runs under a
    caller deadline, but the collector cannot prove an SDK call, so the skill
    stays ``not_verified``. A finding anywhere else is a regression.
    """
    result = collector.mechanical_checks("theme-detector", ROOT)
    assert result["findings"], "yfinance SDK calls are not provable by the collector"
    assert all(f.startswith("scripts/etf_scanner.py") for f in result["findings"])
    assert all("yf." in f or "no proven request timeout" in f for f in result["findings"])
    assert result["exception_key_leak_findings"] == []
