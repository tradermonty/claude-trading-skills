#!/usr/bin/env python3
"""
Black-Scholes Options Pricing Engine

Calculates theoretical option prices and Greeks using Black-Scholes model.

Features:
- European call and put pricing
- All Greeks (Delta, Gamma, Theta, Vega, Rho)
- Historical volatility calculation from price data
- Dividend adjustment support

Usage:
    from black_scholes import OptionPricer

    pricer = OptionPricer(
        S=180,      # Stock price
        K=185,      # Strike price
        T=30/365,   # Time to expiration (years)
        r=0.053,    # Risk-free rate
        sigma=0.25, # Volatility
        q=0.01      # Dividend yield
    )

    call_price = pricer.call_price()
    delta = pricer.call_delta()

Author: Claude Trading Skills
Version: 1.0
"""

import importlib.util
import math
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
from scipy.stats import norm


class OptionPricer:
    """Black-Scholes option pricer with Greeks calculation"""

    def __init__(self, S, K, T, r, sigma, q=0):
        """
        Initialize pricer with option parameters

        Parameters:
        -----------
        S : float
            Current stock price
        K : float
            Strike price
        T : float
            Time to expiration in years (e.g., 30/365 for 30 days)
        r : float
            Risk-free interest rate (annual, e.g., 0.053 for 5.3%)
        sigma : float
            Volatility (annual, e.g., 0.25 for 25%)
        q : float, optional
            Continuous dividend yield (annual, default 0)
        """
        self.S = S
        self.K = K
        self.T = T
        self.r = r
        self.sigma = sigma
        self.q = q

        # Validate inputs
        if S <= 0:
            raise ValueError("Stock price must be positive")
        if K <= 0:
            raise ValueError("Strike price must be positive")
        if T <= 0:
            raise ValueError("Time to expiration must be positive")
        if sigma <= 0:
            raise ValueError("Volatility must be positive")

    def _d1(self):
        """Calculate d1 parameter"""
        numerator = np.log(self.S / self.K) + (self.r - self.q + 0.5 * self.sigma**2) * self.T
        denominator = self.sigma * np.sqrt(self.T)
        return numerator / denominator

    def _d2(self):
        """Calculate d2 parameter"""
        return self._d1() - self.sigma * np.sqrt(self.T)

    # =========================================================================
    # Option Pricing
    # =========================================================================

    def call_price(self):
        """Calculate European call option price"""
        d1 = self._d1()
        d2 = self._d2()

        price = self.S * np.exp(-self.q * self.T) * norm.cdf(d1) - self.K * np.exp(
            -self.r * self.T
        ) * norm.cdf(d2)

        return max(0, price)  # Price cannot be negative

    def put_price(self):
        """Calculate European put option price"""
        d1 = self._d1()
        d2 = self._d2()

        price = self.K * np.exp(-self.r * self.T) * norm.cdf(-d2) - self.S * np.exp(
            -self.q * self.T
        ) * norm.cdf(-d1)

        return max(0, price)

    # =========================================================================
    # Greeks - First Order
    # =========================================================================

    def call_delta(self):
        """
        Calculate call delta

        Delta: Change in option price per $1 change in stock price
        Range: 0 to 1 for calls
        """
        d1 = self._d1()
        return np.exp(-self.q * self.T) * norm.cdf(d1)

    def put_delta(self):
        """
        Calculate put delta

        Delta: Change in option price per $1 change in stock price
        Range: -1 to 0 for puts
        """
        d1 = self._d1()
        return np.exp(-self.q * self.T) * (norm.cdf(d1) - 1)

    def vega(self):
        """
        Calculate vega (same for calls and puts)

        Vega: Change in option price per 1% change in volatility
        Always positive (options gain value when volatility increases)
        """
        d1 = self._d1()
        vega = self.S * np.exp(-self.q * self.T) * norm.pdf(d1) * np.sqrt(self.T)
        return vega / 100  # Per 1% change in volatility

    def call_theta(self):
        """
        Calculate call theta

        Theta: Change in option price per day (time decay)
        Usually negative (options lose value as time passes)
        """
        d1 = self._d1()
        d2 = self._d2()

        term1 = (
            -self.S * norm.pdf(d1) * self.sigma * np.exp(-self.q * self.T) / (2 * np.sqrt(self.T))
        )
        term2 = -self.r * self.K * np.exp(-self.r * self.T) * norm.cdf(d2)
        term3 = self.q * self.S * norm.cdf(d1) * np.exp(-self.q * self.T)

        theta_annual = term1 + term2 + term3
        return theta_annual / 365  # Convert to per-day

    def put_theta(self):
        """Calculate put theta"""
        d1 = self._d1()
        d2 = self._d2()

        term1 = (
            -self.S * norm.pdf(d1) * self.sigma * np.exp(-self.q * self.T) / (2 * np.sqrt(self.T))
        )
        term2 = self.r * self.K * np.exp(-self.r * self.T) * norm.cdf(-d2)
        term3 = -self.q * self.S * norm.cdf(-d1) * np.exp(-self.q * self.T)

        theta_annual = term1 + term2 + term3
        return theta_annual / 365

    def call_rho(self):
        """
        Calculate call rho

        Rho: Change in option price per 1% change in interest rate
        Positive for calls (calls gain value when rates increase)
        """
        d2 = self._d2()
        rho = self.K * self.T * np.exp(-self.r * self.T) * norm.cdf(d2)
        return rho / 100  # Per 1% change

    def put_rho(self):
        """
        Calculate put rho

        Rho: Change in option price per 1% change in interest rate
        Negative for puts (puts lose value when rates increase)
        """
        d2 = self._d2()
        rho = -self.K * self.T * np.exp(-self.r * self.T) * norm.cdf(-d2)
        return rho / 100

    # =========================================================================
    # Greeks - Second Order
    # =========================================================================

    def gamma(self):
        """
        Calculate gamma (same for calls and puts)

        Gamma: Change in delta per $1 change in stock price
        Shows how fast delta changes
        Highest for ATM options, lower for OTM and ITM
        """
        d1 = self._d1()
        gamma = (np.exp(-self.q * self.T) * norm.pdf(d1)) / (self.S * self.sigma * np.sqrt(self.T))
        return gamma

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def intrinsic_value(self, option_type="call"):
        """Calculate intrinsic value"""
        if option_type.lower() == "call":
            return max(0, self.S - self.K)
        else:  # put
            return max(0, self.K - self.S)

    def time_value(self, option_type="call"):
        """Calculate time value (extrinsic value)"""
        if option_type.lower() == "call":
            price = self.call_price()
        else:
            price = self.put_price()

        intrinsic = self.intrinsic_value(option_type)
        return price - intrinsic

    def moneyness(self):
        """
        Determine moneyness

        Returns: 'ITM', 'ATM', or 'OTM'
        """
        ratio = self.S / self.K

        if abs(ratio - 1.0) < 0.02:  # Within 2%
            return "ATM"
        elif ratio > 1.0:
            return "ITM (Call) / OTM (Put)"
        else:
            return "OTM (Call) / ITM (Put)"

    def get_all_greeks(self, option_type="call"):
        """
        Get all Greeks for an option

        Returns: dict with all Greeks
        """
        if option_type.lower() == "call":
            return {
                "price": self.call_price(),
                "delta": self.call_delta(),
                "gamma": self.gamma(),
                "theta": self.call_theta(),
                "vega": self.vega(),
                "rho": self.call_rho(),
                "intrinsic_value": self.intrinsic_value("call"),
                "time_value": self.time_value("call"),
            }
        else:
            return {
                "price": self.put_price(),
                "delta": self.put_delta(),
                "gamma": self.gamma(),
                "theta": self.put_theta(),
                "vega": self.vega(),
                "rho": self.put_rho(),
                "intrinsic_value": self.intrinsic_value("put"),
                "time_value": self.time_value("put"),
            }


# =============================================================================
# Historical Volatility Calculator
# =============================================================================


def calculate_historical_volatility(prices, window=30):
    """
    Calculate historical volatility from price data

    Parameters:
    -----------
    prices : array-like
        Historical prices (daily)
    window : int
        Lookback window in days (default 30)

    Returns:
    --------
    float
        Annualized historical volatility
    """
    if len(prices) < window + 1:
        raise ValueError(f"Need at least {window + 1} price points")

    # Calculate log returns
    prices = np.array(prices)
    log_returns = np.log(prices[1:] / prices[:-1])

    # Use most recent 'window' returns
    recent_returns = log_returns[-window:]

    # Annualized volatility (252 trading days)
    volatility = np.std(recent_returns) * np.sqrt(252)

    return volatility


def _client_class():
    """Load this skill's generated client even when another fmp_client is cached."""
    name = "_options_strategy_advisor_generated_fmp"
    path = Path(__file__).resolve().with_name("fmp_client.py")
    module = sys.modules.get(name)
    if module is None or getattr(module, "__file__", None) != str(path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return module.FMPClient


def _symbol(value):
    return value.strip().upper().replace("-", ".") if isinstance(value, str) else ""


def _number(value, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and (result >= 0 if zero else result > 0) else None


def _fetch_options_data(kind, symbol, api_key):
    """One owned client per public helper call; never echo untrusted exceptions."""
    if not _symbol(symbol) or not isinstance(api_key, str) or not api_key.strip():
        return None
    client = None
    data = None
    try:
        client = _client_class()(api_key=api_key)
        data = getattr(client, "fetch_options_" + kind)(symbol.strip().upper())
    except Exception:
        data = None
    finally:
        if client is not None:
            try:
                client.session.close()
            except Exception:
                data = None
    return data


def _history_rows(data, symbol):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    if data.get("symbol") is not None and _symbol(data["symbol"]) != _symbol(symbol):
        return None
    if "historicalStockList" in data:
        if "historical" in data or not isinstance(data["historicalStockList"], list):
            return None
        entries = data["historicalStockList"]
        if any(not isinstance(entry, dict) for entry in entries):
            return None
        matches = [entry for entry in entries if _symbol(entry.get("symbol")) == _symbol(symbol)]
        return _history_rows(matches[0], symbol) if len(matches) == 1 else None
    rows = data.get("historical")
    return rows if isinstance(rows, list) else None


def fetch_historical_prices_for_hv(symbol, api_key, days=90, *, as_of=None):
    """Return newest requested sessions oldest first, or None when unusable.

    Use adjClose only when consistently supplied for selected rows. Otherwise
    use provider close without certifying its adjustment basis. No mixed basis,
    duplicate consumed dates, future sessions or fabricated prices are accepted.
    """
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError("days must be a positive integer")
    today = date.today() if as_of is None else as_of
    if not isinstance(today, date) or isinstance(today, datetime):
        raise ValueError("as_of must be a date")
    rows = _history_rows(_fetch_options_data("history", symbol, api_key), symbol)
    parsed = []
    valid = bool(rows)
    for row in rows or []:
        if not isinstance(row, dict):
            valid = False
            break
        if row.get("symbol") is not None and _symbol(row["symbol"]) != _symbol(symbol):
            valid = False
            break
        value = row.get("date")
        try:
            day = date.fromisoformat(value)
        except (TypeError, ValueError):
            valid = False
            break
        if not isinstance(value, str) or day.isoformat() != value:
            valid = False
            break
        if day <= today:
            parsed.append((day, row))
    selected = sorted(parsed, key=lambda item: item[0], reverse=True)[:days]
    if valid and selected and len({day for day, _ in selected}) == len(selected):
        adjusted = any(row.get("adjClose") is not None for _, row in selected)
        field = "adjClose" if adjusted else "close"
        prices = [_number(row.get(field)) for _, row in reversed(selected)]
        if all(price is not None for price in prices):
            return prices
    print("Error fetching price history: usable FMP evidence unavailable", file=sys.stderr)
    return None


def _single_record(data, symbol):
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        return None
    return data[0] if _symbol(data[0].get("symbol")) == _symbol(symbol) else None


def get_current_stock_price(symbol, api_key):
    """Return finite positive stable quote evidence, or None (no legacy HTTP)."""
    record = _single_record(_fetch_options_data("quote", symbol, api_key), symbol)
    price = _number(record.get("price")) if record is not None else None
    if price is None:
        print("Error fetching current price: usable FMP evidence unavailable", file=sys.stderr)
    return price


def get_dividend_yield(symbol, api_key):
    """Return trailing profile yield; unavailable evidence retains a warned zero fallback."""
    record = _single_record(_fetch_options_data("profile", symbol, api_key), symbol)
    if record is not None:
        value = record.get("lastDividend")
        if value is None:
            value = record.get("lastDiv")
        dividend = _number(value, zero=True)
        price = _number(record.get("price"))
        if dividend is not None and price is not None:
            result = dividend / price
            if math.isfinite(result):
                return result
    print(
        "Dividend yield unavailable: unverified legacy zero fallback; supply q explicitly",
        file=sys.stderr,
    )
    return 0.0


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("BLACK-SCHOLES OPTIONS PRICER - EXAMPLE")
    print("=" * 70)

    # Example parameters
    stock_price = 180.00
    strike_price = 185.00
    days_to_expiration = 30
    time_to_expiration = days_to_expiration / 365
    risk_free_rate = 0.053  # 5.3%
    volatility = 0.25  # 25%
    dividend_yield = 0.01  # 1%

    print("\nInput Parameters:")
    print(f"  Stock Price: ${stock_price:.2f}")
    print(f"  Strike Price: ${strike_price:.2f}")
    print(f"  Days to Expiration: {days_to_expiration}")
    print(f"  Volatility: {volatility * 100:.1f}%")
    print(f"  Risk-Free Rate: {risk_free_rate * 100:.2f}%")
    print(f"  Dividend Yield: {dividend_yield * 100:.1f}%")

    # Create pricer
    pricer = OptionPricer(
        S=stock_price,
        K=strike_price,
        T=time_to_expiration,
        r=risk_free_rate,
        sigma=volatility,
        q=dividend_yield,
    )

    # Call option
    print(f"\n{'=' * 70}")
    print("CALL OPTION")
    print("=" * 70)

    call_greeks = pricer.get_all_greeks("call")
    print(f"Price: ${call_greeks['price']:.2f}")
    print(f"Intrinsic Value: ${call_greeks['intrinsic_value']:.2f}")
    print(f"Time Value: ${call_greeks['time_value']:.2f}")
    print("\nGreeks:")
    print(f"  Delta: {call_greeks['delta']:.4f} (${call_greeks['delta'] * 100:.2f} per $1 move)")
    print(f"  Gamma: {call_greeks['gamma']:.4f} (delta changes by {call_greeks['gamma']:.4f})")
    print(
        f"  Theta: ${call_greeks['theta']:.2f}/day (loses ${abs(call_greeks['theta']):.2f} per day)"
    )
    print(
        f"  Vega: ${call_greeks['vega']:.2f} per 1% IV (gains ${call_greeks['vega']:.2f} if IV +1%)"
    )
    print(
        f"  Rho: ${call_greeks['rho']:.2f} per 1% rate (gains ${call_greeks['rho']:.2f} if rate +1%)"
    )

    # Put option
    print(f"\n{'=' * 70}")
    print("PUT OPTION")
    print("=" * 70)

    put_greeks = pricer.get_all_greeks("put")
    print(f"Price: ${put_greeks['price']:.2f}")
    print(f"Intrinsic Value: ${put_greeks['intrinsic_value']:.2f}")
    print(f"Time Value: ${put_greeks['time_value']:.2f}")
    print("\nGreeks:")
    print(f"  Delta: {put_greeks['delta']:.4f} (${put_greeks['delta'] * 100:.2f} per $1 move)")
    print(f"  Gamma: {put_greeks['gamma']:.4f} (delta changes by {put_greeks['gamma']:.4f})")
    print(
        f"  Theta: ${put_greeks['theta']:.2f}/day (loses ${abs(put_greeks['theta']):.2f} per day)"
    )
    print(
        f"  Vega: ${put_greeks['vega']:.2f} per 1% IV (gains ${put_greeks['vega']:.2f} if IV +1%)"
    )
    print(
        f"  Rho: ${put_greeks['rho']:.2f} per 1% rate (loses ${abs(put_greeks['rho']):.2f} if rate +1%)"
    )

    # Moneyness
    print(f"\n{'=' * 70}")
    print(f"Moneyness: {pricer.moneyness()}")
    print("=" * 70 + "\n")

    # Historical Volatility Example
    print("\nHistorical Volatility Example:")
    print("-" * 70)

    # Simulate price data
    np.random.seed(42)
    simulated_prices = [180 * np.exp(np.sum(np.random.randn(i) * 0.01)) for i in range(90)]

    hv = calculate_historical_volatility(simulated_prices, window=30)
    print(f"30-Day Historical Volatility: {hv * 100:.2f}%")
    print(f"Implied Volatility (input): {volatility * 100:.1f}%")

    if hv < volatility:
        print("→ IV > HV: Options may be expensive (consider selling premium)")
    elif hv > volatility:
        print("→ IV < HV: Options may be cheap (consider buying)")
    else:
        print("→ IV ≈ HV: Options fairly priced")

    print("\n" + "=" * 70 + "\n")
