# News Failure Patterns (Shapiro Step 2)

## Overview

Step 2 of Jason Shapiro's COT contrarian process (see
`cot-contrarian-detector/references/shapiro-methodology.md` for the full
5-step process) is the core edge: once a market is crowded, check whether
it FAILED to react to news that should have rewarded the crowd. This
document covers what qualifies as a relevant event, how to curate an
events JSON via WebSearch, and the statistical rationale behind the
verdict this skill computes.

## What Qualifies as a Relevant Event

A relevant event is a discrete, dateable piece of news whose
`expected_impact` matches the crowd's `expected_direction`
(CROWDED_LONG → BULLISH news; CROWDED_SHORT → BEARISH news). Examples:

- **Macro data releases** favorable to the crowd's direction (a strong
  jobs report or dovish Fed surprise for a crowded-long equity index; a
  hot CPI print or hawkish Fed surprise for a crowded-short bond market)
- **Company/sector-specific catalysts** for single-name-adjacent futures
  (e.g. a major constituent's earnings beat for an equity index future)
- **Supply/demand shocks** for commodities (an OPEC production cut for
  crowded-short crude; a bumper-crop report for crowded-long grains)
- **Central bank/policy surprises** in the crowd's favor

Counter-direction events (news that would hurt the crowd) are recorded for
context but excluded from the verdict — mixing them in would test the
wrong thing (whether the market reacted to bad news, not whether it failed
to react to good news).

## Worked Example (illustrative)

Large speculators are crowded long on the S&P 500 (COT Index 95+, per
`cot-contrarian-detector`). Over the following two weeks: a strong jobs
report, a dovish Fed comment, and a mega-cap earnings beat all hit — three
genuinely bullish catalysts. If the index barely moves, or sells off, on
all three, that's the tell: everyone who was going to buy on good news
already has. `verdict: CONFIRMED` here means "the market has stopped
rewarding good news for the crowd's direction" — not a prediction of what
happens next; steps 3-5 (price action, entry, exit) still apply.

## Source Hierarchy (4 tiers)

Matches the tier structure used elsewhere in this repo (see
`kanchi-dividend-sop`'s Step 6 event-scan convention) and the issue's
`source_tier` contract:

1. **`primary`** — the issuer/company/agency's own release (press release,
   IR page, official statement)
2. **`official`** — government/regulatory statistics or filings (BLS, Fed,
   SEC, Treasury, central bank statements)
3. **`wire`** — reputable wire services (Reuters, Bloomberg, AP, Dow Jones)
4. **`portal`** — finance news portals/aggregators (secondary only — use
   when primary/official/wire coverage isn't available, and prefer a
   portal article that itself cites a primary source)

Always prefer the highest tier available for a given event; record the
tier used in `source_tier` so the report's evidence table shows source
quality alongside the reaction data.

## Events JSON Curation Guide

WebSearch news in the CLI's `--window-days` window (default 10 days
before `--as-of`). For each candidate event:

1. Confirm it's genuinely dateable (a specific release date/time, not a
   vague "recent trend")
2. Classify `expected_impact` (BULLISH/BEARISH) from the crowd's
   perspective — ask "would a rational holder of the crowd's position see
   this as good news?"
3. Record `event_time` in ISO8601 **with an explicit UTC offset**
   (`2026-07-08T14:30:00-04:00`) — a naive timestamp is rejected by the
   CLI (dropped with reason `unparsable_event_time`) rather than guessing
   at an implicit timezone
4. Cite the real `source_url` and `source_tier` — **never fabricate a URL
   or an event**. If WebSearch can't find a genuinely relevant event in
   the window, that's a valid (if less useful) outcome — don't pad the
   list to hit `--min-events`

### Template

```json
{
  "schema_version": "1.0",
  "symbol": "ES",
  "curated_at": "2026-07-12",
  "events": [
    {
      "event_id": "e1",
      "event": "Fed cuts rates 25bp, signals more cuts ahead",
      "event_time": "2026-07-08T14:30:00-04:00",
      "source_url": "https://www.federalreserve.gov/newsevents/pressreleases/...",
      "source_tier": "official",
      "expected_impact": "BULLISH",
      "notes": "Dovish surprise vs. consensus hold"
    }
  ]
}
```

Save as `reports/nrf_events_<symbol>_<as-of-date>.json` and pass via
`--events-json`.

## Verdict Thresholds (statistical rationale)

**Why not a naive failure-ratio?** An earlier design flagged CONFIRMED
whenever fewer than half of relevant events "responded" (moved favorably
for the crowd). Under pure noise, P(an individual event's z-score < the
response threshold) is roughly 69%, so that naive rule CONFIRMed on random
noise 48-83% of the time depending on sample size — statistically
worthless. See `cot-contrarian-detector`-style design notes; this is the
same class of flaw a naive threshold rule falls into.

**The drift-significance design** (implemented in
`scripts/reaction_math.py`) instead requires the market to have moved
*significantly against* favorable news, not merely "not enough with it":

- `drift_stat = sqrt(n) * mean(direction-adjusted zscore_3d)` over the
  usable, clustered, relevant events (n = number of clusters, not raw
  event count — see "Event Clustering" below)
- Under the null hypothesis (no real drift, iid noise), `drift_stat` is
  approximately standard normal
- `CONFIRMED` iff `drift_stat <= -drift_z` AND `responded_ratio <= 0.25`
  (both conditions — a strong drift alone isn't enough if a meaningful
  fraction of individual events still "responded")
- `drift_z` default is **1.45**, chosen (over 1.0, 1.28, and 1.35, all
  rejected) so the combined null false-CONFIRMED rate stays under a
  documented bound, verified by a seeded, ≥50,000-trial-per-n Monte Carlo
  test — see `scripts/reaction_math.py`'s `DRIFT_Z_DEFAULT` constant for
  the exhaustive rationale comment and
  `scripts/tests/test_reaction_math.py` for the tests themselves

**Measured null false-CONFIRMED rates at drift_z=1.45** (n ∈ {3,4,5,8},
50,000 trials per n per scenario, seeded for reproducibility):

| Scenario | Bound | Worst measured | Gate |
|---|---|---|---|
| i.i.d. N(0,1) noise | < 8% | 7.28-7.30% (varies by MC run) | Hard-asserted |
| AR(1) lag-1, ρ=0.1 (residual correlation after clustering) | < 10% | 9.00% (n=8); range 8.08-9.00% | Hard-asserted |
| AR(1) lag-1, ρ=0.3 (extreme correlation stress) | informational | 13.11% (n=8); range 10.84-13.11% | Measured only, sanity ceiling < 20% |

**Why ρ=0.1 is hard-gated and ρ=0.3 is informational, not hard-gated:**
the clustering rule (below) already removes the correlation a window
overlap would produce — that is precisely the failure mode a correlation
stress test is meant to probe. Across *non-overlapping* 3-day cluster
windows, a lag-1 correlation of ρ=0.3 is roughly an order of magnitude
stronger than the empirical signed-return autocorrelation of liquid
futures contracts. ρ=0.1 remains conservative relative to that empirical
reality while still exercising the realistic residual channel (e.g. two
related headlines a week apart, outside the clustering window but still
weakly correlated), so it is the asserted regression gate. ρ=0.3 is kept
and measured — not silently dropped — as a documented v1 residual risk:
if real-world correlation between non-clustered events is ever that
extreme, the null false-CONFIRMED rate could rise into the 11-13% range.
**Escape hatch:** `--drift-z 1.75` restores a <10% null rate even under
the ρ=0.3 stress scenario (verified), for users who want that extra
margin — at the cost of reduced sensitivity to genuine news-failure
signals (a stricter threshold also misses some real drift, not just
noise).

## Event Clustering (Independence Guard)

Relevant events whose 3-trading-day return windows share any trading day
are collapsed into one cluster, counted once toward `n`, using the
earliest effective date. Rationale: overlapping windows produce
correlated z-scores (the same price move gets counted as "evidence" for
multiple events), which would silently inflate `n` and violate the
approximately-normal-under-the-null assumption the verdict test relies on.

**Pinned rule: a cluster's z3 is the z3 already computed at the cluster's
own effective date — the earliest member's window z3. Member z3 values
are never averaged into the cluster's contribution to `drift_stat`.**
Averaging would mix z-scores computed over different, overlapping return
windows into a statistic that isn't obviously more meaningful than "what
happened in the window starting at the cluster's own effective date," and
would complicate the variance properties the Monte Carlo verification
above relies on. Cluster membership — including every member's own
individual z3 — is always shown in the evidence (`cluster_members[]`) so
nothing is hidden, even though only the earliest member's z3 drives the
verdict.

## Effective Date and Return Windows

- **Effective date:** the first trading date at/after the event. Events at
  or after 16:00 ET count from the next trading day (the close has
  already happened). Weekend/holiday gaps degrade naturally to the next
  available trading bar — never a crash.
- **Returns:** `close(eff + k trading days) / close(eff - 1 trading day) -
  1`, for k ∈ {1, 3} — spans the pre-event baseline through k days after
  the effective date, capturing the full initial reaction window
  (including any overnight/opening gap).
- **Z-scores:** `daily_stdev` is the sample stdev of trailing daily
  returns ending the day before the event (60-trading-day lookback by
  default). `zscore_1d = return_1d / daily_stdev`; `zscore_3d = return_3d
  / (daily_stdev * sqrt(3))` — the sqrt(3) horizon scaling is mandatory
  (a k-day return's noise scales with sqrt(k) under a random-walk
  assumption).

## What Stays Manual (Shapiro Steps 3-5)

This skill automates step 2 only. Steps 3 (price-action confirmation), 4
(entry), and 5 (exit) remain manual — see
`cot-contrarian-detector/references/shapiro-methodology.md`. A CONFIRMED
verdict here is a necessary but not sufficient condition for a contrarian
trade.
