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


class StockAnalyzer:
    """Analyzes stock data and calculates scores"""

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
    def analyze_dividend_sustainability(income_statements: List[Dict], cash_flows: List[Dict]) -> Dict:
        """Analyze dividend sustainability"""
        result = {
            'payout_ratio': None,
            'fcf_payout_ratio': None,
            'sustainable': False
        }

        if not income_statements or not cash_flows:
            return result

        latest_income = income_statements[0]
        latest_cf = cash_flows[0]

        # Payout ratio (Dividends / Net Income)
        net_income = latest_income.get('netIncome', 0)
        dividends_paid = abs(latest_cf.get('dividendsPaid', 0))

        if net_income > 0 and dividends_paid > 0:
            result['payout_ratio'] = (dividends_paid / net_income) * 100

        # FCF payout ratio
        operating_cf = latest_cf.get('operatingCashFlow', 0)
        capex = abs(latest_cf.get('capitalExpenditure', 0))
        fcf = operating_cf - capex

        if fcf > 0 and dividends_paid > 0:
            result['fcf_payout_ratio'] = (dividends_paid / fcf) * 100

        # Sustainable if payout ratio < 80% and FCF covers dividends
        if result['payout_ratio'] and result['fcf_payout_ratio']:
            result['sustainable'] = (result['payout_ratio'] < 80 and result['fcf_payout_ratio'] < 100)

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

    # Step 1: Get candidate list
    if finviz_symbols:
        print(f"Step 1: Using FINVIZ pre-screened symbols ({len(finviz_symbols)} stocks)...", file=sys.stderr)
        # Convert FINVIZ symbols to candidate format for FMP analysis
        # We'll fetch basic quote data for each symbol from FMP
        candidates = []
        print("Fetching basic quote data from FMP for FINVIZ symbols...", file=sys.stderr)
        for symbol in finviz_symbols:
            quote = client._get(f'quote/{symbol}')
            if quote and isinstance(quote, list) and len(quote) > 0:
                candidates.append(quote[0])
            time.sleep(0.3)  # Rate limiting

            if client.rate_limit_reached:
                print(f"⚠️  FMP rate limit reached while fetching quotes. Using {len(candidates)} symbols.", file=sys.stderr)
                break

        print(f"Retrieved quote data for {len(candidates)} symbols from FMP", file=sys.stderr)
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

        # Additional analysis
        sustainability = analyzer.analyze_dividend_sustainability(income_stmts, cash_flows)
        financial_health = analyzer.analyze_financial_health(balance_sheets)
        quality = analyzer.calculate_quality_score(key_metrics, income_stmts)

        # Calculate composite score
        composite_score = 0
        composite_score += min(div_cagr / 10 * 20, 20)  # Max 20 points for 10%+ div growth
        composite_score += min((revenue_cagr or 0) / 10 * 15, 15)  # Max 15 points for revenue
        composite_score += min((eps_cagr or 0) / 15 * 15, 15)  # Max 15 points for EPS
        composite_score += 10 if sustainability['sustainable'] else 0
        composite_score += 10 if financial_health['healthy'] else 0
        composite_score += quality['quality_score'] * 0.3  # Max 30 points from quality

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
            'dividend_cagr_3y': round(div_cagr, 2),
            'dividend_consistent': div_consistent,
            'revenue_cagr_3y': round(revenue_cagr, 2) if revenue_cagr else None,
            'eps_cagr_3y': round(eps_cagr, 2) if eps_cagr else None,
            'payout_ratio': round(sustainability['payout_ratio'], 1) if sustainability['payout_ratio'] else None,
            'fcf_payout_ratio': round(sustainability['fcf_payout_ratio'], 1) if sustainability['fcf_payout_ratio'] else None,
            'dividend_sustainable': sustainability['sustainable'],
            'debt_to_equity': round(financial_health['debt_to_equity'], 2) if financial_health['debt_to_equity'] else None,
            'current_ratio': round(financial_health['current_ratio'], 2) if financial_health['current_ratio'] else None,
            'financially_healthy': financial_health['healthy'],
            'roe': round(key_metrics[0].get('roe', 0) * 100, 1) if key_metrics else None,
            'profit_margin': round(quality['profit_margin'], 1) if quality['profit_margin'] else None,
            'quality_score': quality['quality_score'],
            'composite_score': round(composite_score, 1)
        }

        results.append(result)
        print(f"  ✅ Passed all criteria (Score: {result['composite_score']})", file=sys.stderr)

    # Sort by composite score
    results.sort(key=lambda x: x['composite_score'], reverse=True)

    print(f"\nStep 3: Ranking complete. Top {top_n} stocks selected.", file=sys.stderr)
    return results[:top_n]


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

    parser.add_argument(
        '--output',
        type=str,
        default='dividend_screener_results.json',
        help='Output JSON file path (default: dividend_screener_results.json)'
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
                'revenue_trend': 'positive over 3 years',
                'eps_trend': 'positive over 3 years'
            },
            'total_results': len(results)
        },
        'stocks': results
    }

    # Write to file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"✅ Screening complete! Found {len(results)} stocks.", file=sys.stderr)
    print(f"📄 Results saved to: {args.output}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)


if __name__ == '__main__':
    main()
