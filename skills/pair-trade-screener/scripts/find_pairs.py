#!/usr/bin/env python3
"""
Pair Trade Screener - Find Cointegrated Stock Pairs

This script screens for statistically significant pair trading opportunities by:
1. Fetching historical price data from FMP API
2. Calculating pairwise correlations
3. Testing for cointegration (ADF test)
4. Estimating half-life of mean reversion
5. Ranking pairs by statistical strength

Usage:
    # Sector-based screening
    uv run --with 'statsmodels>=0.14,<0.15' python \
        skills/pair-trade-screener/scripts/find_pairs.py \
        --sector Technology --min-correlation 0.70

    # Custom stock list
    uv run --with 'statsmodels>=0.14,<0.15' python \
        skills/pair-trade-screener/scripts/find_pairs.py \
        --symbols AAPL,MSFT,GOOGL,META --min-correlation 0.75

    # Full options
    uv run --with 'statsmodels>=0.14,<0.15' python \
        skills/pair-trade-screener/scripts/find_pairs.py \
        --sector Financials \\
        --min-correlation 0.70 \\
        --min-market-cap 2000000000 \\
        --lookback-days 730 \\
        --output /tmp/pair-trade/financials.json

Requirements:
    Python 3.9+ and statsmodels>=0.14,<0.15

Author: Claude Trading Skills
Version: 1.0
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from pair_fmp_client import FMPClient
from scipy import stats
from statsmodels_support import require_statsmodels

# =============================================================================
# FMP API Functions
# =============================================================================


def get_api_key(args_api_key):
    """Get API key from args or environment variable"""
    if args_api_key:
        return args_api_key
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        print("ERROR: FMP_API_KEY not found. Set environment variable or use --api-key")
        sys.exit(1)
    return api_key


def fetch_sector_stocks(sector, api_key, min_market_cap=2_000_000_000):
    """Fetch stocks in a sector from FMP API"""
    print(f"\n[1/5] Fetching {sector} sector stocks from FMP API...")

    data = FMPClient(api_key=api_key).fetch_pair_screener_rows(
        {"sector": sector, "marketCapMoreThan": min_market_cap, "limit": 1000}
    )

    if not data:
        print(f"ERROR: No stocks found in {sector} sector with market cap > ${min_market_cap:,}")
        sys.exit(1)

    # Extract symbols and basic info
    stocks = []
    for item in data:
        if item.get("isActivelyTrading", True):
            stocks.append(
                {
                    "symbol": item["symbol"],
                    "name": item.get("companyName", ""),
                    "marketCap": item.get("marketCap", 0),
                    "sector": item.get("sector", sector),
                    "exchange": item.get("exchangeShortName", ""),
                }
            )

    print(f"  → Found {len(stocks)} stocks in {sector} sector")
    return stocks


def fetch_historical_prices(symbol, api_key, lookback_days=730, client=None):
    """Fetch historical dividend-adjusted prices for a symbol.

    Pass one shared ``client`` across a batch so the daily-limit latch and the
    endpoint failure state survive between symbols. The returned Series carries
    ``attrs["price_basis"]``: "dividend_adjusted", "adj_close" or raw "close".
    """
    if client is None:
        client = FMPClient(api_key=api_key)
    data = client.fetch_pair_history(symbol, lookback_days=lookback_days)
    if not data:
        return None

    # Extract historical prices
    historical = data["historical"][:lookback_days]
    historical = historical[::-1]  # Reverse to chronological order

    # Convert to pandas Series
    prices = pd.Series(
        [item.get("adjClose") or item["close"] for item in historical],  # stable shape compat
        index=[pd.to_datetime(item["date"]) for item in historical],
        name=symbol,
    )
    prices.attrs["price_basis"] = data.get("price_basis", "unknown")

    return prices


def summarize_price_basis(price_data):
    """Map symbol -> price basis for a fetched batch."""
    return {
        symbol: series.attrs.get("price_basis", "unknown") for symbol, series in price_data.items()
    }


def warn_on_mixed_price_basis(price_basis):
    """Warn when adjusted and raw-close series are mixed in one run."""
    raw = sorted(s for s, basis in price_basis.items() if basis == "close")
    adjusted = [s for s, b in price_basis.items() if b in ("dividend_adjusted", "adj_close")]
    if raw and adjusted:
        print(
            "WARN: mixed price bases in one run: raw close (not dividend-adjusted) for "
            f"{', '.join(raw)}; adjusted prices for {len(adjusted)} other symbol(s). "
            "Cross-symbol statistics are not comparable.",
            file=sys.stderr,
        )


def fetch_price_data_batch(symbols, api_key, lookback_days=730):
    """Fetch historical prices for multiple symbols"""
    print(f"\n[2/5] Fetching {lookback_days} days of price data for {len(symbols)} stocks...")

    price_data = {}
    failed_symbols = []
    client = FMPClient(api_key=api_key)  # shared: keeps the rate-limit latch and breakers

    for i, symbol in enumerate(symbols, 1):
        if client.rate_limit_reached:
            # Quota is spent: fail the rest immediately, with no HTTP and no sleep.
            failed_symbols.extend(symbols[i - 1 :])
            print("\n  → Daily API limit reached; skipping remaining symbols")
            break

        print(f"  [{i}/{len(symbols)}] Fetching {symbol}...", end="", flush=True)

        prices = fetch_historical_prices(symbol, api_key, lookback_days, client=client)

        if prices is not None and len(prices) >= 250:  # Require at least 250 days
            price_data[symbol] = prices
            print(f" ✓ ({len(prices)} days)")
        else:
            failed_symbols.append(symbol)
            print(" ✗ (insufficient data)")

        # Rate limiting
        if not client.rate_limit_reached:
            time.sleep(0.3)

    print(f"\n  → Successfully fetched {len(price_data)} stocks")
    if failed_symbols:
        print(f"  → Failed: {', '.join(failed_symbols)}")

    warn_on_mixed_price_basis(summarize_price_basis(price_data))

    return price_data


# =============================================================================
# Statistical Analysis Functions
# =============================================================================


def _align_finite_prices(prices_a, prices_b, min_observations=2):
    """Inner-align two price series and drop every non-finite observation pair."""
    try:
        aligned = pd.concat(
            [pd.Series(prices_a, name="price_a"), pd.Series(prices_b, name="price_b")],
            axis=1,
            join="inner",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("price series could not be aligned") from exc

    aligned = aligned.apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(aligned["price_a"].to_numpy()) & np.isfinite(aligned["price_b"].to_numpy())
    aligned = aligned.loc[finite]
    if len(aligned) < min_observations:
        raise ValueError(f"at least {min_observations} paired finite observations are required")
    return aligned["price_a"], aligned["price_b"]


def calculate_correlation(prices_a, prices_b):
    """Calculate Pearson correlation coefficient"""
    try:
        aligned_a, aligned_b = _align_finite_prices(prices_a, prices_b, min_observations=100)
    except ValueError:
        return None

    correlation = aligned_a.corr(aligned_b)
    return correlation if np.isfinite(correlation) else None


def calculate_beta(prices_a, prices_b):
    """Calculate hedge ratio (beta) using OLS regression"""
    aligned_a, aligned_b = _align_finite_prices(prices_a, prices_b)

    if aligned_a.nunique() < 2 or aligned_b.nunique() < 2:
        raise ValueError("at least two finite observations and non-constant prices are required")

    # Linear regression: A = alpha + beta * B
    slope, intercept, r_value, p_value, std_err = stats.linregress(aligned_b, aligned_a)

    return {"beta": slope, "intercept": intercept, "r_squared": r_value**2}


def test_cointegration(prices_a, prices_b, beta):
    """Test for cointegration using Augmented Dickey-Fuller test"""
    _, adfuller = require_statsmodels()

    # ADF test
    try:
        aligned_a, aligned_b = _align_finite_prices(prices_a, prices_b)
        spread = aligned_a - (beta * aligned_b)
        result = adfuller(spread, maxlag=1, regression="c")
        adf_statistic = result[0]
        p_value = result[1]
        critical_values = result[4]

        return {
            "adf_statistic": adf_statistic,
            "p_value": p_value,
            "critical_value_1pct": critical_values["1%"],
            "critical_value_5pct": critical_values["5%"],
            "critical_value_10pct": critical_values["10%"],
            "is_cointegrated": bool(p_value < 0.05),
            "spread": spread,
        }
    except Exception:
        return None


def calculate_half_life(spread):
    """Estimate mean reversion half-life using AR(1) model"""
    AutoReg, _ = require_statsmodels()

    try:
        # Fit AR(1) model
        model = AutoReg(spread.dropna(), lags=1)
        result = model.fit()

        # Extract autocorrelation coefficient
        phi = result.params.iloc[1]

        # Calculate half-life
        if phi >= 1.0 or phi <= 0:
            return None  # No mean reversion

        half_life = -np.log(2) / np.log(phi)

        return half_life

    except Exception:
        return None


def calculate_current_zscore(spread, window=90):
    """Calculate current z-score of spread"""
    if len(spread) < window:
        window = len(spread)

    mean = spread[-window:].mean()
    std = spread[-window:].std()

    if not np.isfinite(std) or std == 0:
        return None

    current_spread = spread.iloc[-1]
    zscore = (current_spread - mean) / std

    return zscore if np.isfinite(zscore) else None


# =============================================================================
# Pair Analysis
# =============================================================================


def analyze_pair(symbol_a, symbol_b, prices_a, prices_b, min_correlation=0.70):
    """Analyze a single pair for cointegration"""

    # Step 1: Calculate correlation
    correlation = calculate_correlation(prices_a, prices_b)
    if correlation is None or correlation < min_correlation:
        return None

    # Step 2: Calculate beta (hedge ratio)
    try:
        beta_result = calculate_beta(prices_a, prices_b)
    except ValueError:
        return None
    beta = beta_result["beta"]

    # Step 3: Test for cointegration
    coint_result = test_cointegration(prices_a, prices_b, beta)
    if coint_result is None:
        return None

    # Step 4: Calculate half-life (if cointegrated)
    half_life = None
    if coint_result["is_cointegrated"]:
        half_life = calculate_half_life(coint_result["spread"])

    # Step 5: Calculate current z-score
    current_zscore = calculate_current_zscore(coint_result["spread"])

    # Step 6: Determine trade signal
    signal = "NONE"
    if current_zscore is not None:
        if current_zscore > 2.0:
            signal = "SHORT"  # Short A, Long B
        elif current_zscore < -2.0:
            signal = "LONG"  # Long A, Short B

    # Step 7: Determine strength rating
    strength = "☆"
    if coint_result["p_value"] < 0.01:
        strength = "★★★"
    elif coint_result["p_value"] < 0.05:
        strength = "★★"

    return {
        "pair": f"{symbol_a}/{symbol_b}",
        "stock_a": symbol_a,
        "stock_b": symbol_b,
        "correlation": round(correlation, 4),
        "beta": round(beta, 4),
        "cointegration_pvalue": round(coint_result["p_value"], 4),
        "adf_statistic": round(coint_result["adf_statistic"], 4),
        "critical_value_5pct": round(coint_result["critical_value_5pct"], 4),
        "is_cointegrated": coint_result["is_cointegrated"],
        "half_life_days": round(half_life, 1) if half_life else None,
        "current_zscore": round(current_zscore, 2) if current_zscore is not None else None,
        "signal": signal,
        "strength": strength,
        "timestamp": datetime.now().isoformat(),
    }


def screen_all_pairs(price_data, min_correlation=0.70):
    """Screen all possible pairs from price data"""
    print("\n[3/5] Calculating correlations and testing pairs...")

    symbols = list(price_data.keys())
    total_pairs = len(list(combinations(symbols, 2)))

    print(f"  → Total possible pairs: {total_pairs}")
    print(f"  → Minimum correlation: {min_correlation}")

    pairs_analyzed = 0
    cointegrated_pairs = []

    # Analyze all combinations
    for symbol_a, symbol_b in combinations(symbols, 2):
        pairs_analyzed += 1

        if pairs_analyzed % 10 == 0 or pairs_analyzed == total_pairs:
            print(f"  [{pairs_analyzed}/{total_pairs}] pairs analyzed...", end="\r", flush=True)

        try:
            result = analyze_pair(
                symbol_a, symbol_b, price_data[symbol_a], price_data[symbol_b], min_correlation
            )
        except (TypeError, ValueError):
            result = None

        if result and result["is_cointegrated"]:
            cointegrated_pairs.append(result)

    print(f"\n  → Found {len(cointegrated_pairs)} cointegrated pairs")

    return cointegrated_pairs


def rank_pairs(pairs):
    """Rank pairs by statistical strength"""
    print("\n[4/5] Ranking pairs by statistical strength...")

    # Sort by p-value (ascending) and then by absolute z-score (descending)
    ranked = sorted(
        pairs, key=lambda x: (x["cointegration_pvalue"], -abs(x["current_zscore"] or 0))
    )

    print("  → Top 10 pairs:")
    for i, pair in enumerate(ranked[:10], 1):
        zscore = pair["current_zscore"]
        zscore_text = f"{zscore:.2f}" if zscore is not None else "N/A"
        print(
            f"    {i}. {pair['pair']} "
            f"(p={pair['cointegration_pvalue']:.4f}, "
            f"z={zscore_text}, "
            f"{pair['strength']})"
        )

    return ranked


# =============================================================================
# Output
# =============================================================================


def save_results(pairs, output_file, price_basis=None):
    """Save results to JSON file.

    ``price_basis`` (symbol -> "dividend_adjusted" | "adj_close" | "close") is
    recorded under ``metadata.price_basis`` when given.
    """
    print(f"\n[5/5] Saving results to {output_file}...")

    output_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_pairs": len(pairs),
            "cointegrated_pairs": sum(1 for p in pairs if p["is_cointegrated"]),
            "active_signals": sum(1 for p in pairs if p["signal"] != "NONE"),
        },
        "pairs": pairs,
    }
    if price_basis is not None:
        output_data["metadata"]["price_basis"] = dict(price_basis)

    output_path = Path(output_file)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file_handle:
            json.dump(output_data, file_handle, indent=2)
    except OSError as exc:
        raise RuntimeError(f"could not write output file {output_path}: {exc}") from exc

    print(f"  → Saved {len(pairs)} pairs to {output_file}")
    print(f"  → Cointegrated pairs: {output_data['metadata']['cointegrated_pairs']}")
    print(f"  → Active signals: {output_data['metadata']['active_signals']}")


def print_summary(pairs):
    """Print summary to console"""
    print("\n" + "=" * 70)
    print("PAIR TRADING SCREEN SUMMARY")
    print("=" * 70)

    cointegrated = [p for p in pairs if p["is_cointegrated"]]
    with_signals = [p for p in cointegrated if p["signal"] != "NONE"]

    print(f"\nTotal pairs analyzed: {len(pairs)}")
    print(f"Cointegrated pairs: {len(cointegrated)}")
    print(f"Pairs with trade signals: {len(with_signals)}")

    if with_signals:
        print(f"\n{'=' * 70}")
        print("ACTIVE TRADE SIGNALS")
        print("=" * 70)

        for pair in with_signals[:10]:
            print(f"\nPair: {pair['pair']}")
            print(f"  Signal: {pair['signal']}")
            print(f"  Z-Score: {pair['current_zscore']:.2f}")
            print(f"  Correlation: {pair['correlation']:.4f}")
            print(f"  P-Value: {pair['cointegration_pvalue']:.4f}")
            print(
                f"  Half-Life: {pair['half_life_days']:.1f} days"
                if pair["half_life_days"]
                else "  Half-Life: N/A"
            )
            print(f"  Strength: {pair['strength']}")

    print(f"\n{'=' * 70}\n")


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Screen for cointegrated stock pairs suitable for pair trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Screen Technology sector
  uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --sector Technology --output /tmp/pair-trade/technology.json

  # Custom stock list
  uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --symbols AAPL,MSFT,GOOGL,META --output /tmp/pair-trade/custom.json

  # Adjust parameters
  uv run --with 'statsmodels>=0.14,<0.15' python skills/pair-trade-screener/scripts/find_pairs.py --sector Financials --min-correlation 0.75 --lookback-days 365 --output /tmp/pair-trade/financials.json
        """,
    )

    parser.add_argument(
        "--sector", type=str, help="Sector to screen (Technology, Financials, Healthcare, etc.)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of stock symbols (alternative to --sector)",
    )
    parser.add_argument(
        "--min-correlation",
        type=float,
        default=0.70,
        help="Minimum correlation threshold (default: 0.70)",
    )
    parser.add_argument(
        "--min-market-cap",
        type=float,
        default=2_000_000_000,
        help="Minimum market cap filter in dollars (default: $2B)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=730,
        help="Historical data lookback period in days (default: 730)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="pair_analysis.json",
        help="Output JSON file (default: pair_analysis.json)",
    )
    parser.add_argument("--api-key", type=str, help="FMP API key (or set FMP_API_KEY env variable)")

    args = parser.parse_args()

    # Validate inputs
    if not args.sector and not args.symbols:
        parser.error("Either --sector or --symbols must be provided")

    if args.sector and args.symbols:
        parser.error("Provide either --sector or --symbols, not both")
    if not math.isfinite(args.min_correlation) or not 0 <= args.min_correlation <= 1:
        parser.error("--min-correlation must be finite and between 0 and 1")
    if args.lookback_days < 250:
        parser.error("--lookback-days must be at least 250")
    if not math.isfinite(args.min_market_cap) or args.min_market_cap < 0:
        parser.error("--min-market-cap must be finite and non-negative")
    custom_symbols = None
    if args.symbols:
        custom_symbols = [symbol.strip().upper() for symbol in args.symbols.split(",")]
        if any(not symbol for symbol in custom_symbols) or len(set(custom_symbols)) < 2:
            parser.error("--symbols must contain at least two distinct, non-empty symbols")

    # Get API key
    api_key = get_api_key(args.api_key)

    print("\n" + "=" * 70)
    print("PAIR TRADE SCREENER")
    print("=" * 70)
    print("Configuration:")
    print(f"  Min Correlation: {args.min_correlation}")
    print(f"  Lookback Days: {args.lookback_days}")
    print(f"  Min Market Cap: ${args.min_market_cap:,.0f}")

    # Get list of stocks to analyze
    if args.sector:
        stocks = fetch_sector_stocks(args.sector, api_key, args.min_market_cap)
        symbols = [s["symbol"] for s in stocks]
    else:
        symbols = custom_symbols

    # Fetch price data
    price_data = fetch_price_data_batch(symbols, api_key, args.lookback_days)

    if len(price_data) < 2:
        print("\nERROR: Need at least 2 stocks with valid data")
        sys.exit(1)

    # Screen all pairs
    pairs = screen_all_pairs(price_data, args.min_correlation)

    if not pairs:
        print("\nNo cointegrated pairs found. Try:")
        print("  - Lowering --min-correlation threshold")
        print("  - Expanding stock universe (--sector or --symbols)")
        print("  - Increasing --lookback-days")
        ranked_pairs = []
    else:
        # Rank pairs
        ranked_pairs = rank_pairs(pairs)

    # Save results
    save_results(ranked_pairs, args.output, summarize_price_basis(price_data))

    # Print summary
    print_summary(ranked_pairs)


def cli():
    """Run the command-line interface without exposing a traceback to users."""
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
