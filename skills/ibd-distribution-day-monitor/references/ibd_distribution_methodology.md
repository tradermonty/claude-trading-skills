# IBD Distribution Day Methodology

## Origin
Investor's Business Daily (IBD) and William O'Neil's CAN SLIM framework popularized the concept that institutional selling can be tracked by counting *Distribution Days* on major indexes. A cluster of distribution days is interpreted as a sign that institutions are unloading positions, often preceding a market correction.

## Detection Rule
A Distribution Day is detected when both conditions hold for the daily bar of an index or large ETF proxy (e.g. QQQ, SPY):

1. **Decline:** Today's close is at least 0.2% below yesterday's close (this skill uses `pct_change <= -0.002`).
2. **Higher Volume:** Today's volume is greater than the reference session's volume. Normally the reference is yesterday. On an early-close (half-day) session and the session after it, the reference is the most recent full-length session, resolved with the vendored `scripts/_market_calendar.py` XNYS calendar. The affected record carries `volume_reference: "previous_full_session"` and `volume_reference_date`.

A small *epsilon* is applied at the boundary so that floating-point noise around 0.2% does not cause flaky detection.

## Removal Rules
A Distribution Day is removed from the active count when either:

- **Expiration:** More than `expiration_sessions` (default 25) trading sessions have elapsed since the Distribution Day occurred.
- **Invalidation:** The index has gained `invalidation_gain_pct` (default 5%) from the Distribution Day close.

This skill records the **first chronological post-DD session** to cross the invalidation threshold so that the audit trail shows exactly when invalidation happened and how many sessions after the DD.

## Invalidation Boundary Choices

The 5% invalidation rule uses `invalidation_price_source` ("high" or "close"):

- `high` (default, more conservative): the post-DD intraday high crossing 5% is enough to invalidate.
- `close`: only post-DD closing prices count.

The Distribution Day's own intraday high is **never** used to invalidate it (`invalidation_session_scope: after_distribution_day_only`). IBD's rule is "5% gain from the Distribution Day close", so DD-day high vs DD close cannot represent post-DD strength.

If the 5% threshold is reached **after** the expiration window (more than 25 sessions later), the record is treated as `expired`, not `invalidated`. The implementation enforces this by limiting the invalidation scan to the expiration window.

## Counting Buckets

`d5_count`, `d15_count`, and `d25_count` count active records satisfying `age_sessions <= N`. Note this includes age 0..N inclusive (N+1 sessions). Reports phrase this as "within N elapsed sessions" rather than "直近 N 取引日" because the latter usually means age 0..N-1.

The d25 bucket and the 25-session expiration are aligned: a record at exactly age=25 is still active and still counted in d25. A record at age=26 is expired and excluded from d25.

## Cluster Interpretation
General IBD heuristics:

- 4-5 distribution days in 4-5 weeks is a meaningful warning.
- 6+ distribution days is typically a "Market in Correction" signal.
- A cluster concentrated in the last 5-10 sessions matters more than evenly distributed days.

This skill encodes a deterministic translation:

| Risk | Trigger |
|------|---------|
| NORMAL | `d25 <= 2` |
| CAUTION | `d25 >= 3` |
| HIGH | `d25 >= 5` OR `d15 >= 3` OR `d5 >= 2` |
| SEVERE | `d25 >= 6` OR `d15 >= 4` OR (`market_below_21ema_or_50ma` AND `d25 >= 5`) |

The MA filter (`market_below_21ema_or_50ma`) only escalates to SEVERE when both the 21EMA and the 50SMA are below the latest close. If either MA cannot be computed (insufficient data), the filter is `None` and SEVERE escalation is skipped — see `audit_flags = ["insufficient_data_for_moving_average"]`.

## TQQQ Considerations
TQQQ targets 3x daily Nasdaq returns. In drawn-out correction phases, daily compounding of negative returns produces deep drawdowns even if cumulative Nasdaq returns are mild. Holding 100% TQQQ through a HIGH/SEVERE state has historically produced material left-tail risk. The exposure policy (see `tqqq_exposure_policy.md`) cuts TQQQ exposure faster than QQQ for the same risk level.

## What This Skill Does NOT Do
- It does not declare a market top. Tops are confirmed by additional signals (broken 50DMA on the major index, leadership breakdown, etc.).
- It does not produce buy signals. Use `ftd-detector` (Follow-Through Day) for the offensive counterpart.
- It does not act on intraday volume. Stalling days (volume up, price flat) are intentionally out of scope for v1.
- It does not execute trades.

## References
- William J. O'Neil, *How to Make Money in Stocks*, McGraw-Hill (multiple editions).
- IBD Big Picture columns: distribution day counts and cluster interpretations.
