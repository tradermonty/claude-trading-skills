#!/usr/bin/env python3
"""Coverage tests for the CANSLIM component calculators (C, A, N, S, L, I, M)."""

import pytest
from calculators import institutional_calculator as inst
from calculators.earnings_calculator import (
    calculate_quarterly_growth,
    detect_earnings_acceleration,
    interpret_earnings_score,
    score_current_earnings,
)
from calculators.growth_calculator import (
    calculate_annual_growth,
    check_consistency,
    interpret_growth_score,
    score_annual_growth,
)
from calculators.leadership_calculator import (
    _sort_prices_ascending,
    calculate_leadership,
    calculate_sector_relative_strength,
    interpret_leadership,
    score_leadership,
    slice_period_return,
)
from calculators.market_calculator import (
    calculate_ema,
    calculate_market_direction,
    interpret_market_score,
    score_market_direction,
)
from calculators.new_highs_calculator import (
    calculate_newness,
    interpret_newness_score,
    score_newness,
)
from calculators.supply_demand_calculator import (
    calculate_supply_demand,
    interpret_supply_demand,
    score_supply_demand,
)

# ---------------------------------------------------------------- C component


def _quarters(eps_latest, eps_year_ago, rev_latest, rev_year_ago):
    """Five quarters, newest first; index 4 is the year-ago quarter."""
    middle = [{"eps": 1.0, "revenue": 100.0} for _ in range(3)]
    return [
        {"date": "2024-06-30", "eps": eps_latest, "revenue": rev_latest},
        *middle,
        {"date": "2023-06-30", "eps": eps_year_ago, "revenue": rev_year_ago},
    ]


class TestEarningsCalculator:
    def test_insufficient_quarters(self):
        result = calculate_quarterly_growth(_quarters(1, 1, 1, 1)[:4])
        assert result["score"] == 0
        assert "at least 5 quarters" in result["error"]
        assert result["latest_qtr_eps_growth"] is None

    def test_exceptional_growth_scores_100(self):
        result = calculate_quarterly_growth(_quarters(3.0, 1.0, 300.0, 100.0))
        assert result["score"] == 100
        assert result["latest_qtr_eps_growth"] == 200.0
        assert result["latest_qtr_revenue_growth"] == 200.0
        assert result["latest_qtr_date"] == "2024-06-30"
        assert result["year_ago_qtr_date"] == "2023-06-30"
        assert result["quality_warning"] is None
        assert result["interpretation"].startswith("Exceptional")

    def test_alternate_eps_field_names(self):
        stmts = _quarters(None, None, 130.0, 100.0)
        stmts[0].pop("eps")
        stmts[4].pop("eps")
        stmts[0]["epsdiluted"] = 1.4
        stmts[4]["netIncomePerShare"] = 1.0
        result = calculate_quarterly_growth(stmts)
        assert result["latest_eps"] == 1.4
        assert result["year_ago_eps"] == 1.0
        assert result["latest_qtr_eps_growth"] == 40.0
        assert result["score"] == 80

    def test_missing_eps(self):
        stmts = _quarters(1.0, 1.0, 100.0, 100.0)
        stmts[0].pop("eps")
        result = calculate_quarterly_growth(stmts)
        assert result["score"] == 0
        assert result["error"] == "EPS data missing or invalid"
        assert result["year_ago_eps"] == 1.0

    @pytest.mark.parametrize("latest_rev,year_ago_rev", [(None, 100.0), (100.0, None), (100.0, 0)])
    def test_missing_or_zero_revenue(self, latest_rev, year_ago_rev):
        result = calculate_quarterly_growth(_quarters(2.0, 1.0, latest_rev, year_ago_rev))
        assert result["score"] == 0
        assert result["error"] == "Revenue data missing or invalid"
        assert result["interpretation"] == "Revenue data unavailable"

    def test_negative_year_ago_eps_uses_abs_denominator(self):
        result = calculate_quarterly_growth(_quarters(0.5, -0.5, 130.0, 100.0))
        # (0.5 - -0.5) / 0.5 = +200%
        assert result["latest_qtr_eps_growth"] == 200.0
        assert result["score"] == 100

    def test_zero_year_ago_eps_via_netincomepershare_turnaround(self):
        # eps / epsdiluted absent, netIncomePerShare == 0 reaches the zero branch
        stmts = _quarters(None, None, 130.0, 100.0)
        stmts[0] = {"date": "2024-06-30", "netIncomePerShare": 0.4, "revenue": 130.0}
        stmts[4] = {"date": "2023-06-30", "netIncomePerShare": 0, "revenue": 100.0}
        result = calculate_quarterly_growth(stmts)
        assert result["latest_qtr_eps_growth"] == 999.9
        assert result["score"] == 100

    def test_zero_year_ago_eps_non_positive_latest_gives_zero_growth(self):
        stmts = _quarters(None, None, 130.0, 100.0)
        stmts[0] = {"date": "2024-06-30", "netIncomePerShare": 0, "revenue": 130.0}
        stmts[4] = {"date": "2023-06-30", "netIncomePerShare": 0, "revenue": 100.0}
        result = calculate_quarterly_growth(stmts)
        assert result["latest_qtr_eps_growth"] == 0
        assert result["score"] == 0

    def test_quality_warning_when_revenue_lags(self):
        result = calculate_quarterly_growth(_quarters(1.5, 1.0, 105.0, 100.0))
        # EPS +50%, revenue +5% < 25%
        assert "buyback-driven" in result["quality_warning"]
        assert result["score"] == 40

    @pytest.mark.parametrize(
        "eps,rev,expected",
        [
            (50, 25, 100),
            (49.9, 25, 80),
            (30, 15, 80),
            (30, 14.9, 60),
            (18, 10, 60),
            (18, 9.9, 40),
            (10, 0, 40),
            (9.9, 100, 0),
            (-5, -5, 0),
        ],
    )
    def test_score_current_earnings_boundaries(self, eps, rev, expected):
        assert score_current_earnings(eps, rev) == expected

    @pytest.mark.parametrize(
        "score,prefix",
        [
            (100, "Exceptional"),
            (80, "Strong"),
            (60, "Acceptable"),
            (40, "Below threshold"),
            (0, "Weak"),
        ],
    )
    def test_interpret_earnings_score(self, score, prefix):
        text = interpret_earnings_score(score, 12.3, 4.5)
        assert text.startswith(prefix)
        assert "12.3%" in text

    def test_acceleration_insufficient_data(self):
        result = detect_earnings_acceleration([{"eps": 1.0}] * 5)
        assert result["trend"] == "unknown"
        assert result["recent_growth"] is None

    def _six(self, recent, recent_ya, prior, prior_ya):
        return [
            {"eps": recent},
            {"eps": prior},
            {"eps": 1.0},
            {"eps": 1.0},
            {"eps": recent_ya},
            {"eps": prior_ya},
        ]

    def test_acceleration_detected(self):
        result = detect_earnings_acceleration(self._six(2.0, 1.0, 1.2, 1.0))
        assert result["trend"] == "accelerating"
        assert result["recent_growth"] == 100.0
        assert result["prior_growth"] == 20.0
        assert "accelerating" in result["interpretation"]

    def test_deceleration_detected(self):
        result = detect_earnings_acceleration(self._six(1.1, 1.0, 2.0, 1.0))
        assert result["trend"] == "decelerating"
        assert result["recent_growth"] == 10.0
        assert result["prior_growth"] == 100.0
        assert "Warning sign" in result["interpretation"]

    def test_stable_trend_and_zero_year_ago(self):
        result = detect_earnings_acceleration(self._six(1.2, 1.0, 1.2, 1.0))
        assert result["trend"] == "stable"
        zero = detect_earnings_acceleration(self._six(1.2, 0, 1.2, 0))
        assert zero["recent_growth"] == 0
        assert zero["prior_growth"] == 0
        assert zero["trend"] == "stable"


# ---------------------------------------------------------------- A component


def _annual(eps_newest_first, revenues_newest_first=None):
    revenues_newest_first = revenues_newest_first or [100.0] * len(eps_newest_first)
    return [
        {"date": f"{2024 - i}-12-31", "eps": e, "revenue": r}
        for i, (e, r) in enumerate(zip(eps_newest_first, revenues_newest_first))
    ]


class TestGrowthCalculator:
    def test_insufficient_years_is_neutral_50(self):
        result = calculate_annual_growth(_annual([3, 2, 1]))
        assert result["score"] == 50
        assert result["stability"] == "unknown"
        assert "at least 4 years" in result["error"]

    def test_missing_eps(self):
        stmts = _annual([8, 4, 2, 1])
        stmts[2].pop("eps")
        result = calculate_annual_growth(stmts)
        assert result["score"] == 0
        assert result["error"] == "Missing EPS data for year 2022-12-31"

    @pytest.mark.parametrize("bad", [-1.0])
    def test_non_positive_eps(self, bad):
        stmts = _annual([8, 4, bad, 1])
        result = calculate_annual_growth(stmts)
        assert result["score"] == 0
        assert "Negative or zero EPS in year 2022-12-31" in result["error"]
        assert result["interpretation"] == "Negative EPS - not a CANSLIM candidate"

    def test_doubling_each_year_with_matching_revenue(self):
        result = calculate_annual_growth(
            _annual([8, 4, 2, 1], [800.0, 400.0, 200.0, 100.0]),
        )
        assert result["eps_cagr_3yr"] == 100.0
        assert result["revenue_cagr_3yr"] == 100.0
        assert result["stability"] == "stable"
        assert result["eps_values"] == [1, 2, 4, 8]
        assert result["revenue_values"] == [100, 200, 400, 800]
        assert result["years_analyzed"] == 4
        assert result["score"] == 100  # 90 base + 10 stability, capped at 100
        assert result["quality_warning"] is None
        assert result["interpretation"].startswith("Exceptional")

    def test_buyback_driven_growth_gets_penalty_and_warning(self):
        result = calculate_annual_growth(_annual([8, 4, 2, 1]))  # flat revenue
        assert result["revenue_cagr_3yr"] == 0.0
        assert "buyback-driven" in result["quality_warning"]
        # 90 * 0.8 = 72 + 10 stability bonus
        assert result["score"] == 82

    def test_erratic_growth_and_zero_start_revenue(self):
        # chronological EPS: 1.0, 3.0, 2.0, 2.0 -> a down year
        stmts = _annual([2.0, 2.0, 3.0, 1.0], [0, 0, 0, 0])
        result = calculate_annual_growth(stmts)
        assert result["stability"] == "erratic"
        assert result["revenue_cagr_3yr"] == 0
        assert result["eps_cagr_3yr"] == pytest.approx(26.0, abs=0.1)
        # base 50, revenue 0 < 13 -> int(40.0), no stability bonus
        assert result["score"] == 40

    def test_alternate_eps_key_epsdiluted(self):
        stmts = [
            {"date": f"{2024 - i}-12-31", "epsdiluted": e, "revenue": 100.0}
            for i, e in enumerate([1.0, 1.0, 1.0, 1.0])
        ]
        result = calculate_annual_growth(stmts)
        assert result["eps_cagr_3yr"] == 0.0
        assert result["score"] == 10  # base 0 (flat) + 10 stability
        assert result["interpretation"].startswith("Weak")

    @pytest.mark.parametrize(
        "cagr,expected",
        [(40, 90), (30, 70), (25, 50), (15, 30), (14.9, 0)],
    )
    def test_score_bases_with_matching_revenue_unstable(self, cagr, expected):
        assert score_annual_growth(cagr, cagr, stable=False) == expected

    def test_score_penalty_and_cap(self):
        assert score_annual_growth(40, 10, stable=False) == 72
        assert score_annual_growth(40, 40, stable=True) == 100

    @pytest.mark.parametrize(
        "score,prefix",
        [
            (95, "Exceptional"),
            (75, "Strong"),
            (55, "Acceptable"),
            (35, "Below threshold"),
            (10, "Weak"),
        ],
    )
    def test_interpret_growth_score(self, score, prefix):
        assert interpret_growth_score(score, 33.3, True).startswith(prefix)

    def test_check_consistency_insufficient(self):
        result = check_consistency([{"eps": 1.0}])
        assert result["down_years"] is None
        assert result["interpretation"] == "Insufficient data"

    def test_check_consistency_pattern(self):
        # chronological: 1.0, 2.0, 1.0, 2.0, 4.0
        stmts = [{"eps": 4.0}, {"eps": 2.0}, {"epsdiluted": 1.0}, {"eps": 2.0}, {"eps": 1.0}]
        result = check_consistency(stmts)
        assert result["growth_pattern"] == [100.0, -50.0, 100.0, 100.0]
        assert result["down_years"] == 1
        assert result["consecutive_growth_years"] == 2
        assert result["interpretation"] == "2 consecutive years of growth, 1 down years"


# ---------------------------------------------------------------- N component


class TestNewHighsCalculator:
    def test_missing_quote(self):
        result = calculate_newness({})
        assert result["score"] == 0
        assert result["error"] == "Quote data missing"

    def test_missing_price_or_high(self):
        result = calculate_newness({"price": 100})
        assert result["score"] == 0
        assert result["error"] == "Price or 52-week high data missing"

    def test_breakout_near_high_scores_100(self):
        quote = {
            "price": 99.8,
            "yearHigh": 100.0,
            "yearLow": 50.0,
            "volume": 1_500_000,
            "avgVolume": 1_000_000,
        }
        result = calculate_newness(quote)
        assert result["breakout_detected"] is True
        assert result["distance_from_high_pct"] == -0.2
        assert result["volume_ratio"] == 1.5
        assert result["score"] == 100
        assert result["interpretation"].startswith("Exceptional")
        assert "with volume breakout" in result["interpretation"]
        assert result["error"] is None

    def test_no_volume_info_no_breakout(self):
        result = calculate_newness({"price": 90.0, "yearHigh": 100.0})
        assert result["breakout_detected"] is False
        assert result["volume_ratio"] is None
        assert result["score"] == 60  # within 15% of high
        assert result["interpretation"].startswith("Acceptable")

    def test_volume_below_threshold_is_not_breakout(self):
        quote = {"price": 100.0, "yearHigh": 100.0, "volume": 1_400_000, "avgVolume": 1_000_000}
        assert calculate_newness(quote)["breakout_detected"] is False

    @pytest.mark.parametrize(
        "dist,breakout,expected",
        [
            (-5, True, 100),
            (-7, True, 80),
            (-20, True, 60),
            (-15, False, 60),
            (-20, False, 40),
            (-25, False, 40),
            (-26, False, 20),
        ],
    )
    def test_score_newness(self, dist, breakout, expected):
        assert score_newness(dist, breakout) == expected

    @pytest.mark.parametrize(
        "score,prefix",
        [
            (100, "Exceptional"),
            (80, "Strong"),
            (60, "Acceptable"),
            (40, "Weak"),
            (20, "Poor"),
        ],
    )
    def test_interpret_newness(self, score, prefix):
        assert interpret_newness_score(score, -3.0, False).startswith(prefix)


# ---------------------------------------------------------------- S component


def _volume_history(up_vol, down_vol, days=60, alternate=True):
    """Newest-first series alternating up/down closes with given volumes."""
    # Build chronologically then reverse. Close moves +1 / -1 alternately.
    chrono = []
    close = 100.0
    for i in range(days):
        if i == 0:
            vol = up_vol
        elif alternate and i % 2 == 1:
            close += 1.0
            vol = up_vol
        else:
            close -= 1.0
            vol = down_vol
        chrono.append({"date": f"d{i:03d}", "close": close, "volume": vol})
    return {"historical": chrono[::-1]}


class TestSupplyDemandCalculator:
    def test_no_data(self):
        result = calculate_supply_demand(None)
        assert result["score"] == 0
        assert result["error"] == "No historical price data provided"
        assert calculate_supply_demand({"x": 1})["score"] == 0

    def test_insufficient_days(self):
        result = calculate_supply_demand({"historical": [{"close": 1, "volume": 1}] * 10})
        assert result["score"] == 0
        assert "need 60+ days, got 10" in result["error"]
        assert "Less than 60 days" in result["quality_warning"]

    def test_too_few_down_days(self):
        # monotonically rising closes -> no down days
        rising = [{"close": 100 - i, "volume": 10} for i in range(60)]
        result = calculate_supply_demand({"historical": rising})
        assert result["score"] == 0
        assert result["error"] == "Insufficient up/down days for analysis"
        assert result["up_days_count"] == 59
        assert result["down_days_count"] == 0
        assert "up: 59, down: 0" in result["quality_warning"]

    def test_strong_accumulation(self):
        result = calculate_supply_demand(_volume_history(2000, 1000))
        assert result["up_down_ratio"] == 2.0
        assert result["score"] == 100
        assert result["accumulation_detected"] is True
        assert result["avg_up_volume"] == 2000
        assert result["avg_down_volume"] == 1000
        assert result["up_days_count"] + result["down_days_count"] == 59
        assert result["interpretation"].startswith("Strong Accumulation")

    def test_zero_down_volume_caps_ratio(self):
        result = calculate_supply_demand(_volume_history(1000, 0))
        assert result["up_down_ratio"] == 5.0
        assert result["score"] == 100

    def test_distribution(self):
        result = calculate_supply_demand(_volume_history(1000, 2500))
        assert result["up_down_ratio"] == pytest.approx(0.4)
        assert result["score"] == 0
        assert result["accumulation_detected"] is False
        assert result["interpretation"].startswith("Strong Distribution")

    def test_incomplete_rows_are_skipped(self):
        data = _volume_history(2000, 1000)
        data["historical"][5] = {"date": "x", "close": None, "volume": 5}
        data["historical"][6] = {"date": "y", "close": 50, "volume": None}
        result = calculate_supply_demand(data)
        assert result["up_days_count"] + result["down_days_count"] < 59

    @pytest.mark.parametrize(
        "ratio,expected",
        [(2.0, 100), (1.5, 80), (1.0, 60), (0.7, 40), (0.5, 20), (0.49, 0)],
    )
    def test_score_boundaries(self, ratio, expected):
        assert score_supply_demand(ratio) == expected

    @pytest.mark.parametrize(
        "ratio,prefix",
        [
            (2.5, "Strong Accumulation"),
            (1.6, "Accumulation"),
            (1.1, "Neutral/Weak Accumulation"),
            (0.8, "Neutral/Weak Distribution"),
            (0.6, "Distribution"),
            (0.1, "Strong Distribution"),
        ],
    )
    def test_interpret_supply_demand(self, ratio, prefix):
        text = interpret_supply_demand(ratio, ratio >= 1.5)
        assert text.startswith(prefix)
        assert f"{ratio:.2f}x" in text


# ---------------------------------------------------------------- L component


def _series(start, end, days, dates_desc=False):
    step = (end - start) / (days - 1)
    rows = [
        {"date": f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", "close": start + step * i}
        for i in range(days)
    ]
    # 2024-xx dates stop being valid after 12 months, but they only need to sort
    return rows[::-1] if dates_desc else rows


class TestLeadershipCalculator:
    def test_sort_prices_ascending_handles_empty_and_type_error(self):
        assert _sort_prices_ascending([]) == []
        mixed = [{"date": 1}, {"date": "2024"}]
        assert _sort_prices_ascending(mixed) == mixed

    def test_slice_period_return_non_numeric_close(self):
        prices = [{"date": "a", "close": "x"}, {"date": "b", "close": 2.0}]
        assert slice_period_return(prices, 2) is None

    def test_slice_period_return_bad_entries(self):
        assert slice_period_return([{"date": "a", "close": 1}], 0) is None
        # Oddity pinned as-is: only TypeError is caught by the sort helper, so non-dict
        # rows raise AttributeError. FMP always returns dict rows, so this is unreachable.
        with pytest.raises(AttributeError):
            slice_period_return(["not-a-dict", "also-bad"], 2)

    def test_insufficient_history(self):
        result = calculate_leadership(_series(100, 110, 10))
        assert result["score"] == 0
        assert "need 50+ days" in result["error"]
        assert result["rs_rating"] == "Weak"
        assert result["missing_periods"] == ["3m", "6m", "12m"]

    def test_invalid_start_price(self):
        prices = _series(0, 10, 60)
        result = calculate_leadership(prices)
        assert result["error"] == "Invalid start price (zero or negative)"
        assert result["score"] == 0

    def test_price_calculation_error(self):
        prices = [{"date": f"d{i:03d}"} for i in range(60)]
        prices[0]["close"] = None
        result = calculate_leadership(prices)
        assert result["score"] == 0
        assert result["error"].startswith("Price calculation error")

    def test_legacy_precomputed_benchmark_path(self):
        prices = _series(100, 160, 60)  # +60%
        result = calculate_leadership(prices, sp500_performance=10.0)
        assert result["stock_52w_performance"] == 60.0
        assert result["relative_performance"] == 50.0
        assert result["score"] == 100
        assert result["rs_rank_estimate"] == 99
        assert result["rs_rating"] == "Market Leader"
        assert result["rs_3m_return"] is None
        assert result["available_periods"] == []
        assert result["benchmark_52w_performance"] == 10.0
        assert result["interpretation"].startswith("Market Leader - 60-day return +60.0%")

    def test_no_benchmark_uses_absolute_with_penalty(self):
        prices = _series(100, 130, 80)  # +30% over 80 bars: no 3m window (63)? yes 63<=80
        result = calculate_leadership(prices)
        assert "unavailable" in result["quality_warning"]
        assert result["sp500_52w_performance"] is None
        assert result["available_periods"] == ["3m"]
        # multi-period absolute: 3m return is smaller than 30%
        assert result["weighted_relative_performance"] is None
        assert result["weighted_stock_performance"] == result["rs_3m_return"]
        assert "(absolute performance)" in result["interpretation"]

    def test_no_benchmark_short_history_uses_legacy_absolute(self):
        prices = _series(100, 130, 55)  # fewer than 63 bars -> no multi-period
        result = calculate_leadership(prices)
        assert result["available_periods"] == []
        assert result["relative_performance"] == 30.0
        # +30% -> 95 base, no benchmark -> int(95 * 0.8)
        assert result["score"] == 76
        assert result["rs_rank_estimate"] == int(95 * 0.9)

    def test_insufficient_benchmark_history(self):
        prices = _series(100, 130, 55)
        bench = _series(100, 105, 20)
        result = calculate_leadership(prices, sp500_historical=bench)
        assert "data insufficient" in result["quality_warning"]
        assert result["score"] == 76

    def test_short_history_with_benchmark_uses_legacy_relative(self):
        prices = _series(100, 130, 55)
        bench = _series(100, 110, 55)
        result = calculate_leadership(prices, sp500_historical=bench)
        assert result["available_periods"] == []
        assert result["sp500_52w_performance"] == 10.0
        assert result["relative_performance"] == 20.0
        assert result["score"] == 90
        assert result["quality_warning"] is None
        assert "+20.0% vs benchmark" in result["interpretation"]

    def test_benchmark_start_price_zero_leaves_legacy_benchmark_none(self):
        prices = _series(100, 130, 55)
        bench = _series(0, 10, 55)
        result = calculate_leadership(prices, sp500_historical=bench)
        assert result["sp500_52w_performance"] is None
        assert result["score"] == 76

    def test_benchmark_with_missing_close_flags_warning(self):
        prices = _series(100, 130, 55)
        bench = [{"date": f"d{i:03d}", "close": None} for i in range(55)]
        result = calculate_leadership(prices, sp500_historical=bench)
        assert result["quality_warning"] == "Benchmark performance calculation failed"

    def test_full_multi_period_relative_path(self):
        prices = _series(100, 200, 260, dates_desc=True)
        bench = _series(100, 110, 260)
        result = calculate_leadership(prices, sp500_historical=bench, rs_benchmark="QQQ")
        assert result["available_periods"] == ["3m", "6m", "12m"]
        assert result["rs_benchmark"] == "QQQ"
        assert result["weighted_relative_performance"] > 0
        assert result["rs_12m_return"] > result["benchmark_12m_return"]
        assert result["rs_benchmark_relative_return"] == result["rel_12m"]
        assert result["score"] == result["rs_component_score"]
        assert result["rs_rank_percentile"] == result["rs_rank_estimate"]
        assert result["stock_52w_performance"] == 100.0
        assert result["sp500_52w_performance"] == 10.0
        assert result["interpretation"].startswith("Market Leader - 52-week return")

    @pytest.mark.parametrize(
        "rel,score,rank",
        [
            (50, 100, 99),
            (30, 95, 95),
            (20, 90, 90),
            (10, 80, 80),
            (5, 70, 70),
            (0, 60, 60),
            (-5, 50, 50),
            (-10, 40, 40),
            (-20, 20, 25),
            (-20.1, 0, 10),
        ],
    )
    def test_score_leadership_bands(self, rel, score, rank):
        assert score_leadership(rel, True) == (score, rank)

    def test_score_leadership_no_benchmark_penalty(self):
        assert score_leadership(50, False) == (80, 89)

    @pytest.mark.parametrize(
        "days,period",
        [(260, "52-week"), (200, "9-month"), (100, "quarterly"), (70, "70-day")],
    )
    def test_interpret_leadership_period_labels(self, days, period):
        text = interpret_leadership(60, 5.0, 3.0, 2.0, days)
        assert f"{period} return +5.0%" in text

    @pytest.mark.parametrize(
        "score,rating",
        [
            (95, "Market Leader"),
            (85, "Strong Performer"),
            (65, "Above Average"),
            (45, "Average"),
            (25, "Laggard"),
            (5, "Weak"),
        ],
    )
    def test_interpret_leadership_ratings(self, score, rating):
        text = interpret_leadership(score, -4.0, -1.0, -3.0, 260)
        assert text.startswith(rating)
        assert "-4.0%" in text
        assert "-3.0% vs benchmark" in text

    def test_sector_relative_strength(self):
        empty = calculate_sector_relative_strength(10.0, [])
        assert empty["sector_rank"] is None
        assert empty["is_sector_leader"] is False
        result = calculate_sector_relative_strength(50.0, [10.0, 20.0, 30.0, 40.0])
        assert result["sector_rank"] == 1
        assert result["sector_total"] == 5
        assert result["sector_percentile"] == 80.0
        assert result["is_sector_leader"] is True
        low = calculate_sector_relative_strength(5.0, [10.0, 20.0, 30.0, 40.0])
        assert low["sector_rank"] == 5
        assert low["sector_percentile"] == 0.0
        assert low["is_sector_leader"] is False


# ---------------------------------------------------------------- M component


def _index_history(n, close=100.0):
    return [{"date": f"d{i:03d}", "close": close} for i in range(n)]


class TestMarketCalculator:
    def test_missing_quote(self):
        result = calculate_market_direction({})
        assert result["score"] == 50
        assert result["trend"] == "unknown"
        assert result["error"] == "S&P 500 quote data missing"

    def test_missing_price(self):
        result = calculate_market_direction({"symbol": "^GSPC"})
        assert result["error"] == "S&P 500 price missing"
        assert result["score"] == 50

    def test_insufficient_history_does_not_fabricate_trend(self):
        result = calculate_market_direction({"price": 5000}, _index_history(30))
        assert result["score"] == 50
        assert result["trend"] == "unknown"
        assert result["sp500_price"] == 5000
        assert result["sp500_ema_50"] is None
        assert "Insufficient S&P 500 history" in result["error"]

    def test_none_closes_are_filtered_before_length_check(self):
        history = _index_history(60)
        for row in history[:20]:
            row["close"] = None
        result = calculate_market_direction({"price": 100}, history)
        assert result["trend"] == "unknown"

    @pytest.mark.parametrize(
        "price,vix,trend,score",
        [
            (103.0, 12.0, "strong_uptrend", 100),
            (103.0, 20.0, "strong_uptrend", 90),
            (101.0, 12.0, "uptrend", 80),
            (101.0, None, "uptrend", 70),
            (99.0, 20.0, "choppy", 40),
            (97.0, 20.0, "downtrend", 20),
            (90.0, 20.0, "bear_market", 0),
            (103.0, 35.0, "strong_uptrend", 0),
        ],
    )
    def test_trend_and_score_matrix(self, price, vix, trend, score):
        vix_quote = {"price": vix} if vix is not None else None
        result = calculate_market_direction({"price": price}, _index_history(60), vix_quote)
        assert result["trend"] == trend
        assert result["score"] == score
        assert result["sp500_ema_50"] == pytest.approx(100.0)
        assert result["vix_level"] == vix
        assert result["error"] is None

    def test_bear_market_warning_and_distance(self):
        result = calculate_market_direction({"price": 90.0}, _index_history(60), {"price": 25.0})
        assert result["distance_from_ema_pct"] == -10.0
        assert "BEAR MARKET" in result["warning"]
        assert result["interpretation"].startswith("Bear market")
        assert "VIX 25.0" in result["interpretation"]

    def test_no_warning_in_uptrend(self):
        result = calculate_market_direction({"price": 101.0}, _index_history(60))
        assert result["warning"] is None
        assert result["distance_from_ema_pct"] == 1.0

    def test_calculate_ema_short_input_is_simple_average(self):
        assert calculate_ema([1.0, 2.0, 3.0], period=50) == 2.0

    def test_calculate_ema_weights_newest_first_input(self):
        # newest first: [20, 10, 10]; oldest-first SMA of first 2 = 10, then 20
        # k = 2/3 -> 20 * 2/3 + 10 * 1/3
        assert calculate_ema([20.0, 10.0, 10.0], period=2) == pytest.approx(50 / 3)

    @pytest.mark.parametrize(
        "score,prefix",
        [
            (100, "Strong bull market"),
            (70, "Bull market"),
            (50, "Early uptrend"),
            (40, "Choppy/neutral"),
            (20, "Downtrend forming"),
            (0, "Bear market"),
        ],
    )
    def test_interpret_market_score(self, score, prefix):
        text = interpret_market_score(score, "x", 1.25, 14.0)
        assert text.startswith(prefix)
        assert "+1.2% from 50-EMA" in text
        assert ", VIX 14.0" in text

    def test_score_market_direction_direct(self):
        assert score_market_direction("uptrend", 14.9) == 80
        assert score_market_direction("downtrend", 31) == 0
        assert score_market_direction("strong_uptrend", 15) == 90


# ---------------------------------------------------------------- I component


def _holders(n, shares=1000, names=None):
    names = names or [f"FUND {i}" for i in range(n)]
    return [{"holder": nm, "shares": shares} for nm in names]


class TestInstitutionalCalculator:
    def test_sweet_spot_from_list_and_profile(self):
        holders = _holders(60, shares=1000)  # 60,000 shares
        profile = {"sharesOutstanding": 150_000}  # 40%
        result = inst.calculate_institutional_sponsorship(holders, profile, "TEST", False)
        assert result["num_holders"] == 60
        assert result["ownership_pct"] == pytest.approx(40.0)
        assert result["total_shares_held"] == 60_000
        assert result["score"] == 100
        assert result["data_source"] == "FMP"
        assert result["superinvestors"] == []
        assert "sweet spot" in result["interpretation"]

    def test_shares_outstanding_derived_from_market_cap(self):
        holders = _holders(60, shares=1000)
        profile = {"marketCap": 15_000_000, "price": 100.0}  # 150,000 shares
        result = inst.calculate_institutional_sponsorship(
            holders, profile, use_finviz_fallback=False
        )
        assert result["shares_outstanding"] == pytest.approx(150_000)
        assert result["ownership_pct"] == pytest.approx(40.0)

    def test_legacy_mktcap_field(self):
        holders = _holders(60, shares=1000)
        profile = {"mktCap": 15_000_000, "price": 100.0}
        result = inst.calculate_institutional_sponsorship(
            holders, profile, use_finviz_fallback=False
        )
        assert result["ownership_pct"] == pytest.approx(40.0)

    def test_no_shares_outstanding_warns_and_scores_by_count(self):
        result = inst.calculate_institutional_sponsorship(
            _holders(60), {"price": 0}, use_finviz_fallback=False
        )
        assert result["ownership_pct"] is None
        assert "Shares outstanding unavailable from FMP." in result["quality_warning"]
        assert "Score reduced by 50%" in result["quality_warning"]
        assert result["score"] == 50

    def test_missing_profile_warning(self):
        result = inst.calculate_institutional_sponsorship(
            _holders(35), None, use_finviz_fallback=False
        )
        assert result["quality_warning"].startswith("Company profile not provided.")
        assert result["score"] == 40
        assert "ownership % unavailable" in result["interpretation"]

    def test_stable_aggregate_dict_with_superinvestor(self):
        agg = {
            "num_holders": 80,
            "ownership_pct": 75.0,
            "top_holders": [
                {"holder": "Berkshire Hathaway Inc", "shares": 10},
                {"holder": "Pershing Square Capital", "shares": 5},
                {"holder": "Scion Asset Management LLC", "shares": 5},
                {"holder": None, "shares": None},
            ],
        }
        result = inst.calculate_institutional_sponsorship(agg, None, use_finviz_fallback=False)
        assert result["superinvestor_present"] is True
        assert result["superinvestors"] == [
            "Berkshire Hathaway Inc",
            "Pershing Square Capital",
            "Scion Asset Management LLC",
        ]
        assert result["ownership_pct"] == 75.0
        assert result["total_shares_held"] == 20
        assert result["score"] == 100  # 90 base + 10 superinvestor bonus
        assert "+1 more" in result["interpretation"]

    def test_missing_holders_everywhere_scores_zero(self):
        result = inst.calculate_institutional_sponsorship(None, {}, "X", False)
        assert result["score"] == 0
        assert result["quality_warning"] == (
            "Institutional holder data unavailable from FMP and Finviz. Score set to 0."
        )

    def test_empty_list_without_profile_scores_zero(self):
        result = inst.calculate_institutional_sponsorship([], None, use_finviz_fallback=False)
        assert result["score"] == 0
        assert result["num_holders"] == 0

    def test_finviz_fallback_success(self, monkeypatch):
        class FakeFinviz:
            def __init__(self, rate_limit_seconds=1.0):
                pass

            def get_institutional_ownership(self, symbol):
                assert symbol == "ABC"
                return {"inst_own_pct": 45.5}

        monkeypatch.setattr(inst, "FinvizStockClient", FakeFinviz, raising=False)
        monkeypatch.setattr(inst, "FINVIZ_AVAILABLE", True)
        result = inst.calculate_institutional_sponsorship(_holders(60), {"price": 0}, "ABC", True)
        assert result["ownership_pct"] == 45.5
        assert result["data_source"] == "Finviz"
        assert result["score"] == 100
        assert "Using Finviz institutional ownership data (45.5%)" in result["quality_warning"]

    def test_finviz_fallback_returns_nothing(self, monkeypatch):
        class FakeFinviz:
            def __init__(self, rate_limit_seconds=1.0):
                pass

            def get_institutional_ownership(self, symbol):
                return {"inst_own_pct": None}

        monkeypatch.setattr(inst, "FinvizStockClient", FakeFinviz, raising=False)
        monkeypatch.setattr(inst, "FINVIZ_AVAILABLE", True)
        result = inst.calculate_institutional_sponsorship(_holders(60), {"price": 0}, "ABC", True)
        assert result["ownership_pct"] is None
        assert "Finviz fallback also unavailable" in result["quality_warning"]
        assert result["data_source"] == "FMP"

    def test_finviz_fallback_raises(self, monkeypatch, capsys):
        class FakeFinviz:
            def __init__(self, rate_limit_seconds=1.0):
                pass

            def get_institutional_ownership(self, symbol):
                raise RuntimeError("boom")

        monkeypatch.setattr(inst, "FinvizStockClient", FakeFinviz, raising=False)
        monkeypatch.setattr(inst, "FINVIZ_AVAILABLE", True)
        result = inst.calculate_institutional_sponsorship(_holders(60), {"price": 0}, "ABC", True)
        assert "Finviz fallback failed" in result["quality_warning"]
        assert "boom" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "holders,sp,expected",
        [
            (60, False, 50),
            (35, False, 40),
            (120, False, 35),
            (200, False, 20),
            (5, False, 10),
            (60, True, 65),
            (200, True, 35),
        ],
    )
    def test_score_without_ownership(self, holders, sp, expected):
        assert inst.score_institutional_sponsorship(holders, None, sp, None) == expected

    def test_score_without_ownership_caps_at_70(self):
        assert inst.score_institutional_sponsorship(60, None, True, None) == 65

    @pytest.mark.parametrize(
        "holders,pct,sp,expected",
        [
            (75, 45, False, 100),
            (200, 45, True, 50 + 10),  # superinvestor but outside 30-150 -> default 50 +10
            (40, 30, False, 80),
            (120, 50, False, 80),
            (25, 40, False, 60),
            (60, 25, False, 60),
            (10, 5, False, 20),
            (10, 95, False, 20),
            (10, 15, False, 40),
            (10, 85, False, 40),
            (10, 50, False, 50),
            (40, 30, True, 100),  # 90 base + 10 superinvestor bonus
        ],
    )
    def test_score_with_ownership(self, holders, pct, sp, expected):
        assert inst.score_institutional_sponsorship(holders, pct, sp, None) == expected

    @pytest.mark.parametrize(
        "holders,msg",
        [
            (75, "sweet spot"),
            (40, "good, but could grow"),
            (120, "getting crowded"),
            (200, "overcrowded"),
            (10, "underowned"),
        ],
    )
    def test_interpret_holder_messages(self, holders, msg):
        text = inst.interpret_institutional_sponsorship(holders, None, False, [])
        assert msg in text

    @pytest.mark.parametrize(
        "pct,msg",
        [
            (45.0, "(ideal range)"),
            (25.0, "(acceptable)"),
            (70.0, "(acceptable)"),
            (10.0, "(underowned, potential upside)"),
            (95.0, "(overcrowded, vulnerable)"),
        ],
    )
    def test_interpret_ownership_messages(self, pct, msg):
        text = inst.interpret_institutional_sponsorship(60, pct, False, [])
        assert msg in text

    def test_interpret_superinvestor_names_truncated(self):
        text = inst.interpret_institutional_sponsorship(60, 40.0, True, ["A", "B", "C", "D"])
        assert "Superinvestors: A, B +2 more" in text


def test_zero_eps_in_annual_growth_is_reported_as_missing():
    """Pin: a literal 0 EPS is falsy, so it is reported as missing rather than non-positive."""
    stmts = _annual([8, 4, 0, 1])
    result = calculate_annual_growth(stmts)
    assert result["score"] == 0
    assert result["error"] == "Missing EPS data for year 2022-12-31"
