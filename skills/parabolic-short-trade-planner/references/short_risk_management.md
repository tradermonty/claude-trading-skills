# Short Risk Management

## SEC Rule 201 (Short Sale Restriction)

Triggered when a security's regular-session intraday price drops 10%
or more from the prior day's regular-session close. While active:

- New short sales are restricted to prices ABOVE the national best bid
  (the "uptick rule").
- The restriction holds for the rest of the trading day **and** the
  full next trading day.

**Implementation note**: this skill inherits `prior_regular_close` from
Phase 1's `key_levels.prior_close` (sourced from FMP's
`historical-price-eod/full`, which is the regular-session 4:00 PM ET
close). It does NOT use FMP's quote endpoint `previousClose`, which
can drift to the aftermarket print.

`ssr_state_tracker.py` persists per-symbol state to
`state/parabolic_short/ssr_state_<ticker>_<date>.json` so today's
`ssr_triggered_today` rolls forward to tomorrow's
`ssr_carryover_from_prior_day`.

## Borrow inventory: Alpaca specifics

Alpaca only allows new short opens on Easy-To-Borrow (ETB) names. The
adapter encodes this exactly:

```
can_open_new_short = shortable AND easy_to_borrow
borrow_fee_apr     = 0.0 if easy_to_borrow else None
manual_locate_required = True   # always
```

A name that is `shortable=True` but `easy_to_borrow=False` (HTB) cannot
be opened on Alpaca regardless of locate. Phase 2 marks these as
`borrow_inventory_unavailable` (a hard blocker) and renders the plan
as `plan_status: watch_only`.

`manual_locate_required` is True even on ETB names. The trader still
confirms locate at the broker before entry — it's an advisory reason,
not blocking, so plans for ETB names stay actionable.

## Position sizing

The `size_recipe_builder.py` outputs:

- `risk_usd` — per-trade risk in USD (account_size × risk_bps/10000).
- `max_position_value_usd` — per-symbol position cap (account_size ×
  max_position_pct/100), tightened if `current_short_exposure` is high.
- `shares_formula` — string form of the formula. Phase 3 evaluates it
  at trigger fire when actual entry/stop are known.
- `exposure_cap_applied` — True if the per-symbol cap was tightened
  because the aggregate short-book budget was already mostly used.
- `remaining_short_exposure_capacity_usd` — how much short-book
  headroom is left.

This deliberately excludes a fixed share count. ORL / first-red /
VWAP-fail entries only have known prices intraday, so committing to a
share count pre-market would be inaccurate.

## Daily loss limits

Not enforced in this MVP. The trader is responsible for honoring
account-level circuit breakers. A future revision can add a `state/`
file recording realized P&L and reject new plans when the daily loss
limit is hit.
