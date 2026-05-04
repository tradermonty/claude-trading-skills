#!/usr/bin/env python3
"""
L Component - Leadership / Relative Strength Calculator (Phase 3.1)

Calculates CANSLIM 'L' component score based on multi-period weighted relative
price performance vs a configurable benchmark (default: ^GSPC).

O'Neil's Rule: "The top-performing stocks, prior to major advances, have Relative Strength
Ratings averaging 87 at pivot points. You want to see 80+ RS Rank - meaning the stock is
outperforming 80% of all other stocks over the past 52 weeks."

Phase 3.1 Multi-Period RS:
- Three trailing periods (3m=63 bars, 6m=126 bars, 12m=252 bars) instead of a single 52w slice.
- Weighted RS = 0.40 * rel_3m + 0.30 * rel_6m + 0.30 * rel_12m
  (When some periods are missing, the available periods are re-normalized so weights sum to 1.0.)
- Benchmark is configurable via the rs_benchmark argument (defaults to ^GSPC).

Backward Compatibility:
- The legacy fields (stock_52w_performance, sp500_52w_performance, relative_performance,
  rs_rank_estimate) are preserved with their original semantics (365-day full-window
  return). Existing callers and JSON consumers continue to work.
- The legacy sp500_performance argument (pre-calculated benchmark return) routes to a
  single-period scoring path; multi-period fields are then None.

Score Bands (vs benchmark, weighted relative performance):
- 100 points: Relative outperformance > +50% (top 1%)
- 95 points: +30% to +50%
- 90 points: +20% to +30%
- 80 points: +10% to +20%
- 70 points: +5% to +10%
- 60 points: 0% to +5%
- 50 points: -5% to 0%
- 40 points: -10% to -5%
- 20 points: -20% to -10%
- 0 points: < -20%

When no benchmark is available, scoring falls back to the weighted absolute performance
of the stock and a 20% penalty is applied (preserves the legacy fallback behavior).
"""

from typing import Optional

# Multi-period configuration (trading days)
DEFAULT_PERIODS_DAYS = {"3m": 63, "6m": 126, "12m": 252}
DEFAULT_PERIOD_WEIGHTS = {"3m": 0.40, "6m": 0.30, "12m": 0.30}


def _sort_prices_ascending(prices: list[dict]) -> list[dict]:
    """
    Normalize a price list to ascending date order.

    FMP returns historical prices newest-first; some callers (notably the legacy
    leadership_calculator) accept either ordering. Normalizing here lets the
    multi-period helpers always work with the most recent close at index -1.
    """
    if not prices:
        return []

    # Use string sort on ISO-format dates ("YYYY-MM-DD" sorts correctly lexicographically).
    # Entries without a "date" key keep their original relative order.
    try:
        return sorted(prices, key=lambda p: p.get("date", ""))
    except TypeError:
        return list(prices)


def slice_period_return(prices: list[dict], days: int) -> Optional[float]:
    """
    Compute the percentage return over the most recent ``days`` trading bars.

    The input list is normalized to ascending date order internally, so the function
    is agnostic to whether FMP returned newest-first or oldest-first.

    Returns None when there are fewer than ``days`` bars available, or when the
    starting close is not strictly positive.
    """
    if not prices or days <= 0:
        return None

    sorted_prices = _sort_prices_ascending(prices)
    if len(sorted_prices) < days:
        return None

    window = sorted_prices[-days:]
    try:
        start_price = window[0].get("close", 0)
        end_price = window[-1].get("close", 0)
    except (AttributeError, KeyError, TypeError):
        return None

    if not isinstance(start_price, (int, float)) or not isinstance(end_price, (int, float)):
        return None
    if start_price <= 0:
        return None

    return ((end_price - start_price) / start_price) * 100


def compute_multi_period_rs(
    stock_prices: list[dict],
    benchmark_prices: Optional[list[dict]],
    periods_days: Optional[dict] = None,
    weights: Optional[dict] = None,
) -> dict:
    """
    Compute multi-period Relative Strength against an optional benchmark.

    Args:
        stock_prices: List of {"date": str, "close": float, ...} for the stock.
        benchmark_prices: Same shape for the benchmark, or None (no benchmark).
        periods_days: Mapping of period label ("3m"/"6m"/"12m") to bar count.
                      Defaults to DEFAULT_PERIODS_DAYS.
        weights: Mapping of period label to weight in [0, 1]. Defaults to
                 DEFAULT_PERIOD_WEIGHTS. Available periods are re-normalized
                 so their weights sum to 1.0.

    Returns a dict with:
        rs_3m_return / rs_6m_return / rs_12m_return: stock absolute return %
        benchmark_3m_return / benchmark_6m_return / benchmark_12m_return: benchmark return %
        rel_3m / rel_6m / rel_12m: stock_return - benchmark_return (None when no benchmark)
        weighted_stock_performance: re-normalized weighted absolute return (None if all missing)
        weighted_relative_performance: re-normalized weighted relative return
                                       (None when no benchmark or all missing)
        available_periods: list of labels with valid stock returns
        missing_periods: list of labels missing valid stock returns
    """
    periods_days = periods_days or DEFAULT_PERIODS_DAYS
    weights = weights or DEFAULT_PERIOD_WEIGHTS

    stock_returns = {}
    benchmark_returns = {}
    relative_returns = {}

    for label, days in periods_days.items():
        stock_returns[label] = slice_period_return(stock_prices, days)
        if benchmark_prices is not None:
            benchmark_returns[label] = slice_period_return(benchmark_prices, days)
        else:
            benchmark_returns[label] = None

        if stock_returns[label] is not None and benchmark_returns[label] is not None:
            relative_returns[label] = stock_returns[label] - benchmark_returns[label]
        else:
            relative_returns[label] = None

    available = [label for label, value in stock_returns.items() if value is not None]
    missing = [label for label in periods_days if label not in available]

    weighted_stock = _weighted_average(stock_returns, weights, available)

    # Weighted relative performance only makes sense when ALL available periods
    # also have a benchmark return; otherwise it would mix relative vs. absolute terms.
    rel_available = [label for label in available if relative_returns.get(label) is not None]
    weighted_relative = _weighted_average(relative_returns, weights, rel_available)

    return {
        "rs_3m_return": _round_or_none(stock_returns.get("3m")),
        "rs_6m_return": _round_or_none(stock_returns.get("6m")),
        "rs_12m_return": _round_or_none(stock_returns.get("12m")),
        "benchmark_3m_return": _round_or_none(benchmark_returns.get("3m")),
        "benchmark_6m_return": _round_or_none(benchmark_returns.get("6m")),
        "benchmark_12m_return": _round_or_none(benchmark_returns.get("12m")),
        "rel_3m": _round_or_none(relative_returns.get("3m")),
        "rel_6m": _round_or_none(relative_returns.get("6m")),
        "rel_12m": _round_or_none(relative_returns.get("12m")),
        "weighted_stock_performance": _round_or_none(weighted_stock),
        "weighted_relative_performance": _round_or_none(weighted_relative),
        "available_periods": available,
        "missing_periods": missing,
    }


def _weighted_average(values: dict, weights: dict, available_keys: list[str]) -> Optional[float]:
    """
    Compute weighted average over the available keys, re-normalizing the weights
    so they sum to 1.0. Returns None if no keys are available or all weights are zero.
    """
    if not available_keys:
        return None

    weight_sum = sum(weights.get(k, 0.0) for k in available_keys)
    if weight_sum <= 0:
        return None

    total = 0.0
    for k in available_keys:
        v = values.get(k)
        if v is None:
            return None
        total += v * (weights.get(k, 0.0) / weight_sum)
    return total


def _round_or_none(value: Optional[float], ndigits: int = 2) -> Optional[float]:
    """Round to ``ndigits`` decimals when value is numeric, otherwise return None."""
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        return None
    return round(value, ndigits)


def classify_rs_rating(rs_rank_estimate: Optional[int]) -> str:
    """
    Convert an RS rank estimate (0-99) into a short label.

    Uses fixed thresholds so it is independent of any human-readable interpretation
    string. Returns "Weak" when the rank is None.
    """
    if rs_rank_estimate is None:
        return "Weak"
    if rs_rank_estimate >= 90:
        return "Market Leader"
    if rs_rank_estimate >= 80:
        return "Strong"
    if rs_rank_estimate >= 60:
        return "Above Average"
    if rs_rank_estimate >= 40:
        return "Average"
    if rs_rank_estimate >= 25:
        return "Laggard"
    return "Weak"


def calculate_leadership(
    historical_prices: list[dict],
    sp500_historical: Optional[list[dict]] = None,
    sp500_performance: Optional[float] = None,
    rs_benchmark: str = "^GSPC",
) -> dict:
    """
    Calculate Leadership/Relative Strength score (L component).

    Args:
        historical_prices: List of daily price data for the stock (any order).
                           Each entry: {"date": str, "close": float, "volume": int}
        sp500_historical: Optional list of daily benchmark prices (same shape).
                          Used by the modern multi-period path.
        sp500_performance: Optional pre-calculated benchmark return (legacy path).
                           When provided, multi-period calculation is skipped.
        rs_benchmark: Symbol of the benchmark used (default: "^GSPC"). Surfaced in
                      the returned dict; does not affect calculation since the data
                      is supplied via sp500_historical / sp500_performance.

    Returns a dict containing both legacy and Phase 3.1 fields. See module docstring
    for full schema details.
    """
    # Validate input
    if not historical_prices or len(historical_prices) < 50:
        return _empty_result(
            error="Insufficient historical price data (need 50+ days)",
            interpretation="Data unavailable",
            rs_benchmark=rs_benchmark,
        )

    # Compute legacy 365-day full-window stock performance for backward compatibility.
    # This preserves the existing semantics of stock_52w_performance.
    try:
        sorted_stock = _sort_prices_ascending(historical_prices)
        start_price = sorted_stock[0].get("close", 0)
        end_price = sorted_stock[-1].get("close", 0)
        if start_price <= 0:
            return _empty_result(
                error="Invalid start price (zero or negative)",
                interpretation="Data quality issue",
                rs_benchmark=rs_benchmark,
            )
        legacy_stock_performance = ((end_price - start_price) / start_price) * 100
        days_analyzed = len(sorted_stock)
    except (KeyError, TypeError, ZeroDivisionError) as e:
        return _empty_result(
            error=f"Price calculation error: {e}",
            interpretation="Calculation error",
            rs_benchmark=rs_benchmark,
        )

    # ---- Legacy path: pre-calculated benchmark performance ----
    if sp500_performance is not None:
        return _legacy_single_period_path(
            stock_performance=legacy_stock_performance,
            sp500_performance=sp500_performance,
            days_analyzed=days_analyzed,
            rs_benchmark=rs_benchmark,
        )

    # ---- Modern path: multi-period weighted RS ----
    multi = compute_multi_period_rs(historical_prices, sp500_historical)

    # Legacy 365-day relative performance (kept for backward compatibility).
    legacy_benchmark_performance = None
    legacy_relative_performance = None
    quality_warning = None

    if sp500_historical and len(sp500_historical) >= 50:
        try:
            sorted_bench = _sort_prices_ascending(sp500_historical)
            bench_start = sorted_bench[0].get("close", 0)
            bench_end = sorted_bench[-1].get("close", 0)
            if bench_start > 0:
                legacy_benchmark_performance = ((bench_end - bench_start) / bench_start) * 100
                legacy_relative_performance = (
                    legacy_stock_performance - legacy_benchmark_performance
                )
        except (KeyError, TypeError, ZeroDivisionError):
            quality_warning = "Benchmark performance calculation failed"
    elif sp500_historical is None:
        quality_warning = (
            f"Benchmark ({rs_benchmark}) data unavailable - using absolute performance only"
        )
    else:
        quality_warning = (
            f"Benchmark ({rs_benchmark}) data insufficient - using absolute performance only"
        )

    # 4-step fallback hierarchy (preferring relative-vs-benchmark over absolute):
    # 1. multi-period weighted relative   (full Phase 3.1 path)
    # 2. multi-period weighted absolute   (multi-period available but no benchmark)
    # 3. legacy 365-day relative          (multi-period missing but benchmark + >=50 bars)
    # 4. legacy 365-day absolute          (no benchmark and no multi-period)
    if multi["weighted_relative_performance"] is not None:
        scoring_input = multi["weighted_relative_performance"]
        has_benchmark = True
    elif multi["weighted_stock_performance"] is not None:
        scoring_input = multi["weighted_stock_performance"]
        has_benchmark = False
    elif legacy_relative_performance is not None:
        scoring_input = legacy_relative_performance
        has_benchmark = True
    else:
        scoring_input = legacy_stock_performance
        has_benchmark = False

    # If even the fallback stock performance is unavailable, flag as data error.
    if scoring_input is None:
        return _empty_result(
            error="Unable to compute relative strength (no usable price periods)",
            interpretation="Data unavailable",
            rs_benchmark=rs_benchmark,
        )

    score, rs_rank_estimate = score_leadership(scoring_input, has_benchmark)
    rs_rating = classify_rs_rating(rs_rank_estimate)

    interpretation = interpret_leadership(
        score=score,
        stock_performance=legacy_stock_performance,
        sp500_performance=legacy_benchmark_performance,
        relative_performance=(
            legacy_relative_performance
            if legacy_relative_performance is not None
            else legacy_stock_performance
        ),
        days_analyzed=days_analyzed,
    )

    return {
        # ---- Legacy fields (semantics preserved) ----
        "score": score,
        "stock_52w_performance": round(legacy_stock_performance, 2),
        "sp500_52w_performance": (
            round(legacy_benchmark_performance, 2)
            if legacy_benchmark_performance is not None
            else None
        ),
        "relative_performance": (
            round(legacy_relative_performance, 2)
            if legacy_relative_performance is not None
            else round(legacy_stock_performance, 2)
        ),
        "rs_rank_estimate": rs_rank_estimate,
        "days_analyzed": days_analyzed,
        "interpretation": interpretation,
        "quality_warning": quality_warning,
        "error": None,
        # ---- Phase 3.1 multi-period fields ----
        "rs_3m_return": multi["rs_3m_return"],
        "rs_6m_return": multi["rs_6m_return"],
        "rs_12m_return": multi["rs_12m_return"],
        "benchmark_3m_return": multi["benchmark_3m_return"],
        "benchmark_6m_return": multi["benchmark_6m_return"],
        "benchmark_12m_return": multi["benchmark_12m_return"],
        "rel_3m": multi["rel_3m"],
        "rel_6m": multi["rel_6m"],
        "rel_12m": multi["rel_12m"],
        "weighted_stock_performance": multi["weighted_stock_performance"],
        "weighted_relative_performance": multi["weighted_relative_performance"],
        "available_periods": multi["available_periods"],
        "missing_periods": multi["missing_periods"],
        "benchmark_52w_performance": (
            round(legacy_benchmark_performance, 2)
            if legacy_benchmark_performance is not None
            else None
        ),
        "rs_benchmark": rs_benchmark,
        "rs_benchmark_relative_return": multi["rel_12m"],
        "rs_rating": rs_rating,
        "rs_component_score": score,
        "rs_rank_percentile": rs_rank_estimate,
    }


def _empty_result(error: str, interpretation: str, rs_benchmark: str = "^GSPC") -> dict:
    """Return a fully-populated zero-score result for error paths."""
    return {
        "score": 0,
        "error": error,
        "stock_52w_performance": None,
        "sp500_52w_performance": None,
        "relative_performance": None,
        "rs_rank_estimate": None,
        "days_analyzed": 0,
        "interpretation": interpretation,
        "quality_warning": None,
        "rs_3m_return": None,
        "rs_6m_return": None,
        "rs_12m_return": None,
        "benchmark_3m_return": None,
        "benchmark_6m_return": None,
        "benchmark_12m_return": None,
        "rel_3m": None,
        "rel_6m": None,
        "rel_12m": None,
        "weighted_stock_performance": None,
        "weighted_relative_performance": None,
        "available_periods": [],
        "missing_periods": list(DEFAULT_PERIODS_DAYS.keys()),
        "benchmark_52w_performance": None,
        "rs_benchmark": rs_benchmark,
        "rs_benchmark_relative_return": None,
        "rs_rating": "Weak",
        "rs_component_score": 0,
        "rs_rank_percentile": None,
    }


def _legacy_single_period_path(
    stock_performance: float,
    sp500_performance: float,
    days_analyzed: int,
    rs_benchmark: str,
) -> dict:
    """
    Legacy scoring path used when a pre-calculated benchmark return is supplied.
    Multi-period fields are returned as None.
    """
    relative_performance = stock_performance - sp500_performance
    score, rs_rank_estimate = score_leadership(relative_performance, has_benchmark=True)
    rs_rating = classify_rs_rating(rs_rank_estimate)
    interpretation = interpret_leadership(
        score=score,
        stock_performance=stock_performance,
        sp500_performance=sp500_performance,
        relative_performance=relative_performance,
        days_analyzed=days_analyzed,
    )
    return {
        "score": score,
        "stock_52w_performance": round(stock_performance, 2),
        "sp500_52w_performance": round(sp500_performance, 2),
        "relative_performance": round(relative_performance, 2),
        "rs_rank_estimate": rs_rank_estimate,
        "days_analyzed": days_analyzed,
        "interpretation": interpretation,
        "quality_warning": None,
        "error": None,
        "rs_3m_return": None,
        "rs_6m_return": None,
        "rs_12m_return": None,
        "benchmark_3m_return": None,
        "benchmark_6m_return": None,
        "benchmark_12m_return": None,
        "rel_3m": None,
        "rel_6m": None,
        "rel_12m": None,
        "weighted_stock_performance": None,
        "weighted_relative_performance": None,
        "available_periods": [],
        "missing_periods": list(DEFAULT_PERIODS_DAYS.keys()),
        "benchmark_52w_performance": round(sp500_performance, 2),
        "rs_benchmark": rs_benchmark,
        "rs_benchmark_relative_return": None,
        "rs_rating": rs_rating,
        "rs_component_score": score,
        "rs_rank_percentile": rs_rank_estimate,
    }


def score_leadership(relative_performance: float, has_benchmark: bool) -> tuple:
    """
    Score leadership based on relative performance.

    Args:
        relative_performance: Stock minus benchmark performance (%) when has_benchmark=True,
                              otherwise the stock's absolute performance (%) is used as
                              a fallback metric.
        has_benchmark: True if a benchmark was available; False applies a 20% penalty.

    Returns:
        tuple: (score, rs_rank_estimate)
    """
    if relative_performance >= 50:
        score = 100
        rs_rank_estimate = 99
    elif relative_performance >= 30:
        score = 95
        rs_rank_estimate = 95
    elif relative_performance >= 20:
        score = 90
        rs_rank_estimate = 90
    elif relative_performance >= 10:
        score = 80
        rs_rank_estimate = 80
    elif relative_performance >= 5:
        score = 70
        rs_rank_estimate = 70
    elif relative_performance >= 0:
        score = 60
        rs_rank_estimate = 60
    elif relative_performance >= -5:
        score = 50
        rs_rank_estimate = 50
    elif relative_performance >= -10:
        score = 40
        rs_rank_estimate = 40
    elif relative_performance >= -20:
        score = 20
        rs_rank_estimate = 25
    else:
        score = 0
        rs_rank_estimate = 10

    if not has_benchmark:
        score = int(score * 0.8)
        rs_rank_estimate = int(rs_rank_estimate * 0.9)

    return score, rs_rank_estimate


def interpret_leadership(
    score: int,
    stock_performance: float,
    sp500_performance: Optional[float],
    relative_performance: float,
    days_analyzed: int,
) -> str:
    """Generate a human-readable interpretation string."""
    if days_analyzed >= 250:
        period = "52-week"
    elif days_analyzed >= 180:
        period = "9-month"
    elif days_analyzed >= 90:
        period = "quarterly"
    else:
        period = f"{days_analyzed}-day"

    if stock_performance > 0:
        stock_msg = f"+{stock_performance:.1f}%"
    else:
        stock_msg = f"{stock_performance:.1f}%"

    if sp500_performance is not None:
        if relative_performance > 0:
            rel_msg = f"+{relative_performance:.1f}% vs benchmark"
        else:
            rel_msg = f"{relative_performance:.1f}% vs benchmark"
    else:
        rel_msg = "(absolute performance)"

    if score >= 90:
        rating = "Market Leader"
        action = "Strong momentum, prime CANSLIM candidate"
    elif score >= 80:
        rating = "Strong Performer"
        action = "Outperforming market significantly"
    elif score >= 60:
        rating = "Above Average"
        action = "Slight outperformance"
    elif score >= 40:
        rating = "Average"
        action = "Matching or slightly lagging market"
    elif score >= 20:
        rating = "Laggard"
        action = "Underperforming market - caution"
    else:
        rating = "Weak"
        action = "Significant underperformance - avoid"

    return f"{rating} - {period} return {stock_msg} ({rel_msg}). {action}"


def calculate_sector_relative_strength(
    stock_performance: float, sector_stocks_performance: list[float]
) -> dict:
    """
    Calculate relative strength within sector (optional enhancement).

    Args:
        stock_performance: Target stock's period return (%)
        sector_stocks_performance: List of sector peers' period returns (%)

    Returns:
        Dict with sector_rank, sector_percentile, is_sector_leader.
    """
    if not sector_stocks_performance:
        return {
            "sector_rank": None,
            "sector_percentile": None,
            "is_sector_leader": False,
            "error": "No sector data available",
        }

    all_stocks = sector_stocks_performance + [stock_performance]
    all_stocks_sorted = sorted(all_stocks, reverse=True)
    rank = all_stocks_sorted.index(stock_performance) + 1
    total = len(all_stocks)
    percentile = ((total - rank) / total) * 100

    return {
        "sector_rank": rank,
        "sector_total": total,
        "sector_percentile": round(percentile, 1),
        "is_sector_leader": percentile >= 80,
    }


# Example usage
if __name__ == "__main__":
    print("Testing Leadership Calculator (L Component)...")
    print()

    sample_prices = [
        {"date": "2024-01-01", "close": 100.0},
        {"date": "2024-06-01", "close": 120.0},
        {"date": "2025-01-01", "close": 180.0},
    ]
    sample_sp500 = [
        {"date": "2024-01-01", "close": 4500.0},
        {"date": "2024-06-01", "close": 4700.0},
        {"date": "2025-01-01", "close": 5400.0},
    ]

    result = calculate_leadership(sample_prices, sample_sp500)
    print("Test 1: Strong Outperformer")
    print(f"  Score: {result['score']}/100")
    print(f"  Interpretation: {result['interpretation']}")
    print()

    result3 = calculate_leadership(sample_prices)
    print("Test 3: Without S&P 500 Data (Fallback)")
    print(f"  Score: {result3['score']}/100 (penalty applied)")
    print(f"  Warning: {result3['quality_warning']}")
    print()

    print("Done.")
