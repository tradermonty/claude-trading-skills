#!/usr/bin/env python3
"""
Test script for Alpaca API connection.

This script verifies that Alpaca API credentials are correctly configured
and tests basic API functionality.

Usage:
    python3 check_alpaca_connection.py

Environment Variables:
    ALPACA_API_KEY: Your Alpaca API Key ID
    ALPACA_SECRET_KEY: Your Alpaca Secret Key
    ALPACA_PAPER: Set to 'true' for paper trading, 'false' for live (default: true)
"""

import os
import sys

try:
    import requests
except ImportError:
    from pathlib import Path as _Path

    print(
        "ERROR: requests library not found. Install this skill's dependencies: "
        f"pip install -r {_Path(__file__).resolve().parents[1] / 'requirements.txt'}",
        file=sys.stderr,
    )
    sys.exit(2)

REQUEST_TIMEOUT_SECONDS = 30


def load_credentials():
    """Load Alpaca API credentials from environment variables."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if not api_key or not secret_key:
        print("ERROR: Alpaca API credentials not found", file=sys.stderr)
        print("\nPlease set environment variables:", file=sys.stderr)
        print(
            "  export ALPACA_API_KEY='your_api_key_id'",  # pragma: allowlist secret
            file=sys.stderr,
        )
        print(
            "  export ALPACA_SECRET_KEY='your_secret_key'",  # pragma: allowlist secret
            file=sys.stderr,
        )
        print("  export ALPACA_PAPER='true'  # or 'false' for live trading", file=sys.stderr)
        print("\nOr add to your shell config file (~/.bashrc or ~/.zshrc):", file=sys.stderr)
        print("  echo 'export ALPACA_API_KEY=\"your_key\"' >> ~/.bashrc", file=sys.stderr)
        print("  echo 'export ALPACA_SECRET_KEY=\"your_secret\"' >> ~/.bashrc", file=sys.stderr)
        print("  echo 'export ALPACA_PAPER=\"true\"' >> ~/.bashrc", file=sys.stderr)
        print("  source ~/.bashrc", file=sys.stderr)
        sys.exit(1)

    return api_key, secret_key, paper


def get_base_url(paper=True):
    """Get appropriate Alpaca API base URL."""
    if paper:
        return "https://paper-api.alpaca.markets"
    return "https://api.alpaca.markets"


def mask_identifier(value):
    """Mask an account identifier while preserving its final four characters."""
    text = str(value or "")
    if not text:
        return "N/A"
    return f"****{text[-4:]}"


def require_object(payload, required_fields, label):
    """Validate an API object without echoing its potentially sensitive content."""
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    missing = required_fields - payload.keys()
    if missing:
        raise ValueError(f"{label} is missing required fields")
    return payload


def test_account_info(api_key, secret_key, base_url):
    """Test account information endpoint."""
    print("\n" + "=" * 60)
    print("Testing Alpaca Account API Connection")
    print("=" * 60)

    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}

    try:
        response = requests.get(
            f"{base_url}/v2/account",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code == 200:
            account = require_object(
                response.json(),
                {
                    "status",
                    "account_number",
                    "equity",
                    "cash",
                    "buying_power",
                    "portfolio_value",
                },
                "account response",
            )
            print("✓ Successfully connected to Alpaca API\n")
            print(f"Account Status: {account.get('status')}")
            print(f"Account Number: {mask_identifier(account.get('account_number'))}")
            print(f"Equity: ${float(account.get('equity', 0)):,.2f}")
            print(f"Cash: ${float(account.get('cash', 0)):,.2f}")
            print(f"Buying Power: ${float(account.get('buying_power', 0)):,.2f}")
            print(f"Portfolio Value: ${float(account.get('portfolio_value', 0)):,.2f}")

            # Check if account is restricted
            if account.get("account_blocked") or account.get("trading_blocked"):
                print("\n⚠ WARNING: Account has restrictions")
                if account.get("account_blocked"):
                    print("  - Account is blocked")
                if account.get("trading_blocked"):
                    print("  - Trading is blocked")

            return True

        elif response.status_code == 401:
            print("✗ Authentication failed")
            print("\nPossible causes:")
            print("  1. Invalid API credentials")
            print("  2. Using paper trading keys with live URL (or vice versa)")
            print("  3. API keys have been revoked")
            print("\nSolutions:")
            print("  1. Verify API Key ID and Secret Key in Alpaca dashboard")
            print("  2. Check ALPACA_PAPER environment variable matches your keys")
            print("  3. Regenerate API keys if needed")
            return False

        elif response.status_code == 403:
            print("✗ Forbidden - insufficient permissions")
            print("\nPossible causes:")
            print("  1. API keys don't have required permissions")
            print("  2. Account not approved for trading")
            print("\nSolutions:")
            print("  1. Regenerate API keys with full permissions")
            print("  2. Complete account approval process in Alpaca dashboard")
            return False

        else:
            print(f"✗ Unexpected error: HTTP {response.status_code}")
            return False

    except requests.exceptions.RequestException:
        print("✗ Network error while contacting Alpaca Account API")
        print("\nPossible causes:")
        print("  1. No internet connection")
        print("  2. Alpaca API is down (check status.alpaca.markets)")
        print("  3. Firewall blocking connection")
        return False
    except (TypeError, ValueError):
        print("✗ Invalid or malformed response from Alpaca Account API")
        return False


def test_positions(api_key, secret_key, base_url):
    """Test positions endpoint."""
    print("\n" + "=" * 60)
    print("Testing Positions API")
    print("=" * 60)

    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}

    try:
        response = requests.get(
            f"{base_url}/v2/positions",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code == 200:
            positions = response.json()
            if not isinstance(positions, list):
                raise ValueError("positions response must be a list")

            if len(positions) == 0:
                print("✓ API connection successful")
                print("Portfolio is empty (no positions)")
            else:
                print("✓ API connection successful")
                print(f"Found {len(positions)} position(s):\n")

                total_value = 0
                total_pl = 0

                for pos in positions:
                    pos = require_object(
                        pos,
                        {
                            "symbol",
                            "qty",
                            "avg_entry_price",
                            "current_price",
                            "market_value",
                            "unrealized_pl",
                            "unrealized_plpc",
                        },
                        "position",
                    )
                    symbol = pos.get("symbol")
                    qty = float(pos.get("qty", 0))
                    avg_price = float(pos.get("avg_entry_price", 0))
                    current_price = float(pos.get("current_price", 0))
                    market_value = float(pos.get("market_value", 0))
                    unrealized_pl = float(pos.get("unrealized_pl", 0))
                    unrealized_plpc = float(pos.get("unrealized_plpc", 0)) * 100

                    total_value += market_value
                    total_pl += unrealized_pl

                    pl_sign = "+" if unrealized_pl >= 0 else ""

                    print(f"{symbol}:")
                    print(f"  Quantity: {qty:.2f} shares")
                    print(f"  Avg Entry: ${avg_price:.2f}")
                    print(f"  Current Price: ${current_price:.2f}")
                    print(f"  Market Value: ${market_value:,.2f}")
                    print(
                        f"  Unrealized P/L: {pl_sign}${unrealized_pl:,.2f} ({pl_sign}{unrealized_plpc:.2f}%)"
                    )
                    print()

                print(f"Total Portfolio Value: ${total_value:,.2f}")
                print(f"Total Unrealized P/L: ${total_pl:,.2f}")

            return True

        else:
            print(f"✗ Error fetching positions: HTTP {response.status_code}", file=sys.stderr)
            return False

    except requests.exceptions.RequestException:
        print("✗ Network error while contacting Alpaca Positions API")
        return False
    except (TypeError, ValueError):
        print("✗ Invalid or malformed response from Alpaca Positions API")
        return False


def test_market_data(api_key, secret_key):
    """Test market data API (optional)."""
    print("\n" + "=" * 60)
    print("Testing Market Data API (Optional)")
    print("=" * 60)

    # Market data uses different base URL
    base_url = "https://data.alpaca.markets"

    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}

    # Test with a simple quote request for AAPL
    try:
        response = requests.get(
            f"{base_url}/v2/stocks/AAPL/quotes/latest",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code == 200:
            payload = require_object(response.json(), {"quote"}, "market data response")
            quote = require_object(payload["quote"], {"bp", "ap"}, "market quote")
            print("✓ Market data API accessible")
            print(f"Sample quote (AAPL): Bid ${quote['bp']:.2f}, Ask ${quote['ap']:.2f}")
        elif response.status_code == 402:
            print("⚠ Market data requires paid subscription")
            print("  Free tier provides delayed data only")
            print("  This is normal for free accounts")
        else:
            print(f"⚠ Market data API returned HTTP {response.status_code}")
            print("  This won't affect portfolio management functionality")

    except requests.exceptions.RequestException:
        print("⚠ Could not contact the market data API")
        print("  This won't affect portfolio management functionality")
    except (TypeError, ValueError):
        print("⚠ Market data API returned invalid or malformed data")
        print("  This won't affect portfolio management functionality")


def main():
    """Main test function."""
    print("Alpaca API Connection Test")
    print("=" * 60)

    # Load credentials
    api_key, secret_key, paper = load_credentials()
    base_url = get_base_url(paper)

    mode = "PAPER TRADING" if paper else "LIVE TRADING"
    print(f"\nMode: {mode}")
    print(f"Base URL: {base_url}")

    # Run tests
    success = True

    # Test 1: Account info
    if not test_account_info(api_key, secret_key, base_url):
        success = False

    # Test 2: Positions (only if account test passed)
    if success:
        if not test_positions(api_key, secret_key, base_url):
            success = False

    # Test 3: Market data (optional, doesn't affect overall success)
    test_market_data(api_key, secret_key)

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    if success:
        print("✓ All tests passed successfully")
        print("\nYour Alpaca API connection is properly configured.")
        print("The Portfolio Manager skill should work correctly.")
        print("\nNext steps:")
        print("  1. Use Portfolio Manager skill in Claude: 'Analyze my portfolio'")
        print("  2. Review the generated portfolio analysis report")
        print("  3. Follow rebalancing recommendations if provided")
        return 0
    else:
        print("✗ Some tests failed")
        print("\nPlease review the errors above and:")
        print("  1. Verify your API credentials are correct")
        print("  2. Check that ALPACA_PAPER setting matches your API keys")
        print("  3. Ensure your Alpaca account is active and approved")
        print("  4. Check Alpaca API status: https://status.alpaca.markets/")
        print("\nFor help, see: portfolio-manager/references/alpaca-mcp-setup.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
