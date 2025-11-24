#!/usr/bin/env python3
"""
Value Dividend Stock Screener using FINVIZ + Financial Modeling Prep API

Two-stage screening approach:
1. FINVIZ Elite API: Pre-screen stocks with basic criteria (fast, cost-effective)
2. FMP API: Detailed analysis of pre-screened candidates (comprehensive)

Screens US stocks based on:
- Dividend yield >= 3.5%
- P/E ratio <= 20
- P/B ratio <= 2
- Dividend CAGR >= 5% (3-year)
- Revenue growth: positive trend over 3 years
- EPS growth: positive trend over 3 years
- Additional analysis: dividend sustainability, financial health, quality scores

Outputs top 20 stocks ranked by composite score.
"""

import argparse
import csv
import io
import json
import os
import sys
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
import time

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


class FINVIZClient:
    """Client for FINVIZ Elite API"""

    BASE_URL = "https://elite.finviz.com/export.ashx"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def screen_stocks(self) -> Set[str]:
        """
        Screen stocks using FINVIZ Elite API with predefined criteria

        Criteria:
        - Market cap: Mid-cap or higher
        - Dividend yield: 3%+
        - Dividend growth (3Y): 5%+
        - EPS growth (3Y): Positive
        - P/B: Under 2
        - P/E: Under 20
        - Sales growth (3Y): Positive
        - Geography: USA

        Returns:
            Set of stock symbols
        """
        # Build filter string in FINVIZ format: key_value,key_value,...
        filters = 'cap_midover,fa_div_o3,fa_divgrowth_3yo5,fa_eps3years_pos,fa_pb_u2,fa_pe_u20,fa_sales3years_pos,geo_usa'

        params = {
            'v': '151',  # View type
            'f': filters,  # Filter conditions
            'ft': '4',   # File type: CSV export
            'auth': self.api_key
        }

        try:
            print(f"Fetching pre-screened stocks from FINVIZ Elite API...", file=sys.stderr)
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
    """Client for Financial Modeling Prep API"""

    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.rate_limit_reached = False
        self.retry_count = 0

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make GET request with rate limiting and error handling"""
        if self.rate_limit_reached:
            return None

        if params is None:
            params = {}
        params['apikey'] = self.api_key

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            time.sleep(0.3)  # Rate limiting: ~3 requests/second

            if response.status_code == 200:
                self.retry_count = 0  # Reset retry count on success
                return response.json()
            elif response.status_code == 429:
                self.retry_count += 1
                if self.retry_count <= 1:  # Only retry once
                    print(f"WARNING: Rate limit exceeded. Waiting 60 seconds...", file=sys.stderr)
                    time.sleep(60)
                    return self._get(endpoint, params)
                else:
                    print(f"ERROR: Daily API rate limit reached. Stopping analysis.", file=sys.stderr)
                    self.rate_limit_reached = True
                    return None
            else:
                print(f"ERROR: API request failed: {response.status_code} - {response.text}", file=sys.stderr)
                return None
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request exception: {e}", file=sys.stderr)
            return None

    def screen_stocks(self, dividend_yield_min: float, pe_max: float, pb_max: float,
                     market_cap_min: float = 2_000_000_000) -> List[Dict]:
        """Screen stocks using Stock Screener API"""
        params = {
            'dividendYieldMoreThan': dividend_yield_min,
            'priceEarningRatioLowerThan': pe_max,
            'priceToBookRatioLowerThan': pb_max,
            'marketCapMoreThan': market_cap_min,
            'exchange': 'NASDAQ,NYSE',
            'limit': 1000
        }

        data = self._get('stock-screener', params)
        return data if data else []

    def get_income_statement(self, symbol: str, limit: int = 5) -> List[Dict]:
        """Get income statement"""
        return self._get(f'income-statement/{symbol}', {'limit': limit}) or []

    def get_balance_sheet(self, symbol: str, limit: int = 5) -> List[Dict]:
        """Get balance sheet"""
        return self._get(f'balance-sheet-statement/{symbol}', {'limit': limit}) or []

    def get_cash_flow(self, symbol: str, limit: int = 5) -> List[Dict]:
        """Get cash flow statement"""
        return self._get(f'cash-flow-statement/{symbol}', {'limit': limit}) or []

    def get_key_metrics(self, symbol: str, limit: int = 5) -> List[Dict]:
        """Get key metrics"""
        return self._get(f'key-metrics/{symbol}', {'limit': limit}) or []

    def get_dividend_history(self, symbol: str) -> List[Dict]:
        """Get dividend history"""
        return self._get(f'historical-price-full/stock_dividend/{symbol}') or {}

    def get_company_profile(self, symbol: str) -> Optional[Dict]:
        """Get company profile including sector information."""
        result = self._get(f'profile/{symbol}')
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        return None

    def get_historical_prices(self, symbol: str, days: int = 30) -> List[Dict]:
        """Get historical daily prices for RSI calculation."""
        result = self._get(f'historical-price-full/{symbol}', {'serietype': 'line'})
        if result and 'historical' in result:
            # Return most recent 'days' entries
            return result['historical'][:days]
        return []


class RSICalculator:
    """Calculate RSI (Relative Strength Index)"""

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """
        Calculate RSI from price data.

        Args:
            prices: List of closing prices (oldest to newest)
            period: RSI period (default 14)

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(prices) < period + 1:
            return None

        # Calculate price changes
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

        # Separate gains and losses
        gains = [max(0, change) for change in changes]
        losses = [abs(min(0, change)) for change in changes]

        # Calculate initial average gain/loss
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Smooth using Wilder's method for remaining periods
        for i in range(period, len(changes)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        # Calculate RSI
        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi, 1)


class StockAnalyzer:
    """Analyzes stock data and calculates scores"""

    @staticmethod
    def is_reit(stock_data: Dict) -> bool:
        """
        Determine if a stock is a REIT based on sector/industry.

        Args:
            stock_data: Dict containing sector and/or industry fields

        Returns:
            True if the stock is likely a REIT
        """
        sector = stock_data.get('sector', '') or ''
        industry = stock_data.get('industry', '') or ''

        sector_lower = sector.lower()
        industry_lower = industry.lower()

        if 'real estate' in sector_lower:
            return True
        if 'reit' in industry_lower:
            return True

        return False

    @staticmethod
    def calculate_ffo(cash_flows: List[Dict]) -> Optional[float]:
        """
        Calculate Funds From Operations (FFO) for REITs.

        FFO = Net Income + Depreciation & Amortization

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
    def calculate_cagr(start_value: float, end_value: float, years: int) -> Optional[float]:
        """Calculate Compound Annual Growth Rate"""
        if start_value <= 0 or end_value <= 0 or years <= 0:
            return None
        return (pow(end_value / start_value, 1 / years) - 1) * 100

    @staticmethod
    def check_positive_trend(values: List[float]) -> bool:
        """Check if values show positive trend (允许一次回落)"""
        if len(values) < 3:
            return False

        # Check overall trend: first < last
        if values[0] >= values[-1]:
            return False

        # Allow one dip but overall upward trend
        dips = sum(1 for i in range(1, len(values)) if values[i] < values[i-1])
        return dips <= 1

    @staticmethod
    def analyze_dividend_growth(dividend_history: List[Dict]) -> Tuple[Optional[float], bool, Optional[float]]:
        """Analyze dividend growth rate (3-year CAGR and consistency) and return latest annual dividend"""
        if not dividend_history or 'historical' not in dividend_history:
            return None, False, None

        dividends = dividend_history['historical']
        if len(dividends) < 4:  # Need at least 4 years
            return None, False, None

        # Sort by date
        dividends = sorted(dividends, key=lambda x: x['date'])

        # Get annual dividends for last 4 years
        annual_dividends = {}
        for div in dividends:
            year = div['date'][:4]
            annual_dividends[year] = annual_dividends.get(year, 0) + div.get('dividend', 0)

        if len(annual_dividends) < 4:
            return None, False, None

        years = sorted(annual_dividends.keys())[-4:]
        div_values = [annual_dividends[y] for y in years]

        # Calculate 3-year CAGR
        cagr = StockAnalyzer.calculate_cagr(div_values[0], div_values[-1], 3)

        # Check for consistency (no dividend cuts)
        consistent = all(div_values[i] >= div_values[i-1] * 0.95 for i in range(1, len(div_values)))

        # Get latest annual dividend (most recent year)
        latest_annual_dividend = div_values[-1]

        return cagr, consistent, latest_annual_dividend

    @staticmethod
    def analyze_revenue_growth(income_statements: List[Dict]) -> Tuple[bool, Optional[float]]:
        """Analyze revenue growth trend"""
        if len(income_statements) < 4:
            return False, None

        revenues = [stmt.get('revenue', 0) for stmt in income_statements[:4]]
        revenues.reverse()  # Oldest to newest

        positive_trend = StockAnalyzer.check_positive_trend(revenues)
        cagr = StockAnalyzer.calculate_cagr(revenues[0], revenues[-1], 3) if revenues[0] > 0 else None

        return positive_trend, cagr

    @staticmethod
    def analyze_eps_growth(income_statements: List[Dict]) -> Tuple[bool, Optional[float]]:
        """Analyze EPS growth trend"""
        if len(income_statements) < 4:
            return False, None

        eps_values = [stmt.get('eps', 0) for stmt in income_statements[:4]]
        eps_values.reverse()  # Oldest to newest

        positive_trend = StockAnalyzer.check_positive_trend(eps_values)
        cagr = StockAnalyzer.calculate_cagr(eps_values[0], eps_values[-1], 3) if eps_values[0] > 0 else None

        return positive_trend, cagr

    @staticmethod
    def analyze_dividend_sustainability(income_statements: List[Dict], cash_flows: List[Dict], is_reit: bool = False) -> Dict:
        """
        Analyze dividend sustainability.

        For REITs, uses FFO-based payout ratio instead of net income-based.

        Args:
            income_statements: List of income statements (newest first)
            cash_flows: List of cash flow statements (newest first)
            is_reit: Whether the stock is a REIT (uses FFO for payout calculation)

        Returns:
            Dict with payout_ratio, fcf_payout_ratio, and sustainable flag
        """
        result = {
            'payout_ratio': None,
            'fcf_payout_ratio': None,
            'sustainable': False
        }

        if not cash_flows:
            return result

        latest_cf = cash_flows[0]
        dividends_paid = abs(latest_cf.get('dividendsPaid', 0))

        # For REITs, use FFO-based payout ratio
        if is_reit:
            ffo_payout = StockAnalyzer.calculate_ffo_payout_ratio(cash_flows)
            if ffo_payout is not None:
                result['payout_ratio'] = ffo_payout
        else:
            # For non-REITs, use traditional net income-based payout ratio
            if income_statements:
                latest_income = income_statements[0]
                net_income = latest_income.get('netIncome', 0)

                if net_income > 0 and dividends_paid > 0:
                    result['payout_ratio'] = (dividends_paid / net_income) * 100

        # FCF payout ratio (same for both REIT and non-REIT)
        operating_cf = latest_cf.get('operatingCashFlow', 0)
        capex = abs(latest_cf.get('capitalExpenditure', 0))
        fcf = operating_cf - capex

        if fcf > 0 and dividends_paid > 0:
            result['fcf_payout_ratio'] = (dividends_paid / fcf) * 100

        # Sustainable if payout ratio < 80% and FCF covers dividends
        if result['payout_ratio'] and result['fcf_payout_ratio']:
            result['sustainable'] = (result['payout_ratio'] < 80 and result['fcf_payout_ratio'] < 100)
        elif result['payout_ratio']:
            # If FCF payout is not available, just check payout ratio
            result['sustainable'] = result['payout_ratio'] < 80

        return result

    @staticmethod
    def analyze_financial_health(balance_sheets: List[Dict]) -> Dict:
        """Analyze financial health metrics"""
        result = {
            'debt_to_equity': None,
            'current_ratio': None,
            'healthy': False
        }

        if not balance_sheets:
            return result

        latest_bs = balance_sheets[0]

        # Debt-to-Equity ratio
        total_debt = latest_bs.get('totalDebt', 0)
        shareholders_equity = latest_bs.get('totalStockholdersEquity', 0)

        if shareholders_equity > 0:
            result['debt_to_equity'] = total_debt / shareholders_equity

        # Current ratio
        current_assets = latest_bs.get('totalCurrentAssets', 0)
        current_liabilities = latest_bs.get('totalCurrentLiabilities', 0)

        if current_liabilities > 0:
            result['current_ratio'] = current_assets / current_liabilities

        # Healthy if D/E < 2.0 and Current Ratio > 1.0
        if result['debt_to_equity'] is not None and result['current_ratio'] is not None:
            result['healthy'] = (result['debt_to_equity'] < 2.0 and result['current_ratio'] > 1.0)

        return result

    @staticmethod
    def analyze_dividend_stability(dividend_history: Dict) -> Dict:
        """
        Analyze dividend stability and growth consistency.

        Evaluates:
        - Year-over-year dividend growth
        - Volatility (variation in annual dividends)
        - Consecutive years of growth

        Args:
            dividend_history: Dict with 'historical' key containing dividend records

        Returns:
            Dict with is_stable, is_growing, volatility_pct, years_of_growth
        """
        result = {
            'is_stable': False,
            'is_growing': False,
            'volatility_pct': None,
            'years_of_growth': 0,
            'annual_dividends': {}
        }

        if not dividend_history or 'historical' not in dividend_history:
            return result

        dividends = dividend_history['historical']
        if len(dividends) < 4:
            return result

        # Calculate annual dividends
        annual_dividends = {}
        for div in dividends:
            year = div.get('date', '')[:4]
            if year:
                annual_dividends[year] = annual_dividends.get(year, 0) + div.get('dividend', 0)

        if len(annual_dividends) < 3:
            return result

        result['annual_dividends'] = annual_dividends

        # Get sorted years (newest to oldest for analysis)
        years = sorted(annual_dividends.keys(), reverse=True)
        div_values = [annual_dividends[y] for y in years]

        # Calculate volatility (coefficient of variation)
        if len(div_values) >= 2:
            avg_div = sum(div_values) / len(div_values)
            if avg_div > 0:
                max_div = max(div_values)
                min_div = min(div_values)
                # Volatility as percentage variation from average
                volatility = ((max_div - min_div) / avg_div) * 100
                result['volatility_pct'] = round(volatility, 1)

                # Stable if volatility < 50% (allowing some variation)
                result['is_stable'] = volatility < 50

        # Count consecutive years of growth (from oldest to newest)
        years_oldest_first = sorted(annual_dividends.keys())
        div_values_oldest_first = [annual_dividends[y] for y in years_oldest_first]

        years_of_growth = 0
        for i in range(1, len(div_values_oldest_first)):
            # Allow small decrease (5%) as "no cut"
            if div_values_oldest_first[i] >= div_values_oldest_first[i-1] * 0.95:
                years_of_growth += 1
            else:
                years_of_growth = 0  # Reset on dividend cut

        result['years_of_growth'] = years_of_growth

        # Growing if at least 2 consecutive years of growth and overall uptrend
        if len(div_values_oldest_first) >= 3:
            overall_growth = div_values_oldest_first[-1] > div_values_oldest_first[0]
            result['is_growing'] = years_of_growth >= 2 and overall_growth

        return result

    @staticmethod
    def analyze_revenue_trend(income_statements: List[Dict]) -> Dict:
        """
        Analyze revenue trend for year-over-year growth.

        Args:
            income_statements: List of income statements (newest first)

        Returns:
            Dict with is_uptrend, years_of_growth, cagr
        """
        result = {
            'is_uptrend': False,
            'years_of_growth': 0,
            'cagr': None
        }

        if len(income_statements) < 3:
            return result

        # Get revenues (newest first in input, reverse for analysis)
        revenues = [stmt.get('revenue', 0) for stmt in income_statements[:4]]
        revenues_oldest_first = list(reversed(revenues))

        # Count years of growth
        years_of_growth = 0
        for i in range(1, len(revenues_oldest_first)):
            if revenues_oldest_first[i] > revenues_oldest_first[i-1]:
                years_of_growth += 1
            else:
                # Allow one dip but don't reset completely
                pass

        result['years_of_growth'] = years_of_growth

        # Calculate CAGR
        if revenues_oldest_first[0] > 0 and revenues_oldest_first[-1] > 0:
            years = len(revenues_oldest_first) - 1
            if years > 0:
                cagr = (pow(revenues_oldest_first[-1] / revenues_oldest_first[0], 1 / years) - 1) * 100
                result['cagr'] = round(cagr, 2)

        # Uptrend if overall growth and at least 2 years of growth
        overall_growth = revenues_oldest_first[-1] > revenues_oldest_first[0]
        result['is_uptrend'] = overall_growth and years_of_growth >= 2

        return result

    @staticmethod
    def analyze_earnings_trend(income_statements: List[Dict]) -> Dict:
        """
        Analyze earnings/profit trend for year-over-year growth.

        Args:
            income_statements: List of income statements (newest first)

        Returns:
            Dict with is_uptrend, years_of_growth, cagr
        """
        result = {
            'is_uptrend': False,
            'years_of_growth': 0,
            'cagr': None
        }

        if len(income_statements) < 3:
            return result

        # Get net income (newest first in input, reverse for analysis)
        earnings = [stmt.get('netIncome', 0) for stmt in income_statements[:4]]
        earnings_oldest_first = list(reversed(earnings))

        # Check for negative earnings (not a good sign)
        if any(e <= 0 for e in earnings_oldest_first):
            return result

        # Count years of growth
        years_of_growth = 0
        for i in range(1, len(earnings_oldest_first)):
            if earnings_oldest_first[i] > earnings_oldest_first[i-1]:
                years_of_growth += 1

        result['years_of_growth'] = years_of_growth

        # Calculate CAGR
        if earnings_oldest_first[0] > 0 and earnings_oldest_first[-1] > 0:
            years = len(earnings_oldest_first) - 1
            if years > 0:
                cagr = (pow(earnings_oldest_first[-1] / earnings_oldest_first[0], 1 / years) - 1) * 100
                result['cagr'] = round(cagr, 2)

        # Uptrend if overall growth and at least 2 years of growth
        overall_growth = earnings_oldest_first[-1] > earnings_oldest_first[0]
        result['is_uptrend'] = overall_growth and years_of_growth >= 2

        return result

    @staticmethod
    def calculate_stability_score(stability: Dict) -> float:
        """
        Calculate a stability score based on dividend stability metrics.

        Args:
            stability: Dict from analyze_dividend_stability

        Returns:
            Score from 0-100
        """
        score = 0

        # Stability bonus (max 40 points)
        if stability.get('is_stable'):
            score += 40
        elif stability.get('volatility_pct') is not None:
            # Partial credit for lower volatility
            volatility = stability['volatility_pct']
            if volatility < 100:
                score += max(0, 40 - (volatility * 0.4))

        # Growth bonus (max 30 points)
        if stability.get('is_growing'):
            score += 30

        # Years of growth bonus (max 30 points, 10 per year)
        years = stability.get('years_of_growth', 0)
        score += min(years * 10, 30)

        return round(score, 1)

    @staticmethod
    def calculate_quality_score(key_metrics: List[Dict], income_statements: List[Dict]) -> Dict:
        """Calculate quality scores (ROE, Profit Margin)"""
        result = {
            'roe': None,
            'profit_margin': None,
            'quality_score': 0
        }

        if not key_metrics or not income_statements:
            return result

        # ROE (Return on Equity)
        latest_metrics = key_metrics[0]
        result['roe'] = latest_metrics.get('roe')

        # Profit Margin
        latest_income = income_statements[0]
        revenue = latest_income.get('revenue', 0)
        net_income = latest_income.get('netIncome', 0)

        if revenue > 0:
            result['profit_margin'] = (net_income / revenue) * 100

        # Quality score (0-100)
        score = 0
        if result['roe']:
            roe_pct = result['roe'] * 100
            score += min(roe_pct / 20 * 50, 50)  # Max 50 points for 20%+ ROE

        if result['profit_margin']:
            score += min(result['profit_margin'] / 15 * 50, 50)  # Max 50 points for 15%+ margin

        result['quality_score'] = round(score, 1)

        return result


def screen_value_dividend_stocks(fmp_api_key: str, top_n: int = 20,
                                finviz_symbols: Optional[Set[str]] = None) -> List[Dict]:
    """
    Main screening function

    Args:
        fmp_api_key: Financial Modeling Prep API key
        top_n: Number of top stocks to return
        finviz_symbols: Optional set of symbols from FINVIZ pre-screening

    Returns:
        List of stocks with detailed analysis, sorted by composite score
    """
    client = FMPClient(fmp_api_key)
    analyzer = StockAnalyzer()
    rsi_calc = RSICalculator()

    # Step 1: Get candidate list
    if finviz_symbols:
        print(f"Step 1: Using FINVIZ pre-screened symbols ({len(finviz_symbols)} stocks)...", file=sys.stderr)
        # Convert FINVIZ symbols to candidate format for FMP analysis
        # Fetch quote + profile to get sector information
        candidates = []
        print("Fetching quote and profile data from FMP for FINVIZ symbols...", file=sys.stderr)
        for symbol in finviz_symbols:
            quote = client._get(f'quote/{symbol}')
            if quote and isinstance(quote, list) and len(quote) > 0:
                stock_data = quote[0].copy()
                # Fetch profile for sector information
                profile = client.get_company_profile(symbol)
                if profile:
                    stock_data['sector'] = profile.get('sector', 'N/A')
                    stock_data['industry'] = profile.get('industry', '')
                    stock_data['companyName'] = profile.get('companyName', stock_data.get('name', ''))
                candidates.append(stock_data)

            if client.rate_limit_reached:
                print(f"⚠️  FMP rate limit reached while fetching quotes. Using {len(candidates)} symbols.", file=sys.stderr)
                break

        print(f"Retrieved quote and profile data for {len(candidates)} symbols from FMP", file=sys.stderr)
    else:
        print("Step 1: Initial screening using FMP Stock Screener (Dividend Yield >= 3.0%, P/E <= 20, P/B <= 2)...", file=sys.stderr)
        print("Criteria: Div Yield >= 3.0%, Div Growth >= 4.0% CAGR", file=sys.stderr)
        candidates = client.screen_stocks(dividend_yield_min=3.0, pe_max=20, pb_max=2)
        print(f"Found {len(candidates)} initial candidates", file=sys.stderr)

    if not candidates:
        print("No stocks found matching initial criteria", file=sys.stderr)
        return []

    results = []

    print(f"\nStep 2: Detailed analysis of candidates...", file=sys.stderr)
    print(f"Note: Analysis will continue until API rate limit is reached", file=sys.stderr)

    for i, stock in enumerate(candidates, 1):  # Analyze all candidates until rate limit
        symbol = stock.get('symbol', '')
        company_name = stock.get('name', stock.get('companyName', ''))

        print(f"[{i}/{len(candidates)}] Analyzing {symbol} - {company_name}...", file=sys.stderr)

        # Check if rate limit reached
        if client.rate_limit_reached:
            print(f"\n⚠️  API rate limit reached after analyzing {i-1} stocks.", file=sys.stderr)
            print(f"Returning results collected so far: {len(results)} qualified stocks", file=sys.stderr)
            break

        # Fetch detailed data
        income_stmts = client.get_income_statement(symbol, limit=5)
        if client.rate_limit_reached:
            break

        balance_sheets = client.get_balance_sheet(symbol, limit=5)
        if client.rate_limit_reached:
            break

        cash_flows = client.get_cash_flow(symbol, limit=5)
        if client.rate_limit_reached:
            break

        key_metrics = client.get_key_metrics(symbol, limit=5)
        if client.rate_limit_reached:
            break

        dividend_history = client.get_dividend_history(symbol)
        if client.rate_limit_reached:
            break

        # Fetch historical prices for RSI calculation
        historical_prices = client.get_historical_prices(symbol, days=30)
        if client.rate_limit_reached:
            break

        # Calculate RSI for technical analysis
        rsi = None
        if historical_prices and len(historical_prices) >= 20:
            # Prices come newest first, reverse for RSI calculation
            prices = [p.get('close', 0) for p in reversed(historical_prices)]
            rsi = rsi_calc.calculate_rsi(prices, period=14)

        if rsi is None:
            print(f"  ⚠️  RSI calculation failed (insufficient price data)", file=sys.stderr)
            continue

        # Store RSI for later filtering
        stock['_rsi'] = rsi

        # Fetch profile for sector information if not already present
        if not stock.get('sector') or stock.get('sector') == 'N/A':
            profile = client.get_company_profile(symbol)
            if profile:
                stock['sector'] = profile.get('sector', 'N/A')
                stock['industry'] = profile.get('industry', '')
            if client.rate_limit_reached:
                break

        # Skip if insufficient data
        if len(income_stmts) < 4:
            print(f"  ⚠️  Insufficient income statement data", file=sys.stderr)
            continue

        # Analyze dividend growth and get latest annual dividend
        div_cagr, div_consistent, annual_dividend = analyzer.analyze_dividend_growth(dividend_history)
        if not div_cagr or div_cagr < 4.0:
            print(f"  ⚠️  Dividend CAGR < 4% (or no data)", file=sys.stderr)
            continue

        # Calculate actual dividend yield
        current_price = stock.get('price', 0)
        if current_price <= 0 or not annual_dividend:
            print(f"  ⚠️  Cannot calculate dividend yield (price or dividend data missing)", file=sys.stderr)
            continue

        actual_dividend_yield = (annual_dividend / current_price) * 100

        # Verify dividend yield >= 3.0%
        if actual_dividend_yield < 3.0:
            print(f"  ⚠️  Dividend yield {actual_dividend_yield:.2f}% < 3.0%", file=sys.stderr)
            continue

        # Analyze revenue growth
        revenue_positive, revenue_cagr = analyzer.analyze_revenue_growth(income_stmts)
        if not revenue_positive:
            print(f"  ⚠️  Revenue trend not positive", file=sys.stderr)
            continue

        # Analyze EPS growth
        eps_positive, eps_cagr = analyzer.analyze_eps_growth(income_stmts)
        if not eps_positive:
            print(f"  ⚠️  EPS trend not positive", file=sys.stderr)
            continue

        # NEW: Check dividend stability - filter out highly volatile dividends
        dividend_stability = analyzer.analyze_dividend_stability(dividend_history)
        if dividend_stability['volatility_pct'] and dividend_stability['volatility_pct'] > 100:
            # Allow if consistently growing despite volatility
            if not dividend_stability['is_growing'] or dividend_stability['years_of_growth'] < 3:
                print(f"  ⚠️  Dividend too volatile ({dividend_stability['volatility_pct']:.1f}%) and not consistently growing", file=sys.stderr)
                continue

        # Check if this is a REIT (uses different payout ratio calculation)
        is_reit = analyzer.is_reit(stock)

        # Additional analysis
        sustainability = analyzer.analyze_dividend_sustainability(income_stmts, cash_flows, is_reit=is_reit)
        financial_health = analyzer.analyze_financial_health(balance_sheets)
        quality = analyzer.calculate_quality_score(key_metrics, income_stmts)

        # Calculate stability score (dividend_stability already analyzed above)
        stability_score = analyzer.calculate_stability_score(dividend_stability)

        # NEW: Analyze revenue and earnings trends
        revenue_trend = analyzer.analyze_revenue_trend(income_stmts)
        earnings_trend = analyzer.analyze_earnings_trend(income_stmts)

        # Calculate composite score (updated to include stability)
        composite_score = 0
        composite_score += min(div_cagr / 10 * 15, 15)  # Max 15 points for 10%+ div growth
        composite_score += stability_score * 0.2  # Max 20 points from stability (100 * 0.2)
        composite_score += min((revenue_cagr or 0) / 10 * 10, 10)  # Max 10 points for revenue
        composite_score += min((eps_cagr or 0) / 15 * 10, 10)  # Max 10 points for EPS
        composite_score += 10 if sustainability['sustainable'] else 0
        composite_score += 10 if financial_health['healthy'] else 0
        composite_score += quality['quality_score'] * 0.25  # Max 25 points from quality

        result = {
            'symbol': symbol,
            'company_name': company_name,
            'sector': stock.get('sector', 'N/A'),
            'market_cap': stock.get('marketCap', 0),
            'price': stock.get('price', 0),
            'dividend_yield': round(actual_dividend_yield, 2),
            'annual_dividend': round(annual_dividend, 2),
            'pe_ratio': stock.get('pe', 0),
            'pb_ratio': stock.get('priceToBook', 0),
            'rsi': rsi,
            'dividend_cagr_3y': round(div_cagr, 2),
            'dividend_consistent': div_consistent,
            'dividend_stable': dividend_stability['is_stable'],
            'dividend_growing': dividend_stability['is_growing'],
            'dividend_volatility_pct': dividend_stability['volatility_pct'],
            'dividend_years_of_growth': dividend_stability['years_of_growth'],
            'revenue_cagr_3y': round(revenue_cagr, 2) if revenue_cagr else None,
            'revenue_uptrend': revenue_trend['is_uptrend'],
            'revenue_years_of_growth': revenue_trend['years_of_growth'],
            'eps_cagr_3y': round(eps_cagr, 2) if eps_cagr else None,
            'earnings_uptrend': earnings_trend['is_uptrend'],
            'earnings_years_of_growth': earnings_trend['years_of_growth'],
            'payout_ratio': round(sustainability['payout_ratio'], 1) if sustainability['payout_ratio'] else None,
            'fcf_payout_ratio': round(sustainability['fcf_payout_ratio'], 1) if sustainability['fcf_payout_ratio'] else None,
            'dividend_sustainable': sustainability['sustainable'],
            'debt_to_equity': round(financial_health['debt_to_equity'], 2) if financial_health['debt_to_equity'] else None,
            'current_ratio': round(financial_health['current_ratio'], 2) if financial_health['current_ratio'] else None,
            'financially_healthy': financial_health['healthy'],
            'roe': round(key_metrics[0].get('roe', 0) * 100, 1) if key_metrics else None,
            'profit_margin': round(quality['profit_margin'], 1) if quality['profit_margin'] else None,
            'quality_score': quality['quality_score'],
            'stability_score': stability_score,
            'composite_score': round(composite_score, 1)
        }

        results.append(result)
        print(f"  ✅ Passed all criteria (RSI: {rsi:.1f}, Score: {result['composite_score']})", file=sys.stderr)

    # Step 3: Filter by RSI
    # Prefer RSI <= 40 (oversold), but if none found, return lowest RSI stocks
    oversold_results = [r for r in results if r['rsi'] <= 40]

    if oversold_results:
        print(f"\nStep 3: Found {len(oversold_results)} oversold stocks (RSI <= 40)", file=sys.stderr)
        # Sort oversold stocks by composite score
        oversold_results.sort(key=lambda x: x['composite_score'], reverse=True)
        results = oversold_results[:top_n]
    else:
        print(f"\nStep 3: No oversold stocks found (RSI <= 40). Returning lowest RSI stocks.", file=sys.stderr)
        # Sort by RSI (lowest first), then by composite score
        results.sort(key=lambda x: (x['rsi'], -x['composite_score']))
        results = results[:top_n]

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Screen value dividend stocks using FINVIZ + FMP API (two-stage approach)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Two-stage screening: FINVIZ pre-screen + FMP detailed analysis (RECOMMENDED)
  python3 screen_dividend_stocks.py --use-finviz

  # FMP-only screening (original method)
  python3 screen_dividend_stocks.py

  # Provide API keys as arguments
  python3 screen_dividend_stocks.py --use-finviz --fmp-api-key YOUR_FMP_KEY --finviz-api-key YOUR_FINVIZ_KEY

  # Custom output location
  python3 screen_dividend_stocks.py --use-finviz --output /path/to/results.json

  # Get top 50 stocks
  python3 screen_dividend_stocks.py --use-finviz --top 50

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

    # Determine default output directory (project root logs/ folder)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate from .claude/skills/value-dividend-screener/scripts to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    logs_dir = os.path.join(project_root, 'logs')
    default_output = os.path.join(logs_dir, 'dividend_screener_results.json')

    parser.add_argument(
        '--output',
        type=str,
        default=default_output,
        help=f'Output JSON file path (default: {default_output})'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=20,
        help='Number of top stocks to return (default: 20)'
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

        print(f"\n{'='*60}", file=sys.stderr)
        print("VALUE DIVIDEND STOCK SCREENER (TWO-STAGE)", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

        finviz_client = FINVIZClient(finviz_api_key)
        finviz_symbols = finviz_client.screen_stocks()

        if not finviz_symbols:
            print("ERROR: FINVIZ pre-screening failed or returned no results", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"\n{'='*60}", file=sys.stderr)
        print("VALUE DIVIDEND STOCK SCREENER (FMP ONLY)", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

    # Run detailed screening
    results = screen_value_dividend_stocks(fmp_api_key, top_n=args.top, finviz_symbols=finviz_symbols)

    if not results:
        print("\nNo stocks found matching all criteria.", file=sys.stderr)
        sys.exit(1)

    # Add metadata
    output_data = {
        'metadata': {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'criteria': {
                'dividend_yield_min': 3.0,
                'pe_ratio_max': 20,
                'pb_ratio_max': 2,
                'dividend_cagr_min': 4.0,
                'dividend_stability': 'low volatility, year-over-year growth',
                'revenue_trend': 'positive over 3 years',
                'eps_trend': 'positive over 3 years'
            },
            'scoring': {
                'dividend_growth': 'max 15 points (10%+ CAGR)',
                'dividend_stability': 'max 20 points (stable, growing)',
                'revenue_growth': 'max 10 points (10%+ CAGR)',
                'eps_growth': 'max 10 points (15%+ CAGR)',
                'dividend_sustainable': '10 points',
                'financial_health': '10 points',
                'quality_score': 'max 25 points'
            },
            'total_results': len(results)
        },
        'stocks': results
    }

    # Write to file
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"✅ Screening complete! Found {len(results)} stocks.", file=sys.stderr)
    print(f"📄 Results saved to: {args.output}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)


if __name__ == '__main__':
    main()
