#!/usr/bin/env python3
"""
Pair Trade Spread Analyzer

Analyzes a specific pair's spread behavior and generates trading signals.

Usage:
    python analyze_spread.py --stock-a AAPL --stock-b MSFT

    python analyze_spread.py \\
        --stock-a JPM \\
        --stock-b BAC \\
        --lookback-days 365 \\
        --entry-zscore 2.0 \\
        --exit-zscore 0.5

Requirements:
    pip install pandas numpy scipy statsmodels requests matplotlib

Author: Claude Trading Skills
Version: 1.0
"""

import argparse
import os
import sys
import time
from datetime import datetime

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


def fetch_historical_prices(symbol, api_key, lookback_days=365):
    """Fetch historical adjusted close prices for a symbol"""
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
    params = {'apikey': api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'historical' not in data:
            print(f"ERROR: No data found for {symbol}")
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

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to fetch data for {symbol}: {e}")
        return None


# =============================================================================
# Statistical Analysis
# =============================================================================

def calculate_hedge_ratio(prices_a, prices_b):
    """Calculate hedge ratio using OLS regression"""
    # Align dates
    common_dates = prices_a.index.intersection(prices_b.index)
    aligned_a = prices_a.loc[common_dates]
    aligned_b = prices_b.loc[common_dates]

    # Linear regression
    slope, intercept, r_value, p_value, std_err = stats.linregress(aligned_b, aligned_a)

    return {
        'beta': slope,
        'intercept': intercept,
        'r_value': r_value,
        'r_squared': r_value ** 2,
        'aligned_a': aligned_a,
        'aligned_b': aligned_b
    }


def test_cointegration(spread):
    """Test for cointegration using ADF test"""
    try:
        result = adfuller(spread, maxlag=1, regression='c')
        return {
            'adf_statistic': result[0],
            'p_value': result[1],
            'critical_values': result[4],
            'is_cointegrated': result[1] < 0.05
        }
    except Exception as e:
        print(f"ERROR: Cointegration test failed: {e}")
        return None


def calculate_half_life(spread):
    """Estimate mean reversion half-life"""
    try:
        model = AutoReg(spread.dropna(), lags=1)
        result = model.fit()
        phi = result.params[1]

        if phi >= 1.0 or phi <= 0:
            return None

        half_life = -np.log(2) / np.log(phi)
        return half_life
    except Exception:
        return None


def calculate_zscore_series(spread, window=90):
    """Calculate rolling z-score of spread"""
    rolling_mean = spread.rolling(window).mean()
    rolling_std = spread.rolling(window).std()

    zscore = (spread - rolling_mean) / rolling_std
    return zscore


# =============================================================================
# Analysis & Reporting
# =============================================================================

def generate_ascii_chart(zscore, width=60, height=15):
    """Generate ASCII chart of z-score over time"""
    # Filter out NaN values
    valid_z = zscore.dropna()

    if len(valid_z) == 0:
        return "No data available for chart"

    # Determine scale
    max_abs_z = max(abs(valid_z.min()), abs(valid_z.max()), 3.0)

    # Create chart
    lines = []
    lines.append(f"\n{'Z-Score History (Last {len(valid_z)} days)':^{width}}")
    lines.append("-" * width)

    # Y-axis levels
    levels = np.linspace(max_abs_z, -max_abs_z, height)

    for level in levels:
        if abs(level) < 0.1:
            label = f" 0.0 |"
        else:
            label = f"{level:4.1f} |"

        # Sample z-scores for this row
        row = label

        for i in range(width - len(label)):
            idx = int(i / (width - len(label)) * len(valid_z))
            z_value = valid_z.iloc[idx]

            # Determine character
            if abs(z_value - level) < max_abs_z / height:
                if abs(z_value) > 2.0:
                    char = '*'  # Extreme values
                elif abs(z_value) > 1.5:
                    char = '+'  # High values
                else:
                    char = '.'  # Normal values
            elif abs(level) < 0.1:
                char = '-'  # Zero line
            elif abs(level - 2.0) < 0.1 or abs(level + 2.0) < 0.1:
                char = '='  # Entry thresholds
            else:
                char = ' '

            row += char

        lines.append(row)

    lines.append(" " * (len(label) - 1) + "|" + "-" * (width - len(label)))
    lines.append(" " * len(label) + "Time →")

    return "\n".join(lines)


def print_analysis_report(symbol_a, symbol_b, prices_a, prices_b, beta_result, spread,
                           coint_result, half_life, zscore, current_zscore,
                           entry_zscore, exit_zscore):
    """Print comprehensive analysis report"""

    print("\n" + "="*70)
    print(f"PAIR TRADE ANALYSIS: {symbol_a} / {symbol_b}")
    print("="*70)

    # Basic Statistics
    print("\n[ PAIR STATISTICS ]")
    print(f"  Stock A: {symbol_a}")
    print(f"  Stock B: {symbol_b}")
    print(f"  Data Points: {len(spread)}")
    print(f"  Date Range: {spread.index[0].date()} to {spread.index[-1].date()}")
    print(f"  Correlation: {beta_result['r_value']:.4f}")
    print(f"  R-squared: {beta_result['r_squared']:.4f}")
    print(f"  Hedge Ratio (Beta): {beta_result['beta']:.4f}")

    # Cointegration Results
    print("\n[ COINTEGRATION TEST ]")
    print(f"  ADF Statistic: {coint_result['adf_statistic']:.4f}")
    print(f"  P-value: {coint_result['p_value']:.4f}")
    print(f"  Critical Values:")
    for key, value in coint_result['critical_values'].items():
        print(f"    {key}: {value:.4f}")

    if coint_result['is_cointegrated']:
        print(f"  Result: ✅ COINTEGRATED (p < 0.05)")
        if coint_result['p_value'] < 0.01:
            print(f"  Strength: ★★★ Very Strong")
        else:
            print(f"  Strength: ★★ Moderate")
    else:
        print(f"  Result: ❌ NOT COINTEGRATED (p ≥ 0.05)")

    # Mean Reversion
    print("\n[ MEAN REVERSION ]")
    if half_life:
        print(f"  Half-Life: {half_life:.1f} days")
        if half_life < 30:
            print(f"  Speed: Fast (ideal for short-term trading)")
        elif half_life < 60:
            print(f"  Speed: Moderate (suitable for pair trading)")
        else:
            print(f"  Speed: Slow (requires patience)")
    else:
        print(f"  Half-Life: N/A (spread may not be mean-reverting)")

    # Spread Analysis
    print("\n[ SPREAD ANALYSIS ]")
    print(f"  Current Spread: {spread.iloc[-1]:.4f}")
    print(f"  Mean Spread: {spread.mean():.4f}")
    print(f"  Std Dev Spread: {spread.std():.4f}")
    print(f"  Min Spread: {spread.min():.4f} ({spread.idxmin().date()})")
    print(f"  Max Spread: {spread.max():.4f} ({spread.idxmax().date()})")

    # Z-Score
    print("\n[ Z-SCORE ]")
    print(f"  Current Z-Score: {current_zscore:.2f}")
    print(f"  Entry Threshold: ±{entry_zscore:.1f}")
    print(f"  Exit Threshold: ±{exit_zscore:.1f}")

    valid_z = zscore.dropna()
    print(f"  Historical Range: [{valid_z.min():.2f}, {valid_z.max():.2f}]")
    print(f"  Times above +{entry_zscore}: {sum(valid_z > entry_zscore)} days ({sum(valid_z > entry_zscore)/len(valid_z)*100:.1f}%)")
    print(f"  Times below -{entry_zscore}: {sum(valid_z < -entry_zscore)} days ({sum(valid_z < -entry_zscore)/len(valid_z)*100:.1f}%)")

    # Trade Signal
    print("\n[ TRADE SIGNAL ]")
    if not coint_result['is_cointegrated']:
        print(f"  Signal: ⚠️ NO TRADE (pair not cointegrated)")
    elif abs(current_zscore) < entry_zscore:
        print(f"  Signal: ⏸ WAIT (|z| < {entry_zscore})")
        print(f"  Status: Spread within normal range, no trade signal")
    elif current_zscore > entry_zscore:
        print(f"  Signal: 🔻 SHORT SPREAD")
        print(f"  Action: Short {symbol_a}, Long {symbol_b}")
        print(f"  Rationale: Z-score = {current_zscore:.2f} (>{entry_zscore}) → {symbol_a} expensive relative to {symbol_b}")
    else:  # current_zscore < -entry_zscore
        print(f"  Signal: 🔺 LONG SPREAD")
        print(f"  Action: Long {symbol_a}, Short {symbol_b}")
        print(f"  Rationale: Z-score = {current_zscore:.2f} (<-{entry_zscore}) → {symbol_a} cheap relative to {symbol_b}")

    # Position Sizing (if signal exists)
    if coint_result['is_cointegrated'] and abs(current_zscore) >= entry_zscore:
        print(f"\n[ POSITION SIZING ]")
        portfolio_allocation = 10000  # Example $10k allocation
        print(f"  Example Allocation: ${portfolio_allocation:,}")

        if current_zscore > entry_zscore:
            # Short A, Long B
            short_a = portfolio_allocation / 2
            long_b = short_a * beta_result['beta']
            print(f"  SHORT {symbol_a}: ${short_a:,.0f} ({short_a / prices_a.iloc[-1]:.0f} shares @ ${prices_a.iloc[-1]:.2f})")
            print(f"  LONG {symbol_b}: ${long_b:,.0f} ({long_b / prices_b.iloc[-1]:.0f} shares @ ${prices_b.iloc[-1]:.2f})")
        else:
            # Long A, Short B
            long_a = portfolio_allocation / 2
            short_b = long_a * beta_result['beta']
            print(f"  LONG {symbol_a}: ${long_a:,.0f} ({long_a / prices_a.iloc[-1]:.0f} shares @ ${prices_a.iloc[-1]:.2f})")
            print(f"  SHORT {symbol_b}: ${short_b:,.0f} ({short_b / prices_b.iloc[-1]:.0f} shares @ ${prices_b.iloc[-1]:.2f})")

        print(f"\n  Exit Conditions:")
        print(f"    - Primary: Z-score crosses {exit_zscore} (mean reversion)")
        print(f"    - Stop Loss: Z-score > ±3.0 (extreme divergence)")
        print(f"    - Time-based: No reversion after 90 days")

    # ASCII Chart
    if len(zscore.dropna()) > 0:
        print("\n[ Z-SCORE CHART ]")
        print(generate_ascii_chart(zscore))

    print("\n" + "="*70)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze spread behavior for a specific stock pair',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--stock-a', type=str, required=True,
                        help='First stock ticker symbol')
    parser.add_argument('--stock-b', type=str, required=True,
                        help='Second stock ticker symbol')
    parser.add_argument('--lookback-days', type=int, default=365,
                        help='Historical data lookback period (default: 365)')
    parser.add_argument('--entry-zscore', type=float, default=2.0,
                        help='Z-score threshold for entry (default: 2.0)')
    parser.add_argument('--exit-zscore', type=float, default=0.0,
                        help='Z-score threshold for exit (default: 0.0)')
    parser.add_argument('--api-key', type=str,
                        help='FMP API key (or set FMP_API_KEY env variable)')

    args = parser.parse_args()

    # Get API key
    api_key = get_api_key(args.api_key)

    # Fetch price data
    print(f"\nFetching price data for {args.stock_a} and {args.stock_b}...")

    prices_a = fetch_historical_prices(args.stock_a, api_key, args.lookback_days)
    time.sleep(0.3)  # Rate limiting
    prices_b = fetch_historical_prices(args.stock_b, api_key, args.lookback_days)

    if prices_a is None or prices_b is None:
        sys.exit(1)

    # Calculate hedge ratio
    beta_result = calculate_hedge_ratio(prices_a, prices_b)

    # Calculate spread
    spread = beta_result['aligned_a'] - (beta_result['beta'] * beta_result['aligned_b'])

    # Test cointegration
    coint_result = test_cointegration(spread)
    if not coint_result:
        sys.exit(1)

    # Calculate half-life
    half_life = calculate_half_life(spread)

    # Calculate z-score
    zscore = calculate_zscore_series(spread, window=90)
    current_zscore = zscore.iloc[-1] if not pd.isna(zscore.iloc[-1]) else None

    # Print report
    print_analysis_report(
        args.stock_a, args.stock_b,
        prices_a, prices_b,
        beta_result, spread,
        coint_result, half_life,
        zscore, current_zscore,
        args.entry_zscore, args.exit_zscore
    )


if __name__ == '__main__':
    main()
