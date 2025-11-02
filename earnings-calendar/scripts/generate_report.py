#!/usr/bin/env python3
"""
Earnings Calendar Report Generator

Generates formatted markdown reports from earnings data JSON.

Usage:
    # Output to stdout
    python generate_report.py earnings_data.json

    # Output to file
    python generate_report.py earnings_data.json earnings_calendar.md

    # Help
    python generate_report.py --help
"""

import sys
import json
from datetime import datetime
from collections import defaultdict
from typing import List, Dict


def load_earnings_data(filepath: str) -> List[Dict]:
    """
    Load earnings data from JSON file

    Args:
        filepath: Path to JSON file

    Returns:
        List of earnings announcements
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

            # Handle case where file has progress messages before JSON
            json_start = content.find('[')
            if json_start != -1:
                content = content[json_start:]

            data = json.loads(content)

            if not isinstance(data, list):
                print("ERROR: JSON file must contain an array of earnings data", file=sys.stderr)
                sys.exit(1)

            return data

    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error reading file: {e}", file=sys.stderr)
        sys.exit(1)


def group_by_date(earnings: List[Dict]) -> Dict:
    """
    Group earnings by date and timing

    Args:
        earnings: List of earnings announcements

    Returns:
        Dictionary grouped by date and timing
    """
    by_date = defaultdict(lambda: {'BMO': [], 'AMC': [], 'TAS': []})

    for stock in earnings:
        date = stock.get('date')
        timing = stock.get('timing', 'TAS')

        if date:
            by_date[date][timing].append(stock)

    return by_date


def calculate_summary_stats(earnings: List[Dict]) -> Dict:
    """
    Calculate summary statistics

    Args:
        earnings: List of earnings announcements

    Returns:
        Dictionary with summary statistics
    """
    total = len(earnings)
    large_cap = sum(1 for s in earnings if s.get('marketCap', 0) >= 10_000_000_000)
    mid_cap = total - large_cap

    # Sector distribution
    sectors = defaultdict(int)
    for stock in earnings:
        sector = stock.get('sector', 'N/A')
        sectors[sector] += 1

    # Peak day
    by_date = group_by_date(earnings)
    peak = max(by_date.items(), key=lambda x: sum(len(v) for v in x[1].values()))
    peak_date, peak_data = peak
    peak_count = sum(len(v) for v in peak_data.values())

    return {
        'total': total,
        'large_cap': large_cap,
        'mid_cap': mid_cap,
        'sectors': dict(sectors),
        'peak_date': peak_date,
        'peak_count': peak_count
    }


def get_day_name(date_str: str) -> str:
    """
    Convert date string to full day name

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Formatted day name (e.g., "Monday, November 03, 2025")
    """
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    return date_obj.strftime('%A, %B %d, %Y')


def format_revenue(revenue: float) -> str:
    """
    Format revenue in human-readable format

    Args:
        revenue: Revenue in dollars

    Returns:
        Formatted string (e.g., "$3.5B", "$150M")
    """
    if revenue >= 1e12:
        return f"${revenue/1e12:.1f}T"
    elif revenue >= 1e9:
        return f"${revenue/1e9:.1f}B"
    elif revenue >= 1e6:
        return f"${revenue/1e6:.0f}M"
    else:
        return f"${revenue:,.0f}"


def generate_report(earnings: List[Dict]) -> str:
    """
    Generate markdown earnings calendar report

    Args:
        earnings: List of earnings announcements

    Returns:
        Formatted markdown report
    """
    if not earnings:
        return "# Earnings Calendar\n\nNo earnings data available.\n"

    # Calculate statistics
    stats = calculate_summary_stats(earnings)
    by_date = group_by_date(earnings)

    # Get date range
    dates = sorted(by_date.keys())
    if dates:
        start_date = datetime.strptime(dates[0], '%Y-%m-%d')
        end_date = datetime.strptime(dates[-1], '%Y-%m-%d')
        date_range = f"{start_date.strftime('%B %d')} to {end_date.strftime('%B %d, %Y')}"
    else:
        date_range = "Unknown"

    # Top 5 by market cap
    top5 = sorted(earnings, key=lambda x: x.get('marketCap', 0), reverse=True)[:5]

    # Generate report
    report = f"""# Upcoming Earnings Calendar - Week of {date_range}

**Report Generated**: {datetime.now().strftime('%B %d, %Y')}
**Data Source**: FMP API (US stocks, Mid-cap and above, >$2B market cap)
**Coverage Period**: Next 7 days
**Total Companies**: {stats['total']}

---

## Executive Summary

- **Total Companies Reporting**: {stats['total']}
- **Mega/Large Cap (>$10B)**: {stats['large_cap']}
- **Mid Cap ($2B-$10B)**: {stats['mid_cap']}
- **Peak Day**: {get_day_name(stats['peak_date']).split(',')[0]} ({stats['peak_count']} companies)

---

"""

    # Generate day-by-day sections
    for date in dates:
        day_name = get_day_name(date)
        report += f"## {day_name}\n\n"

        timings = ['BMO', 'AMC', 'TAS']
        timing_labels = {
            'BMO': 'Before Market Open (BMO)',
            'AMC': 'After Market Close (AMC)',
            'TAS': 'Time Not Announced (TAS)'
        }

        for timing in timings:
            stocks = by_date[date][timing]

            report += f"### {timing_labels[timing]}\n\n"

            if not stocks:
                report += "*No earnings announcements*\n\n"
            else:
                report += "| Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est. |\n"
                report += "|--------|---------|------------|--------|----------|--------------|\n"

                # Top 30 by market cap
                display_stocks = sorted(stocks, key=lambda x: x.get('marketCap', 0), reverse=True)[:30]

                for stock in display_stocks:
                    ticker = stock.get('symbol', 'N/A')
                    company = stock.get('companyName', 'N/A')[:35]
                    mcap = stock.get('marketCapFormatted', 'N/A')
                    sector = stock.get('sector', 'N/A')[:18]

                    eps = stock.get('epsEstimated')
                    eps_str = f"${eps:.2f}" if eps is not None else 'N/A'

                    rev = stock.get('revenueEstimated')
                    rev_str = format_revenue(rev) if rev else 'N/A'

                    report += f"| {ticker} | {company} | {mcap} | {sector} | {eps_str} | {rev_str} |\n"

                if len(stocks) > 30:
                    report += f"\n*Showing top 30 of {len(stocks)} companies by market cap*\n"

                report += "\n"

        report += "---\n\n"

    # Key observations
    report += "## Key Observations\n\n### Highest Market Cap Companies This Week\n"
    for i, stock in enumerate(top5, 1):
        date_str = datetime.strptime(stock['date'], '%Y-%m-%d').strftime('%a')
        company = stock.get('companyName', stock.get('symbol'))
        ticker = stock.get('symbol', 'N/A')
        mcap = stock.get('marketCapFormatted', 'N/A')
        timing = stock.get('timing', 'TAS')
        report += f"{i}. {company} ({ticker}) - {mcap} - {date_str} {timing}\n"

    report += "\n### Sector Distribution\n"
    top_sectors = sorted(stats['sectors'].items(), key=lambda x: x[1], reverse=True)[:5]
    for sector, count in top_sectors:
        report += f"- **{sector}**: {count} companies\n"

    peak_day_name = get_day_name(stats['peak_date']).split(',')[0]
    report += f"""
### Trading Considerations
- **Peak Day**: {peak_day_name} with {stats['peak_count']} earnings announcements
- **Pre-Market Focus**: BMO announcements before 9:30 AM ET
- **After-Hours Focus**: AMC announcements after 4:00 PM ET

---

## Timing Reference

- **BMO (Before Market Open)**: Announcements typically around 6:00-8:00 AM ET before market opens at 9:30 AM ET
- **AMC (After Market Close)**: Announcements typically around 4:00-5:00 PM ET after market closes at 4:00 PM ET
- **TAS (Time Not Announced)**: Specific time not yet disclosed - monitor company investor relations

---

## Data Notes

- **Market Cap Categories**:
  - Mega Cap: >$200B
  - Large Cap: $10B-$200B
  - Mid Cap: $2B-$10B

- **Filter Criteria**: This report includes US companies with market cap $2B and above (mid-cap+) with earnings scheduled for the next week.

- **Data Source**: Financial Modeling Prep (FMP) API

- **Data Freshness**: Earnings dates and times can change. Verify critical dates through company investor relations websites for the most current information.

- **EPS and Revenue Estimates**: Analyst consensus estimates from FMP API. Actual results will be reported on earnings date.

---

## Additional Resources

- **FMP API Documentation**: https://site.financialmodelingprep.com/developer/docs
- **Seeking Alpha Calendar**: https://seekingalpha.com/earnings/earnings-calendar
- **Yahoo Finance Calendar**: https://finance.yahoo.com/calendar/earnings

---

*Report generated using FMP Earnings Calendar API with US stocks mid-cap+ filter (>$2B market cap). Data current as of report generation time. Always verify earnings dates through official company sources.*
"""

    return report


def print_usage():
    """Print usage instructions"""
    print("Usage:", file=sys.stderr)
    print("  python generate_report.py INPUT_JSON [OUTPUT_FILE]", file=sys.stderr)
    print("", file=sys.stderr)
    print("Arguments:", file=sys.stderr)
    print("  INPUT_JSON   Path to earnings data JSON file (required)", file=sys.stderr)
    print("  OUTPUT_FILE  Path to output markdown file (optional, defaults to stdout)", file=sys.stderr)
    print("", file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print("  python generate_report.py earnings_data.json", file=sys.stderr)
    print("  python generate_report.py earnings_data.json earnings_calendar.md", file=sys.stderr)
    print("", file=sys.stderr)
    print("Input JSON format:", file=sys.stderr)
    print("  Array of earnings objects with fields: symbol, companyName, date, timing,", file=sys.stderr)
    print("  marketCap, marketCapFormatted, sector, epsEstimated, revenueEstimated", file=sys.stderr)


def main():
    """Main execution"""
    # Check for help flag
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help", "help"]:
        print_usage()
        sys.exit(0)

    # Validate arguments
    if len(sys.argv) < 2:
        print("ERROR: Missing required argument", file=sys.stderr)
        print("", file=sys.stderr)
        print_usage()
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"📄 Loading earnings data from: {input_file}", file=sys.stderr)
    earnings = load_earnings_data(input_file)
    print(f"✓ Loaded {len(earnings)} companies", file=sys.stderr)

    print("📝 Generating markdown report...", file=sys.stderr)
    report = generate_report(earnings)

    if output_file:
        with open(output_file, 'w') as f:
            f.write(report)
        print(f"✓ Report saved to: {output_file}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
