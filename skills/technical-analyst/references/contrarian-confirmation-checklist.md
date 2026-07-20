# Contrarian Confirmation Checklist (Shapiro Step 3)

## Overview

Step 3 of Jason Shapiro's COT contrarian process: once a market is flagged
crowded (`cot-contrarian-detector`, step 1) and, optionally, shown to have
failed to react to favorable news (`news-reaction-failure-analyzer`, step
2), this checklist confirms whether the WEEKLY chart itself is showing
price-action evidence of a reversal. It is the last check before entry
planning (step 4, still manual) and exit planning (step 5, still manual).

**This checklist is judged identically by two consumers**: Claude reading
a user-supplied weekly chart image (chart mode, `technical-analyst`'s
primary workflow) and `scripts/check_weekly_price_action.py` (the
data-driven fallback). The definitions below are written once and applied
the same way by both, so a chart-mode read and a script-mode read of the
same market should reach the same verdict. When they disagree, the
conservative-precedence rule (below) applies.

## Direction Convention

Fading a **CROWDED_LONG** market means seeking BEARISH reversal evidence
at or after UPSIDE extremes: watch highs, watch closes breaking below
prior lows, watch failed pushes above resistance. Fading a **CROWDED_SHORT**
market is the exact mirror: watch lows, watch closes breaking above prior
highs, watch failed pushes below support. Every rule below is stated for
CROWDED_LONG; swap high<->low and above<->below for CROWDED_SHORT.

All comparisons are **STRICT inequalities**. Equal-to-a-prior-extreme
never counts as a new extreme; a close exactly at a prior level never
counts as a reversal, breakout, or failure. This is deliberate: a market
that merely matches (not exceeds) a level has not actually generated new
evidence.

## Window Terminology

- **Swing-lookback weeks** (default 13): defines what counts as a "recent"
  high/low for the weekly key reversal trigger.
- **Extreme-lookback weeks** (default 52): defines what counts as a
  longer-horizon extreme, used by failed-extreme, failed-breakout, and the
  continuation veto, and as the confidence-HIGH bonus condition for weekly
  key reversal.
- **Signal-recency weeks** (default 4): a signal (a triggered check) older
  than this does not confirm. Only the FAILURE week counts as the signal
  for failed_breakout (see below), not the earlier breakout week.
- **Prior weeks strictly exclude the evaluation week itself** — "the prior
  N completed weeks" always means the N completed weeks immediately
  before the week being tested, never including it.
- **Window truncation is per-evaluated-week, not per-run.** When fewer
  completed weeks exist before an evaluated week than the configured
  window, the window truncates to whatever is available. Two different
  weeks within the same recency scan can have genuinely different amounts
  of prior history available (for example 26 vs. 29 weeks, right at the
  `min_weeks` floor) — the confidence-HIGH 52-week-extreme condition
  always reads the window size actually used by the ONE triggering week
  being reported, never any other week's value.
- `min_weeks` (default 30) is the hard floor: fewer completed weeks than
  this and the verdict is `INSUFFICIENT_DATA` (`insufficient_weekly_bars`)
  regardless of anything else.

## The Three Signal Checks

### 1. Weekly Key Reversal

The week's HIGH is a new swing-lookback high — STRICTLY greater than the
max high of the prior swing-lookback completed weeks — AND the week's
CLOSE is STRICTLY below the prior week's LOW.

Bullish mirror (CROWDED_SHORT): new swing-lookback LOW AND close STRICTLY
above the prior week's HIGH.

This is the only check that references TWO lookback windows: the
swing-lookback window drives the trigger itself, and the (larger)
extreme-lookback window is checked SEPARATELY, only to decide whether the
same new high/low also qualifies as an extreme of the full extreme-lookback
window — this second, stronger condition feeds the confidence-HIGH gate
below and never affects whether the check triggers at all.

### 2. Failed Extreme (intraweek poke-and-fail)

Within the signal-recency window, a week traded STRICTLY above the prior
extreme-lookback HIGH but CLOSED back BELOW that same prior high — the
market pushed into new territory intraweek and failed to hold it by the
close. Mirror for lows (CROWDED_SHORT).

Distinct from a key reversal: no requirement about the prior week's own
low/high, and it uses the extreme-lookback window, not the swing-lookback
window.

### 3. Failed Breakout (confirmed-then-rejected)

A weekly CLOSE above the prior extreme-lookback HIGH (a genuine CLOSING
breakout, not just an intraweek poke) at week B, followed within <=3
subsequent completed weeks by a weekly CLOSE back below that same
breakout level. Mirror down for CROWDED_SHORT.

**`week_of` on this check is the FAILURE week** (the close back through
the level), never the breakout week B itself — the breakout week only
appears inside the check's `detail` text. This matters for the
signal-recency window: only the FAILURE week needs to fall within
`signal_recency_weeks`; the breakout week B may be older. It also matters
for the continuation veto (below): because the breakout week is, by
construction, always strictly older than its own failure week, it can
never later be picked up as a "new closing extreme" that vetoes its own
signal (no self-veto).

Only the FIRST close back through the level after a given breakout counts
as that breakout's failure — a later close back through the same level is
not treated as a second, independent failure of the same breakout.

Worked example: breakout at week W, failure at week W+2, no later bars ->
CONFIRMED. Same breakout/failure, but a NEW closing high at week W+3
(within the recency window) -> NOT_CONFIRMED (`continuation_intact`), the
continuation veto fires.

## Continuation Veto

Independent of the three signal checks above: has the market set a new
CLOSING extreme in the crowd's direction (a new highest CLOSE for
CROWDED_LONG, relative to each evaluated week's own prior extreme-lookback
window of CLOSES — not intraweek highs) strictly more recently than the
newest triggered signal?

- If a signal triggered, the scan for a new closing extreme starts the
  week AFTER that signal's own `week_of` — so the signal week itself (and
  anything before it) can never self-veto.
- If NO signal triggered at all, the scan covers the full
  signal-recency window instead, so a market that just kept grinding to
  new highs with no reversal evidence anywhere gets the correct
  `continuation_intact` reason rather than the generic
  `no_reversal_evidence`.

## Swing Levels (fractal pivots, for the stop reference)

A **swing high** is a completed week whose HIGH is STRICTLY greater than
the highs of the 2 completed weeks on EACH side (a 5-week fractal). A
**swing low** mirrors on lows. `nearest` is the most recent such pivot
within the extreme-lookback window.

**Fallback**: if no fractal pivot exists anywhere in that window, fall
back to the max high (min low) of the (smaller) swing-lookback window
instead, flagged `fallback: true` so a consumer knows this is a weaker,
non-fractal substitute.

**`stop_reference`** follows the fade direction, not the crowd's
direction: fading a crowded LONG means going short, so the stop sits
ABOVE at the nearest swing HIGH; fading a crowded SHORT means going long,
so the stop sits BELOW at the nearest swing LOW.

## Verdict Synthesis (fail-closed)

1. Fewer than `min_weeks` completed weeks, or no usable price source ->
   `INSUFFICIENT_DATA` (`insufficient_weekly_bars` / `no_price_source`).
2. Continuation veto fired (a new closing extreme in the crowd's
   direction occurred after the newest signal, or with no signal at all
   within the recency window) -> `NOT_CONFIRMED` (`continuation_intact`).
   This ALWAYS wins over a triggered signal.
3. Otherwise, if any of the 3 signal checks triggered within the
   signal-recency window -> `CONFIRMED`, with `verdict_reason` naming
   whichever detector produced the newest triggered signal
   (`key_reversal` / `failed_extreme` / `failed_breakout`).
4. Otherwise -> `NOT_CONFIRMED` (`no_reversal_evidence`). Absence of
   evidence never confirms.

### Confidence

`HIGH` iff **either**:

- At least 2 DISTINCT detector types triggered within the recency window
  (the same detector firing does not count twice — this module only ever
  reports one, most-recent trigger per detector, so this is automatic);
  **or**
- The triggering `weekly_key_reversal`'s new high/low is ALSO an extreme
  of a FULL, untruncated (>=52-week) extreme-lookback window — i.e. its
  own `extreme_window_weeks_used >= 52` AND `is_full_window_extreme` is
  true.

Otherwise `MEDIUM`. `LOW` is reserved and never emitted in v1.

**A single-signal MEDIUM verdict is deliberately weak evidence.** One
weekly key reversal, one failed extreme, or one failed breakout, on its
own, is suggestive but not strong confirmation — treat a lone MEDIUM
signal as a reason to keep watching, not a reason to size up. The
`confidence` field is carried into the `handoff` block precisely so a
downstream consumer (`contrarian-setup-gate`, #241, not yet built) can
weigh single-signal evidence more cautiously than 2-signal or full-window
evidence.

## Output Contract (script mode; chart mode mirrors the same shape)

```yaml
symbol: BT
direction: CROWDED_LONG
mode: data # "chart" when Claude is reading a user-supplied chart image
verdict: CONFIRMED | NOT_CONFIRMED | INSUFFICIENT_DATA
confidence: HIGH | MEDIUM | LOW # LOW reserved, never emitted in v1
verdict_reason: key_reversal | failed_extreme | failed_breakout |
  continuation_intact | no_reversal_evidence |
  insufficient_weekly_bars | no_price_source | ...
checks:
  weekly_key_reversal:
    { triggered, week_of, swing_window_weeks_used,
      extreme_window_weeks_used, is_full_window_extreme, detail }
  failed_extreme: { triggered, attempted_level, week_of, window_weeks_used, detail }
  failed_breakout: { triggered, breakout_level, week_of, window_weeks_used, detail }
  continuation: { new_closing_extreme_with_crowd, week_of, window_weeks_used }
swing_levels:
  nearest_swing_high: { price, week_of, fallback }
  nearest_swing_low: { price, week_of, fallback }
  stop_reference: 0.0
weekly_bars_used: 52
last_completed_week: 2026-07-06
handoff: # consumed by contrarian-setup-gate (#241)
  price_action: { verdict, confidence, stop_reference, report_path }
run_context:
  {
    price_symbol,
    price_source,
    proxy_used,
    as_of,
    lookbacks,
    recency,
    min_weeks,
    detector_json,
    detector_age_days,
    schema_version,
  }
```

Output filenames: `ta_confirmation_<SYMBOL>_<as-of>.json` /
`ta_confirmation_<SYMBOL>_<as-of>.md`.

**Invariant: `checks` (and `swing_levels`) is `null` whenever `verdict:
INSUFFICIENT_DATA`** — a single, consistent shape regardless of the
specific reason (`no_price_source`, `insufficient_weekly_bars`, any
detector-json refusal reason, ...). This holds for every INSUFFICIENT_DATA
path, both the ones the CLI short-circuits on before ever fetching price
data and the one `run_weekly_price_action()` reaches after a successful
fetch but too little history (`n < min_weeks`). A downstream consumer
(`contrarian-setup-gate`, #241) can check `verdict` alone before deciding
whether `checks.*` is safe to read, without branching on
`verdict_reason` or which code path produced it — never a placeholder
dict of all-`false` checks.

## Chart-Mode Walkthrough

When a user supplies a weekly chart image and asks for a contrarian
confirmation read (rather than, or in addition to, running the script):

1. Confirm the crowd direction being faded (CROWDED_LONG / CROWDED_SHORT)
   — from the user, or from a prior `cot-contrarian-detector` /
   `news-reaction-failure-analyzer` result.
2. Visually scan the most recent `signal_recency_weeks` (default 4) weekly
   bars for each of the 3 signal patterns above, using the SAME strict
   definitions (a new swing-lookback extreme, a close through the prior
   week's opposite level, an intraweek poke that fails, a closing
   breakout that fails within 3 weeks).
3. Check whether the market has since printed a new CLOSING extreme in the
   crowd's direction more recently than any pattern found in step 2 (the
   continuation veto).
4. Identify the nearest fractal swing high/low for the stop reference.
5. Emit the SAME `mode: chart` YAML block as the script (§ above), filling
   `checks.*` from the visual read; `window_weeks_used` fields may be
   approximate (chart mode cannot count bars as precisely as the script)
   — note this explicitly in `detail` rather than fabricating a false
   precision.

## Conservative Disagreement Rule

If BOTH chart mode and script mode produce a result for the same
symbol/direction and their verdicts DISAGREE, the final verdict is
**`NOT_CONFIRMED`** with `verdict_reason: mode_disagreement`, and both
sub-results are attached for the user to review side by side — never
silently pick one mode over the other.

If one mode returns `INSUFFICIENT_DATA` and the other returns a clean
verdict (`CONFIRMED` or `NOT_CONFIRMED`), the clean verdict stands; note
the other mode's insufficiency rather than treating it as a disagreement.

## Guardrails

- **Verdict-only — never a trade recommendation on its own.** This
  confirms step 3 of 5. Entry (step 4) and exit (step 5) are still manual
  and still required, and position sizing belongs to `position-sizer` /
  `futures-position-sizer`, not this checklist.
- **`INSUFFICIENT_DATA` never advances the pipeline.** Fewer than
  `min_weeks` completed weeks, no usable price source, or a
  `--detector-json` that is unreadable (missing/can't be opened),
  syntactically invalid, structurally malformed, stale, future-dated, or
  carries a non-`CROWDED_*` classification all fail closed (reasons
  `detector_json_unreadable` / `detector_json_parse_error` /
  `malformed_detector_json` / `detector_json_stale` /
  `detector_future_data_date` / `not_crowded` respectively) — never a
  crash, never a bare non-zero exit with no report, never a forced call on
  inadequate data.
- **Weekly timeframe only.** This checklist is defined entirely in terms
  of completed ISO calendar weeks; it says nothing about daily or
  intraday price action.
- **The existing chart-analysis workflow is unchanged.** This mode only
  activates on an explicit contrarian-confirmation request (typically
  following `cot-contrarian-detector` and/or
  `news-reaction-failure-analyzer`); a plain "analyze this chart" request
  still runs the skill's original pure technical-analysis workflow.
- **A single-signal MEDIUM verdict is weak evidence** — see the
  Confidence section above. Do not treat it the same as a HIGH-confidence,
  2-signal or full-window-extreme confirmation.
