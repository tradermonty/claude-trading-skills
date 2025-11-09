#!/usr/bin/env python3
"""
Macro Indicators Dashboard - Data Fetcher
Retrieves macroeconomic indicators from FMP API and calculates trends
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import urllib.request
import urllib.error
import urllib.parse
from statistics import mean


# Supported economic indicators
SUPPORTED_INDICATORS = {
    'GDP': {
        'name': 'GDP',
        'display_name': 'Gross Domestic Product',
        'unit': '%',
        'frequency': 'quarterly',
        'description': 'Real GDP growth rate (annualized)'
    },
    'CPI': {
        'name': 'CPI',
        'display_name': 'Consumer Price Index',
        'unit': '%',
        'frequency': 'monthly',
        'description': 'Year-over-year inflation rate'
    },
    'unemployment': {
        'name': 'unemployment',
        'display_name': 'Unemployment Rate',
        'unit': '%',
        'frequency': 'monthly',
        'description': 'Percentage of labor force unemployed'
    },
    'retailSales': {
        'name': 'retailSales',
        'display_name': 'Retail Sales',
        'unit': 'billion USD',
        'frequency': 'monthly',
        'description': 'Total retail sales'
    },
    'industrialProduction': {
        'name': 'industrialProduction',
        'display_name': 'Industrial Production Index',
        'unit': 'index',
        'frequency': 'monthly',
        'description': 'Manufacturing, mining, and utilities output'
    },
    'consumerConfidence': {
        'name': 'consumerConfidence',
        'display_name': 'Consumer Confidence Index',
        'unit': 'index',
        'frequency': 'monthly',
        'description': 'Consumer sentiment survey'
    },
    'inflation': {
        'name': 'inflation',
        'display_name': 'Inflation Rate',
        'unit': '%',
        'frequency': 'monthly',
        'description': 'General inflation rate'
    }
}

# Default indicators to fetch
DEFAULT_INDICATORS = ['GDP', 'CPI', 'unemployment', 'retailSales', 'industrialProduction']


def get_api_key() -> Optional[str]:
    """
    Get FMP API key from environment variable.

    Returns:
        API key string or None if not found
    """
    api_key = os.environ.get('FMP_API_KEY')
    if not api_key:
        print("Warning: FMP_API_KEY environment variable not set", file=sys.stderr)
    return api_key


def fetch_economic_indicator(
    indicator_name: str,
    api_key: str,
    country: str = 'US'
) -> List[Dict]:
    """
    Fetch economic indicator data from FMP API.

    Args:
        indicator_name: Name of the indicator (e.g., 'GDP', 'CPI', 'unemployment')
        api_key: FMP API key
        country: Country code (default: 'US')

    Returns:
        List of data points with dates and values

    Raises:
        urllib.error.HTTPError: If API request fails
        ValueError: If response is invalid
    """
    # FMP API endpoint for economic indicators
    base_url = "https://financialmodelingprep.com/stable/economic-indicators"

    # Build query parameters
    params = {
        'name': indicator_name,
        'apikey': api_key
    }

    # Construct URL with parameters
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        # Make API request
        with urllib.request.urlopen(url) as response:
            if response.status != 200:
                raise ValueError(f"API returned status code {response.status}")

            data = json.loads(response.read().decode('utf-8'))

            if not isinstance(data, list):
                raise ValueError(f"Unexpected API response format for {indicator_name}: {type(data)}")

            return data

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else 'No error details'
        print(f"Warning: Failed to fetch {indicator_name}: {e.code} - {e.reason}", file=sys.stderr)
        print(f"  Details: {error_body}", file=sys.stderr)
        return []
    except urllib.error.URLError as e:
        print(f"Warning: Network error fetching {indicator_name}: {e.reason}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Warning: Unexpected error fetching {indicator_name}: {e}", file=sys.stderr)
        return []


def calculate_percentage_change(current: float, previous: float) -> Optional[float]:
    """
    Calculate percentage change between two values.

    Args:
        current: Current value
        previous: Previous value

    Returns:
        Percentage change or None if calculation not possible
    """
    if previous is None or current is None or previous == 0:
        return None
    return ((current - previous) / previous) * 100


def calculate_percentile(value: float, data_series: List[float]) -> int:
    """
    Calculate percentile rank of a value in a data series.

    Args:
        value: Value to rank
        data_series: List of values for comparison

    Returns:
        Percentile rank (0-100)
    """
    if not data_series or value is None:
        return 50  # Default to median if no data

    sorted_data = sorted(data_series)
    position = sum(1 for x in sorted_data if x <= value)
    percentile = int((position / len(sorted_data)) * 100)
    return percentile


def analyze_indicator_trend(data_points: List[Dict]) -> Dict[str, Any]:
    """
    Analyze trend for an economic indicator.

    Args:
        data_points: List of data points from FMP API

    Returns:
        Dictionary with trend analysis
    """
    if not data_points or len(data_points) == 0:
        return {
            'error': 'No data available',
            'available': False
        }

    # Sort by date (most recent first)
    sorted_data = sorted(data_points, key=lambda x: x.get('date', ''), reverse=True)

    # Get latest data point
    latest = sorted_data[0]
    latest_value = latest.get('value')
    latest_date = latest.get('date')

    if latest_value is None:
        return {
            'error': 'Latest value not available',
            'available': False
        }

    # Calculate changes
    yoy_change = None
    qoq_change = None
    mom_change = None

    # Year-over-year (12 months ago)
    if len(sorted_data) >= 13:
        yoy_previous = sorted_data[12].get('value')
        yoy_change = calculate_percentage_change(latest_value, yoy_previous)

    # Quarter-over-quarter (3 months ago)
    if len(sorted_data) >= 4:
        qoq_previous = sorted_data[3].get('value')
        qoq_change = calculate_percentage_change(latest_value, qoq_previous)

    # Month-over-month (1 month ago)
    if len(sorted_data) >= 2:
        mom_previous = sorted_data[1].get('value')
        mom_change = calculate_percentage_change(latest_value, mom_previous)

    # Calculate 5-year average (60 months)
    values_5yr = [dp.get('value') for dp in sorted_data[:60] if dp.get('value') is not None]
    avg_5yr = mean(values_5yr) if values_5yr else None

    # Calculate percentile (5-year context)
    percentile_5yr = calculate_percentile(latest_value, values_5yr)

    # Determine trend direction
    trend = 'stable'
    if yoy_change is not None:
        if yoy_change > 2:
            trend = 'accelerating'
        elif yoy_change < -2:
            trend = 'decelerating'
        else:
            trend = 'stable'

    # Check for inflection point (change in direction)
    inflection = False
    if len(sorted_data) >= 3:
        recent_changes = []
        for i in range(min(3, len(sorted_data) - 1)):
            curr_val = sorted_data[i].get('value')
            prev_val = sorted_data[i + 1].get('value')
            if curr_val is not None and prev_val is not None:
                change = curr_val - prev_val
                recent_changes.append(change)

        # Inflection if direction changes
        if len(recent_changes) >= 2:
            if (recent_changes[0] > 0 and recent_changes[1] < 0) or \
               (recent_changes[0] < 0 and recent_changes[1] > 0):
                inflection = True

    # Build historical series (last 20 data points)
    historical = []
    for dp in sorted_data[:20]:
        historical.append({
            'date': dp.get('date'),
            'value': dp.get('value')
        })

    return {
        'available': True,
        'latest': {
            'value': latest_value,
            'date': latest_date
        },
        'previous': {
            'value': sorted_data[1].get('value') if len(sorted_data) >= 2 else None,
            'date': sorted_data[1].get('date') if len(sorted_data) >= 2 else None
        },
        'changes': {
            'yoy': round(yoy_change, 2) if yoy_change is not None else None,
            'qoq': round(qoq_change, 2) if qoq_change is not None else None,
            'mom': round(mom_change, 2) if mom_change is not None else None
        },
        'context': {
            'avg_5yr': round(avg_5yr, 2) if avg_5yr is not None else None,
            'percentile_5yr': percentile_5yr
        },
        'trend': {
            'direction': trend,
            'inflection_point': inflection
        },
        'historical': historical
    }


def fetch_all_indicators(
    indicators: List[str],
    api_key: str,
    country: str = 'US'
) -> Dict[str, Any]:
    """
    Fetch and analyze multiple economic indicators.

    Args:
        indicators: List of indicator names to fetch
        api_key: FMP API key
        country: Country code (default: 'US')

    Returns:
        Dictionary with analyzed data for all indicators
    """
    results = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'country': country,
            'indicators_requested': indicators,
            'indicators_fetched': []
        },
        'indicators': {}
    }

    for indicator in indicators:
        if indicator not in SUPPORTED_INDICATORS:
            print(f"Warning: Unsupported indicator '{indicator}', skipping", file=sys.stderr)
            continue

        print(f"Fetching {indicator}...", file=sys.stderr)

        # Fetch raw data
        raw_data = fetch_economic_indicator(indicator, api_key, country)

        if not raw_data:
            print(f"  No data available for {indicator}", file=sys.stderr)
            results['indicators'][indicator] = {
                'metadata': SUPPORTED_INDICATORS[indicator],
                'analysis': {
                    'available': False,
                    'error': 'No data returned from API'
                }
            }
            continue

        # Analyze trend
        analysis = analyze_indicator_trend(raw_data)

        # Store results
        results['indicators'][indicator] = {
            'metadata': SUPPORTED_INDICATORS[indicator],
            'analysis': analysis
        }

        if analysis.get('available'):
            results['metadata']['indicators_fetched'].append(indicator)
            print(f"  ✓ {indicator}: {analysis['latest']['value']} ({analysis['latest']['date']})", file=sys.stderr)
        else:
            print(f"  ✗ {indicator}: {analysis.get('error', 'Unknown error')}", file=sys.stderr)

    return results


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Fetch macroeconomic indicators from FMP API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch default indicators (GDP, CPI, unemployment, retail sales, industrial production)
  python fetch_macro_data.py

  # Fetch specific indicators
  python fetch_macro_data.py --indicators GDP,CPI,unemployment

  # Fetch for specific country
  python fetch_macro_data.py --country US

  # Save to custom output file
  python fetch_macro_data.py --output my_macro_data.json

  # Provide API key via argument
  python fetch_macro_data.py --api-key YOUR_KEY_HERE
        """
    )

    # Indicator selection
    parser.add_argument(
        '--indicators',
        default=','.join(DEFAULT_INDICATORS),
        help=f'Comma-separated list of indicators to fetch (default: {",".join(DEFAULT_INDICATORS)}). ' +
             f'Available: {", ".join(SUPPORTED_INDICATORS.keys())}'
    )

    # Country
    parser.add_argument(
        '--country',
        default='US',
        help='Country code (default: US)'
    )

    # API key
    parser.add_argument(
        '--api-key', dest='api_key',
        help='FMP API key (overrides FMP_API_KEY environment variable)'
    )

    # Output file
    parser.add_argument(
        '--output', '-o',
        default='macro_data.json',
        help='Output file path (default: macro_data.json)'
    )

    # Lookback period (for documentation purposes, data availability depends on FMP API)
    parser.add_argument(
        '--lookback-years',
        type=int,
        default=5,
        help='Years of historical data to analyze (default: 5, actual availability depends on API)'
    )

    # Parse arguments
    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or get_api_key()
    if not api_key:
        print("Error: FMP API key is required. Set FMP_API_KEY environment variable or use --api-key",
              file=sys.stderr)
        sys.exit(1)

    # Parse indicators
    indicators = [i.strip() for i in args.indicators.split(',')]

    try:
        # Fetch and analyze indicators
        print(f"Fetching macroeconomic indicators for {args.country}...", file=sys.stderr)
        print(f"Requested indicators: {', '.join(indicators)}", file=sys.stderr)
        print(f"Lookback period: {args.lookback_years} years", file=sys.stderr)
        print("", file=sys.stderr)

        results = fetch_all_indicators(indicators, api_key, args.country)

        # Write output
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print("", file=sys.stderr)
        print(f"✓ Successfully fetched {len(results['metadata']['indicators_fetched'])} of {len(indicators)} indicators",
              file=sys.stderr)
        print(f"✓ Output written to {args.output}", file=sys.stderr)

        if len(results['metadata']['indicators_fetched']) < len(indicators):
            print("", file=sys.stderr)
            print("⚠ Some indicators could not be fetched. Check warnings above.", file=sys.stderr)
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
