"""WS-1 golden + edge-case tests for dividend_basis.py (offline, deterministic).

Fixtures model the FMP `historical-price-full/stock_dividend` shape and the
real dividend cadences observed on 2026-05-17. Verdicts frozen here are the
P0 regression gate for defects D1 (freeze), D4 (special/variable), D5
(stale-dividend false-negative near the floor).

# DATA-DATE: 2026-05-17
# VALID-UNTIL: 2026-08-31 (re-confirm CMCSA freeze / CFR raise next quarter)
# REVIEW-TRIGGER: CMCSA dividend restart, CFR dividend change
"""

from datetime import date, timedelta

from dividend_basis import analyze_dividends, step1_decision


def _series(start: date, n: int, amounts, step_days: int = 91, label="cash"):
    """Build a newest-last dividend history; amounts is a value or list."""
    out = []
    for i in range(n):
        amt = amounts[i] if isinstance(amounts, (list, tuple)) else amounts
        out.append(
            {
                "date": (start + timedelta(days=step_days * i)).isoformat(),
                "dividend": amt,
                "label": label,
            }
        )
    return out


# --- D4: CALM variable-dividend policy -> FAIL ---
def test_calm_variable_policy_flag_and_fail():
    hist = _series(
        date(2023, 2, 1),
        12,
        [0.006, 0.116, 0.755, 0.77, 0.997, 1.019, 1.378, 1.489, 3.495, 2.354, 0.723, 0.357],
    )
    b = analyze_dividends(hist, price=76.88, floor_pct=4.0)
    assert b.variable_policy_flag is True
    verdict, _ = step1_decision(b, 4.0)
    assert verdict == "FAIL"


# --- D4 + v2.1 R-1: ORI specials removed BEFORE variable test ---
def test_ori_special_excluded_not_variable():
    # Steady growing regular quarterly + two large annual specials.
    hist = []
    reg = [0.245, 0.265, 0.265, 0.265, 0.265, 0.29, 0.29, 0.29, 0.315]
    d = date(2023, 12, 1)
    for i, amt in enumerate(reg):
        hist.append(
            {"date": (d + timedelta(days=91 * i)).isoformat(), "dividend": amt, "label": "cash"}
        )
    hist.append({"date": "2025-01-03", "dividend": 2.00, "label": "cash"})
    hist.append({"date": "2026-01-02", "dividend": 2.50, "label": "cash"})
    b = analyze_dividends(hist, price=39.32, floor_pct=3.0)
    assert b.special_dividend_flag is True  # specials detected by amount-outlier
    assert b.variable_policy_flag is False  # residual is steady (R-1 ordering)
    assert b.ttm_yield_pct > b.regular_forward_yield_pct  # specials inflate ttm only


# --- D1: freeze via time-series path ---
def test_freeze_timepath_holds_review():
    hist = _series(date(2022, 3, 1), 13, 0.33)  # >3y flat, no increase ever
    b = analyze_dividends(hist, price=24.76, floor_pct=4.0)
    assert b.freeze_flag is True
    assert b.cut_flag is False
    verdict, reason = step1_decision(b, 4.0)
    assert verdict == "HOLD-REVIEW" and reason == "dividend_freeze"


# --- D1: freeze via issuer language when YoY rate unavailable (short history) ---
def test_freeze_language_path():
    hist = _series(date(2025, 6, 1), 4, 0.33)  # only 4 pays -> no prior-year rate
    b = analyze_dividends(
        hist,
        price=24.76,
        floor_pct=4.0,
        issuer_language="Comcast maintains dividend unchanged for 2026",
    )
    assert b.freeze_flag is True


# --- D5: CFR near-floor on the LATEST declared raise -> RECHECK, not FAIL ---
def test_cfr_d5_freshness_recheck_not_fail():
    hist = _series(date(2023, 5, 30), 13, [1.00] * 12 + [1.03])  # latest declared raise to 1.03
    b = analyze_dividends(hist, price=134.70, floor_pct=3.0)
    # 1.03 * 4 / 134.70 = 3.06% -> just above 3.0 floor, inside freshness band
    assert b.latest_declared_annualized == 4.12
    assert b.floor_borderline is True
    verdict, _ = step1_decision(b, 3.0, source_confirmed=False)
    assert verdict == "STEP1-RECHECK"  # NOT "FAIL" (the D5 bug)
    verdict_ok, _ = step1_decision(b, 3.0, source_confirmed=True)
    assert verdict_ok in ("STEP1-PASS", "HOLD-REVIEW")


# --- cut detected and FAIL'd, distinct from freeze ---
def test_cut_flag_distinct_from_freeze():
    hist = _series(date(2023, 1, 1), 12, [0.50] * 8 + [0.40] * 4)  # recent cut
    b = analyze_dividends(hist, price=30.0, floor_pct=3.0)
    assert b.cut_flag is True
    assert b.freeze_flag is False
    assert step1_decision(b, 3.0)[0] == "FAIL"


# --- monthly REIT must NOT misfire variable_policy_flag ---
def test_monthly_reit_no_variable_misfire():
    hist = _series(date(2024, 1, 15), 24, 0.2625, step_days=30, label="cash")
    b = analyze_dividends(hist, price=58.0, floor_pct=4.0)
    assert b.cadence == "monthly" and b.pays_per_year == 12
    assert b.variable_policy_flag is False
    assert b.cut_flag is False and b.freeze_flag is True  # flat & old -> freeze


# --- insufficient history -> ASSUMPTION-REQUIRED, not a hard verdict ---
def test_annual_only_short_history_assumption_required():
    hist = _series(date(2024, 6, 1), 2, [1.0, 1.05], step_days=365)
    b = analyze_dividends(hist, price=50.0, floor_pct=3.0)
    assert b.status == "ASSUMPTION-REQUIRED"
    assert step1_decision(b, 3.0)[0] == "STEP1-RECHECK"


def test_no_dividend_history():
    b = analyze_dividends([], price=10.0, floor_pct=3.0)
    assert b.status == "NO-DIVIDEND"
    assert step1_decision(b, 3.0)[0] == "FAIL"
