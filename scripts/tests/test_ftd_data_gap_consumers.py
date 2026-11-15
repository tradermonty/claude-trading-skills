"""Issue #655: downstream consumers read ftd-detector's data-gap JSON as no confirmation.

The degraded ftd-detector output keeps ``quality_score.total_score`` and
``post_ftd_distribution.distribution_count`` as ints (0). The real
exposure-coach extractor gets 0, and the stanley-druckenmiller-investment
loader maps the report to state ``DATA_GAP`` (bottom confirmation 10, the
RALLY_FAILED floor), so a gap can never raise either downstream score.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"


def _load(monkeypatch, skill: str, module: str, local_deps: tuple[str, ...] = ()):
    scripts = SKILLS / skill / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    for dep in local_deps:  # make sure the skill's own sibling module is imported
        monkeypatch.delitem(sys.modules, dep, raising=False)
    name = f"issue655_{skill.replace('-', '_')}_{module}"
    spec = importlib.util.spec_from_file_location(name, scripts / f"{module}.py")
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def ftd_monitor(monkeypatch):
    return _load(monkeypatch, "ftd-detector", "post_ftd_monitor", ("_price_bars",))


@pytest.fixture
def consumers(monkeypatch):
    loader = _load(monkeypatch, "stanley-druckenmiller-investment", "report_loader")
    scorer = _load(monkeypatch, "stanley-druckenmiller-investment", "scorer")
    exposure = _load(monkeypatch, "exposure-coach", "calculate_exposure", ("provenance_contract",))
    return loader, scorer, exposure


def _gapped_ftd_json(ftd_monitor) -> dict:
    """An FTD_CONFIRMED run whose post-FTD distribution check hit a data gap."""
    distribution = {
        "distribution_count": 0,
        "days_monitored": 0,
        "earliest_distribution_day": None,
        "details": [],
        "data_gap": True,
        "reason": "Data gap: 1 bar(s) with missing or invalid close/volume",
    }
    market_state = {
        "combined_state": "FTD_CONFIRMED",
        "dual_confirmation": False,
        "sp500": {"ftd": {"ftd_detected": True, "ftd_day_number": 5, "gain_pct": 2.1}},
        "nasdaq": {},
        "post_ftd_distribution": distribution,
        "ftd_invalidation": {"invalidated": False},
    }
    quality = ftd_monitor.calculate_ftd_quality_score(market_state)
    assert quality["total_score"] == 0 and quality["signal"] == "Unavailable: data gap"
    return {
        "market_state": {
            "combined_state": "FTD_CONFIRMED",
            "dual_confirmation": False,
            "ftd_index": "S&P 500",
            "data_gap": True,
        },
        "data_gap": True,
        "quality_score": quality,
        "post_ftd_distribution": distribution,
    }


@pytest.mark.parametrize("marker", ["all", "market_state_only", "signal_only"])
def test_druckenmiller_and_exposure_coach_read_gap_as_no_confirmation(
    ftd_monitor, consumers, marker
):
    loader, scorer, exposure = consumers
    data = _gapped_ftd_json(ftd_monitor)
    if marker != "all":
        del data["data_gap"]
    if marker == "signal_only":
        del data["market_state"]["data_gap"]

    signal = loader._extract_ftd(data)
    assert signal["state"] == "DATA_GAP"
    assert signal["quality_score"] == 0
    assert signal["post_ftd_distribution_count"] == 0
    assert signal["exposure_range"] == "0-25%"
    bottom = scorer.calculate_bottom_confirmation({"ftd_detector": signal})
    # DATA_GAP scores as low as RALLY_FAILED, below FTD_INVALIDATED (15)
    assert bottom == 10
    invalidated = scorer.calculate_bottom_confirmation(
        {"ftd_detector": {"state": "FTD_INVALIDATED", "quality_score": 0}}
    )
    assert bottom < invalidated

    assert exposure.extract_ftd_score(data) == 0


def test_insufficient_qqq_run_stays_no_ftd(ftd_monitor, consumers):
    loader, scorer, exposure = consumers
    quality = ftd_monitor.calculate_ftd_quality_score(
        {
            "sp500": {"state": "FTD_WINDOW", "ftd": {"ftd_detected": False}},
            "nasdaq": {"state": "NO_SIGNAL", "error": "Insufficient data"},
        }
    )
    assert quality["signal"] == "No FTD"
    assert "data_gap" not in quality
    data = {"market_state": {"combined_state": "FTD_WINDOW"}, "quality_score": quality}
    assert exposure.extract_ftd_score(data) == 0
    signal = loader._extract_ftd(data)
    assert scorer.calculate_bottom_confirmation({"ftd_detector": signal}) == 60
