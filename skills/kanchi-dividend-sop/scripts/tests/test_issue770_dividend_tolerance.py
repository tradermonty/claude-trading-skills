"""Issue #770: finer raise/freeze tolerance, TTM evaluation-date window,
per-ticker price-date provenance (offline, deterministic)."""

from datetime import date, datetime, timedelta, timezone

from build_entry_signals import build_entry_row, render_markdown, write_csv
from dividend_basis import analyze_dividends, step1_decision


def _monthly_series(amounts, start=date(2025, 1, 15), step_days=30):
    return [
        {
            "date": (start + timedelta(days=step_days * i)).isoformat(),
            "dividend": amt,
            "label": "cash",
        }
        for i, amt in enumerate(amounts)
    ]


def _quarterly_series(amounts, dates):
    return [
        {"date": d.isoformat(), "dividend": amt, "label": "cash"} for d, amt in zip(dates, amounts)
    ]


# --- Finding 1: a ~0.9% monthly raise is detected, not frozen ---
def test_monthly_raise_detected_not_frozen():
    hist = _monthly_series([0.2695] * 6 + [0.2715] * 6 + [0.2740])
    b = analyze_dividends(hist, price=50.0, floor_pct=3.0)
    assert b.freeze_flag is False
    assert b.last_increase_date == "2026-01-10"
    verdict, reason = step1_decision(b, 3.0)
    assert verdict == "STEP1-PASS", reason


# --- Finding 1 guard: sub-cent noise still counts as "equal" ---
def test_subcent_noise_still_equal_and_frozen():
    hist = _monthly_series([0.2700] * 12 + [0.2701])
    b = analyze_dividends(hist, price=50.0, floor_pct=3.0)
    assert b.last_increase_date is None
    assert b.freeze_flag is True


# --- Finding 2: TTM window ends at the evaluation date ---
def test_ttm_uses_evaluation_date_not_latest_pay():
    dates = [
        date(2025, 11, 10),
        date(2026, 2, 10),
        date(2026, 5, 10),
        date(2026, 8, 10),
        date(2026, 11, 10),
    ]
    hist = _quarterly_series([0.70] * 5, dates)
    b = analyze_dividends(hist, price=50.0, floor_pct=3.0, as_of_date="2026-11-15")
    assert b.regular_annual_dividend == 2.80
    assert b.ttm_dividend_incl_special == 2.80
    # Without an evaluation date the window still ends at the latest pay.
    b_old = analyze_dividends(hist, price=50.0, floor_pct=3.0)
    assert b_old.regular_annual_dividend == 3.50
    assert b_old.ttm_dividend_incl_special == 3.50


# --- Finding 3: per-ticker price date is recorded and flagged ---
def _epoch(year, month, day, hour=15, minute=30):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()


def test_price_date_recorded_and_mismatch_flagged(tmp_path):
    row = build_entry_row(
        ticker="CFR",
        alpha_pp=0.5,
        quote={"price": 100.0, "timestamp": _epoch(2026, 11, 11)},
        profile=None,
        key_metrics=[{"dividendYield": 0.04}],
        as_of="2026-11-13",
    )
    assert row["price_date"] == "2026-11-11"
    assert row["price_date_mismatch"] is True
    assert "price_date_mismatch" in row["notes"]
    md = render_markdown([row], "2026-11-13", 0.5)
    assert "2026-11-11" in md
    assert "differs" in md
    csv_path = tmp_path / "out.csv"
    write_csv([row], csv_path)
    assert "price_date" in csv_path.read_text().splitlines()[0]


def test_price_date_matching_run_date_is_not_flagged():
    row = build_entry_row(
        ticker="CFR",
        alpha_pp=0.5,
        quote={"price": 100.0, "timestamp": _epoch(2026, 11, 13)},
        profile=None,
        key_metrics=[{"dividendYield": 0.04}],
        as_of="2026-11-13",
    )
    assert row["price_date"] == "2026-11-13"
    assert row["price_date_mismatch"] is False
    assert "price_date_mismatch" not in row["notes"]


def test_price_date_missing_when_quote_has_no_timestamp():
    row = build_entry_row(
        ticker="CFR",
        alpha_pp=0.5,
        quote={"price": 100.0},
        profile=None,
        key_metrics=[{"dividendYield": 0.04}],
        as_of="2026-11-13",
    )
    assert row["price_date"] is None
    assert row["price_date_mismatch"] is False
