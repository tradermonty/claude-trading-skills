"""Tests for the ftd-detector market status cap overlay."""

import json
import subprocess
import sys
from pathlib import Path

import calculate_exposure as ce
import pytest
from calculate_exposure import (
    apply_market_status_overlay,
    generate_markdown_report,
)

TESTS = Path(__file__).resolve().parent
SCRIPT = TESTS.parent / "calculate_exposure.py"
FIXTURES = TESTS / "fixtures"
REAL = FIXTURES / "ftd_real_shape"
LEGACY = FIXTURES / "legacy_baseline"


def ftd(
    status,
    state,
    days=None,
    sp500=None,
    nasdaq=None,
    reasons=(),
):
    """Minimal ftd-detector-shaped dict (the real-shape tests use generated fixtures)."""
    data = {
        "market_state": {"combined_state": state, "market_status": status, "data_gap": False},
        "sp500": {"market_status": sp500 if sp500 is not None else status},
        "nasdaq": {"market_status": nasdaq if nasdaq is not None else status},
        "quality_score": {"total_score": 60},
    }
    if reasons:
        for key in ("sp500", "nasdaq"):
            data[key]["cycle"] = {"pressure_reasons": list(reasons)}
    if days is not None:
        data["ftd_invalidation"] = {"invalidated": False, "days_since_ftd": days}
    return data


def real(name):
    return json.loads((REAL / f"{name}.json").read_text(encoding="utf-8"))


# --- constants ---------------------------------------------------------------


def test_constants_are_named_and_flagged_uncalibrated():
    assert ce.STATUS_CAP_CORRECTION == 20
    assert ce.UPTREND_RESUMED_CAP == 80
    source = SCRIPT.read_text(encoding="utf-8")
    assert "uncalibrated" in source.split("STATUS_CAP_CORRECTION")[0].lower()


# --- correction ---------------------------------------------------------------


@pytest.mark.parametrize(
    "state", ["CORRECTION", "RALLY_ATTEMPT", "FTD_WINDOW", "RALLY_FAILED", "FTD_INVALIDATED"]
)
def test_correction_states_cap_at_20(state):
    ceiling, rec, block = apply_market_status_overlay(
        ftd("market_in_correction", state), 70, "NEW_ENTRY_ALLOWED"
    )
    assert ceiling == 20
    assert rec == "REDUCE_ONLY"
    assert block["status"] == "market_in_correction"
    assert block["legacy_state"] == state
    assert block["cap_pct"] == 20
    assert block["applied"] is True
    assert block["days_since_ftd"] is None
    assert block["pressure_reasons"] == []


def test_correction_keeps_reduce_only_and_cash_priority():
    _, rec, _ = apply_market_status_overlay(
        ftd("market_in_correction", "CORRECTION"), 70, "REDUCE_ONLY"
    )
    assert rec == "REDUCE_ONLY"
    _, rec, _ = apply_market_status_overlay(
        ftd("market_in_correction", "CORRECTION"), 70, "CASH_PRIORITY"
    )
    assert rec == "CASH_PRIORITY"


def test_correction_with_low_composite_ceiling_uses_min_and_is_not_applied_to_ceiling():
    ceiling, rec, block = apply_market_status_overlay(
        ftd("market_in_correction", "CORRECTION"), 12, "CASH_PRIORITY"
    )
    assert ceiling == 12  # min(12, 20)
    assert rec == "CASH_PRIORITY"
    assert block["cap_pct"] == 20
    assert block["applied"] is False


def test_correction_applied_when_only_the_recommendation_changes():
    ceiling, rec, block = apply_market_status_overlay(
        ftd("market_in_correction", "CORRECTION"), 15, "NEW_ENTRY_ALLOWED"
    )
    assert ceiling == 15
    assert rec == "REDUCE_ONLY"
    assert block["applied"] is True


# --- confirmed uptrend with an FTD ---------------------------------------------


@pytest.mark.parametrize(
    "days,cap",
    [(0, 40), (4, 40), (5, 60), (14, 60), (15, 80), (60, 80), (None, 60)],
)
def test_confirmed_ftd_cap_by_age(days, cap):
    ceiling, rec, block = apply_market_status_overlay(
        ftd("confirmed_uptrend", "FTD_CONFIRMED", days=days), 95, "NEW_ENTRY_ALLOWED"
    )
    assert block["cap_pct"] == cap
    assert ceiling == cap
    assert rec == "NEW_ENTRY_ALLOWED"
    assert block["applied"] is True
    assert block["days_since_ftd"] == days


def test_confirmed_ftd_min_with_low_composite_ceiling():
    ceiling, rec, block = apply_market_status_overlay(
        ftd("confirmed_uptrend", "FTD_CONFIRMED", days=2), 33, "REDUCE_ONLY"
    )
    assert ceiling == 33
    assert rec == "REDUCE_ONLY"
    assert block["cap_pct"] == 40
    assert block["applied"] is False


def test_confirmed_ftd_ignores_invalid_age_values():
    for bad in (-1, True, "5", 2.5):
        data = ftd("confirmed_uptrend", "FTD_CONFIRMED")
        data["ftd_invalidation"] = {"days_since_ftd": bad}
        _, _, block = apply_market_status_overlay(data, 95, "NEW_ENTRY_ALLOWED")
        assert block["cap_pct"] == 60
        assert block["days_since_ftd"] is None


# --- uptrend resumed -------------------------------------------------------------


def test_uptrend_resumed_caps_at_80_and_is_labelled_not_an_ftd():
    ceiling, rec, block = apply_market_status_overlay(
        ftd("confirmed_uptrend", "UPTREND_RESUMED"), 95, "NEW_ENTRY_ALLOWED"
    )
    assert ceiling == 80
    assert rec == "NEW_ENTRY_ALLOWED"
    assert block["cap_pct"] == 80
    assert block["legacy_state"] == "UPTREND_RESUMED"
    assert "new high" in block["reason"].lower()
    assert "not an ftd" in block["reason"].lower()


def test_uptrend_resumed_ignores_days_since_ftd():
    _, _, block = apply_market_status_overlay(
        ftd("confirmed_uptrend", "UPTREND_RESUMED", days=2), 95, "NEW_ENTRY_ALLOWED"
    )
    assert block["cap_pct"] == 80


# --- under pressure ----------------------------------------------------------------


@pytest.mark.parametrize(
    "days,cap",
    [(0, 20), (4, 20), (5, 40), (14, 40), (15, 60), (None, 40)],
)
def test_under_pressure_is_one_band_below_confirmed_ftd(days, cap):
    ceiling, rec, block = apply_market_status_overlay(
        ftd("uptrend_under_pressure", "FTD_CONFIRMED", days=days, reasons=["distribution"]),
        95,
        "NEW_ENTRY_ALLOWED",
    )
    assert block["cap_pct"] == cap
    assert ceiling == cap
    assert rec == "NEW_ENTRY_ALLOWED"
    assert "be selective" in block["reason"].lower()
    assert block["pressure_reasons"] == ["distribution"]


def test_under_pressure_resumed_is_60():
    _, _, block = apply_market_status_overlay(
        ftd("uptrend_under_pressure", "UPTREND_RESUMED", reasons=["below_50sma"]),
        95,
        "NEW_ENTRY_ALLOWED",
    )
    assert block["cap_pct"] == 60
    assert block["pressure_reasons"] == ["below_50sma"]


def test_under_pressure_never_below_floor():
    assert ce.PRESSURE_CAP_FLOOR == 20
    _, _, block = apply_market_status_overlay(
        ftd("uptrend_under_pressure", "FTD_CONFIRMED", days=1), 95, "NEW_ENTRY_ALLOWED"
    )
    assert block["cap_pct"] == 20


def test_pressure_reasons_come_from_pressured_indexes_deduplicated():
    data = ftd("uptrend_under_pressure", "FTD_CONFIRMED", days=20)
    data["sp500"] = {
        "market_status": "uptrend_under_pressure",
        "cycle": {"pressure_reasons": ["distribution", "below_50sma"]},
    }
    data["nasdaq"] = {
        "market_status": "uptrend_under_pressure",
        "cycle": {"pressure_reasons": ["below_50sma", "ftd_low_close_breach"]},
    }
    _, _, block = apply_market_status_overlay(data, 95, "NEW_ENTRY_ALLOWED")
    assert block["pressure_reasons"] == ["distribution", "below_50sma", "ftd_low_close_breach"]
    assert block["per_index"] == {
        "sp500": "uptrend_under_pressure",
        "nasdaq": "uptrend_under_pressure",
    }


def test_pressure_reasons_skip_a_confirmed_index():
    data = ftd("uptrend_under_pressure", "FTD_CONFIRMED", days=20)
    data["sp500"] = {
        "market_status": "confirmed_uptrend",
        "cycle": {"pressure_reasons": []},
    }
    data["nasdaq"] = {
        "market_status": "uptrend_under_pressure",
        "cycle": {"pressure_reasons": ["distribution"]},
    }
    _, _, block = apply_market_status_overlay(data, 95, "NEW_ENTRY_ALLOWED")
    assert block["pressure_reasons"] == ["distribution"]
    assert block["per_index"]["sp500"] == "confirmed_uptrend"


# --- no overlay ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"quality_score": {"total_score": 82}},
        {"market_state": {"combined_state": "NO_SIGNAL", "market_status": None}},
        {"market_state": {"combined_state": "FTD_CONFIRMED"}},
        {"market_state": {"market_status": "bogus_status", "combined_state": "CORRECTION"}},
        {"market_state": {"market_status": "market_in_correction", "data_gap": True}},
        {"market_state": "not a dict"},
        {"market_state": {"market_status": ["market_in_correction"]}},
    ],
)
def test_no_overlay_without_a_usable_status(data):
    assert apply_market_status_overlay(data, 70, "NEW_ENTRY_ALLOWED") == (
        70,
        "NEW_ENTRY_ALLOWED",
        None,
    )


def test_unusable_evaluation_coverage_gives_no_overlay():
    data = ftd("market_in_correction", "CORRECTION")
    data["evaluation_coverage"] = {"complete": False}
    assert ce.evaluation_input_usable(data) is False
    assert apply_market_status_overlay(data, 70, "NEW_ENTRY_ALLOWED")[2] is None


# --- real-shape fixtures (generated from ftd-detector's own functions) ----------------


def test_real_shape_rally_attempt_day3_is_a_correction_cap():
    data = real("correction_rally_attempt_day3")
    assert data["sp500"]["rally_attempt"]["current_day_count"] == 3
    ceiling, rec, block = apply_market_status_overlay(data, 70, "NEW_ENTRY_ALLOWED")
    assert (ceiling, rec) == (20, "REDUCE_ONLY")
    assert block["legacy_state"] == "RALLY_ATTEMPT"
    assert block["per_index"] == {
        "sp500": "market_in_correction",
        "nasdaq": "market_in_correction",
    }


def test_real_shape_rally_failed_is_a_correction_cap():
    block = apply_market_status_overlay(real("correction_rally_failed"), 70, "NEW_ENTRY_ALLOWED")[2]
    assert block["legacy_state"] == "RALLY_FAILED"
    assert block["cap_pct"] == 20


@pytest.mark.parametrize(
    "name,days,cap",
    [
        ("ftd_confirmed_fresh", 0, 40),
        ("ftd_confirmed_age_6", 6, 60),
        ("ftd_confirmed_age_16", 16, 80),
    ],
)
def test_real_shape_ftd_age_bands(name, days, cap):
    data = real(name)
    assert data["ftd_invalidation"]["days_since_ftd"] == days
    ceiling, _, block = apply_market_status_overlay(data, 95, "NEW_ENTRY_ALLOWED")
    assert (block["days_since_ftd"], block["cap_pct"], ceiling) == (days, cap, cap)


def test_real_shape_uptrend_resumed():
    data = real("uptrend_resumed")
    assert data["sp500"]["cycle"]["resumed_without_ftd"] is True
    ceiling, _, block = apply_market_status_overlay(data, 95, "NEW_ENTRY_ALLOWED")
    assert ceiling == 80
    assert block["legacy_state"] == "UPTREND_RESUMED"


def test_real_shape_under_pressure():
    data = real("uptrend_under_pressure")
    assert data["ftd_invalidation"]["days_since_ftd"] >= 15
    ceiling, _, block = apply_market_status_overlay(data, 95, "NEW_ENTRY_ALLOWED")
    assert block["status"] == "uptrend_under_pressure"
    assert ceiling == 60  # mature FTD 80 minus one band
    assert block["pressure_reasons"] == ["distribution"]


def test_fixtures_match_what_ftd_detector_produces_today():
    """Drift guard: regenerate from ftd-detector in a subprocess and compare."""
    committed = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in REAL.glob("*.json")}
    out = subprocess.run(
        [sys.executable, str(TESTS / "build_ftd_fixtures.py"), "--stdout"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(out) == committed


# --- report / rationale integration ----------------------------------------------------


def run_main(tmp_path, *extra):
    args = [
        sys.executable,
        str(SCRIPT),
        "--breadth",
        str(LEGACY / "breadth.json"),
        "--top-risk",
        str(LEGACY / "top_risk.json"),
        "--output-dir",
        str(tmp_path),
        *extra,
    ]
    subprocess.run(args, check=True, capture_output=True, text=True)
    result = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    md = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    return result, md


def test_main_emits_overlay_in_json_markdown_and_rationale(tmp_path):
    result, md = run_main(tmp_path, "--ftd", str(REAL / "correction_rally_attempt_day3.json"))
    block = result["market_status_overlay"]
    assert set(block) == {
        "status",
        "legacy_state",
        "cap_pct",
        "applied",
        "reason",
        "days_since_ftd",
        "per_index",
        "pressure_reasons",
    }
    assert result["exposure_ceiling_pct"] == 20
    assert result["recommendation"] == "REDUCE_ONLY"
    assert "Market status" in result["rationale"]
    assert "20%" in result["rationale"]
    assert "### Market Status Overlay" in md
    assert "RALLY_ATTEMPT" in md
    assert "Exposure Ceiling: 20%" in md


def test_main_rationale_quotes_the_final_ceiling_not_the_composite_one(tmp_path):
    result, _ = run_main(tmp_path, "--ftd", str(REAL / "ftd_confirmed_fresh.json"))
    assert result["exposure_ceiling_pct"] == 40
    assert "within the 40% ceiling" in result["rationale"]


def test_main_composite_score_is_untouched_by_the_overlay(tmp_path):
    with_overlay, _ = run_main(tmp_path / "a", "--ftd", str(REAL / "correction_rally_failed.json"))
    legacy = tmp_path / "ftd.json"
    legacy.write_text(
        json.dumps({"quality_score": real("correction_rally_failed")["quality_score"]}),
        encoding="utf-8",
    )
    plain, _ = run_main(tmp_path / "b", "--ftd", str(legacy))
    assert with_overlay["composite_score"] == plain["composite_score"]
    assert with_overlay["component_scores"] == plain["component_scores"]


def test_markdown_section_absent_without_overlay():
    base = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "confidence": "HIGH",
        "exposure_ceiling_pct": 70,
        "component_scores": {},
        "recommendation": "NEW_ENTRY_ALLOWED",
        "bias": "NEUTRAL",
        "participation": "BROAD",
        "rationale": "r",
        "inputs_missing": [],
    }
    assert "Market Status Overlay" not in generate_markdown_report(base)


# --- old-format output is unchanged from the pre-overlay code ----------------------------

GOLDEN = json.loads((LEGACY / "expected_outputs.json").read_text(encoding="utf-8"))
LEGACY_ARGS = {
    "ftd_legacy": ["--ftd", str(LEGACY / "ftd_legacy.json")],
    "ftd_null_status": ["--ftd", str(LEGACY / "ftd_null_status.json")],
    "no_ftd": [],
}


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_old_format_and_missing_ftd_outputs_are_identical_to_pre_overlay_code(tmp_path, case):
    """Golden outputs were captured by running the pre-overlay calculate_exposure.py."""
    # run_main passes --breadth/--top-risk only; the golden run also passed --regime.
    args = [
        sys.executable,
        str(SCRIPT),
        "--breadth",
        str(LEGACY / "breadth.json"),
        "--top-risk",
        str(LEGACY / "top_risk.json"),
        "--regime",
        str(LEGACY / "regime.json"),
        *LEGACY_ARGS[case],
        "--output-dir",
        str(tmp_path),
    ]
    subprocess.run(args, check=True, capture_output=True, text=True)
    result = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    md_lines = next(tmp_path.glob("*.md")).read_text(encoding="utf-8").split("\n")
    result.pop("generated_at")
    assert result == GOLDEN[case]["json"]
    assert md_lines[2:] == GOLDEN[case]["markdown_after_header"]
    assert "market_status_overlay" not in result
