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

import numpy as np
from scipy.stats import norm
import requests
import os
from datetime import datetime, timedelta


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

        price = (self.S * np.exp(-self.q * self.T) * norm.cdf(d1) -
                 self.K * np.exp(-self.r * self.T) * norm.cdf(d2))

        return max(0, price)  # Price cannot be negative

    def put_price(self):
        """Calculate European put option price"""
        d1 = self._d1()
        d2 = self._d2()

        price = (self.K * np.exp(-self.r * self.T) * norm.cdf(-d2) -
                 self.S * np.exp(-self.q * self.T) * norm.cdf(-d1))

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

        term1 = -self.S * norm.pdf(d1) * self.sigma * np.exp(-self.q * self.T) / (2 * np.sqrt(self.T))
        term2 = -self.r * self.K * np.exp(-self.r * self.T) * norm.cdf(d2)
        term3 = self.q * self.S * norm.cdf(d1) * np.exp(-self.q * self.T)

        theta_annual = term1 + term2 + term3
        return theta_annual / 365  # Convert to per-day

    def put_theta(self):
        """Calculate put theta"""
        d1 = self._d1()
        d2 = self._d2()

        term1 = -self.S * norm.pdf(d1) * self.sigma * np.exp(-self.q * self.T) / (2 * np.sqrt(self.T))
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

    def intrinsic_value(self, option_type='call'):
        """Calculate intrinsic value"""
        if option_type.lower() == 'call':
            return max(0, self.S - self.K)
        else:  # put
            return max(0, self.K - self.S)

    def time_value(self, option_type='call'):
        """Calculate time value (extrinsic value)"""
        if option_type.lower() == 'call':
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
            return 'ATM'
        elif ratio > 1.0:
            return 'ITM (Call) / OTM (Put)'
        else:
            return 'OTM (Call) / ITM (Put)'

    def get_all_greeks(self, option_type='call'):
        """
        Get all Greeks for an option

        Returns: dict with all Greeks
        """
        if option_type.lower() == 'call':
            return {
                'price': self.call_price(),
                'delta': self.call_delta(),
                'gamma': self.gamma(),
                'theta': self.call_theta(),
                'vega': self.vega(),
                'rho': self.call_rho(),
                'intrinsic_value': self.intrinsic_value('call'),
                'time_value': self.time_value('call')
            }
        else:
            return {
                'price': self.put_price(),
                'delta': self.put_delta(),
                'gamma': self.gamma(),
                'theta': self.put_theta(),
                'vega': self.vega(),
                'rho': self.put_rho(),
                'intrinsic_value': self.intrinsic_value('put'),
                'time_value': self.time_value('put')
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


def fetch_historical_prices_for_hv(symbol, api_key, days=90):
    """
    Fetch historical prices from FMP API for HV calculation

    Parameters:
    -----------
    symbol : str
        Stock ticker
    api_key : str
        FMP API key
    days : int
        Number of days to fetch

    Returns:
    --------
    list
        List of adjusted close prices
    """
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
    params = {'apikey': api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'historical' not in data:
            return None

        # Get most recent 'days' of data
        historical = data['historical'][:days]
        historical = historical[::-1]  # Reverse to chronological order

        prices = [item['adjClose'] for item in historical]
        return prices

    except Exception as e:
        print(f"Error fetching prices for {symbol}: {e}")
        return None


# =============================================================================
# FMP API Integration
# =============================================================================

def get_current_stock_price(symbol, api_key):
    """Fetch current stock price from FMP API"""
    url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
    params = {'apikey': api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data and len(data) > 0:
            return data[0]['price']
        return None

    except Exception as e:
        print(f"Error fetching current price for {symbol}: {e}")
        return None


def get_dividend_yield(symbol, api_key):
    """Fetch dividend yield from FMP API"""
    url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
    params = {'apikey': api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data and len(data) > 0:
            # Last annual dividend / current price
            last_div = data[0].get('lastDiv', 0)
            price = data[0].get('price', 1)
            div_yield = (last_div / price) if price > 0 else 0
            return div_yield

        return 0

    except Exception:
        return 0


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == '__main__':
    print("\n" + "="*70)
    print("BLACK-SCHOLES OPTIONS PRICER - EXAMPLE")
    print("="*70)

    # Example parameters
    stock_price = 180.00
    strike_price = 185.00
    days_to_expiration = 30
    time_to_expiration = days_to_expiration / 365
    risk_free_rate = 0.053  # 5.3%
    volatility = 0.25  # 25%
    dividend_yield = 0.01  # 1%

    print(f"\nInput Parameters:")
    print(f"  Stock Price: ${stock_price:.2f}")
    print(f"  Strike Price: ${strike_price:.2f}")
    print(f"  Days to Expiration: {days_to_expiration}")
    print(f"  Volatility: {volatility*100:.1f}%")
    print(f"  Risk-Free Rate: {risk_free_rate*100:.2f}%")
    print(f"  Dividend Yield: {dividend_yield*100:.1f}%")

    # Create pricer
    pricer = OptionPricer(
        S=stock_price,
        K=strike_price,
        T=time_to_expiration,
        r=risk_free_rate,
        sigma=volatility,
        q=dividend_yield
    )

    # Call option
    print(f"\n{'='*70}")
    print("CALL OPTION")
    print("="*70)

    call_greeks = pricer.get_all_greeks('call')
    print(f"Price: ${call_greeks['price']:.2f}")
    print(f"Intrinsic Value: ${call_greeks['intrinsic_value']:.2f}")
    print(f"Time Value: ${call_greeks['time_value']:.2f}")
    print(f"\nGreeks:")
    print(f"  Delta: {call_greeks['delta']:.4f} (${call_greeks['delta']*100:.2f} per $1 move)")
    print(f"  Gamma: {call_greeks['gamma']:.4f} (delta changes by {call_greeks['gamma']:.4f})")
    print(f"  Theta: ${call_greeks['theta']:.2f}/day (loses ${abs(call_greeks['theta']):.2f} per day)")
    print(f"  Vega: ${call_greeks['vega']:.2f} per 1% IV (gains ${call_greeks['vega']:.2f} if IV +1%)")
    print(f"  Rho: ${call_greeks['rho']:.2f} per 1% rate (gains ${call_greeks['rho']:.2f} if rate +1%)")

    # Put option
    print(f"\n{'='*70}")
    print("PUT OPTION")
    print("="*70)

    put_greeks = pricer.get_all_greeks('put')
    print(f"Price: ${put_greeks['price']:.2f}")
    print(f"Intrinsic Value: ${put_greeks['intrinsic_value']:.2f}")
    print(f"Time Value: ${put_greeks['time_value']:.2f}")
    print(f"\nGreeks:")
    print(f"  Delta: {put_greeks['delta']:.4f} (${put_greeks['delta']*100:.2f} per $1 move)")
    print(f"  Gamma: {put_greeks['gamma']:.4f} (delta changes by {put_greeks['gamma']:.4f})")
    print(f"  Theta: ${put_greeks['theta']:.2f}/day (loses ${abs(put_greeks['theta']):.2f} per day)")
    print(f"  Vega: ${put_greeks['vega']:.2f} per 1% IV (gains ${put_greeks['vega']:.2f} if IV +1%)")
    print(f"  Rho: ${put_greeks['rho']:.2f} per 1% rate (loses ${abs(put_greeks['rho']):.2f} if rate +1%)")

    # Moneyness
    print(f"\n{'='*70}")
    print(f"Moneyness: {pricer.moneyness()}")
    print("="*70 + "\n")

    # Historical Volatility Example
    print("\nHistorical Volatility Example:")
    print("-" * 70)

    # Simulate price data
    np.random.seed(42)
    simulated_prices = [180 * np.exp(np.sum(np.random.randn(i) * 0.01)) for i in range(90)]

    hv = calculate_historical_volatility(simulated_prices, window=30)
    print(f"30-Day Historical Volatility: {hv*100:.2f}%")
    print(f"Implied Volatility (input): {volatility*100:.1f}%")

    if hv < volatility:
        print(f"→ IV > HV: Options may be expensive (consider selling premium)")
    elif hv > volatility:
        print(f"→ IV < HV: Options may be cheap (consider buying)")
    else:
        print(f"→ IV ≈ HV: Options fairly priced")

    print("\n" + "="*70 + "\n")
