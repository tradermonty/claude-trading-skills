#!/usr/bin/env python3
"""
Dividend Growth Pullback Screener using FINVIZ + Financial Modeling Prep API

Two-stage screening approach:
1. FINVIZ Elite API: Pre-screen stocks with dividend growth + RSI criteria (fast, cost-effective)
2. FMP API: Detailed analysis of pre-screened candidates (comprehensive)

Screens for high-quality dividend growth stocks (12%+ dividend CAGR, 1.5%+ yield)
that are experiencing temporary pullbacks identified by RSI oversold conditions (RSI ≤40).

Usage:
    # Two-stage screening with FINVIZ (RECOMMENDED)
    python3 screen_dividend_growth_rsi.py --use-finviz

    # FMP-only screening (original method)
    python3 screen_dividend_growth_rsi.py

Environment variables:
    export FMP_API_KEY=your_fmp_key_here
    export FINVIZ_API_KEY=your_finviz_key_here  # Required for --use-finviz
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Set
import requests


class FINVIZClient:
    """Client for FINVIZ Elite API"""

    BASE_URL = "https://elite.finviz.com/export.ashx"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def screen_stocks(self) -> Set[str]:
        """
        Screen stocks using FINVIZ Elite API with predefined criteria

        Criteria for dividend growth pullback opportunities (Balanced):
        - Market cap: Mid-cap or higher
        - Dividend yield: 0.5-3% (captures dividend growers without REITs/utilities)
        - Dividend growth (3Y): 10%+ (we'll verify 12%+ with FMP)
        - EPS growth (3Y): 5%+ (positive earnings momentum)
        - Sales growth (3Y): 5%+ (positive revenue momentum)
        - RSI (14): Under 40 (oversold/pullback)
        - Geography: USA

        Returns:
            Set of stock symbols
        """
        # Build filter string in FINVIZ format: key_value,key_value,...
        # Balanced criteria: Div Growth 10%+, EPS/Sales Growth 5%+ (30-40 candidates expected)
        filters = 'cap_midover,fa_div_0.5to3,fa_divgrowth_3yo10,fa_eps3years_o5,fa_sales3years_o5,geo_usa,ta_rsi_os40'

        params = {
            'v': '151',  # View type
            'f': filters,  # Filter conditions
            'ft': '4',   # File type: CSV export
            'auth': self.api_key
        }

        try:
            print(f"Fetching pre-screened stocks from FINVIZ Elite API...", file=sys.stderr)
            print(f"FINVIZ Filters: Div Yield 0.5-3%, Div Growth 10%+, EPS Growth 5%+, Sales Growth 5%+, RSI <40", file=sys.stderr)
            response = self.session.get(self.BASE_URL, params=params, timeout=30)

            if response.status_code == 200:
                # Parse CSV response
                csv_content = response.content.decode('utf-8')
                reader = csv.DictReader(io.StringIO(csv_content))

                symbols = set()
                for row in reader:
                    # FINVIZ CSV has 'Ticker' column
                    ticker = row.get('Ticker', '').strip()
                    if ticker:
                        symbols.add(ticker)

                print(f"✅ FINVIZ returned {len(symbols)} pre-screened stocks", file=sys.stderr)
                return symbols

            elif response.status_code == 401 or response.status_code == 403:
                print(f"ERROR: FINVIZ API authentication failed. Check your API key.", file=sys.stderr)
                print(f"Status code: {response.status_code}", file=sys.stderr)
                return set()
            else:
                print(f"ERROR: FINVIZ API request failed: {response.status_code}", file=sys.stderr)
                return set()

        except requests.exceptions.RequestException as e:
            print(f"ERROR: FINVIZ request exception: {e}", file=sys.stderr)
            return set()


class FMPClient:
    """Financial Modeling Prep API client with rate limiting."""

    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.rate_limit_reached = False
        self.retry_count = 0

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Execute GET request with rate limiting and error handling."""
        if self.rate_limit_reached:
            return None

        if params is None:
            params = {}
        params['apikey'] = self.api_key

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)

            if response.status_code == 200:
                self.retry_count = 0
                time.sleep(0.3)  # Rate limiting: 0.3s between requests
                return response.json()
            elif response.status_code == 429:
                self.retry_count += 1
                if self.retry_count <= 1:
                    print(f"WARNING: Rate limit exceeded. Waiting 60 seconds...", file=sys.stderr)
                    time.sleep(60)
                    return self._get(endpoint, params)
                else:
                    print(f"ERROR: Daily API rate limit reached. Stopping analysis.", file=sys.stderr)
                    self.rate_limit_reached = True
                    return None
            else:
                print(f"WARNING: API request failed ({response.status_code}): {url}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"ERROR: Request failed for {url}: {e}", file=sys.stderr)
            return None

    def screen_stocks(self, min_market_cap: int = 2000000000, exchange: str = None) -> List[Dict]:
        """Screen stocks by market cap and exchange."""
        params = {'marketCapMoreThan': min_market_cap}
        if exchange:
            params['exchange'] = exchange

        result = self._get('stock-screener', params)
        return result if result else []

    def get_historical_prices(self, symbol: str, days: int = 30) -> Optional[List[Dict]]:
        """Get historical daily prices."""
        result = self._get(f'historical-price-full/{symbol}', {'timeseries': days})
        if result and 'historical' in result:
            return result['historical']
        return None

    def get_dividend_history(self, symbol: str) -> Optional[Dict]:
        """Get historical dividend payments."""
        result = self._get(f'historical-price-full/stock_dividend/{symbol}')
        return result

    def get_income_statement(self, symbol: str, limit: int = 5) -> Optional[List[Dict]]:
        """Get income statement data."""
        result = self._get(f'income-statement/{symbol}', {'limit': limit})
        return result if result else []

    def get_balance_sheet(self, symbol: str, limit: int = 5) -> Optional[List[Dict]]:
        """Get balance sheet data."""
        result = self._get(f'balance-sheet-statement/{symbol}', {'limit': limit})
        return result if result else []

    def get_cash_flow(self, symbol: str, limit: int = 5) -> Optional[List[Dict]]:
        """Get cash flow statement data."""
        result = self._get(f'cash-flow-statement/{symbol}', {'limit': limit})
        return result if result else []

    def get_key_metrics(self, symbol: str, limit: int = 5) -> Optional[List[Dict]]:
        """Get key financial metrics."""
        result = self._get(f'key-metrics/{symbol}', {'limit': limit})
        return result if result else []

    def get_company_profile(self, symbol: str) -> Optional[Dict]:
        """Get company profile including sector information."""
        result = self._get(f'profile/{symbol}')
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        return None

    def get_quote_with_profile(self, symbol: str) -> Optional[Dict]:
        """
        Get quote data merged with profile data to include sector information.

        Returns:
            Dict with quote data + sector/companyName from profile, or None on error
        """
        # First get quote data
        quote = self._get(f'quote/{symbol}')
        if not quote or not isinstance(quote, list) or len(quote) == 0:
            return None

        quote_data = quote[0].copy()

        # Then get profile for sector information
        profile = self.get_company_profile(symbol)
        if profile:
            # Merge profile data into quote (profile has more accurate sector/companyName)
            quote_data['sector'] = profile.get('sector', 'Unknown')
            quote_data['companyName'] = profile.get('companyName', quote_data.get('name', ''))
            quote_data['industry'] = profile.get('industry', '')
        else:
            # Fallback if profile fetch fails
            quote_data['sector'] = quote_data.get('sector', 'Unknown')
            quote_data['companyName'] = quote_data.get('name', quote_data.get('companyName', ''))

        return quote_data


class RSICalculator:
    """Calculate Relative Strength Index (RSI) from price data."""

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """
        Calculate RSI using standard formula.

        Args:
            prices: List of closing prices (oldest first)
            period: RSI period (default 14)

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(prices) < period + 1:
            return None

        # Calculate price changes
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        # Separate gains and losses
        gains = [change if change > 0 else 0 for change in changes]
        losses = [-change if change < 0 else 0 for change in changes]

        # Calculate initial average gain and loss
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Calculate smoothed averages for remaining periods
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        # Calculate RSI
        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi, 2)


class StockAnalyzer:
    """Analyze stock fundamentals and dividend growth."""

    @staticmethod
    def calculate_cagr(start_value: float, end_value: float, years: int) -> Optional[float]:
        """Calculate Compound Annual Growth Rate."""
        if start_value <= 0 or end_value <= 0 or years <= 0:
            return None
        return round(((end_value / start_value) ** (1 / years) - 1) * 100, 2)

    @staticmethod
    def analyze_dividend_growth(dividend_history: List[Dict]) -> Tuple[Optional[float], bool, Optional[float], int]:
        """
        Analyze dividend growth rate (3-year CAGR and consistency) and return latest annual dividend.

        Returns:
            Tuple of (CAGR%, consistent_growth, latest_annual_dividend, years_of_growth)
        """
        if not dividend_history or 'historical' not in dividend_history:
            return None, False, None, 0

        dividends = dividend_history['historical']
        if len(dividends) < 4:
            return None, False, None, 0

        # Sort by date and aggregate by year
        dividends = sorted(dividends, key=lambda x: x['date'])
        annual_dividends = {}
        for div in dividends:
            year = div['date'][:4]
            annual_dividends[year] = annual_dividends.get(year, 0) + div.get('dividend', 0)

        if len(annual_dividends) < 4:
            return None, False, None, 0

        # Get all available years sorted (oldest first)
        all_years = sorted(annual_dividends.keys())
        all_div_values = [annual_dividends[y] for y in all_years]

        # Get last 4 years for CAGR calculation
        years = all_years[-4:]
        div_values = [annual_dividends[y] for y in years]

        # Calculate 3-year CAGR
        cagr = StockAnalyzer.calculate_cagr(div_values[0], div_values[-1], 3)

        # Check consistency (no significant cuts)
        consistent = all(div_values[i] >= div_values[i-1] * 0.95 for i in range(1, len(div_values)))

        # Count consecutive years of growth (from most recent going back)
        years_of_growth = 0
        for i in range(len(all_div_values) - 1, 0, -1):
            if all_div_values[i] >= all_div_values[i-1] * 0.95:  # Allow 5% tolerance
                years_of_growth += 1
            else:
                break

        # Latest annual dividend
        latest_annual_dividend = div_values[-1]

        return cagr, consistent, latest_annual_dividend, years_of_growth

    @staticmethod
    def is_reit(stock_data: Dict) -> bool:
        """
        Determine if a stock is a REIT based on sector/industry.

        Args:
            stock_data: Dict containing sector and/or industry fields

        Returns:
            True if the stock is likely a REIT
        """
        sector = stock_data.get('sector', '').lower()
        industry = stock_data.get('industry', '').lower()

        # Check for Real Estate sector or REIT in industry
        if 'real estate' in sector:
            return True
        if 'reit' in industry:
            return True

        return False

    @staticmethod
    def calculate_ffo(cash_flows: List[Dict]) -> Optional[float]:
        """
        Calculate Funds From Operations (FFO) for REITs.

        FFO = Net Income + Depreciation & Amortization
        (Simplified formula - does not include gains/losses on property sales)

        Args:
            cash_flows: List of cash flow statements (newest first)

        Returns:
            FFO value or None if data is missing
        """
        if not cash_flows:
            return None

        latest_cf = cash_flows[0]
        net_income = latest_cf.get('netIncome', 0)
        depreciation = latest_cf.get('depreciationAndAmortization', 0)

        if net_income == 0 and depreciation == 0:
            return None

        return net_income + depreciation

    @staticmethod
    def calculate_ffo_payout_ratio(cash_flows: List[Dict]) -> Optional[float]:
        """
        Calculate FFO payout ratio for REITs.

        FFO Payout Ratio = Dividends Paid / FFO

        Args:
            cash_flows: List of cash flow statements (newest first)

        Returns:
            FFO payout ratio as percentage, or None if calculation fails
        """
        if not cash_flows:
            return None

        ffo = StockAnalyzer.calculate_ffo(cash_flows)
        if not ffo or ffo <= 0:
            return None

        latest_cf = cash_flows[0]
        dividends_paid = abs(latest_cf.get('dividendsPaid', 0))

        if dividends_paid <= 0:
            return None

        return round((dividends_paid / ffo) * 100, 1)

    @staticmethod
    def calculate_payout_ratios(income_stmts: List[Dict], cash_flows: List[Dict], is_reit: bool = False) -> Dict:
        """
        Calculate payout ratios using dividendsPaid from cash flow statement.

        For REITs, uses FFO-based payout ratio instead of net income-based.

        Args:
            income_stmts: List of income statements (newest first)
            cash_flows: List of cash flow statements (newest first)
            is_reit: Whether the stock is a REIT (uses FFO for payout calculation)

        Returns:
            Dict with payout_ratio and fcf_payout_ratio (as percentages)
        """
        result = {
            'payout_ratio': None,
            'fcf_payout_ratio': None
        }

        if not cash_flows:
            return result

        latest_cf = cash_flows[0]
        dividends_paid = abs(latest_cf.get('dividendsPaid', 0))
        fcf = latest_cf.get('freeCashFlow', 0)

        # For REITs, use FFO-based payout ratio
        if is_reit:
            result['payout_ratio'] = StockAnalyzer.calculate_ffo_payout_ratio(cash_flows)
        else:
            # For non-REITs, use traditional net income-based payout ratio
            if income_stmts:
                latest_income = income_stmts[0]
                net_income = latest_income.get('netIncome', 0)

                if net_income > 0 and dividends_paid > 0:
                    result['payout_ratio'] = round((dividends_paid / net_income) * 100, 1)

        # Calculate FCF payout ratio (same for both REIT and non-REIT)
        if fcf > 0 and dividends_paid > 0:
            result['fcf_payout_ratio'] = round((dividends_paid / fcf) * 100, 1)

        return result

    @staticmethod
    def get_payout_ratio_from_metrics(key_metrics: List[Dict]) -> Optional[float]:
        """
        Get payout ratio directly from key_metrics as fallback.

        Args:
            key_metrics: List of key metrics (newest first)

        Returns:
            Payout ratio as percentage, or None if not available
        """
        if not key_metrics:
            return None

        latest = key_metrics[0]
        payout_ratio = latest.get('payoutRatio')

        if payout_ratio is not None:
            # payoutRatio from FMP is a decimal (e.g., 0.316 = 31.6%)
            return round(payout_ratio * 100, 1)

        return None

    @staticmethod
    def analyze_financial_health(balance_sheet: List[Dict]) -> Dict:
        """Analyze financial health metrics."""
        if not balance_sheet:
            return {}

        latest = balance_sheet[0]

        total_debt = latest.get('totalDebt', 0)
        total_equity = latest.get('totalStockholdersEquity', 0)
        current_assets = latest.get('totalCurrentAssets', 0)
        current_liabilities = latest.get('totalCurrentLiabilities', 0)

        debt_to_equity = round(total_debt / total_equity, 2) if total_equity > 0 else None
        current_ratio = round(current_assets / current_liabilities, 2) if current_liabilities > 0 else None

        financially_healthy = (
            (debt_to_equity is None or debt_to_equity < 2.0) and
            (current_ratio is None or current_ratio > 1.0)
        )

        return {
            'debt_to_equity': debt_to_equity,
            'current_ratio': current_ratio,
            'financially_healthy': financially_healthy
        }

    @staticmethod
    def analyze_growth_metrics(income_stmts: List[Dict]) -> Dict:
        """Analyze revenue and EPS growth trends."""
        if not income_stmts or len(income_stmts) < 4:
            return {'revenue_cagr_3y': None, 'eps_cagr_3y': None}

        # Sort by date (newest first from API)
        revenue_3y_ago = income_stmts[3].get('revenue', 0)
        revenue_latest = income_stmts[0].get('revenue', 0)

        eps_3y_ago = income_stmts[3].get('eps', 0)
        eps_latest = income_stmts[0].get('eps', 0)

        revenue_cagr = StockAnalyzer.calculate_cagr(revenue_3y_ago, revenue_latest, 3)
        eps_cagr = StockAnalyzer.calculate_cagr(eps_3y_ago, eps_latest, 3)

        return {
            'revenue_cagr_3y': revenue_cagr,
            'eps_cagr_3y': eps_cagr
        }

    @staticmethod
    def calculate_composite_score(stock_data: Dict) -> float:
        """
        Calculate composite score (0-100) based on:
        - Dividend Growth (40%): Reward higher CAGR
        - Financial Quality (30%): ROE, profit margins, debt levels
        - Technical Setup (20%): Lower RSI = better entry opportunity
        - Valuation (10%): P/E and P/B for context
        """
        score = 0.0

        # Dividend Growth Score (40 points max)
        div_cagr = stock_data.get('dividend_cagr_3y', 0)
        if div_cagr >= 20:
            score += 40
        elif div_cagr >= 15:
            score += 35
        elif div_cagr >= 12:
            score += 30
        else:
            score += 20

        # Add bonus for consistency
        if stock_data.get('dividend_consistent', False):
            score += 5

        # Financial Quality Score (30 points max)
        roe = stock_data.get('roe', 0)
        profit_margin = stock_data.get('profit_margin', 0)
        debt_to_equity = stock_data.get('debt_to_equity', 999)

        if roe >= 20:
            score += 12
        elif roe >= 15:
            score += 10
        elif roe >= 10:
            score += 7
        else:
            score += 3

        if profit_margin >= 20:
            score += 10
        elif profit_margin >= 15:
            score += 8
        elif profit_margin >= 10:
            score += 6
        else:
            score += 3

        if debt_to_equity < 0.5:
            score += 8
        elif debt_to_equity < 1.0:
            score += 6
        elif debt_to_equity < 2.0:
            score += 3

        # Technical Setup Score (20 points max) - Lower RSI = Higher score
        rsi = stock_data.get('rsi', 50)
        if rsi <= 25:
            score += 20  # Extreme oversold
        elif rsi <= 30:
            score += 18
        elif rsi <= 35:
            score += 15
        elif rsi <= 40:
            score += 12
        else:
            score += 5

        # Valuation Score (10 points max) - Context only, not exclusionary
        pe_ratio = stock_data.get('pe_ratio', 999)
        pb_ratio = stock_data.get('pb_ratio', 999)

        if pe_ratio < 15:
            score += 5
        elif pe_ratio < 25:
            score += 3

        if pb_ratio < 3:
            score += 5
        elif pb_ratio < 5:
            score += 3

        return round(min(score, 100), 1)


def screen_dividend_growth_pullbacks(
    api_key: str,
    min_yield: float = 1.5,
    min_div_growth: float = 12.0,
    rsi_max: float = 40.0,
    max_candidates: int = None,
    finviz_symbols: Optional[Set[str]] = None
) -> List[Dict]:
    """
    Main screening function.

    Args:
        api_key: FMP API key
        min_yield: Minimum dividend yield % (default 1.5%)
        min_div_growth: Minimum 3-year dividend CAGR % (default 12%)
        rsi_max: Maximum RSI value (default 40)
        max_candidates: Maximum number of candidates to analyze (None = all)
        finviz_symbols: Optional set of symbols from FINVIZ pre-screening

    Returns:
        List of qualified stocks with full analysis
    """
    client = FMPClient(api_key)
    analyzer = StockAnalyzer()
    rsi_calc = RSICalculator()

    print(f"\n{'='*80}", file=sys.stderr)
    print(f"Dividend Growth Pullback Screener", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    print(f"\nCriteria:", file=sys.stderr)
    print(f"  - Dividend Yield ≥ {min_yield}%", file=sys.stderr)
    print(f"  - Dividend Growth (3Y CAGR) ≥ {min_div_growth}%", file=sys.stderr)
    print(f"  - RSI ≤ {rsi_max}", file=sys.stderr)
    print(f"  - Market Cap ≥ $2B", file=sys.stderr)
    print(f"  - Exchange: NYSE, NASDAQ", file=sys.stderr)
    print(f"\n{'='*80}\n", file=sys.stderr)

    # Step 1: Get candidate list
    if finviz_symbols:
        print(f"Step 1: Using FINVIZ pre-screened symbols ({len(finviz_symbols)} stocks)...", file=sys.stderr)
        # Convert FINVIZ symbols to candidate format for FMP analysis
        # We'll fetch quote data with profile to get sector information
        candidates = []
        print("Fetching quote and profile data from FMP for FINVIZ symbols...", file=sys.stderr)
        for symbol in finviz_symbols:
            stock_data = client.get_quote_with_profile(symbol)
            if stock_data:
                candidates.append(stock_data)

            if client.rate_limit_reached:
                print(f"⚠️  FMP rate limit reached while fetching quotes. Using {len(candidates)} symbols.", file=sys.stderr)
                break

        print(f"Retrieved quote and profile data for {len(candidates)} symbols from FMP", file=sys.stderr)
    else:
        print("Step 1: Initial screening using FMP Stock Screener...", file=sys.stderr)
        candidates = client.screen_stocks(min_market_cap=2000000000)
        print(f"Found {len(candidates)} initial candidates", file=sys.stderr)

    if not candidates:
        print("ERROR: No candidates found or API error", file=sys.stderr)
        return []

    # Limit candidates if specified
    if max_candidates and not finviz_symbols:
        candidates = candidates[:max_candidates]
        print(f"Limiting analysis to first {max_candidates} candidates", file=sys.stderr)

    print(f"\nStep 2: Detailed analysis of candidates...", file=sys.stderr)
    print(f"Note: Analysis will continue until API rate limit is reached\n", file=sys.stderr)

    results = []

    for i, stock in enumerate(candidates, 1):
        symbol = stock.get('symbol', '')
        company_name = stock.get('companyName', '')

        print(f"[{i}/{len(candidates)}] Analyzing {symbol} - {company_name}...", file=sys.stderr)

        # Check rate limit
        if client.rate_limit_reached:
            print(f"\n⚠️  API rate limit reached after analyzing {i-1} stocks.", file=sys.stderr)
            print(f"Returning results collected so far: {len(results)} qualified stocks", file=sys.stderr)
            break

        # Get current price
        current_price = stock.get('price', 0)
        if current_price <= 0:
            print(f"  ⚠️  No valid price data", file=sys.stderr)
            continue

        # Fetch dividend history
        dividend_history = client.get_dividend_history(symbol)
        if client.rate_limit_reached:
            break

        if not dividend_history:
            print(f"  ⚠️  No dividend history", file=sys.stderr)
            continue

        # Analyze dividend growth
        div_cagr, div_consistent, annual_dividend, div_years_of_growth = analyzer.analyze_dividend_growth(dividend_history)
        if not div_cagr or div_cagr < min_div_growth:
            print(f"  ⚠️  Dividend CAGR {div_cagr}% < {min_div_growth}%", file=sys.stderr)
            continue

        if not annual_dividend:
            print(f"  ⚠️  Cannot determine annual dividend", file=sys.stderr)
            continue

        # Calculate actual dividend yield
        actual_dividend_yield = (annual_dividend / current_price) * 100

        if actual_dividend_yield < min_yield:
            print(f"  ⚠️  Dividend yield {actual_dividend_yield:.2f}% < {min_yield}%", file=sys.stderr)
            continue

        print(f"  ✓ Dividend: {actual_dividend_yield:.2f}% yield, {div_cagr}% CAGR", file=sys.stderr)

        # Fetch historical prices for RSI
        historical_prices = client.get_historical_prices(symbol, days=30)
        if client.rate_limit_reached:
            break

        if not historical_prices or len(historical_prices) < 20:
            print(f"  ⚠️  Insufficient price data for RSI calculation", file=sys.stderr)
            continue

        # Calculate RSI
        prices = [p['close'] for p in reversed(historical_prices)]  # Oldest first
        rsi = rsi_calc.calculate_rsi(prices, period=14)

        if rsi is None:
            print(f"  ⚠️  RSI calculation failed", file=sys.stderr)
            continue

        if rsi > rsi_max:
            print(f"  ⚠️  RSI {rsi} > {rsi_max}", file=sys.stderr)
            continue

        print(f"  ✓ RSI: {rsi} (oversold)", file=sys.stderr)

        # Fetch additional fundamental data
        income_stmts = client.get_income_statement(symbol, limit=5)
        if client.rate_limit_reached:
            break

        balance_sheet = client.get_balance_sheet(symbol, limit=5)
        if client.rate_limit_reached:
            break

        cash_flow = client.get_cash_flow(symbol, limit=5)
        if client.rate_limit_reached:
            break

        key_metrics = client.get_key_metrics(symbol, limit=1)
        if client.rate_limit_reached:
            break

        # Analyze growth metrics
        growth_metrics = analyzer.analyze_growth_metrics(income_stmts if income_stmts else [])

        # Check for positive revenue and EPS growth
        revenue_cagr = growth_metrics.get('revenue_cagr_3y')
        eps_cagr = growth_metrics.get('eps_cagr_3y')

        if revenue_cagr is not None and revenue_cagr < 0:
            print(f"  ⚠️  Negative revenue growth", file=sys.stderr)
            continue

        if eps_cagr is not None and eps_cagr < 0:
            print(f"  ⚠️  Negative EPS growth", file=sys.stderr)
            continue

        # Analyze financial health
        health_metrics = analyzer.analyze_financial_health(balance_sheet if balance_sheet else [])

        if not health_metrics.get('financially_healthy', False):
            print(f"  ⚠️  Financial health concerns", file=sys.stderr)
            continue

        # Extract additional metrics
        latest_income = income_stmts[0] if income_stmts else {}
        latest_metrics = key_metrics[0] if key_metrics else {}

        # Check if this is a REIT (uses different payout ratio calculation)
        is_reit = analyzer.is_reit(stock)

        # Calculate payout ratios using the new method
        payout_ratios = analyzer.calculate_payout_ratios(
            income_stmts if income_stmts else [],
            cash_flow if cash_flow else [],
            is_reit=is_reit
        )
        payout_ratio = payout_ratios['payout_ratio']
        fcf_payout_ratio = payout_ratios['fcf_payout_ratio']

        # Fallback to key_metrics if calculation failed (only for non-REITs)
        if payout_ratio is None and not is_reit:
            payout_ratio = analyzer.get_payout_ratio_from_metrics(key_metrics if key_metrics else [])

        # Determine dividend sustainability
        # Sustainable if payout ratio < 80% and FCF covers dividends
        dividend_sustainable = False
        if payout_ratio and fcf_payout_ratio:
            dividend_sustainable = (payout_ratio < 80 and fcf_payout_ratio < 100)
        elif payout_ratio:
            dividend_sustainable = payout_ratio < 80

        # Build result object
        result = {
            'symbol': symbol,
            'company_name': company_name,
            'sector': stock.get('sector', 'Unknown'),
            'market_cap': stock.get('marketCap', 0),
            'price': current_price,
            'dividend_yield': round(actual_dividend_yield, 2),
            'annual_dividend': round(annual_dividend, 2),
            'dividend_cagr_3y': div_cagr,
            'dividend_consistent': div_consistent,
            'rsi': rsi,
            'pe_ratio': latest_metrics.get('peRatio', 0),
            'pb_ratio': latest_metrics.get('pbRatio', 0),
            'revenue_cagr_3y': revenue_cagr,
            'eps_cagr_3y': eps_cagr,
            'payout_ratio': payout_ratio,
            'fcf_payout_ratio': fcf_payout_ratio,
            'dividend_sustainable': dividend_sustainable,
            'dividend_years_of_growth': div_years_of_growth,
            'debt_to_equity': health_metrics.get('debt_to_equity'),
            'current_ratio': health_metrics.get('current_ratio'),
            'financially_healthy': health_metrics.get('financially_healthy', False),
            'roe': latest_metrics.get('roe', 0),
            'profit_margin': latest_metrics.get('netProfitMargin', 0)
        }

        # Calculate composite score
        result['composite_score'] = analyzer.calculate_composite_score(result)

        results.append(result)
        print(f"  ✅ QUALIFIED - Score: {result['composite_score']}", file=sys.stderr)

    # Sort by composite score
    results.sort(key=lambda x: x['composite_score'], reverse=True)

    print(f"\n{'='*80}", file=sys.stderr)
    print(f"Screening Complete!", file=sys.stderr)
    print(f"Qualified Stocks: {len(results)}", file=sys.stderr)
    print(f"{'='*80}\n", file=sys.stderr)

    return results


def generate_markdown_report(results: List[Dict], criteria: Dict, output_path: str):
    """Generate human-readable markdown report."""

    report = f"""# Dividend Growth Pullback Screening Report

**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
**Data Source:** Financial Modeling Prep API

## Executive Summary

**Total Qualified Stocks:** {len(results)}

### Screening Criteria

- **Dividend Yield:** ≥ {criteria['dividend_yield_min']}%
- **Dividend Growth (3Y CAGR):** ≥ {criteria['dividend_cagr_min']}%
- **RSI:** ≤ {criteria['rsi_max']} (oversold/pullback)
- **Market Cap:** ≥ $2 billion
- **Financial Health:** Positive revenue/EPS growth, D/E < 2.0, Current Ratio > 1.0

---

"""

    if not results:
        report += """## No Stocks Qualified

**Possible Reasons:**
- Strong bull market with few oversold stocks
- Dividend growth criteria (12%+) is very selective
- RSI threshold may be too strict for current market conditions

**Recommendations:**
- Relax RSI threshold to ≤45 for early pullback phase
- Lower dividend growth to ≥10% for more candidates
- Check back during market corrections or sector rotations

"""
    else:
        for i, stock in enumerate(results, 1):
            rsi_interpretation = (
                "Extreme Oversold" if stock['rsi'] < 30
                else "Strong Oversold" if stock['rsi'] < 35
                else "Early Pullback"
            )

            report += f"""## {i}. {stock['symbol']} - {stock['company_name']}

**Sector:** {stock['sector']}
**Market Cap:** ${stock['market_cap'] / 1e9:.1f}B
**Current Price:** ${stock['price']:.2f}
**Composite Score:** {stock['composite_score']}/100

### Dividend Growth Profile

| Metric | Value | Assessment |
|--------|-------|------------|
| Dividend Yield | **{stock['dividend_yield']:.2f}%** | {'✓ Above 2%' if stock['dividend_yield'] >= 2 else '⚠ Below 2%'} |
| Annual Dividend | ${stock['annual_dividend']:.2f} | |
| 3Y Dividend CAGR | **{stock['dividend_cagr_3y']:.2f}%** | {'🔥 Exceptional' if stock['dividend_cagr_3y'] >= 20 else '✓ Excellent' if stock['dividend_cagr_3y'] >= 15 else '✓ Strong'} |
| Dividend Consistency | {'Yes' if stock['dividend_consistent'] else 'No'} | {'✓' if stock['dividend_consistent'] else '⚠'} |
| Payout Ratio | {f"{stock['payout_ratio']:.1f}%" if stock['payout_ratio'] else 'N/A'} | {'✓ Sustainable' if stock['payout_ratio'] and stock['payout_ratio'] < 70 else '⚠ High' if stock['payout_ratio'] and stock['payout_ratio'] < 100 else '❌ Risk' if stock['payout_ratio'] else 'N/A'} |

### Technical Setup

| Metric | Value | Interpretation |
|--------|-------|----------------|
| RSI (14-period) | **{stock['rsi']:.1f}** | {rsi_interpretation} |
| Entry Timing | {'Immediate - Scale in 50%' if stock['rsi'] < 30 else 'Good - Full position OK' if stock['rsi'] < 35 else 'Conservative - High conviction'} | |
| Stop Loss Suggestion | {f"{((stock['rsi'] - 30) / 2 + 3):.0f}% below entry" if stock['rsi'] >= 30 else "8% below entry"} | |

**RSI Context:** {
    'Extreme oversold reading suggests panic selling or negative news. Wait for RSI to turn up (>30) before entry to confirm stabilization.' if stock['rsi'] < 30
    else 'Strong oversold in uptrend. Normal correction creating entry opportunity. Can initiate position with standard risk management.' if stock['rsi'] < 35
    else 'Early pullback in uptrend. Conservative entry point with lower risk of further decline. Suitable for high-conviction additions.'
}

### Business Fundamentals

| Metric | Value | Status |
|--------|-------|--------|
| Revenue CAGR (3Y) | {f"{stock['revenue_cagr_3y']:.2f}%" if stock['revenue_cagr_3y'] else 'N/A'} | {'✓' if stock['revenue_cagr_3y'] and stock['revenue_cagr_3y'] > 0 else '⚠'} |
| EPS CAGR (3Y) | {f"{stock['eps_cagr_3y']:.2f}%" if stock['eps_cagr_3y'] else 'N/A'} | {'✓' if stock['eps_cagr_3y'] and stock['eps_cagr_3y'] > 0 else '⚠'} |
| ROE | {f"{stock['roe']:.1f}%" if stock['roe'] else 'N/A'} | {'✓ Excellent' if stock['roe'] and stock['roe'] >= 20 else '✓ Good' if stock['roe'] and stock['roe'] >= 15 else '⚠ Moderate' if stock['roe'] else 'N/A'} |
| Net Profit Margin | {f"{stock['profit_margin']:.1f}%" if stock['profit_margin'] else 'N/A'} | {'✓' if stock['profit_margin'] and stock['profit_margin'] >= 10 else '⚠'} |

### Financial Health

| Metric | Value | Status |
|--------|-------|--------|
| Debt-to-Equity | {f"{stock['debt_to_equity']:.2f}" if stock['debt_to_equity'] is not None else 'N/A'} | {'✓ Very Low' if stock['debt_to_equity'] and stock['debt_to_equity'] < 0.5 else '✓ Low' if stock['debt_to_equity'] and stock['debt_to_equity'] < 1.0 else '⚠ Moderate' if stock['debt_to_equity'] else 'N/A'} |
| Current Ratio | {f"{stock['current_ratio']:.2f}" if stock['current_ratio'] else 'N/A'} | {'✓ Healthy' if stock['current_ratio'] and stock['current_ratio'] > 1.2 else '⚠ Adequate' if stock['current_ratio'] else 'N/A'} |

### Investment Thesis

**10-Year Dividend Projection ({stock['dividend_cagr_3y']:.0f}% CAGR):**
- Current Yield on Cost: {stock['dividend_yield']:.2f}%
- Year 5 Yield on Cost: {stock['dividend_yield'] * (1 + stock['dividend_cagr_3y']/100)**5:.2f}%
- Year 10 Yield on Cost: {stock['dividend_yield'] * (1 + stock['dividend_cagr_3y']/100)**10:.2f}%

**Entry Strategy:**
{f"- RSI {stock['rsi']:.0f} indicates {rsi_interpretation.lower()} condition"}
- {'Scale in with 50% position now, add remaining on RSI >30 confirmation' if stock['rsi'] < 30 else f"Full position acceptable with stop loss {((stock['rsi'] - 30) / 2 + 3):.0f}% below entry" if stock['rsi'] < 35 else 'Conservative entry for high-conviction add with 3-5% stop loss'}
- Time horizon: 6-12 months minimum (long-term dividend growth play)

**Risk Factors:**
{f"- Payout ratio {stock['payout_ratio']:.0f}% limits dividend growth runway" if stock['payout_ratio'] and stock['payout_ratio'] > 70 else "- Monitor payout ratio sustainability"}
{f"- Debt-to-equity {stock['debt_to_equity']:.1f} requires monitoring" if stock['debt_to_equity'] and stock['debt_to_equity'] > 1.0 else ""}
- RSI can remain oversold in downtrends - watch for reversal confirmation
- Dividend growth may slow if business growth moderates

---

"""

    report += f"""
## Methodology

This screening combines fundamental dividend analysis with technical timing indicators:

1. **Fundamental Filter:** Dividend yield ≥{criteria['dividend_yield_min']}%, dividend CAGR ≥{criteria['dividend_cagr_min']}%, positive business growth
2. **Technical Filter:** RSI ≤{criteria['rsi_max']} identifies temporary pullbacks in quality stocks
3. **Quality Filter:** Financial health checks (debt, liquidity, profitability)
4. **Ranking:** Composite score balancing dividend growth (40%), quality (30%), technical setup (20%), valuation (10%)

**Investment Philosophy:**
High dividend growth stocks (12%+ CAGR) compound wealth through rising dividends rather than high current yield. A 1.5% yielding stock growing dividends at 15%/year becomes a 4% yielder in 6 years and 9% yielder in 12 years - far superior to a 4% yielder growing at 3%/year. Buying during RSI oversold conditions (≤40) enhances returns by entering at technical support levels.

---

**Disclaimer:** This report is for informational purposes only. Past dividend growth does not guarantee future performance. RSI oversold conditions do not guarantee price reversals. Conduct thorough due diligence and consult a financial advisor before making investment decisions.

**Report Generated:** {datetime.utcnow().isoformat()}Z
"""

    # Write report
    with open(output_path, 'w') as f:
        f.write(report)

    print(f"✅ Markdown report saved: {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description='Screen dividend growth stocks with RSI oversold using FINVIZ + FMP API (two-stage approach)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Two-stage screening: FINVIZ pre-screen + FMP detailed analysis (RECOMMENDED)
  python3 screen_dividend_growth_rsi.py --use-finviz

  # FMP-only screening (original method)
  python3 screen_dividend_growth_rsi.py

  # Provide API keys as arguments
  python3 screen_dividend_growth_rsi.py --use-finviz --fmp-api-key YOUR_FMP_KEY --finviz-api-key YOUR_FINVIZ_KEY

  # Custom parameters
  python3 screen_dividend_growth_rsi.py --use-finviz --min-yield 2.0 --min-div-growth 15.0 --rsi-max 35

Environment Variables:
  FMP_API_KEY       - Financial Modeling Prep API key
  FINVIZ_API_KEY    - FINVIZ Elite API key (required for --use-finviz)
        '''
    )

    parser.add_argument(
        '--fmp-api-key',
        type=str,
        help='FMP API key (or set FMP_API_KEY environment variable)'
    )
    parser.add_argument(
        '--finviz-api-key',
        type=str,
        help='FINVIZ Elite API key (or set FINVIZ_API_KEY environment variable)'
    )
    parser.add_argument(
        '--use-finviz',
        action='store_true',
        help='Use FINVIZ Elite API for pre-screening (recommended to reduce FMP API calls)'
    )
    parser.add_argument(
        '--min-yield',
        type=float,
        default=1.5,
        help='Minimum dividend yield %% (default: 1.5)'
    )
    parser.add_argument(
        '--min-div-growth',
        type=float,
        default=12.0,
        help='Minimum 3-year dividend CAGR %% (default: 12.0)'
    )
    parser.add_argument(
        '--rsi-max',
        type=float,
        default=40.0,
        help='Maximum RSI value (default: 40.0)'
    )
    parser.add_argument(
        '--max-candidates',
        type=int,
        default=None,
        help='Maximum candidates to analyze (default: all, only applies to FMP-only mode)'
    )

    args = parser.parse_args()

    # Get FMP API key
    fmp_api_key = args.fmp_api_key or os.environ.get('FMP_API_KEY')
    if not fmp_api_key:
        print("ERROR: FMP API key required. Provide via --fmp-api-key or FMP_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    # FINVIZ pre-screening (optional)
    finviz_symbols = None
    if args.use_finviz:
        finviz_api_key = args.finviz_api_key or os.environ.get('FINVIZ_API_KEY')
        if not finviz_api_key:
            print("ERROR: FINVIZ API key required when using --use-finviz. Provide via --finviz-api-key or FINVIZ_API_KEY environment variable", file=sys.stderr)
            sys.exit(1)

        print(f"\n{'='*80}", file=sys.stderr)
        print("DIVIDEND GROWTH PULLBACK SCREENER (TWO-STAGE)", file=sys.stderr)
        print(f"{'='*80}\n", file=sys.stderr)

        finviz_client = FINVIZClient(finviz_api_key)
        finviz_symbols = finviz_client.screen_stocks()

        if not finviz_symbols:
            print("ERROR: No stocks found in FINVIZ pre-screening", file=sys.stderr)
            sys.exit(1)

        print(f"\n{'='*80}\n", file=sys.stderr)

    # Run screening
    results = screen_dividend_growth_pullbacks(
        api_key=fmp_api_key,
        min_yield=args.min_yield,
        min_div_growth=args.min_div_growth,
        rsi_max=args.rsi_max,
        max_candidates=args.max_candidates,
        finviz_symbols=finviz_symbols
    )

    # Prepare metadata
    criteria = {
        'dividend_yield_min': args.min_yield,
        'dividend_cagr_min': args.min_div_growth,
        'rsi_max': args.rsi_max,
        'revenue_trend': 'positive over 3 years',
        'eps_trend': 'positive over 3 years'
    }

    # Generate outputs
    today = date.today().isoformat()

    # Determine output directory (project root logs/ folder)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate from .claude/skills/dividend-growth-pullback-screener/scripts to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # JSON output
    json_output = {
        'metadata': {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'criteria': criteria,
            'total_results': len(results)
        },
        'stocks': results
    }

    json_path = os.path.join(logs_dir, f'dividend_growth_pullback_results_{today}.json')
    with open(json_path, 'w') as f:
        json.dump(json_output, f, indent=2)

    print(f"✅ JSON results saved: {json_path}", file=sys.stderr)

    # Markdown report
    md_path = os.path.join(logs_dir, f'dividend_growth_pullback_screening_{today}.md')
    generate_markdown_report(results, criteria, md_path)

    print(f"\n{'='*80}", file=sys.stderr)
    print(f"Screening complete! Found {len(results)} qualified stocks.", file=sys.stderr)
    print(f"{'='*80}\n", file=sys.stderr)


if __name__ == '__main__':
    main()
