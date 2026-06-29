import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "run_20pct_study.py"
spec = importlib.util.spec_from_file_location("run_20pct_study", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def record(symbol, ret):
    return {
        "record_id": f"{symbol}:2026-01-01:UP:5D",
        "symbol": symbol,
        "event_date": "2026-01-01",
        "direction": "UP",
        "catalyst": {"label": "EARNINGS_REVALUATION"},
        "technical_context": {"pattern_label": "GAP_AND_GO", "close_quality": "STRONG_CLOSE"},
        "outcomes": {
            "5d": {
                "status": "MATURED",
                "directional_close_return_pct": ret,
                "close_return_pct": ret,
                "directional_mfe_pct": ret + 4,
                "directional_mae_pct": -2,
                "outcome_tag": "CONTINUED" if ret > 0 else "FAILED_FADE",
            }
        },
    }


def test_summarize_cohorts_exports_rule_candidate():
    records = [record("AAA", 5), record("BBB", 4), record("CCC", 3), record("DDD", -1)]

    summary = mod.summarize_cohorts(
        records,
        group_by=[
            "direction",
            "catalyst.label",
            "technical_context.pattern_label",
            "technical_context.close_quality",
        ],
        min_sample=3,
        horizon=5,
    )

    assert summary["records_matured"] == 4
    assert len(summary["cohorts"]) == 1
    assert summary["cohorts"][0]["sample_size"] == 4
    assert summary["rule_candidates"]
    assert summary["rule_candidates"][0]["status"] == "candidate_for_review"


def test_summarize_cohorts_holds_rule_below_min_sample():
    records = [record("AAA", 5), record("BBB", 4)]

    summary = mod.summarize_cohorts(
        records,
        group_by=[
            "direction",
            "catalyst.label",
            "technical_context.pattern_label",
            "technical_context.close_quality",
        ],
        min_sample=3,
        horizon=5,
    )

    assert summary["records_matured"] == 2
    assert summary["cohorts"][0]["sample_size"] == 2
    assert summary["rule_candidates"] == []


def test_summarize_cohorts_reports_data_quality_flag_counts():
    records = [record("AAA", 5), record("BBB", 4), record("CCC", 3)]
    records[0]["data_quality"] = {"flags": [mod.BACKFILL_SURVIVORSHIP_BIAS_FLAG]}

    summary = mod.summarize_cohorts(
        records,
        group_by=[
            "direction",
            "catalyst.label",
            "technical_context.pattern_label",
            "technical_context.close_quality",
        ],
        min_sample=3,
        horizon=5,
    )

    flag_counts = summary["cohorts"][0]["data_quality_flag_counts"]
    assert flag_counts[mod.BACKFILL_SURVIVORSHIP_BIAS_FLAG] == 1
    assert flag_counts["NO_FLAGS"] == 2
    assert (
        mod.BACKFILL_SURVIVORSHIP_BIAS_FLAG
        in summary["rule_candidates"][0]["evidence"]["data_quality_flag_counts"]
    )
