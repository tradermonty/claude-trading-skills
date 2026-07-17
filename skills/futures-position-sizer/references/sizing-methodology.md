# Futures Position Sizing Methodology

## Why a Separate Skill from `position-sizer`

`position-sizer` computes a SHARE count for long equity trades: `shares = floor(dollar_risk / (entry - stop))`, where one share's dollar risk is simply its own price move. Futures contracts are different in a way that makes that formula silently wrong if reused as-is: every contract has a **multiplier** that converts a one-point price move into a dollar amount, and that multiplier varies by roughly two orders of magnitude across symbols in the same table -- a 0.25-point move is $12.50 on ES (multiplier 50) but $5.00 on NQ (multiplier 20) and $31.25 on ZB (multiplier 1000, tick 1/32). Feeding a futures entry/stop into the equity sizer would compute a "share" count using the raw point difference as if it were a dollar difference, understating or overstating real risk by 20-1000x depending on the symbol. This skill exists specifically to apply the correct multiplier, tick size, and (for FX/international contracts) currency conversion before any risk arithmetic happens.

## Core Formula

```
stop_distance       = |entry - stop|                          (price points)
risk_per_contract   = stop_distance * multiplier * fx_rate     (USD)
risk_budget         = account_size * risk_pct / 100            (USD)
contracts            = floor(risk_budget / risk_per_contract)   (never rounds up)
total_risk           = contracts * risk_per_contract            (USD, when SIZED)
```

`fx_rate` converts a non-USD-quoted contract's risk into USD; it is `1.0` for every symbol in the verified core table (all 23 are USD-quoted -- see `futures-contract-specs.md`) and is required, with no default, for any operator-supplied override symbol quoted in another currency.

## The Floor Algorithm (Exact Rational Arithmetic -- No Epsilon)

```python
from fractions import Fraction
q = Fraction(risk_budget) / Fraction(risk_per_contract)
contracts = math.floor(q)
```

`Fraction(finite_float)` converts a float64 to the *exact* rational number it represents -- every float64 is a dyadic rational (an exact fraction with a power-of-2 denominator), so this conversion loses nothing. The division and floor that follow are then exact rational operations: `contracts * risk_per_contract <= risk_budget` holds *by construction*, with no epsilon, no iteration, and no float-representation edge case of any kind.

This design replaced two earlier float-heuristic attempts, both of which were bugs caught by independent user review across two rounds:

1. **A relative epsilon** (`math.floor(q * (1 + 1e-9))`, an early plan-review addition meant to recover a contract lost to float64 under-counting at an exact `k * risk_per_contract` boundary). A relative nudge's *absolute* size grows with `q`, and at large scale (`q ~ 1e8`, a big account against a cheap contract) a `1e-9`-relative nudge was already large enough (~0.1 in absolute terms) to swallow a *genuine* fractional shortfall and round the contract count UP past the actual risk budget -- the reported repro was `q = 99999999.95` (a true 0.05-contract shortfall) rounding to `100,000,000` contracts, $50 over budget, still `SIZED`.
2. **An absolute epsilon plus a hard post-condition loop** (`contracts = floor(q + 1e-9)`, then `while contracts * risk_per_contract > risk_budget: contracts -= 1` to walk any over-count back down). This fixed the rounding-up defect, but a *second* independent re-review found it could not terminate in practice at large scale: once `contracts` is large enough (the reported repro reached roughly `2.4e285`), float64 can no longer represent the difference between `contracts` and `contracts - 1` when each is multiplied by `risk_per_contract` -- `(contracts - 1) * risk_per_contract` and `contracts * risk_per_contract` become bit-for-bit identical -- so the loop's exit condition never becomes true and it decrements toward zero one candidate contract at a time. Not an infinite loop in the mathematical sense, but computationally indistinguishable from a hang.

Both defects came from trying to patch float64's inherent imprecision with more float64 heuristics. The fix is to stop doing float arithmetic for this comparison at all -- `Fraction` sidesteps the entire problem class rather than adding another layer meant to compensate for it.

**A consequence worth knowing:** this design is money-safe in a way that can look surprising at a glance. Take `risk_per_contract = 0.1 * 3 = 0.30000000000000004` (slightly *above* the mathematical 0.3) against a budget of exactly `0.9`: `3 * risk_per_contract = 0.9000000000000001`, which *exceeds* the 0.9 budget in float64 terms. Three contracts would cost more than the budget allows; the exact-rational floor correctly returns `2`, not `3` -- even though "3 times risk-per-contract is about 0.9" looks intuitively fine at a glance. This is the same "never round up" guarantee working correctly at a scale where naive intuition (and the old epsilon-based designs) got it wrong.

**Sanity cap on the result.** The exact-rational floor can no longer hang on an absurd input (e.g. a denormal-scale `--multiplier` override combined with a large `--account-size`), but it can still return a technically correct, economically meaningless answer -- the hang repro above computes an exact contract count with hundreds of digits. `CONTRACTS_SANITY_MAX` (1e12, four orders of magnitude above the largest legitimate case this skill's own tests exercise, ~1e8) rejects anything above it outright as `contracts_implausibly_large`, turning nonsense input into a clean `ConfigError` instead of a nonsensical `SIZED` report.

The tick-grid check (`is_on_tick_grid`) and the minimum-stop-distance guard (`meets_min_stop_distance`) are unrelated to this and keep their own *relative* float epsilon (unchanged) -- that construction is still correct for them, since tick sizes span multiple orders of magnitude across symbols and a ratio-based (not budget-based) comparison is what they're doing; the float-epsilon defects above were specific to the contract-count floor, where the "risk_budget / risk_per_contract" quotient's own scale set the failure mode.

**Minimum-stop-distance guard.** If the entry/stop distance is less than one tick, sizing is refused rather than silently computing an ultra-high, effectively meaningless contract count from a near-zero `risk_per_contract`. This closes the regime where `risk_per_contract` itself would be vanishingly small and even a tiny risk budget would imply an enormous (and nonsensical) contract count -- now doubly guarded by `CONTRACTS_SANITY_MAX` as well.

## Two Fail-Closed Classes: ConfigError vs. NO_TRADE

Every validation failure in this skill resolves to one of two outcomes, and which one depends on **who supplied the offending value** -- not on which rule was violated:

| Violation | Operator-supplied value (mode A `--stop`, or entry in either mode) | Gate-supplied value (mode B `--stop` = gate's `invalidation_level`) |
|---|---|---|
| Geometry (LONG stop >= entry, or SHORT stop <= entry) | `ConfigError` "direction_stop_mismatch" -- exit 2, no report | `NO_TRADE` "entry_on_wrong_side_of_stop" -- exit 0, report written |
| Stop closer than one tick | `ConfigError` "stop_too_close" -- exit 2 | `NO_TRADE` "gate_stop_too_close" -- exit 0 |
| Bond-family (ZT/ZF/ZN/ZB) off tick grid | `ConfigError` "entry_off_tick_grid" / "stop_off_tick_grid" -- exit 2 | `NO_TRADE` "gate_stop_off_tick_grid" -- exit 0 (entry is always operator-supplied, so an off-grid ENTRY is always a ConfigError even in mode B) |

This mirrors `contrarian-setup-gate`'s own convention for untrusted-file handling: a CLI usage mistake is the operator's problem (loud failure, no report, exit 2); a problem discovered inside an untrusted input FILE is never allowed to crash the tool -- it always produces a report naming exactly why sizing was refused (exit 0). Blaming the CLI invocation for a bad value that actually came from the gate's JSON file would be misleading, and would break the "every run either sizes or explains why not" contract every skill in this pipeline follows.

`risk_below_one_contract` (the risk budget can't afford even one contract at this stop distance) is **not** in this two-class table -- it is always `NO_TRADE`, in both modes, because it isn't anyone's mistake. It is the correct, expected output of risk-based sizing when the numbers simply don't support a position; widening the stop, raising `--risk-pct` (up to the 10% ceiling), or accepting no trade are all legitimate operator responses.

## Bond/Note Off-Grid Guard: Why It's Hard, Not Soft

ZT (2-Year), ZF (5-Year), ZN (10-Year), and ZB (30-Year) Treasury futures are the only fractional-notation family among the 23 core symbols -- they quote in 32nds (or, for ZN, 64ths; for ZF, quarter-32nds) of a point, conventionally written with an apostrophe: `110'16` means `110 + 16/32 = 110.50`. Every other symbol in the table quotes in plain decimal points.

The trap: an operator who mentally reads `110'16` and types `110.16` into `--entry` has entered a price that is **not on the tick grid at all** (`110.16 / 0.03125` is nowhere near an integer), and would have the sizer compute a stop distance using a price roughly 34 cents away from the intended one -- a small-looking but real, silent, wrong-money-math error. Every other symbol's off-grid price is legitimate (a mid-quote, an odd fill price) and only produces a warning; the bond family's off-grid price is treated as almost certainly a notation mistake and is a hard, fail-closed rejection instead, with a message that spells out the 32nds-to-decimal conversion.

## Worked Examples

### ES, LONG, explicit mode

```
entry = 5000.25, stop = 4980.00, multiplier = 50, tick_size = 0.25
stop_distance = 20.25 points = 81 ticks
risk_per_contract = 20.25 * 50 = $1,012.50
account_size = 100,000, risk_pct = 2.0% -> risk_budget = $2,000.00
contracts = floor(2000.00 / 1012.50) = floor(1.975...) = 1
total_risk = 1 * 1012.50 = $1,012.50 (1.01% of account)
```

At `risk_pct = 1.0%` instead, `risk_budget = $1,000.00 < risk_per_contract`, so `contracts = 0` -- `sizing_status: NO_TRADE`, `no_trade_reason: risk_below_one_contract`. The risk math (stop distance, risk per contract, risk budget) is still reported in full; only the trade itself is refused.

### B6, SHORT, gate handoff

A `contrarian-setup-gate` report for B6 reaches `READY_FOR_PLAN` with `direction: SHORT` and `invalidation_level: 1.3450` (the gate's stop reference). The operator supplies only the entry:

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --gate-json reports/contrarian_setup_gate_B6_2026-07-15.json \
  --entry 1.3400 --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/ --format both
```

B6 (British Pound, contract size GBP 62,500) is USD-quoted, so no `--fx-rate` is needed. `direction` and `stop` come entirely from the gate file; if `1.3400` (SHORT entry) were on the wrong side of `1.3450` (stop) -- i.e. the entry were above the stop for a SHORT -- the result would be `NO_TRADE` with reason `entry_on_wrong_side_of_stop`, exit 0, not a crash.

## Risk-Percentage Guardrails

`--risk-pct` accepts `(0, 10]`; values above `10` are an argparse-level usage error (no override). A value above `2.0` produces the `risk_pct_above_2` warning (never a rejection) -- consistent with `position-sizer`'s own 1-2% guideline for a single trade's risk. Futures leverage means the SAME percentage risk moves faster in dollar terms than an unlevered equity position of the same nominal size; this warning is a deliberately low bar.

## Margin Is Never Computed

The `margin_note` field is always the same static reminder text, never a computed number. Exchange initial/maintenance margin requirements are broker-specific and change with volatility regimes, sometimes intraday during stress -- a computed "margin estimate" would either be wrong the moment it's stale, or would require live broker data this skill deliberately does not fetch (fully offline, no API keys, no network). The issue that motivated this skill (#242) asked for a "margin estimate note"; this skill reads that as "a note ABOUT margin" (honest, never-stale) rather than "a computed estimate presented as a note" (which would rot). This interpretation was flagged explicitly for review rather than decided silently -- see the PR description.
