"""Tests for the options strategy P/L simulator.

Covers:
- OptionLeg validation and intrinsic value
- P/L at expiration for single-leg, spread, stock-overlay and ratio strategies
- Max profit / max loss (including unlimited) and exact breakevens
- Probability of profit (lognormal) and range-share metrics
- Position Greeks aggregation against OptionPricer
- Mark-to-model value before expiration and for multi-expiry strategies
- ASCII P/L diagram
"""

import math

import pytest
from black_scholes import OptionPricer
from strategy_simulator import (
    OptionLeg,
    StockLeg,
    Strategy,
    bear_call_spread,
    bear_put_spread,
    bull_call_spread,
    bull_put_spread,
    calendar_spread,
    cash_secured_put,
    collar,
    covered_call,
    diagonal_spread,
    generate_pnl_diagram,
    iron_butterfly,
    iron_condor,
    long_straddle,
    long_strangle,
    poor_mans_covered_call,
    protective_put,
    ratio_spread,
    short_straddle,
    short_strangle,
)

S, T, R, SIGMA = 100.0, 30 / 365, 0.05, 0.25


def _call(K, T_=T):
    return OptionPricer(S, K, T_, R, SIGMA).call_price()


def _put(K, T_=T):
    return OptionPricer(S, K, T_, R, SIGMA).put_price()


# ── OptionLeg ─────────────────────────────────────────────────────────


class TestOptionLeg:
    def test_rejects_bad_type(self):
        with pytest.raises(ValueError, match="option_type"):
            OptionLeg("straddle", 100, "long", 1.0)

    def test_rejects_bad_position(self):
        with pytest.raises(ValueError, match="position"):
            OptionLeg("call", 100, "buy", 1.0)

    def test_rejects_non_positive_quantity(self):
        with pytest.raises(ValueError, match="quantity"):
            OptionLeg("call", 100, "long", 1.0, quantity=0)

    def test_intrinsic(self):
        assert OptionLeg("call", 100, "long", 1).intrinsic(110) == 10
        assert OptionLeg("call", 100, "long", 1).intrinsic(90) == 0
        assert OptionLeg("put", 100, "long", 1).intrinsic(90) == 10
        assert OptionLeg("put", 100, "long", 1).intrinsic(110) == 0


# ── Hand-priced strategies: exact P/L arithmetic ──────────────────────


class TestHandPricedPnl:
    def test_long_call(self):
        s = Strategy("Long Call", [OptionLeg("call", 100, "long", 3.0)], contracts=2)
        assert s.net_premium == pytest.approx(600)
        assert s.pnl_at_expiration(90) == pytest.approx(-600)
        assert s.pnl_at_expiration(110) == pytest.approx(1400)
        m = s.metrics()
        assert math.isinf(m["max_profit"]) and m["max_profit"] > 0
        assert m["max_loss"] == pytest.approx(-600)
        assert m["breakevens"] == [pytest.approx(103.0)]

    def test_bull_call_spread_matches_skill_example(self):
        # $180/$185 spread, $2.50 net debit, 10 contracts (SKILL.md Step 5)
        s = Strategy(
            "Bull Call Spread",
            [OptionLeg("call", 180, "long", 4.0), OptionLeg("call", 185, "short", 1.5)],
            contracts=10,
        )
        m = s.metrics()
        assert m["net_premium"] == pytest.approx(2500)
        assert m["max_profit"] == pytest.approx(2500)
        assert m["max_loss"] == pytest.approx(-2500)
        assert m["breakevens"] == [pytest.approx(182.5)]
        assert m["reward_to_risk"] == pytest.approx(1.0)

    def test_short_put_unlimited_profit_flag_false(self):
        s = Strategy("Short Put", [OptionLeg("put", 100, "short", 2.0)])
        m = s.metrics()
        assert m["max_profit"] == pytest.approx(200)
        assert m["max_loss"] == pytest.approx(-9800)  # stock to zero
        assert m["breakevens"] == [pytest.approx(98.0)]

    def test_stock_leg(self):
        s = Strategy(
            "Covered Call",
            [OptionLeg("call", 105, "short", 1.0)],
            stock=StockLeg(shares=100, cost_basis=100.0),
        )
        assert s.pnl_at_expiration(110) == pytest.approx(600)
        assert s.pnl_at_expiration(95) == pytest.approx(-400)
        assert s.metrics()["breakevens"] == [pytest.approx(99.0)]

    def test_multi_expiry_rejects_expiration_pnl(self):
        s = Strategy(
            "Calendar",
            [
                OptionLeg("call", 100, "short", 2.0, expiry_T=30 / 365),
                OptionLeg("call", 100, "long", 3.0, expiry_T=60 / 365),
            ],
        )
        with pytest.raises(ValueError, match="different expirations"):
            s.pnl_at_expiration(100)


# ── Builders (Black-Scholes priced) ───────────────────────────────────


class TestBuilders:
    def test_bull_call_spread_premiums_from_pricer(self):
        s = bull_call_spread(S, 100, 105, T, R, SIGMA, contracts=3)
        assert s.net_premium == pytest.approx((_call(100) - _call(105)) * 300)
        m = s.metrics()
        assert m["max_profit"] + abs(m["max_loss"]) == pytest.approx(5 * 300)

    def test_bear_put_spread(self):
        m = bear_put_spread(S, 105, 100, T, R, SIGMA).metrics()
        assert m["max_profit"] + abs(m["max_loss"]) == pytest.approx(500)
        assert len(m["breakevens"]) == 1

    @pytest.mark.parametrize("builder", [bull_put_spread, bear_call_spread])
    def test_credit_spreads_receive_credit(self, builder):
        if builder is bull_put_spread:
            s = builder(S, 95, 90, T, R, SIGMA)
        else:
            s = builder(S, 105, 110, T, R, SIGMA)
        m = s.metrics()
        assert m["net_premium"] < 0
        assert m["max_profit"] == pytest.approx(-m["net_premium"])
        assert m["max_loss"] == pytest.approx(-(500 + m["net_premium"]))

    def test_iron_condor(self):
        s = iron_condor(S, 90, 95, 105, 110, T, R, SIGMA)
        m = s.metrics()
        credit = -s.net_premium
        assert credit > 0
        assert m["max_profit"] == pytest.approx(credit)
        assert m["max_loss"] == pytest.approx(-(500 - credit))
        lo, hi = m["breakevens"]
        assert lo == pytest.approx(95 - credit / 100, abs=1e-3)
        assert hi == pytest.approx(105 + credit / 100, abs=1e-3)

    def test_iron_condor_strike_order(self):
        with pytest.raises(ValueError, match="strikes"):
            iron_condor(S, 95, 90, 105, 110, T, R, SIGMA)

    def test_iron_butterfly_is_condor_with_shared_body(self):
        s = iron_butterfly(S, 100, 5, T, R, SIGMA)
        assert sorted(leg.strike for leg in s.legs) == [95, 100, 100, 105]

    def test_straddles_and_strangles(self):
        assert math.isinf(long_straddle(S, 100, T, R, SIGMA).metrics()["max_profit"])
        assert math.isinf(long_strangle(S, 95, 105, T, R, SIGMA).metrics()["max_profit"])
        assert short_straddle(S, 100, T, R, SIGMA).metrics()["max_loss"] == -math.inf
        assert short_strangle(S, 95, 105, T, R, SIGMA).metrics()["max_loss"] == -math.inf
        assert len(long_straddle(S, 100, T, R, SIGMA).metrics()["breakevens"]) == 2

    def test_stock_strategies(self):
        cc = covered_call(S, 105, T, R, SIGMA, contracts=2)
        assert cc.stock.shares == 200
        assert cc.metrics()["max_profit"] == pytest.approx((5 + _call(105)) * 200)
        pp = protective_put(S, 95, T, R, SIGMA)
        assert pp.metrics()["max_loss"] == pytest.approx(-(5 + _put(95)) * 100)
        assert math.isinf(pp.metrics()["max_profit"])
        col = collar(S, 95, 105, T, R, SIGMA)
        m = col.metrics()
        assert math.isfinite(m["max_profit"]) and math.isfinite(m["max_loss"])

    def test_cash_secured_put_notes_cash(self):
        s = cash_secured_put(S, 95, T, R, SIGMA, contracts=2)
        assert any("19,000" in n for n in s.notes)

    def test_ratio_spread_unlimited_upside_risk(self):
        s = ratio_spread(S, 100, 105, T, R, SIGMA, long_qty=1, short_qty=2)
        m = s.metrics()
        assert m["max_loss"] == -math.inf
        assert math.isfinite(m["max_profit"])

    def test_multi_expiry_builders(self):
        for s in (
            calendar_spread(S, 100, 30 / 365, 60 / 365, R, SIGMA),
            diagonal_spread(S, 105, 100, 30 / 365, 60 / 365, R, SIGMA),
            poor_mans_covered_call(S, 80, 105, 1.0, 30 / 365, R, SIGMA),
        ):
            assert not s.is_single_expiry
            assert s.net_premium > 0  # long the longer-dated leg: net debit

    def test_builder_rejects_expired_option(self):
        with pytest.raises(ValueError):
            bull_call_spread(S, 100, 105, 0.0, R, SIGMA)


# ── Probability and range metrics ─────────────────────────────────────


class TestProbability:
    def test_long_call_pop_matches_lognormal(self):
        s = Strategy("Long Call", [OptionLeg("call", 100, "long", 3.0, expiry_T=T)])
        pop = s.probability_of_profit(S, T, SIGMA, r=R)
        # P(S_T > 103) under risk-neutral lognormal
        d2 = (math.log(S / 103) + (R - 0.5 * SIGMA**2) * T) / (SIGMA * math.sqrt(T))
        from scipy.stats import norm

        assert pop == pytest.approx(norm.cdf(d2), abs=1e-9)

    def test_iron_condor_pop_between_zero_and_one(self):
        pop = iron_condor(S, 90, 95, 105, 110, T, R, SIGMA).probability_of_profit(S, T, SIGMA, R)
        assert 0.5 < pop < 0.9

    def test_range_profit_share(self):
        s = Strategy("Long Call", [OptionLeg("call", 100, "long", 0.0)])
        assert s.range_profit_share(100, pct=0.30) == pytest.approx(0.5, abs=0.01)


# ── Greeks and mark-to-model ──────────────────────────────────────────


class TestGreeksAndValuation:
    def test_position_greeks_match_pricer(self):
        s = bull_call_spread(S, 100, 105, T, R, SIGMA, contracts=2)
        g = s.position_greeks(S, R, SIGMA)
        a = OptionPricer(S, 100, T, R, SIGMA).get_all_greeks("call")
        b = OptionPricer(S, 105, T, R, SIGMA).get_all_greeks("call")
        for k in ("delta", "gamma", "theta", "vega", "rho"):
            assert g[k] == pytest.approx((a[k] - b[k]) * 200)

    def test_position_greeks_include_stock_delta(self):
        g = covered_call(S, 105, T, R, SIGMA).position_greeks(S, R, SIGMA)
        call_delta = OptionPricer(S, 105, T, R, SIGMA).call_delta()
        assert g["delta"] == pytest.approx(100 - call_delta * 100)

    def test_value_at_inception_is_zero(self):
        s = iron_condor(S, 90, 95, 105, 110, T, R, SIGMA)
        assert s.value_at(S, 0.0, R, SIGMA) == pytest.approx(0.0, abs=1e-6)

    def test_value_at_expiry_equals_expiration_pnl(self):
        s = long_straddle(S, 100, T, R, SIGMA)
        for price in (85, 100, 118):
            assert s.value_at(price, T, R, SIGMA) == pytest.approx(s.pnl_at_expiration(price))

    def test_iv_crush_hurts_long_straddle(self):
        s = long_straddle(S, 100, 7 / 365, R, 0.80)
        assert s.value_at(100, 1 / 365, R, 0.35) < s.value_at(100, 1 / 365, R, 0.80) < 0

    def test_calendar_value_at_near_expiry(self):
        s = calendar_spread(S, 100, 30 / 365, 60 / 365, R, SIGMA)
        # At the near expiry with S at the strike, a calendar is at its best.
        at_strike = s.value_at(100, 30 / 365, R, SIGMA)
        assert at_strike > 0
        assert at_strike > s.value_at(80, 30 / 365, R, SIGMA)
        assert at_strike > s.value_at(120, 30 / 365, R, SIGMA)


# ── Output ────────────────────────────────────────────────────────────


class TestOutput:
    def test_summary_contains_key_metrics(self):
        text = iron_condor(S, 90, 95, 105, 110, T, R, SIGMA).summary(S, r=R, sigma=SIGMA)
        for needle in ("Net Credit", "Max Profit", "Max Loss", "Breakeven", "Position Greeks"):
            assert needle in text

    def test_summary_unlimited(self):
        assert "Unlimited" in short_straddle(S, 100, T, R, SIGMA).summary(S)

    def test_summary_multi_expiry(self):
        assert "value_at" in calendar_spread(S, 100, 30 / 365, 60 / 365, R, SIGMA).summary(S)

    def test_diagram_shape(self):
        out = generate_pnl_diagram(bull_call_spread(S, 100, 105, T, R, SIGMA), S)
        lines = out.splitlines()
        assert lines[0].startswith("P/L at expiration")
        assert any("$0 |" in line for line in lines)
        assert "+" in out and "*" in out
