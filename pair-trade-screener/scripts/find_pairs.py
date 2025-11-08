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
    python find_pairs.py --sector Technology --min-correlation 0.70

    # Custom stock list
    python find_pairs.py --symbols AAPL,MSFT,GOOGL,META --min-correlation 0.75

    # Full options
    python find_pairs.py \\
        --sector Financials \\
        --min-correlation 0.70 \\
        --min-market-cap 2000000000 \\
        --lookback-days 730 \\
        --output pairs_analysis.json \\
        --api-key YOUR_KEY

Requirements:
    pip install pandas numpy scipy statsmodels requests

Author: Claude Trading Skills
Version: 1.0
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from itertools import combinations

import numpy as np
import pandas as pd
import requests
from scipy import stats
from statsmodels.tsa.ar_model import AutoReg
from statsmodels.tsa.stattools import adfuller


# =============================================================================
# FMP API Functions
# =============================================================================

def get_api_key(args_api_key):
    """Get API key from args or environment variable"""
    if args_api_key:
        return args_api_key
    api_key = os.environ.get('FMP_API_KEY')
    if not api_key:
        print("ERROR: FMP_API_KEY not found. Set environment variable or use --api-key")
        sys.exit(1)
    return api_key


def fetch_sector_stocks(sector, api_key, min_market_cap=2_000_000_000):
    """Fetch stocks in a sector from FMP API"""
    print(f"\n[1/5] Fetching {sector} sector stocks from FMP API...")

    # Use stock screener to get sector stocks
    url = f"https://financialmodelingprep.com/api/v3/stock-screener"
    params = {
        'sector': sector,
        'marketCapMoreThan': min_market_cap,
        'limit': 1000,
        'apikey': api_key
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data:
            print(f"ERROR: No stocks found in {sector} sector with market cap > ${min_market_cap:,}")
            sys.exit(1)

        # Extract symbols and basic info
        stocks = []
        for item in data:
            if item.get('isActivelyTrading', True):
                stocks.append({
                    'symbol': item['symbol'],
                    'name': item.get('companyName', ''),
                    'marketCap': item.get('marketCap', 0),
                    'sector': item.get('sector', sector),
                    'exchange': item.get('exchangeShortName', '')
                })

        print(f"  → Found {len(stocks)} stocks in {sector} sector")
        return stocks

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to fetch sector stocks: {e}")
        sys.exit(1)


def fetch_historical_prices(symbol, api_key, lookback_days=730):
    """Fetch historical adjusted close prices for a symbol"""
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
    params = {'apikey': api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'historical' not in data:
            return None

        # Extract historical prices
        historical = data['historical'][:lookback_days]
        historical = historical[::-1]  # Reverse to chronological order

        # Convert to pandas Series
        prices = pd.Series(
            [item['adjClose'] for item in historical],
            index=[pd.to_datetime(item['date']) for item in historical],
            name=symbol
        )

        return prices

    except requests.exceptions.RequestException:
        return None


def fetch_price_data_batch(symbols, api_key, lookback_days=730):
    """Fetch historical prices for multiple symbols"""
    print(f"\n[2/5] Fetching {lookback_days} days of price data for {len(symbols)} stocks...")

    price_data = {}
    failed_symbols = []

    for i, symbol in enumerate(symbols, 1):
        print(f"  [{i}/{len(symbols)}] Fetching {symbol}...", end='', flush=True)

        prices = fetch_historical_prices(symbol, api_key, lookback_days)

        if prices is not None and len(prices) >= 250:  # Require at least 250 days
            price_data[symbol] = prices
            print(f" ✓ ({len(prices)} days)")
        else:
            failed_symbols.append(symbol)
            print(" ✗ (insufficient data)")

        # Rate limiting
        time.sleep(0.3)

    print(f"\n  → Successfully fetched {len(price_data)} stocks")
    if failed_symbols:
        print(f"  → Failed: {', '.join(failed_symbols)}")

    return price_data


# =============================================================================
# Statistical Analysis Functions
# =============================================================================

def calculate_correlation(prices_a, prices_b):
    """Calculate Pearson correlation coefficient"""
    # Align dates
    common_dates = prices_a.index.intersection(prices_b.index)
    if len(common_dates) < 100:
        return None

    aligned_a = prices_a.loc[common_dates]
    aligned_b = prices_b.loc[common_dates]

    correlation = aligned_a.corr(aligned_b)
    return correlation


def calculate_beta(prices_a, prices_b):
    """Calculate hedge ratio (beta) using OLS regression"""
    # Align dates
    common_dates = prices_a.index.intersection(prices_b.index)
    aligned_a = prices_a.loc[common_dates]
    aligned_b = prices_b.loc[common_dates]

    # Linear regression: A = alpha + beta * B
    slope, intercept, r_value, p_value, std_err = stats.linregress(aligned_b, aligned_a)

    return {
        'beta': slope,
        'intercept': intercept,
        'r_squared': r_value ** 2
    }


def test_cointegration(prices_a, prices_b, beta):
    """Test for cointegration using Augmented Dickey-Fuller test"""
    # Align dates
    common_dates = prices_a.index.intersection(prices_b.index)
    aligned_a = prices_a.loc[common_dates]
    aligned_b = prices_b.loc[common_dates]

    # Calculate spread
    spread = aligned_a - (beta * aligned_b)

    # ADF test
    try:
        result = adfuller(spread, maxlag=1, regression='c')
        adf_statistic = result[0]
        p_value = result[1]
        critical_values = result[4]

        return {
            'adf_statistic': adf_statistic,
            'p_value': p_value,
            'critical_value_1pct': critical_values['1%'],
            'critical_value_5pct': critical_values['5%'],
            'critical_value_10pct': critical_values['10%'],
            'is_cointegrated': p_value < 0.05,
            'spread': spread
        }
    except Exception as e:
        return None


def calculate_half_life(spread):
    """Estimate mean reversion half-life using AR(1) model"""
    try:
        # Fit AR(1) model
        model = AutoReg(spread.dropna(), lags=1)
        result = model.fit()

        # Extract autocorrelation coefficient
        phi = result.params[1]

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

    if std == 0:
        return None

    current_spread = spread.iloc[-1]
    zscore = (current_spread - mean) / std

    return zscore


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
    beta_result = calculate_beta(prices_a, prices_b)
    beta = beta_result['beta']

    # Step 3: Test for cointegration
    coint_result = test_cointegration(prices_a, prices_b, beta)
    if coint_result is None:
        return None

    # Step 4: Calculate half-life (if cointegrated)
    half_life = None
    if coint_result['is_cointegrated']:
        half_life = calculate_half_life(coint_result['spread'])

    # Step 5: Calculate current z-score
    current_zscore = calculate_current_zscore(coint_result['spread'])

    # Step 6: Determine trade signal
    signal = 'NONE'
    if current_zscore is not None:
        if current_zscore > 2.0:
            signal = 'SHORT'  # Short A, Long B
        elif current_zscore < -2.0:
            signal = 'LONG'   # Long A, Short B

    # Step 7: Determine strength rating
    strength = '☆'
    if coint_result['p_value'] < 0.01:
        strength = '★★★'
    elif coint_result['p_value'] < 0.05:
        strength = '★★'

    return {
        'pair': f"{symbol_a}/{symbol_b}",
        'stock_a': symbol_a,
        'stock_b': symbol_b,
        'correlation': round(correlation, 4),
        'beta': round(beta, 4),
        'cointegration_pvalue': round(coint_result['p_value'], 4),
        'adf_statistic': round(coint_result['adf_statistic'], 4),
        'critical_value_5pct': round(coint_result['critical_value_5pct'], 4),
        'is_cointegrated': coint_result['is_cointegrated'],
        'half_life_days': round(half_life, 1) if half_life else None,
        'current_zscore': round(current_zscore, 2) if current_zscore else None,
        'signal': signal,
        'strength': strength,
        'timestamp': datetime.now().isoformat()
    }


def screen_all_pairs(price_data, min_correlation=0.70):
    """Screen all possible pairs from price data"""
    print(f"\n[3/5] Calculating correlations and testing pairs...")

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
            print(f"  [{pairs_analyzed}/{total_pairs}] pairs analyzed...", end='\r', flush=True)

        result = analyze_pair(
            symbol_a, symbol_b,
            price_data[symbol_a],
            price_data[symbol_b],
            min_correlation
        )

        if result and result['is_cointegrated']:
            cointegrated_pairs.append(result)

    print(f"\n  → Found {len(cointegrated_pairs)} cointegrated pairs")

    return cointegrated_pairs


def rank_pairs(pairs):
    """Rank pairs by statistical strength"""
    print(f"\n[4/5] Ranking pairs by statistical strength...")

    # Sort by p-value (ascending) and then by absolute z-score (descending)
    ranked = sorted(
        pairs,
        key=lambda x: (x['cointegration_pvalue'], -abs(x['current_zscore'] or 0))
    )

    print(f"  → Top 10 pairs:")
    for i, pair in enumerate(ranked[:10], 1):
        print(f"    {i}. {pair['pair']} "
              f"(p={pair['cointegration_pvalue']:.4f}, "
              f"z={pair['current_zscore']:.2f}, "
              f"{pair['strength']})")

    return ranked


# =============================================================================
# Output
# =============================================================================

def save_results(pairs, output_file):
    """Save results to JSON file"""
    print(f"\n[5/5] Saving results to {output_file}...")

    output_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_pairs': len(pairs),
            'cointegrated_pairs': sum(1 for p in pairs if p['is_cointegrated']),
            'active_signals': sum(1 for p in pairs if p['signal'] != 'NONE')
        },
        'pairs': pairs
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"  → Saved {len(pairs)} pairs to {output_file}")
    print(f"  → Cointegrated pairs: {output_data['metadata']['cointegrated_pairs']}")
    print(f"  → Active signals: {output_data['metadata']['active_signals']}")


def print_summary(pairs):
    """Print summary to console"""
    print("\n" + "="*70)
    print("PAIR TRADING SCREEN SUMMARY")
    print("="*70)

    cointegrated = [p for p in pairs if p['is_cointegrated']]
    with_signals = [p for p in cointegrated if p['signal'] != 'NONE']

    print(f"\nTotal pairs analyzed: {len(pairs)}")
    print(f"Cointegrated pairs: {len(cointegrated)}")
    print(f"Pairs with trade signals: {len(with_signals)}")

    if with_signals:
        print(f"\n{'='*70}")
        print("ACTIVE TRADE SIGNALS")
        print("="*70)

        for pair in with_signals[:10]:
            print(f"\nPair: {pair['pair']}")
            print(f"  Signal: {pair['signal']}")
            print(f"  Z-Score: {pair['current_zscore']:.2f}")
            print(f"  Correlation: {pair['correlation']:.4f}")
            print(f"  P-Value: {pair['cointegration_pvalue']:.4f}")
            print(f"  Half-Life: {pair['half_life_days']:.1f} days" if pair['half_life_days'] else "  Half-Life: N/A")
            print(f"  Strength: {pair['strength']}")

    print(f"\n{'='*70}\n")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Screen for cointegrated stock pairs suitable for pair trading',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Screen Technology sector
  python find_pairs.py --sector Technology

  # Custom stock list
  python find_pairs.py --symbols AAPL,MSFT,GOOGL,META

  # Adjust parameters
  python find_pairs.py --sector Financials --min-correlation 0.75 --lookback-days 365
        """
    )

    parser.add_argument('--sector', type=str,
                        help='Sector to screen (Technology, Financials, Healthcare, etc.)')
    parser.add_argument('--symbols', type=str,
                        help='Comma-separated list of stock symbols (alternative to --sector)')
    parser.add_argument('--min-correlation', type=float, default=0.70,
                        help='Minimum correlation threshold (default: 0.70)')
    parser.add_argument('--min-market-cap', type=float, default=2_000_000_000,
                        help='Minimum market cap filter in dollars (default: $2B)')
    parser.add_argument('--lookback-days', type=int, default=730,
                        help='Historical data lookback period in days (default: 730)')
    parser.add_argument('--output', type=str, default='pair_analysis.json',
                        help='Output JSON file (default: pair_analysis.json)')
    parser.add_argument('--api-key', type=str,
                        help='FMP API key (or set FMP_API_KEY env variable)')

    args = parser.parse_args()

    # Validate inputs
    if not args.sector and not args.symbols:
        parser.error("Either --sector or --symbols must be provided")

    if args.sector and args.symbols:
        parser.error("Provide either --sector or --symbols, not both")

    # Get API key
    api_key = get_api_key(args.api_key)

    print("\n" + "="*70)
    print("PAIR TRADE SCREENER")
    print("="*70)
    print(f"Configuration:")
    print(f"  Min Correlation: {args.min_correlation}")
    print(f"  Lookback Days: {args.lookback_days}")
    print(f"  Min Market Cap: ${args.min_market_cap:,.0f}")

    # Get list of stocks to analyze
    if args.sector:
        stocks = fetch_sector_stocks(args.sector, api_key, args.min_market_cap)
        symbols = [s['symbol'] for s in stocks]
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(',')]

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
        sys.exit(0)

    # Rank pairs
    ranked_pairs = rank_pairs(pairs)

    # Save results
    save_results(ranked_pairs, args.output)

    # Print summary
    print_summary(ranked_pairs)


if __name__ == '__main__':
    main()
