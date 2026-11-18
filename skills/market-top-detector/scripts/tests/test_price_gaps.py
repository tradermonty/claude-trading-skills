"""Missing OHLCV must never become a healthy market verdict (#655)."""

import copy
import json

import pytest
from calculators.defensive_rotation_calculator import (
    DEFENSIVE_ETFS,
    OFFENSIVE_ETFS,
    calculate_defensive_rotation,
)
from calculators.distribution_day_calculator import calculate_distribution_days
from calculators.index_technical_calculator import calculate_index_technical
from calculators.leading_stock_calculator import calculate_leading_stock_health
from helpers import make_history
from report_generator import generate_json_report, generate_markdown_report
from scenario_engine import generate_scenarios
from scorer import COMPONENT_WEIGHTS, calculate_composite_score, detect_follow_through_day


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), False, -1])
@pytest.mark.parametrize("component", ["distribution", "technical", "leading", "rotation", "ftd"])
def test_invalid_close_makes_signal_explicitly_unavailable(component, bad):
    clean = make_history([120 - i * 0.1 for i in range(210)])
    broken = copy.deepcopy(clean)
    broken[0]["close"] = bad  # valid adjClose must not mask invalid primary
    if component == "distribution":
        result = calculate_distribution_days(broken, clean)
    elif component == "technical":
        result = calculate_index_technical(broken, clean)
    elif component == "leading":
        result = calculate_leading_stock_health(
            {"A": {"price": 120, "yearHigh": 130}}, {"A": broken}
        )
    elif component == "rotation":
        histories = {s: clean for s in DEFENSIVE_ETFS + OFFENSIVE_ETFS}
        histories["XLU"] = broken
        result = calculate_defensive_rotation(histories)
    else:
        result = detect_follow_through_day(broken, 60)
    assert result.get("data_available") is False, result
    assert result.get("data_gaps"), result
    assert "unavailable" in result.get("signal", result.get("reason", "")).lower()


@pytest.mark.parametrize("field", ["close", "volume"])
def test_missing_distribution_field_is_not_clear(field):
    hist = make_history([100] * 30)
    del hist[0][field]
    if field == "close":
        del hist[0]["adjClose"]
    result = calculate_distribution_days(hist, make_history([100] * 30))
    assert result.get("data_available") is False
    assert "CLEAR" not in result["signal"]


def test_missing_close_can_use_existing_adjusted_close_fallback():
    hist = make_history([100 + i for i in range(30)])
    expected = calculate_distribution_days(hist, hist)
    fallback = copy.deepcopy(hist)
    del fallback[0]["close"]
    assert calculate_distribution_days(fallback, fallback) == expected


def test_zero_volume_is_valid_and_unused_old_fields_do_not_block():
    hist = make_history([100 + i for i in range(210)])
    hist[0]["volume"] = 0
    hist[100].pop("volume")
    hist[100].pop("open")
    hist[100].pop("low")
    result = calculate_index_technical(hist, hist)
    assert result["data_available"] is True


def test_rotation_ignores_unread_interior_bars():
    hist = make_history([100 + i for i in range(50)])
    expected = calculate_defensive_rotation({s: hist for s in DEFENSIVE_ETFS + OFFENSIVE_ETFS})
    unused = copy.deepcopy(hist)
    del unused[3]["close"]
    del unused[3]["adjClose"]
    assert (
        calculate_defensive_rotation({s: unused for s in DEFENSIVE_ETFS + OFFENSIVE_ETFS})
        == expected
    )


def test_unavailable_component_is_not_weighted_or_rendered_healthy(tmp_path):
    hist = make_history([100] * 30)
    hist[0].pop("volume")
    dd = calculate_distribution_days(hist, hist)
    scores = {key: 0 for key in COMPONENT_WEIGHTS}
    scores["distribution_days"] = dd["score"]
    avail = {key: True for key in COMPONENT_WEIGHTS}
    avail["distribution_days"] = dd.get("data_available", True)
    composite = calculate_composite_score(scores, avail)
    assert composite["component_scores"]["distribution_days"]["weighted_contribution"] == 0
    analysis = {"composite": composite, "components": {"distribution_days": dd}}
    path = tmp_path / "report.md"
    generate_markdown_report(analysis, str(path))
    text = path.read_text()
    assert "UNAVAILABLE" in text and "N/A" in text
    assert "0 distribution + 0 stalling" not in text


def test_no_available_components_never_claims_green_or_budget(tmp_path):
    scores = {key: 50 for key in COMPONENT_WEIGHTS}
    avail = {key: False for key in COMPONENT_WEIGHTS}
    result = calculate_composite_score(scores, avail)
    assert result["composite_score"] is None
    assert "Green" not in result["zone"]
    assert result["risk_budget"] == "Not assessed"
    assert generate_scenarios(scores, avail) == []
    ftd = detect_follow_through_day(make_history([100] * 40), result["composite_score"])
    assert ftd.get("data_available") is False
    analysis = {"composite": result, "follow_through_day": ftd}
    path = tmp_path / "report.md"
    js = tmp_path / "report.json"
    generate_markdown_report(analysis, str(path))
    generate_json_report(analysis, str(js))
    assert "Green (Normal)" not in path.read_text()
    assert "N/A" in path.read_text()
    assert json.loads(js.read_text())["composite"]["composite_score"] is None


@pytest.mark.parametrize("instant", ["2026-01-14T03:00:00+00:00", "2026-07-15T03:00:00+00:00"])
def test_fake_provider_cli_propagates_gaps_and_handles_unassessed_previous_report(
    tmp_path, monkeypatch, capsys, instant
):
    from datetime import datetime, timedelta

    import market_top_detector as app

    frozen_now = datetime.fromisoformat(instant)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen_now.replace(tzinfo=None)
            return frozen_now.astimezone(tz)

    monkeypatch.setattr(app, "datetime", FrozenDateTime)
    # The host is already on the next UTC day in both standard and daylight time.
    # Match the CLI's New York cutoff so the deliberately broken latest bar survives.
    fixture_day = frozen_now.astimezone(app.ZoneInfo("America/New_York")).date()
    assert fixture_day < frozen_now.date()

    class FakeClient:
        healthy = False

        def get_quote(self, symbol):
            if symbol in ("^VIX", "^VIX3M"):
                return None
            return [{"symbol": symbol, "price": 120, "yearHigh": 130}]

        def history(self, days):
            rows = make_history([120 - i * 0.1 for i in range(min(days, 210))])
            for i, row in enumerate(rows):
                row["date"] = (fixture_day - timedelta(days=i)).isoformat()
            if not self.healthy:
                rows[0]["close"] = None
            return rows

        def get_historical_prices(self, symbol, days=260):
            return {"historical": self.history(days)}

        def get_batch_quotes(self, symbols):
            return {symbol: self.get_quote(symbol)[0] for symbol in symbols}

        def get_batch_historical(self, symbols, days=60):
            return {symbol: self.history(days) for symbol in symbols}

        def get_vix_term_structure(self):
            return None

        def get_api_stats(self):
            return {"api_calls_made": 0, "cache_entries": 0}

    client = FakeClient()
    monkeypatch.setattr(app, "FMPClient", lambda **kwargs: client)
    argv = ["--static-basket", "--no-auto-breadth", "--output-dir", str(tmp_path)]
    for healthy in (False, False, True, False):
        client.healthy = healthy
        assert app.main(argv) == 0
        captured = capsys.readouterr()
        report = json.loads(max(tmp_path.glob("market_top_*.json")).read_text())
        assert report["metadata"]["as_of_date"] == fixture_day.isoformat()
        assert report["components"]["distribution_days"].get("data_available", True) is healthy
        if not healthy:
            assert report["composite"]["composite_score"] is None
            assert report["composite"]["risk_budget"] == "Not assessed"
            assert "Risk Zone: Green" not in captured.out
            assert "Heuristic Risk Score: N/A/100" in captured.out
            assert report["components"]["distribution_days"]["sp500"]["distribution_days"] is None
        else:
            assert report["composite"]["composite_score"] is not None


def test_rotation_short_unusable_history_keeps_existing_partial_fetch_policy():
    hist = make_history([100 + i for i in range(50)])
    histories = {s: hist for s in DEFENSIVE_ETFS + OFFENSIVE_ETFS}
    histories["XLU"] = []
    expected = calculate_defensive_rotation(histories)
    histories["XLU"] = [{"close": None}]
    assert calculate_defensive_rotation(histories) == expected


def test_ftd_gap_diagnostic_identifies_latest_bad_session():
    hist = make_history([100] * 40)
    hist[0]["close"] = None
    hist[3]["close"] = float("nan")
    result = detect_follow_through_day(hist, 60)
    assert result["data_gaps"]["latest_bad"] == "day-0"


def test_actual_unavailable_producer_shape_is_rejected_by_consumers(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    result = calculate_composite_score(
        {key: 50 for key in COMPONENT_WEIGHTS}, {key: False for key in COMPONENT_WEIGHTS}
    )
    artifact = tmp_path / "unavailable.json"
    generate_json_report({"composite": result}, str(artifact))
    skills = Path(__file__).resolve().parents[3]
    exposure_code = """import json,sys
sys.path.insert(0,sys.argv[1])
from calculate_exposure import extract_top_risk_score
with open(sys.argv[2], encoding="utf-8") as handle:
    payload=json.load(handle)
assert extract_top_risk_score(payload) is None
"""
    stanley_code = """import json,sys
sys.path.insert(0,sys.argv[1])
from report_loader import extract_signal
try:
    extract_signal("market_top",json.load(open(sys.argv[2], encoding="utf-8")))
except ValueError:
    pass
else:
    raise AssertionError("unavailable report was accepted")
"""
    for skill, code in (
        ("exposure-coach", exposure_code),
        ("stanley-druckenmiller-investment", stanley_code),
    ):
        completed = subprocess.run(
            [sys.executable, "-c", code, str(skills / skill / "scripts"), str(artifact)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("missing_history", [None, []])
def test_rotation_missing_fetch_matches_absent_symbol(missing_history):
    hist = make_history([100 + i for i in range(50)])
    histories = {s: hist for s in DEFENSIVE_ETFS + OFFENSIVE_ETFS if s != "XLU"}
    expected = calculate_defensive_rotation(histories)
    histories["XLU"] = missing_history
    assert calculate_defensive_rotation(histories) == expected
