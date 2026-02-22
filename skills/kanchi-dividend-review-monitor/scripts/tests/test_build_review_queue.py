"""Unit tests for build_review_queue.py trigger logic."""

from build_review_queue import (
    build_report,
    render_markdown,
    t1_dividend_cut_or_suspension,
    t2_coverage_deterioration,
    t3_credit_stress_proxy,
    t4_governance_or_filing_alert,
    t5_structural_decline,
)


def test_t1_detects_dividend_cut() -> None:
    holding = {
        "ticker": "AAA",
        "dividend": {"latest_regular": 0.20, "prior_regular": 0.25, "is_missing": False},
    }
    finding = t1_dividend_cut_or_suspension(holding)
    assert finding is not None
    assert finding.status == "REVIEW"
    assert finding.trigger == "T1"


def test_t2_returns_review_when_history_shows_two_consecutive_breaches() -> None:
    holding = {
        "instrument_type": "stock",
        "cashflow": {
            "fcf": 100.0,
            "dividends_paid": 130.0,
            "coverage_ratio_history": [1.05, 1.10],
        },
    }
    finding = t2_coverage_deterioration(holding)
    assert finding is not None
    assert finding.status == "REVIEW"
    assert finding.trigger == "T2"


def test_t2_returns_warn_for_single_period_breach_only() -> None:
    holding = {
        "instrument_type": "stock",
        "cashflow": {
            "fcf": 100.0,
            "dividends_paid": 110.0,
            "coverage_ratio_history": [0.75, 0.90],
        },
    }
    finding = t2_coverage_deterioration(holding)
    assert finding is not None
    assert finding.status == "WARN"
    assert finding.trigger == "T2"


def test_t2_returns_review_when_denominator_non_positive_with_distribution() -> None:
    holding = {
        "instrument_type": "stock",
        "cashflow": {
            "fcf": -5.0,
            "dividends_paid": 120.0,
            "coverage_ratio_history": [],
        },
    }
    finding = t2_coverage_deterioration(holding)
    assert finding is not None
    assert finding.status == "REVIEW"


def test_t2_warns_when_ratio_above_point8_and_rising() -> None:
    holding = {
        "instrument_type": "stock",
        "cashflow": {
            "fcf": 100.0,
            "dividends_paid": 80.0,
            "coverage_ratio_history": [0.70, 0.85],
        },
    }
    finding = t2_coverage_deterioration(holding)
    assert finding is not None
    assert finding.status == "WARN"


def test_t3_returns_review_on_debt_up_and_coverage_weakening() -> None:
    holding = {
        "balance_sheet": {
            "net_debt_history": [1000, 1200, 1400],
            "interest_coverage_history": [4.0, 3.0, 2.3],
        },
        "capital_returns": {"buybacks": 10.0, "dividends_paid": 60.0, "fcf": 100.0},
    }
    finding = t3_credit_stress_proxy(holding)
    assert finding is not None
    assert finding.status == "REVIEW"
    assert finding.trigger == "T3"


def test_t3_returns_warn_on_debt_up_only() -> None:
    holding = {
        "balance_sheet": {
            "net_debt_history": [1000, 1200, 1400],
            "interest_coverage_history": [6.0, 6.1, 6.2],
        },
        "capital_returns": {"buybacks": 10.0, "dividends_paid": 60.0, "fcf": 1000.0},
    }
    finding = t3_credit_stress_proxy(holding)
    assert finding is not None
    assert finding.status == "WARN"
    assert finding.trigger == "T3"


def test_t4_detects_item_402_keyword() -> None:
    holding = {
        "filings": {"recent_text": "The company filed 8-K Item 4.02 non-reliance disclosure."}
    }
    finding = t4_governance_or_filing_alert(holding)
    assert finding is not None
    assert finding.status == "REVIEW"
    assert finding.trigger == "T4"


def test_t5_warns_on_two_structural_decline_signals() -> None:
    holding = {
        "operations": {
            "revenue_cagr_5y": -1.0,
            "margin_trend": "down",
            "guidance_trend": "flat",
            "dividend_growth_stalled": False,
        }
    }
    finding = t5_structural_decline(holding)
    assert finding is not None
    assert finding.status == "WARN"
    assert finding.trigger == "T5"


def test_render_markdown_title_includes_as_of_date() -> None:
    report = {
        "generated_at": "2026-02-22T00:00:00+00:00",
        "as_of": "2026-02-22",
        "summary": {"OK": 1, "WARN": 0, "REVIEW": 0},
        "results": [
            {"ticker": "AAA", "status": "OK", "actions": [], "findings": []},
        ],
    }
    markdown = render_markdown(report)
    assert markdown.splitlines()[0] == "# Dividend Review Queue (as_of: 2026-02-22)"


def test_build_report_counts_states() -> None:
    payload = {
        "as_of": "2026-02-22",
        "holdings": [
            {
                "ticker": "AAA",
                "instrument_type": "stock",
                "dividend": {"latest_regular": 0.1, "prior_regular": 0.2, "is_missing": False},
            },
            {
                "ticker": "BBB",
                "instrument_type": "stock",
                "dividend": {"latest_regular": 0.2, "prior_regular": 0.2, "is_missing": False},
            },
        ],
    }
    report = build_report(payload)
    assert report["summary"]["REVIEW"] == 1
    assert report["summary"]["OK"] == 1
