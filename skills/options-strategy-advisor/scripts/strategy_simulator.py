#!/usr/bin/env python3
"""Options strategy construction, P/L simulation and position Greeks.

Builds on ``black_scholes.OptionPricer`` to model multi-leg strategies:
P/L at expiration, max profit/loss (including unlimited), exact breakevens,
lognormal probability of profit, aggregated position Greeks, mark-to-model
value before expiration (IV crush, calendars) and an ASCII P/L diagram.

Premiums are per share; P/L values are dollars for the whole position
(premium x 100 multiplier x quantity x contracts). ``T`` is years and
``r``/``sigma``/``q`` are annual decimals, as in ``black_scholes.py``.

Usage:
    from strategy_simulator import iron_condor, generate_pnl_diagram

    ic = iron_condor(S=100, K_put_long=90, K_put_short=95, K_call_short=105,
                     K_call_long=110, T=30/365, r=0.05, sigma=0.25, contracts=2)
    print(ic.summary(S=100, r=0.05, sigma=0.25))
    print(generate_pnl_diagram(ic, current_price=100))

Educational model only; not a trading recommendation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from black_scholes import OptionPricer
from scipy.stats import norm

CONTRACT_MULTIPLIER = 100
GREEK_KEYS = ("delta", "gamma", "theta", "vega", "rho")


def _option_value(S, K, T, r, sigma, q, option_type) -> float:
    """Black-Scholes value, or intrinsic value once the option has expired."""
    if T <= 0:
        return max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    pricer = OptionPricer(S, K, T, r, sigma, q)
    return float(pricer.call_price() if option_type == "call" else pricer.put_price())


def _option_greeks(S, K, T, r, sigma, q, option_type) -> dict[str, float]:
    if T <= 0:
        itm = (S > K) if option_type == "call" else (S < K)
        delta = (1.0 if option_type == "call" else -1.0) if itm else 0.0
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    g = OptionPricer(S, K, T, r, sigma, q).get_all_greeks(option_type)
    return {k: float(g[k]) for k in GREEK_KEYS}


def _money(v: float, decimals: int = 2) -> str:
    return f"{'-' if v < 0 else ''}${abs(v):,.{decimals}f}"


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class OptionLeg:
    option_type: str  # "call" or "put"
    strike: float
    position: str  # "long" or "short"
    premium: float  # per share, paid (long) or received (short)
    quantity: int = 1  # contracts per strategy unit
    expiry_T: float | None = None  # years to expiry (needed for Greeks / value_at)
    sigma: float | None = None  # leg-specific IV (optional)

    def __post_init__(self) -> None:
        self.option_type = self.option_type.lower()
        self.position = self.position.lower()
        if self.option_type not in ("call", "put"):
            raise ValueError("option_type must be 'call' or 'put'")
        if self.position not in ("long", "short"):
            raise ValueError("position must be 'long' or 'short'")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive; use position='short' for short legs")

    @property
    def sign(self) -> int:
        return 1 if self.position == "long" else -1

    def intrinsic(self, S: float) -> float:
        if self.option_type == "call":
            return max(0.0, S - self.strike)
        return max(0.0, self.strike - S)


@dataclass
class StockLeg:
    shares: int  # positive = long, negative = short
    cost_basis: float  # per share


@dataclass
class Strategy:
    name: str
    legs: list[OptionLeg]
    contracts: int = 1
    stock: StockLeg | None = None
    notes: list[str] = field(default_factory=list)

    # ----- basic quantities --------------------------------------------
    @property
    def _scale(self) -> int:
        return CONTRACT_MULTIPLIER * self.contracts

    @property
    def net_premium(self) -> float:
        """Net premium in dollars for the position. Positive = debit paid, negative = credit."""
        return sum(leg.sign * leg.premium * leg.quantity for leg in self.legs) * self._scale

    @property
    def is_single_expiry(self) -> bool:
        exps = {round(leg.expiry_T, 10) for leg in self.legs if leg.expiry_T is not None}
        return len(exps) <= 1

    def pnl_at_expiration(self, S_T: float) -> float:
        if not self.is_single_expiry:
            raise ValueError(
                f"{self.name} has legs with different expirations; use value_at(S, t_elapsed, ...) "
                "at the near-term expiration instead"
            )
        pnl = (
            sum(leg.sign * (leg.intrinsic(S_T) - leg.premium) * leg.quantity for leg in self.legs)
            * self._scale
        )
        if self.stock is not None:
            pnl += (S_T - self.stock.cost_basis) * self.stock.shares
        return pnl

    def pnl_curve(self, prices: Sequence[float]) -> np.ndarray:
        return np.array([self.pnl_at_expiration(float(p)) for p in prices])

    # ----- mark-to-model (before expiration / multi-expiry) -------------
    def value_at(self, S: float, t_elapsed: float, r: float, sigma: float, q: float = 0.0) -> float:
        """Theoretical P/L if the underlying is at S after ``t_elapsed`` years.

        Legs already expired are valued at intrinsic. Uses each leg's own sigma
        when set, otherwise ``sigma`` (pass a lower sigma to model IV crush).
        """
        pnl = 0.0
        for leg in self.legs:
            if leg.expiry_T is None:
                raise ValueError("value_at needs expiry_T on every leg")
            remaining = max(0.0, leg.expiry_T - t_elapsed)
            leg_sigma = leg.sigma if leg.sigma is not None else sigma
            val = _option_value(S, leg.strike, remaining, r, leg_sigma, q, leg.option_type)
            pnl += leg.sign * (val - leg.premium) * leg.quantity
        pnl *= self._scale
        if self.stock is not None:
            pnl += (S - self.stock.cost_basis) * self.stock.shares
        return pnl

    # ----- analytics -----------------------------------------------------
    def _kinks(self) -> list[float]:
        return sorted({0.0} | {leg.strike for leg in self.legs})

    def _right_slope(self) -> float:
        """dP/L / dS for S above every strike."""
        slope = (
            sum(leg.sign * leg.quantity for leg in self.legs if leg.option_type == "call")
            * self._scale
        )
        if self.stock is not None:
            slope += self.stock.shares
        return slope

    def breakevens(self) -> list[float]:
        kinks = self._kinks()
        far = max(kinks) * 10 + 1.0
        pts = kinks + [far]
        out: list[float] = []
        for a, b in zip(pts[:-1], pts[1:]):
            pa, pb = self.pnl_at_expiration(a), self.pnl_at_expiration(b)
            if abs(pa) < 1e-9 and a > 0:
                out.append(a)
            elif pa * pb < 0:
                out.append(a + (b - a) * (-pa) / (pb - pa))
        return sorted({round(x, 4) for x in out})

    def metrics(self) -> dict[str, object]:
        kinks = self._kinks()
        values = [self.pnl_at_expiration(k) for k in kinks]
        slope = self._right_slope()
        max_profit = math.inf if slope > 0 else max(values)
        max_loss = -math.inf if slope < 0 else min(values)
        rr = None
        if math.isfinite(max_profit) and math.isfinite(max_loss) and max_loss < 0:
            rr = max_profit / abs(max_loss)
        return {
            "net_premium": self.net_premium,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "breakevens": self.breakevens(),
            "reward_to_risk": rr,
        }

    def probability_of_profit(
        self, S: float, T: float, sigma: float, r: float = 0.0, q: float = 0.0
    ) -> float:
        """Probability P/L > 0 at expiration, lognormal S_T with drift (r - q).

        Uses the risk-neutral drift by default; it is a model estimate, not a forecast.
        """
        if T <= 0 or sigma <= 0:
            return 1.0 if self.pnl_at_expiration(S) > 0 else 0.0
        bounds = sorted(set([0.0] + self._kinks() + self.breakevens())) + [math.inf]
        mu = math.log(S) + (r - q - 0.5 * sigma**2) * T
        sd = sigma * math.sqrt(T)

        def cdf(x: float) -> float:
            if x <= 0:
                return 0.0
            if math.isinf(x):
                return 1.0
            return float(norm.cdf((math.log(x) - mu) / sd))

        prob = 0.0
        for a, b in zip(bounds[:-1], bounds[1:]):
            mid = (a + b) / 2 if math.isfinite(b) else a * 2 + 1
            if self.pnl_at_expiration(mid) > 0:
                prob += cdf(b) - cdf(a)
        return prob

    def range_profit_share(self, current_price: float, pct: float = 0.30, n: int = 601) -> float:
        """Simplified 'profit probability': share of a +/-pct price grid that is profitable."""
        grid = np.linspace(current_price * (1 - pct), current_price * (1 + pct), n)
        return float(np.mean(self.pnl_curve(grid) > 0))

    def position_greeks(self, S: float, r: float, sigma: float, q: float = 0.0) -> dict[str, float]:
        """Dollar-share Greeks for the whole position (delta in share-equivalents)."""
        tot = dict.fromkeys(GREEK_KEYS, 0.0)
        for leg in self.legs:
            if leg.expiry_T is None:
                raise ValueError("position_greeks needs expiry_T on every leg")
            leg_sigma = leg.sigma if leg.sigma is not None else sigma
            g = _option_greeks(S, leg.strike, leg.expiry_T, r, leg_sigma, q, leg.option_type)
            mult = leg.sign * leg.quantity * self._scale
            for k in tot:
                tot[k] += g[k] * mult
        if self.stock is not None:
            tot["delta"] += self.stock.shares
        return tot

    def summary(
        self, S: float, r: float | None = None, sigma: float | None = None, q: float = 0.0
    ) -> str:
        m = self.metrics() if self.is_single_expiry else None
        lines = [
            f"{self.name} ({self.contracts} contract{'s' if self.contracts != 1 else ''})",
            f"Current Price: ${S:,.2f}",
        ]
        for leg in self.legs:
            exp = f", {leg.expiry_T * 365:.0f} DTE" if leg.expiry_T is not None else ""
            lines.append(
                f"  {leg.position:>5} {leg.quantity}x {leg.strike:g} {leg.option_type} @ ${leg.premium:.2f}{exp}"
            )
        if self.stock is not None:
            lines.append(f"  stock {self.stock.shares:+d} sh @ ${self.stock.cost_basis:.2f}")
        np_ = self.net_premium
        lines.append(f"Net {'Debit' if np_ >= 0 else 'Credit'}: ${abs(np_):,.2f}")
        if m is not None:

            def fmt(v: float) -> str:
                return "Unlimited" if math.isinf(v) else _money(v)

            lines.append(f"Max Profit: {fmt(m['max_profit'])}")
            lines.append(f"Max Loss: {fmt(m['max_loss'])}")
            be = ", ".join(f"${b:,.2f}" for b in m["breakevens"]) or "none"
            lines.append(f"Breakeven(s): {be}")
            if m["reward_to_risk"] is not None:
                lines.append(f"Reward/Risk: {m['reward_to_risk']:.2f} : 1")
            lines.append(f"Profitable share of +/-30% range: {self.range_profit_share(S):.0%}")
            exps = [leg.expiry_T for leg in self.legs if leg.expiry_T]
            if sigma is not None and exps:
                pop = self.probability_of_profit(S, exps[0], sigma, r or 0.0, q)
                lines.append(f"Model probability of profit (lognormal): {pop:.0%}")
        else:
            lines.append(
                "Multi-expiration strategy: evaluate with value_at() at the near-term expiration."
            )
        if r is not None and sigma is not None:
            g = self.position_greeks(S, r, sigma, q)
            lines.append(
                "Position Greeks: "
                f"delta {g['delta']:+.1f} sh, gamma {g['gamma']:+.2f}, theta ${g['theta']:+.2f}/day, "
                f"vega ${g['vega']:+.2f}/vol pt, rho ${g['rho']:+.2f}/rate pt"
            )
        lines.extend(self.notes)
        return "\n".join(lines)


# --------------------------------------------------------------------------
# ASCII P/L diagram
# --------------------------------------------------------------------------
def generate_pnl_diagram(
    strategy: Strategy, current_price: float, pct: float = 0.30, width: int = 60, height: int = 15
) -> str:
    prices = np.linspace(current_price * (1 - pct), current_price * (1 + pct), width)
    pnl = strategy.pnl_curve(prices)
    lo, hi = float(min(pnl.min(), 0.0)), float(max(pnl.max(), 0.0))
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    rows = [[" "] * width for _ in range(height)]

    def row_of(v: float) -> int:
        return int(round((hi - v) / (hi - lo) * (height - 1)))

    zero_row = row_of(0.0)
    for c in range(width):
        rows[zero_row][c] = "-"
    cur_col = int(round((current_price - prices[0]) / (prices[-1] - prices[0]) * (width - 1)))
    for r_ in range(height):
        if rows[r_][cur_col] == " ":
            rows[r_][cur_col] = ":"
    for c, v in enumerate(pnl):
        rows[row_of(float(v))][c] = "+" if v > 0 else ("*" if v < 0 else "0")

    label_w = 12
    out = [f"P/L at expiration - {strategy.name}"]
    for i, row in enumerate(rows):
        val = hi - i * (hi - lo) / (height - 1)
        if i == zero_row:
            val = 0.0
        label = _money(val, 0) if i in (0, zero_row, height - 1) else ""
        out.append(f"{label:>{label_w}} |{''.join(row)}")
    out.append(" " * label_w + " +" + "-" * width)
    left, right = f"${prices[0]:,.0f}", f"${prices[-1]:,.0f}"
    mid = f"now ${current_price:,.0f}"
    pad = max(1, width - len(left) - len(right) - len(mid))
    out.append(" " * (label_w + 2) + left + " " * (pad // 2) + mid + " " * (pad - pad // 2) + right)
    out.append(" " * (label_w + 2) + "+ profit   * loss   : current price")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Builders (premiums priced with Black-Scholes unless given)
# --------------------------------------------------------------------------
def _leg(S, K, T, r, sigma, q, option_type, position, qty=1, premium=None) -> OptionLeg:
    if premium is None:
        pricer = OptionPricer(S, K, T, r, sigma, q)  # raises ValueError for T <= 0
        premium = float(pricer.call_price() if option_type == "call" else pricer.put_price())
    return OptionLeg(option_type, K, position, premium, qty, expiry_T=T)


def covered_call(S, K_call, T, r, sigma, q=0.0, contracts=1, cost_basis=None):
    return Strategy(
        "Covered Call",
        [_leg(S, K_call, T, r, sigma, q, "call", "short")],
        contracts,
        StockLeg(100 * contracts, S if cost_basis is None else cost_basis),
    )


def cash_secured_put(S, K_put, T, r, sigma, q=0.0, contracts=1):
    s = Strategy("Cash-Secured Put", [_leg(S, K_put, T, r, sigma, q, "put", "short")], contracts)
    s.notes.append(f"Cash reserved: ${K_put * 100 * contracts:,.2f}")
    return s


def protective_put(S, K_put, T, r, sigma, q=0.0, contracts=1, cost_basis=None):
    return Strategy(
        "Protective Put",
        [_leg(S, K_put, T, r, sigma, q, "put", "long")],
        contracts,
        StockLeg(100 * contracts, S if cost_basis is None else cost_basis),
    )


def collar(S, K_put, K_call, T, r, sigma, q=0.0, contracts=1, cost_basis=None):
    return Strategy(
        "Collar",
        [
            _leg(S, K_put, T, r, sigma, q, "put", "long"),
            _leg(S, K_call, T, r, sigma, q, "call", "short"),
        ],
        contracts,
        StockLeg(100 * contracts, S if cost_basis is None else cost_basis),
    )


def bull_call_spread(S, K_long, K_short, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Bull Call Spread {K_long:g}/{K_short:g}",
        [
            _leg(S, K_long, T, r, sigma, q, "call", "long"),
            _leg(S, K_short, T, r, sigma, q, "call", "short"),
        ],
        contracts,
    )


def bear_call_spread(S, K_short, K_long, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Bear Call Spread {K_short:g}/{K_long:g}",
        [
            _leg(S, K_short, T, r, sigma, q, "call", "short"),
            _leg(S, K_long, T, r, sigma, q, "call", "long"),
        ],
        contracts,
    )


def bull_put_spread(S, K_short, K_long, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Bull Put Spread {K_long:g}/{K_short:g}",
        [
            _leg(S, K_short, T, r, sigma, q, "put", "short"),
            _leg(S, K_long, T, r, sigma, q, "put", "long"),
        ],
        contracts,
    )


def bear_put_spread(S, K_long, K_short, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Bear Put Spread {K_short:g}/{K_long:g}",
        [
            _leg(S, K_long, T, r, sigma, q, "put", "long"),
            _leg(S, K_short, T, r, sigma, q, "put", "short"),
        ],
        contracts,
    )


def long_straddle(S, K, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Long Straddle {K:g}",
        [_leg(S, K, T, r, sigma, q, "call", "long"), _leg(S, K, T, r, sigma, q, "put", "long")],
        contracts,
    )


def short_straddle(S, K, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Short Straddle {K:g}",
        [_leg(S, K, T, r, sigma, q, "call", "short"), _leg(S, K, T, r, sigma, q, "put", "short")],
        contracts,
    )


def long_strangle(S, K_put, K_call, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Long Strangle {K_put:g}/{K_call:g}",
        [
            _leg(S, K_put, T, r, sigma, q, "put", "long"),
            _leg(S, K_call, T, r, sigma, q, "call", "long"),
        ],
        contracts,
    )


def short_strangle(S, K_put, K_call, T, r, sigma, q=0.0, contracts=1):
    return Strategy(
        f"Short Strangle {K_put:g}/{K_call:g}",
        [
            _leg(S, K_put, T, r, sigma, q, "put", "short"),
            _leg(S, K_call, T, r, sigma, q, "call", "short"),
        ],
        contracts,
    )


def iron_condor(
    S, K_put_long, K_put_short, K_call_short, K_call_long, T, r, sigma, q=0.0, contracts=1
):
    if not K_put_long < K_put_short <= K_call_short < K_call_long:
        raise ValueError("strikes must satisfy put_long < put_short <= call_short < call_long")
    return Strategy(
        f"Iron Condor {K_put_long:g}/{K_put_short:g}/{K_call_short:g}/{K_call_long:g}",
        [
            _leg(S, K_put_long, T, r, sigma, q, "put", "long"),
            _leg(S, K_put_short, T, r, sigma, q, "put", "short"),
            _leg(S, K_call_short, T, r, sigma, q, "call", "short"),
            _leg(S, K_call_long, T, r, sigma, q, "call", "long"),
        ],
        contracts,
    )


def iron_butterfly(S, K_center, wing, T, r, sigma, q=0.0, contracts=1):
    s = iron_condor(
        S, K_center - wing, K_center, K_center, K_center + wing, T, r, sigma, q, contracts
    )
    s.name = f"Iron Butterfly {K_center - wing:g}/{K_center:g}/{K_center + wing:g}"
    return s


def ratio_spread(
    S, K_long, K_short, T, r, sigma, q=0.0, option_type="call", long_qty=1, short_qty=2, contracts=1
):
    return Strategy(
        f"{option_type.title()} Ratio Spread {long_qty}x{K_long:g}/{short_qty}x{K_short:g}",
        [
            _leg(S, K_long, T, r, sigma, q, option_type, "long", long_qty),
            _leg(S, K_short, T, r, sigma, q, option_type, "short", short_qty),
        ],
        contracts,
    )


def calendar_spread(
    S,
    K,
    T_near,
    T_far,
    r,
    sigma,
    q=0.0,
    option_type="call",
    contracts=1,
    sigma_near=None,
    sigma_far=None,
):
    near = _leg(S, K, T_near, r, sigma_near or sigma, q, option_type, "short")
    far = _leg(S, K, T_far, r, sigma_far or sigma, q, option_type, "long")
    near.sigma, far.sigma = sigma_near, sigma_far
    return Strategy(f"{option_type.title()} Calendar {K:g}", [near, far], contracts)


def diagonal_spread(
    S, K_near, K_far, T_near, T_far, r, sigma, q=0.0, option_type="call", contracts=1
):
    return Strategy(
        f"{option_type.title()} Diagonal {K_far:g}/{K_near:g}",
        [
            _leg(S, K_near, T_near, r, sigma, q, option_type, "short"),
            _leg(S, K_far, T_far, r, sigma, q, option_type, "long"),
        ],
        contracts,
    )


def poor_mans_covered_call(S, K_leaps, K_short, T_leaps, T_short, r, sigma, q=0.0, contracts=1):
    s = diagonal_spread(S, K_short, K_leaps, T_short, T_leaps, r, sigma, q, "call", contracts)
    s.name = f"Poor Man's Covered Call {K_leaps:g} LEAPS / {K_short:g}"
    return s


def _demo() -> None:
    S = 180.0
    s = bull_call_spread(S, 180.0, 185.0, 30 / 365, 0.05, 0.25, contracts=10)
    print(s.summary(S, r=0.05, sigma=0.25))
    print()
    print(generate_pnl_diagram(s, S))
    print("\nFictional inputs; educational model only, not a trading recommendation.")


if __name__ == "__main__":
    _demo()
