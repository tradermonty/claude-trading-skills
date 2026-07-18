"""Tests for the pure futures_sizing module: validators, risk math, floor
algorithm, tick-grid guards, and gate-report normalization.

Contract-spec-table invariant/spot-check tests live in this same file (added
once the spec table is populated) but are import-order independent of the
tests below -- everything here exercises the core sizing math against
synthetic, hand-built spec dicts so it never depends on the verified table
being complete.
"""

from __future__ import annotations

import math

import futures_sizing as fs
import pytest

# A synthetic ES-like spec used across many tests so the math tests don't
# depend on the real (WebSearch-verified) CONTRACT_SPECS table.
ES_SPEC = {
    "cot_symbol": "ES",
    "exchange_product": "E-mini S&P 500",
    "multiplier": 50,
    "tick_size": 0.25,
    "tick_value": 12.5,
    "currency": "USD",
    "exchange": "CME",
    "source_url": "https://example.invalid/es",
    "verified_date": "2026-07-17",
}

# A synthetic bond-family spec (mirrors ZB: 1/32 = 0.03125 point tick).
ZB_SPEC = {
    "cot_symbol": "ZB",
    "exchange_product": "30-Year T-Bond",
    "multiplier": 1000,
    "tick_size": 0.03125,
    "tick_value": 31.25,
    "currency": "USD",
    "exchange": "CBOT",
    "source_url": "https://example.invalid/zb",
    "verified_date": "2026-07-17",
}


# --- Numeric string validator (argparse-facing, pure logic) ----------------


class TestStrictPositiveFloat:
    def test_accepts_plain_positive(self):
        assert fs.strict_positive_float("5000.25") == 5000.25

    def test_rejects_inf_string(self):
        with pytest.raises(ValueError):
            fs.strict_positive_float("inf")

    def test_rejects_neg_inf_string(self):
        with pytest.raises(ValueError):
            fs.strict_positive_float("-inf")

    def test_rejects_nan_string(self):
        with pytest.raises(ValueError):
            fs.strict_positive_float("nan")

    def test_rejects_overflow_literal(self):
        # 1e309 overflows float64 to inf on parse -- must still be rejected.
        with pytest.raises(ValueError):
            fs.strict_positive_float("1e309")

    def test_rejects_zero(self):
        with pytest.raises(ValueError):
            fs.strict_positive_float("0")

    def test_rejects_negative(self):
        with pytest.raises(ValueError):
            fs.strict_positive_float("-5")

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError):
            fs.strict_positive_float("banana")

    def test_max_value_boundary_inclusive(self):
        assert fs.strict_positive_float("10.0", max_value=10.0) == 10.0

    def test_max_value_boundary_rejected_above(self):
        with pytest.raises(ValueError):
            fs.strict_positive_float("10.01", max_value=10.0)


class TestStrictNonNegInt:
    def test_accepts_zero(self):
        assert fs.strict_nonneg_int("0") == 0

    def test_accepts_positive(self):
        assert fs.strict_nonneg_int("5") == 5

    def test_rejects_negative(self):
        with pytest.raises(ValueError):
            fs.strict_nonneg_int("-1")

    def test_rejects_non_integer(self):
        with pytest.raises(ValueError):
            fs.strict_nonneg_int("1.5")

    def test_rejects_inf(self):
        with pytest.raises(ValueError):
            fs.strict_nonneg_int("inf")

    def test_rejects_nan(self):
        with pytest.raises(ValueError):
            fs.strict_nonneg_int("nan")

    # --- Code review round 3 (user re-review), P2-4: a value beyond
    # float64's 2**53 exact-integer range used to silently round-trip to a
    # DIFFERENT integer via the old float()-based parser, making the "hard
    # cap" --max-contracts exists to provide exceedable by one.

    def test_p2_4_beyond_2_pow_53_round_trips_exactly(self):
        # 2**53 = 9007199254740992; this value is 3 above it and is NOT
        # exactly representable as a float64 -- float("9007199254740995")
        # rounds to 9007199254740996.0, a different integer. int() must
        # parse it exactly regardless.
        value = "9007199254740995"
        assert float(value) != 9_007_199_254_740_995  # confirms the float trap is real here
        assert fs.strict_nonneg_int(value) == 9_007_199_254_740_995

    def test_much_larger_than_2_pow_53_still_exact(self):
        value = str(2**100 + 7)
        assert fs.strict_nonneg_int(value) == 2**100 + 7


# --- Floor algorithm (PINNED, exact rational arithmetic -- no epsilon) -----


class TestComputeContracts:
    def test_exact_k_times_rpc_gives_k(self):
        # rpc built from a non-binary-exact product (0.1 * 3) so the exact
        # multiple isn't binary-representable. budget is computed AS
        # rpc * 7 (the same rpc, round-tripped), so the exact rational
        # quotient recovers exactly 7 -- no epsilon involved at all now,
        # just exact Fraction arithmetic.
        rpc = 0.1 * 3  # 0.30000000000000004 in float64
        budget = rpc * 7
        assert fs.compute_contracts(budget, rpc) == 7

    def test_k_times_rpc_minus_true_shortfall_gives_k_minus_1(self):
        rpc = 0.1 * 3
        # A REAL shortfall much larger than float noise must still floor down.
        budget = rpc * 7 - 0.01
        assert fs.compute_contracts(budget, rpc) == 6

    def test_true_two_point_five_stays_two(self):
        rpc = 100.0
        budget = 250.0
        assert fs.compute_contracts(budget, rpc) == 2

    def test_large_scale_exact_multiple_still_recovers_exactly(self):
        # q ~ 1e5: the exact-rational floor recovers an exact multiple
        # without ever rounding up a genuine fractional remainder --
        # by construction, not by an epsilon's sizing.
        rpc = 1012.50
        budget = rpc * 100_000
        assert fs.compute_contracts(budget, rpc) == 100_000
        assert fs.compute_contracts(budget - 1.0, rpc) == 99_999

    def test_zero_budget_floors_to_zero(self):
        assert fs.compute_contracts(0.0, 1012.50) == 0

    def test_sub_one_contract_floors_to_zero(self):
        assert fs.compute_contracts(999.99, 1012.50) == 0

    def test_max_contracts_caps_when_lower(self):
        assert fs.compute_contracts(10_000.0, 100.0, max_contracts=3) == 3

    def test_max_contracts_no_effect_when_higher(self):
        assert fs.compute_contracts(300.0, 100.0, max_contracts=10) == 3

    def test_max_contracts_none_means_uncapped(self):
        assert fs.compute_contracts(1000.0, 100.0, max_contracts=None) == 10

    # --- Code review round 3, P1-1 (and its own re-review): the relative
    # epsilon rounded UP past the actual risk budget at large q; the
    # absolute-epsilon + hard-post-condition-loop fix that replaced it
    # could not terminate in practice at large scale (float64 loses the
    # ability to represent `(contracts - 1) * rpc != contracts * rpc` once
    # contracts is huge, so the loop's exit condition never becomes true).
    # Both are now replaced by an EXACT rational floor (Fraction), which
    # has no epsilon, no loop, and no representable-difference failure
    # mode -- it terminates in O(1) and is exact by construction. ---

    def test_p1_1_exact_repro_does_not_round_up_past_budget(self):
        # Exact reviewer repro: budget=$99,999,999,950, rpc=$1,000 ->
        # q=99999999.95 (a true 0.05-contract shortfall). The relative-
        # epsilon bug rounded this UP to 100,000,000 -- $50 over budget,
        # still SIZED. Must floor down to 99999999.
        budget = 99_999_999_950.0
        rpc = 1_000.0
        contracts = fs.compute_contracts(budget, rpc)
        assert contracts == 99_999_999
        assert contracts * rpc <= budget

    def test_hang_repro_terminates_instantly_and_is_rejected_as_absurd(self):
        # The reviewer's exact hang repro for the (now-removed)
        # epsilon+while design: at this scale, `(contracts - 1) * rpc`
        # and `contracts * rpc` are bit-for-bit identical in float64, so
        # the old post-condition loop's exit test never became true and
        # it decremented toward zero one candidate contract at a time --
        # computationally indistinguishable from a hang (~2.4e285
        # iterations). The exact-rational floor computes the (equally
        # absurd) answer in O(1); CONTRACTS_SANITY_MAX then rejects it
        # outright as economically implausible, exit 2, rather than
        # returning a technically-correct nonsense SIZED report.
        distance = 1.0  # |entry - stop| = |2 - 1|
        multiplier = 1.4296227991821346e-275
        rpc = distance * multiplier
        account_size = 341482236954.82006
        risk_pct = 10.0
        budget = account_size * risk_pct / 100.0
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.compute_contracts(budget, rpc)
        assert exc_info.value.reason == "contracts_implausibly_large"

    def test_money_safety_correction_3_times_rpc_exceeds_0_9_budget(self):
        # The epsilon-based designs' "under-count fix" was itself a bug at
        # this exact scale: rpc = 0.1 * 3 = 0.30000000000000004 (slightly
        # ABOVE the mathematical 0.3), so 3 * rpc = 0.9000000000000001,
        # which EXCEEDS a separately-specified 0.9 budget. 3 contracts
        # would cost more than the budget allows in float64 terms; the
        # money-safe answer is 2, and the exact-rational floor correctly
        # returns 2 (an epsilon nudge would have pushed this to the wrong
        # answer, 3).
        rpc = 0.1 * 3
        budget = 0.9
        assert 3 * rpc > budget  # confirms the money-unsafe direction is real
        contracts = fs.compute_contracts(budget, rpc)
        assert contracts == 2
        assert contracts * rpc <= budget

    def test_moderately_large_legit_case_still_sized_under_sanity_cap(self):
        # ~1e8 contracts (a $1 trillion account against a cheap contract)
        # is a legitimate case this module's own tests exercise elsewhere
        # (e.g. the P1-1 repro above) -- it must stay well under
        # CONTRACTS_SANITY_MAX and never be rejected.
        budget = 1_000.0 * 100_000_000  # $100,000,000,000
        rpc = 1_000.0
        contracts = fs.compute_contracts(budget, rpc)
        assert contracts == 100_000_000
        assert contracts < fs.CONTRACTS_SANITY_MAX

    def test_invariant_holds_across_a_scale_sweep(self):
        # contracts * rpc <= budget must hold regardless of scale -- exact
        # by construction now, not by trusting any epsilon's sizing. Sweep
        # several orders of magnitude, each with a genuine, deliberately
        # non-round fractional shortfall.
        for rpc in (0.30000000000000004, 1.0, 1012.50, 1_000.0, 7.8125):
            for k in (1, 2, 100, 100_000, 10**8):
                budget = rpc * k - 0.5 * rpc  # a true (k - 0.5)x budget
                contracts = fs.compute_contracts(budget, rpc)
                assert contracts * rpc <= budget, (rpc, k, contracts, budget)
                assert contracts <= k - 1, (rpc, k, contracts)


# --- Geometry ---------------------------------------------------------------


class TestGeometryOk:
    def test_long_stop_below_entry_ok(self):
        assert fs.geometry_ok("LONG", entry=5000.0, stop=4980.0) is True

    def test_long_stop_above_entry_rejected(self):
        assert fs.geometry_ok("LONG", entry=5000.0, stop=5010.0) is False

    def test_long_stop_equal_entry_rejected(self):
        assert fs.geometry_ok("LONG", entry=5000.0, stop=5000.0) is False

    def test_short_stop_above_entry_ok(self):
        assert fs.geometry_ok("SHORT", entry=5000.0, stop=5010.0) is True

    def test_short_stop_below_entry_rejected(self):
        assert fs.geometry_ok("SHORT", entry=5000.0, stop=4980.0) is False

    def test_short_stop_equal_entry_rejected(self):
        assert fs.geometry_ok("SHORT", entry=5000.0, stop=5000.0) is False


# --- Tick grid ---------------------------------------------------------------


class TestIsOnTickGrid:
    def test_on_grid_decimal(self):
        assert fs.is_on_tick_grid(5000.25, 0.25) is True

    def test_off_grid_decimal(self):
        assert fs.is_on_tick_grid(5000.10, 0.25) is False

    def test_bond_on_grid_32nds_converted(self):
        # 110'16 = 110 + 16/32 = 110.50, which IS on a 1/32 grid.
        assert fs.is_on_tick_grid(110.50, 0.03125) is True

    def test_bond_off_grid_mistyped_decimal(self):
        # The classic trap: someone types "110.16" thinking it means 110'16.
        assert fs.is_on_tick_grid(110.16, 0.03125) is False

    def test_bond_quarter_32nd_on_grid(self):
        # ZF: 1/4-of-1/32 = 0.0078125
        assert fs.is_on_tick_grid(110.5078125, 0.0078125) is True

    def test_float_noise_does_not_false_reject(self):
        # 81 ticks of 0.25 accumulated via subtraction can carry float dust.
        entry = 5000.25
        stop = entry - 0.25 * 81
        assert fs.is_on_tick_grid(stop, 0.25) is True


class TestMeetsMinStopDistance:
    def test_one_tick_exactly_ok(self):
        assert fs.meets_min_stop_distance(5000.25, 5000.00, 0.25) is True

    def test_multiple_ticks_ok(self):
        assert fs.meets_min_stop_distance(5000.25, 4980.00, 0.25) is True

    def test_less_than_one_tick_rejected(self):
        assert fs.meets_min_stop_distance(5000.20, 5000.10, 0.25) is False

    def test_zero_distance_rejected(self):
        assert fs.meets_min_stop_distance(5000.0, 5000.0, 0.25) is False

    def test_float_noise_one_tick_not_falsely_rejected(self):
        tick = 0.1 * 3  # non-binary-exact tick size
        entry = 100.0
        stop = entry - tick
        assert fs.meets_min_stop_distance(entry, stop, tick) is True


# --- resolve_spec -------------------------------------------------------------


class TestResolveSpec:
    def test_known_symbol_returns_table_row(self):
        specs = {"ES": ES_SPEC}
        spec = fs.resolve_spec("ES", specs=specs)
        assert spec["multiplier"] == 50
        assert spec["tick_size"] == 0.25

    def test_known_symbol_case_insensitive(self):
        specs = {"ES": ES_SPEC}
        spec = fs.resolve_spec("es", specs=specs)
        assert spec["cot_symbol"] == "ES"

    def test_known_symbol_with_override_conflict_raises(self):
        specs = {"ES": ES_SPEC}
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.resolve_spec("ES", specs=specs, multiplier=99)
        assert exc_info.value.reason == "known_symbol_override_conflict"

    def test_unknown_symbol_without_overrides_raises(self):
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.resolve_spec("ZZZZ", specs={})
        assert exc_info.value.reason == "unknown_symbol_incomplete_override"

    def test_unknown_symbol_with_partial_overrides_raises(self):
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.resolve_spec("ZZZZ", specs={}, multiplier=50, tick_size=0.25)
        assert exc_info.value.reason == "unknown_symbol_incomplete_override"

    def test_unknown_symbol_with_full_overrides_builds_adhoc_spec(self):
        spec = fs.resolve_spec(
            "ZZZZ", specs={}, multiplier=50, tick_size=0.25, contract_currency="USD"
        )
        assert spec["multiplier"] == 50
        assert spec["tick_size"] == 0.25
        assert spec["tick_value"] == pytest.approx(12.5)
        assert spec["currency"] == "USD"
        assert spec["source_url"] is None
        assert spec["verified_date"] is None


# --- size_futures_position: mode A (explicit) geometry / off-grid / distance


class TestSizeFuturesPositionModeA:
    def base_kwargs(self, **overrides):
        kwargs = dict(
            symbol="ES",
            direction="LONG",
            entry=5000.25,
            stop=4980.00,
            stop_source="operator",
            spec=ES_SPEC,
            account_size=100_000.0,
            risk_pct=2.0,
            max_contracts=None,
            fx_rate=1.0,
            as_of="2026-07-17",
        )
        kwargs.update(overrides)
        return kwargs

    def test_hand_checked_es_long_sized(self):
        result = fs.size_futures_position(**self.base_kwargs())
        assert result["sizing_status"] == "SIZED"
        assert result["stop_distance_points"] == pytest.approx(20.25)
        assert result["stop_distance_ticks"] == 81
        assert result["risk_per_contract_usd"] == pytest.approx(1012.50)
        assert result["risk_budget_usd"] == pytest.approx(2000.00)
        assert result["contracts"] == 1
        assert result["total_risk_usd"] == pytest.approx(1012.50)
        assert result["no_trade_reason"] is None

    def test_one_pct_risk_yields_zero_contracts_no_trade(self):
        result = fs.size_futures_position(**self.base_kwargs(risk_pct=1.0))
        assert result["sizing_status"] == "NO_TRADE"
        assert result["no_trade_reason"] == "risk_below_one_contract"
        assert result["contracts"] == 0
        assert result["total_risk_usd"] is None
        assert result["risk_pct_of_account"] is None
        # Math fields still populated per the output contract.
        assert result["risk_per_contract_usd"] == pytest.approx(1012.50)
        assert result["risk_budget_usd"] == pytest.approx(1000.00)

    def test_short_mirror(self):
        result = fs.size_futures_position(
            **self.base_kwargs(direction="SHORT", entry=4980.00, stop=5000.25)
        )
        assert result["sizing_status"] == "SIZED"
        assert result["stop_distance_points"] == pytest.approx(20.25)
        assert result["contracts"] == 1

    def test_geometry_violation_mode_a_raises_config_error(self):
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(direction="LONG", entry=5000.0, stop=5010.0)
            )
        assert exc_info.value.reason == "direction_stop_mismatch"

    def test_geometry_equality_mode_a_raises_config_error(self):
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(direction="LONG", entry=5000.0, stop=5000.0)
            )
        assert exc_info.value.reason == "direction_stop_mismatch"

    def test_stop_too_close_mode_a_raises_config_error(self):
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(**self.base_kwargs(entry=5000.20, stop=5000.10))
        assert exc_info.value.reason == "stop_too_close"

    def test_off_grid_non_bond_symbol_is_warning_only(self):
        result = fs.size_futures_position(**self.base_kwargs(entry=5000.10, stop=4980.00))
        assert result["sizing_status"] == "SIZED"
        assert "off_tick_grid_entry" in result["warnings"]

    def test_bond_entry_off_grid_mode_a_raises_config_error(self):
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(symbol="ZB", spec=ZB_SPEC, entry=110.16, stop=108.00)
            )
        assert exc_info.value.reason == "entry_off_tick_grid"

    def test_bond_stop_off_grid_mode_a_raises_config_error(self):
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(symbol="ZB", spec=ZB_SPEC, entry=110.50, stop=108.16)
            )
        assert exc_info.value.reason == "stop_off_tick_grid"

    def test_extreme_bond_entry_gets_overflow_attribution_not_32nds(self):
        # Code review round 3, P3: an extreme --entry on a BOND symbol used
        # to raise the 32nds-notation message (misleading -- the ratio
        # price/tick_size overflowed, this isn't a genuine off-grid
        # notation mistake). Must now fall through to the correctly-
        # attributed risk_per_contract_overflow error instead.
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(symbol="ZB", spec=ZB_SPEC, entry=1e308, stop=1.0)
            )
        assert exc_info.value.reason == "risk_per_contract_overflow"
        assert exc_info.value.reason != "entry_off_tick_grid"
        message = str(exc_info.value)
        assert "32nds" not in message
        assert "--entry" in message

    def test_normal_off_grid_bond_entry_still_gets_32nds_message(self):
        # Regression guard: an ordinary (finite) off-grid bond price must
        # still get the 32nds-notation message, not be misrouted into the
        # overflow path.
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(symbol="ZB", spec=ZB_SPEC, entry=110.16, stop=108.00)
            )
        assert exc_info.value.reason == "entry_off_tick_grid"
        assert "32nds" in str(exc_info.value)

    def test_risk_pct_above_2_warns(self):
        result = fs.size_futures_position(**self.base_kwargs(risk_pct=3.0))
        assert "risk_pct_above_2" in result["warnings"]

    def test_risk_pct_at_2_does_not_warn(self):
        result = fs.size_futures_position(**self.base_kwargs(risk_pct=2.0))
        assert "risk_pct_above_2" not in result["warnings"]

    def test_max_contracts_cap_applied_flag(self):
        result = fs.size_futures_position(**self.base_kwargs(risk_pct=10.0, max_contracts=2))
        assert result["max_contracts_cap_applied"] is True
        assert result["contracts"] == 2

    def test_fx_conversion_applied(self):
        result = fs.size_futures_position(**self.base_kwargs(fx_rate=1.25))
        # Compare against the same round(x, 2) the implementation applies for
        # display -- 1265.625 sits exactly on a float64 rounding boundary
        # (round(1265.625, 2) == 1265.62, not .63), so pytest.approx against
        # the unrounded product would be a test artifact, not a real bug.
        assert result["risk_per_contract_usd"] == round(20.25 * 50 * 1.25, 2)
        assert result["fx_rate_used"] == 1.25


# --- size_futures_position: float64 overflow defense-in-depth --------------
#
# The CLI layer caps --account-size/--multiplier/--tick-size/--fx-rate so an
# individually-extreme flag is an ordinary argparse usage error (see
# test_futures_position_sizer.py). These tests exercise the pure module's
# OWN isfinite() guards directly, bypassing any CLI-level cap entirely --
# the module must never crash with an uncaught OverflowError/ValueError
# regardless of what a caller (CLI today, anything else tomorrow) passes it.


class TestSizeFuturesPositionOverflowGuards:
    def base_kwargs(self, **overrides):
        kwargs = dict(
            symbol="ES",
            direction="LONG",
            entry=5000.25,
            stop=4980.00,
            stop_source="operator",
            spec=ES_SPEC,
            account_size=100_000.0,
            risk_pct=2.0,
            max_contracts=None,
            fx_rate=1.0,
            as_of="2026-07-17",
        )
        kwargs.update(overrides)
        return kwargs

    def test_risk_budget_overflow_raises_config_error(self):
        # account_size * risk_pct / 100 overflows to inf. Individually,
        # 1.5e308 is a "valid" (finite, positive) float -- only the PRODUCT
        # overflows, which is exactly what the CLI-level per-flag caps can't
        # catch on their own (repro A from code review round 1).
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(**self.base_kwargs(account_size=1.5e308, risk_pct=10.0))
        assert exc_info.value.reason == "risk_budget_overflow"

    def test_risk_per_contract_overflow_raises_config_error(self):
        # distance * multiplier * fx_rate overflows to inf via an extreme
        # unknown-symbol-override multiplier (repro B from code review
        # round 1).
        huge_spec = dict(ES_SPEC, multiplier=1e308, tick_size=0.01, tick_value=1e306)
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(**self.base_kwargs(spec=huge_spec))
        assert exc_info.value.reason == "risk_per_contract_overflow"

    def test_risk_per_contract_overflow_via_extreme_entry_not_multiplier(self):
        # A second route to the SAME overflow: an extreme --entry (which the
        # CLI deliberately does NOT cap -- real prices have no reason to be
        # bounded) combined with an ordinary multiplier. This is the case
        # the argparse-level caps on multiplier/tick-size/fx-rate alone
        # cannot prevent -- only the isfinite() guard on the computed
        # product can.
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(**self.base_kwargs(entry=1e308, stop=1.0))
        assert exc_info.value.reason == "risk_per_contract_overflow"

    def test_one_trillion_account_size_still_sizes_normally(self):
        # Control case: the largest account size the CLI's new cap allows
        # must still size an ordinary trade correctly -- the guard must
        # never false-positive on a merely LARGE (but finite) value.
        result = fs.size_futures_position(**self.base_kwargs(account_size=1e12, risk_pct=1.0))
        assert result["sizing_status"] == "SIZED"
        assert result["risk_budget_usd"] == pytest.approx(1e12 * 1.0 / 100.0)
        assert math.isfinite(result["risk_budget_usd"])

    # --- Code review round 3, P1-2: denormal underflow -> risk_per_contract
    # == 0.0 -> ZeroDivisionError inside compute_contracts(), exit 1. 0.0 is
    # perfectly finite, so the isfinite() guard alone never caught this. ---

    def test_p1_2_denormal_underflow_raises_config_error_not_zerodiv(self):
        # Exact reviewer repro: entry/stop/multiplier/tick_size all ~1e-308
        # (individually finite and positive, passing every validator), but
        # distance * multiplier underflows to exactly 0.0.
        denormal_spec = dict(ES_SPEC, multiplier=1e-308, tick_size=1e-308, tick_value=1e-616)
        assert 2e-308 * 1e-308 == 0.0  # confirms this repro underflows in this environment
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(entry=2e-308, stop=1e-308, spec=denormal_spec)
            )
        assert exc_info.value.reason == "risk_per_contract_non_positive"

    def test_risk_per_contract_exactly_zero_raises_config_error(self):
        # Direct construction (not relying on the exact underflow repro
        # above continuing to underflow identically on every platform).
        zero_multiplier_spec = dict(ES_SPEC, multiplier=0.0, tick_value=0.0)
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(**self.base_kwargs(spec=zero_multiplier_spec))
        assert exc_info.value.reason == "risk_per_contract_non_positive"

    def test_quotient_overflow_now_caught_as_implausibly_large(self):
        # Follow-up to P1-2, superseded by the round-3 exact-rational floor
        # (round-3, second re-review): risk_per_contract can be finite and
        # POSITIVE (not underflowed to exactly 0.0) yet still so tiny
        # relative to a large-but-capped risk_budget that the naive FLOAT
        # quotient would have overflowed to inf. Fraction arithmetic has no
        # such overflow ceiling -- the exact quotient is instead a
        # legitimately astronomical (but finite, exact) integer, which the
        # CONTRACTS_SANITY_MAX check now catches as economically
        # implausible rather than as a numeric overflow. Same end result
        # (a clean ConfigError, exit 2), different, more accurate reason.
        tiny_spec = dict(ES_SPEC, multiplier=1e-300, tick_size=0.25, tick_value=2.5e-301)
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(spec=tiny_spec, account_size=1e12, risk_pct=10.0)
            )
        assert exc_info.value.reason == "contracts_implausibly_large"


# --- size_futures_position: mode B (gate-supplied stop) --------------------


class TestSizeFuturesPositionModeB:
    def base_kwargs(self, **overrides):
        kwargs = dict(
            symbol="ES",
            direction="LONG",
            entry=5000.25,
            stop=4980.00,
            stop_source="gate",
            spec=ES_SPEC,
            account_size=100_000.0,
            risk_pct=2.0,
            max_contracts=None,
            fx_rate=1.0,
            as_of="2026-07-17",
            gate_block={
                "report_path": "reports/gate.json",
                "setup_status": "READY_FOR_PLAN",
                "gate_confidence": "HIGH",
                "warnings": [],
            },
        )
        kwargs.update(overrides)
        return kwargs

    def test_geometry_violation_mode_b_is_no_trade_not_config_error(self):
        result = fs.size_futures_position(
            **self.base_kwargs(direction="LONG", entry=5000.0, stop=5010.0)
        )
        assert result["sizing_status"] == "NO_TRADE"
        assert result["no_trade_reason"] == "entry_on_wrong_side_of_stop"

    def test_stop_too_close_mode_b_is_no_trade(self):
        result = fs.size_futures_position(**self.base_kwargs(entry=5000.20, stop=5000.10))
        assert result["sizing_status"] == "NO_TRADE"
        assert result["no_trade_reason"] == "gate_stop_too_close"

    def test_bond_stop_off_grid_mode_b_is_no_trade(self):
        result = fs.size_futures_position(
            **self.base_kwargs(symbol="ZB", spec=ZB_SPEC, entry=110.50, stop=108.16)
        )
        assert result["sizing_status"] == "NO_TRADE"
        assert result["no_trade_reason"] == "gate_stop_off_tick_grid"

    def test_bond_entry_off_grid_mode_b_still_config_error(self):
        # Entry is ALWAYS operator-supplied, even in mode B -- this must
        # still raise, not degrade to NO_TRADE.
        with pytest.raises(fs.ConfigError) as exc_info:
            fs.size_futures_position(
                **self.base_kwargs(symbol="ZB", spec=ZB_SPEC, entry=110.16, stop=108.00)
            )
        assert exc_info.value.reason == "entry_off_tick_grid"

    def test_sized_result_carries_gate_block(self):
        result = fs.size_futures_position(**self.base_kwargs())
        assert result["gate"]["setup_status"] == "READY_FOR_PLAN"
        assert result["gate"]["gate_confidence"] == "HIGH"


# --- Gate report normalization ----------------------------------------------


def _ready_gate_report(**overrides):
    report = {
        "schema_version": "1.0",
        "symbol": "B6",
        "setup_status": "READY_FOR_PLAN",
        "direction": "SHORT",
        "invalidation_level": 1.3450,
        "gate_confidence": "HIGH",
        "warnings": ["price_action_confidence_medium"],
    }
    report.update(overrides)
    return report


class TestNormalizeGateReport:
    def test_unreadable_load_error(self):
        g = fs.normalize_gate_report(None, "unreadable", symbol=None)
        assert g.usable is False
        assert g.reason == "gate_json_unreadable"

    def test_parse_error_load_error(self):
        g = fs.normalize_gate_report(None, "parse_error", symbol=None)
        assert g.usable is False
        assert g.reason == "gate_json_parse_error"

    def test_non_finite_load_error(self):
        g = fs.normalize_gate_report(None, "non_finite", symbol=None)
        assert g.usable is False
        assert g.reason == "gate_json_non_finite"

    def test_top_level_not_dict_is_malformed(self):
        g = fs.normalize_gate_report([1, 2, 3], None, symbol=None)
        assert g.usable is False
        assert g.reason == "gate_json_malformed"

    def test_unsupported_schema_version(self):
        g = fs.normalize_gate_report(_ready_gate_report(schema_version="2.0"), None, symbol="B6")
        assert g.usable is False
        assert g.reason == "gate_json_schema_unsupported"

    def test_missing_schema_version(self):
        report = _ready_gate_report()
        del report["schema_version"]
        g = fs.normalize_gate_report(report, None, symbol="B6")
        assert g.usable is False
        assert g.reason == "gate_json_schema_unsupported"

    def test_symbol_mismatch(self):
        g = fs.normalize_gate_report(_ready_gate_report(), None, symbol="ES")
        assert g.usable is False
        assert g.reason == "gate_symbol_mismatch"

    # --- Code review round 3 (user re-review), P1-3: an invalid gate-file
    # symbol used to slip past validation (whitespace-only) or reach an
    # output filename unsanitized (path-hostile characters). Both must now
    # fail closed as gate_json_malformed -- exit 0, a report IS written,
    # naming the reason -- never a crash and never an unsafe filename.

    def test_whitespace_only_symbol_is_malformed_not_usable(self):
        # A non-empty string of spaces is truthy in Python, so a naive
        # `not report_symbol` check does NOT catch this -- it must be
        # caught by validating the STRIPPED value against the allowlist.
        g = fs.normalize_gate_report(_ready_gate_report(symbol="   "), None, symbol=None)
        assert g.usable is False
        assert g.reason == "gate_json_malformed"

    def test_path_hostile_symbol_is_malformed_not_usable(self):
        # "A/B" must never become GateNormalized.symbol -- it would
        # otherwise flow straight into an output filename path component.
        g = fs.normalize_gate_report(_ready_gate_report(symbol="A/B"), None, symbol=None)
        assert g.usable is False
        assert g.reason == "gate_json_malformed"
        assert g.symbol is None

    def test_symbol_with_leading_trailing_whitespace_is_normalized_and_accepted(self):
        # A genuinely valid symbol surrounded by incidental whitespace
        # should still work -- strip-then-validate, not reject outright.
        g = fs.normalize_gate_report(_ready_gate_report(symbol="  B6  "), None, symbol=None)
        assert g.usable is True
        assert g.symbol == "B6"

    def test_overlong_symbol_is_malformed(self):
        g = fs.normalize_gate_report(_ready_gate_report(symbol="A" * 13), None, symbol=None)
        assert g.usable is False
        assert g.reason == "gate_json_malformed"

    def test_symbol_taken_from_report_when_omitted(self):
        g = fs.normalize_gate_report(_ready_gate_report(), None, symbol=None)
        assert g.usable is True
        assert g.symbol == "B6"

    def test_symbol_case_insensitive_match(self):
        g = fs.normalize_gate_report(_ready_gate_report(), None, symbol="b6")
        assert g.usable is True

    def test_non_ready_status_refused(self):
        for status in (
            "WATCHING_PRICE",
            "CROWDED",
            "REJECTED",
            "INSUFFICIENT_EVIDENCE",
            "SOMETHING_UNKNOWN",
        ):
            g = fs.normalize_gate_report(
                _ready_gate_report(setup_status=status, direction=None, invalidation_level=None),
                None,
                symbol="B6",
            )
            assert g.usable is False, status
            assert g.reason == "gate_not_ready", status
            assert g.setup_status == status

    def test_not_ready_still_echoes_confidence_and_warnings(self):
        g = fs.normalize_gate_report(
            _ready_gate_report(
                setup_status="WATCHING_PRICE", direction=None, invalidation_level=None
            ),
            None,
            symbol="B6",
        )
        assert g.gate_confidence == "HIGH"
        assert "price_action_confidence_medium" in g.warnings

    def test_invalid_direction_type(self):
        g = fs.normalize_gate_report(_ready_gate_report(direction="SIDEWAYS"), None, symbol="B6")
        assert g.usable is False
        assert g.reason == "gate_json_invalid_direction"

    def test_missing_direction(self):
        report = _ready_gate_report()
        report["direction"] = None
        g = fs.normalize_gate_report(report, None, symbol="B6")
        assert g.usable is False
        assert g.reason == "gate_json_invalid_direction"

    @pytest.mark.parametrize(
        "bad_value",
        [0, -1.5, float("inf"), float("nan"), True, "1.30", None],
    )
    def test_invalid_invalidation_level(self, bad_value):
        g = fs.normalize_gate_report(
            _ready_gate_report(invalidation_level=bad_value), None, symbol="B6"
        )
        assert g.usable is False
        assert g.reason == "gate_json_invalid_invalidation_level"

    def test_fully_valid_ready_report(self):
        g = fs.normalize_gate_report(_ready_gate_report(), None, symbol="B6")
        assert g.usable is True
        assert g.reason is None
        assert g.direction == "SHORT"
        assert g.invalidation_level == pytest.approx(1.3450)
        assert g.gate_confidence == "HIGH"
        assert g.setup_status == "READY_FOR_PLAN"
        assert "price_action_confidence_medium" in g.warnings

    def test_non_list_warnings_degrades_to_empty(self):
        g = fs.normalize_gate_report(_ready_gate_report(warnings="not-a-list"), None, symbol="B6")
        assert g.usable is True
        assert g.warnings == ()

    def test_non_string_gate_confidence_degrades_to_none(self):
        g = fs.normalize_gate_report(_ready_gate_report(gate_confidence=123), None, symbol="B6")
        assert g.usable is True
        assert g.gate_confidence is None


# --- build_gate_failure_result -----------------------------------------------


class TestBuildGateFailureResult:
    def test_carries_reason_and_entry(self):
        result = fs.build_gate_failure_result(
            symbol="B6",
            entry=1.345,
            reason="gate_not_ready",
            as_of="2026-07-17",
            report_path="reports/gate.json",
            setup_status="CROWDED",
        )
        assert result["sizing_status"] == "NO_TRADE"
        assert result["no_trade_reason"] == "gate_not_ready"
        assert result["entry"] == 1.345
        assert result["stop"] is None
        assert result["contracts"] == 0
        assert result["gate"]["setup_status"] == "CROWDED"
        # allow_nan=False safety: nothing non-finite anywhere in the result.
        assert not fs.contains_non_finite(result)


# --- Currency / fx-rate guard -------------------------------------------------


class TestRequiresFxRate:
    def test_usd_does_not_require_fx_rate(self):
        assert fs.requires_fx_rate("USD") is False

    def test_non_usd_requires_fx_rate(self):
        assert fs.requires_fx_rate("GBP") is True

    def test_case_insensitive(self):
        assert fs.requires_fx_rate("usd") is False


# --- contains_non_finite (reused iterative whole-structure scan) -----------


class TestContainsNonFinite:
    def test_clean_structure_false(self):
        assert fs.contains_non_finite({"a": 1, "b": [1.0, 2.0, {"c": "x"}]}) is False

    def test_top_level_nan(self):
        assert fs.contains_non_finite(float("nan")) is True

    def test_nested_inf(self):
        assert fs.contains_non_finite({"a": [1, {"b": float("inf")}]}) is True

    def test_deep_but_finite_structure_no_recursion_error(self):
        deep = 1.0
        for _ in range(5000):
            deep = [deep]
        assert fs.contains_non_finite(deep) is False


# --- Contract-spec table: table-wide invariant + independent spot-checks ---
#
# The table-wide test mechanically catches a transcription error (tick_value
# not matching multiplier * tick_size) on ANY of the 23 rows. The spot-check
# literals below are pinned INDEPENDENTLY of the table -- i.e. hand-typed
# from the official contract-spec pages, not derived by reading
# fs.CONTRACT_SPECS -- so they would catch a wrong EDIT to the table itself
# (a bad tick_value that still happens to equal multiplier * tick_size would
# pass the invariant test but fail these).

CORE_SYMBOLS = frozenset(
    {
        "ES", "NQ", "YM", "QR", "VX",
        "ZT", "ZF", "ZN", "ZB",
        "DX", "E6", "J6", "B6", "A6", "D6", "S6",
        "GC", "SI", "HG", "PL",
        "CL", "NG",
        "BT",
    }
)  # fmt: skip


class TestContractSpecTableCompleteness:
    def test_table_has_exactly_the_23_core_symbols(self):
        assert set(fs.CONTRACT_SPECS) == CORE_SYMBOLS

    def test_every_row_has_required_keys(self):
        required = {
            "exchange_product",
            "multiplier",
            "tick_size",
            "tick_value",
            "currency",
            "exchange",
            "source_url",
            "verified_date",
        }
        for symbol, row in fs.CONTRACT_SPECS.items():
            assert required.issubset(row.keys()), symbol


class TestContractSpecTableInvariants:
    def test_tick_value_equals_multiplier_times_tick_size_for_every_row(self):
        for symbol, row in fs.CONTRACT_SPECS.items():
            expected = row["multiplier"] * row["tick_size"]
            assert row["tick_value"] == pytest.approx(expected, rel=1e-9), symbol

    def test_every_row_is_usd_quoted(self):
        # Named gotcha: CME FX futures (E6/J6/B6/A6/D6/S6) and ICE DX have
        # non-USD contract SIZES (e.g. B6 is GBP 62,500) but are all
        # QUOTE-currency USD -- this is the currency this table records.
        for symbol, row in fs.CONTRACT_SPECS.items():
            assert row["currency"] == "USD", symbol

    def test_every_row_is_verified(self):
        # Fails until every row carries a real source_url/verified_date --
        # this is the money-critical gate: the table must never ship with a
        # PROVISIONAL/unverified row.
        for symbol, row in fs.CONTRACT_SPECS.items():
            assert row["source_url"], f"{symbol} has no verified source_url"
            assert row["verified_date"], f"{symbol} has no verified_date"


class TestContractSpecSpotChecks:
    """Independent literal spot-checks, NOT derived from the table -- these
    catch a wrong edit to CONTRACT_SPECS itself, not just an internal
    inconsistency within a row."""

    def test_es_tick_value_is_12_50(self):
        assert fs.CONTRACT_SPECS["ES"]["tick_value"] == pytest.approx(12.50)
        assert fs.CONTRACT_SPECS["ES"]["multiplier"] == 50
        assert fs.CONTRACT_SPECS["ES"]["tick_size"] == pytest.approx(0.25)

    def test_gc_tick_value_is_10_00(self):
        assert fs.CONTRACT_SPECS["GC"]["tick_value"] == pytest.approx(10.00)
        assert fs.CONTRACT_SPECS["GC"]["multiplier"] == 100
        assert fs.CONTRACT_SPECS["GC"]["tick_size"] == pytest.approx(0.10)

    def test_zb_tick_value_is_31_25(self):
        # 1/32 of a point on a $100,000-par, $1000/point contract.
        assert fs.CONTRACT_SPECS["ZB"]["tick_value"] == pytest.approx(31.25)
        assert fs.CONTRACT_SPECS["ZB"]["multiplier"] == 1000
        assert fs.CONTRACT_SPECS["ZB"]["tick_size"] == pytest.approx(1 / 32)
