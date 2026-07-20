# Jason Shapiro's COT Contrarian Methodology

## Overview

Jason Shapiro is a discretionary futures trader whose approach is documented
in Jack Schwager's *Unknown Market Wizards* (2020), Chapter 2, "The
Contrarian." His edge is built on a simple observation: retail and
speculative trend-following flows tend to be maximally positioned at trend
*exhaustion*, not trend *inception* — because trend followers only get
maximally long or short after a trend has run far enough to convince them
it's real. By the time everyone who wants to be long is long, there is no
incremental buyer left to push price higher, and the market becomes
vulnerable to reversal.

Shapiro's process has five steps. This skill automates step 1 only. Steps 2-5
require news judgment, chart reading, and discretionary risk management, and
are documented here as the manual process to guide the user through.

## The Five Steps

### Step 1: Crowding Detection (AUTOMATED by this skill)

Identify markets where large speculators ("non-commercial" traders in CFTC
terminology — hedge funds, CTAs, momentum funds) are at or near an extreme of
their net positioning over a multi-year lookback. This skill computes a COT
Index (see `cot-index-calculation.md`) over a 156-week (3-year) window and
flags markets where the index is >= 90 (crowded long) or <= 10 (crowded
short).

**Why speculators, not commercials:** Commercial traders (producers, end
users, banks hedging exposure) transact for structural/hedging reasons tied
to their business, not because they believe the market is about to move.
Their positioning reflects supply-chain economics, not crowd psychology.
Speculators, by contrast, are directional bettors — their positioning *is*
the crowd. Shapiro's edge specifically targets fading the speculative crowd,
because commercials being "extreme" carries no comparable behavioral signal.

**Why a 3-year lookback:** A COT Index measures where current positioning
sits relative to its own recent range. Too short a lookback (a few months)
produces false extremes in choppy, range-bound markets. Too long (10+ years)
mixes structurally different regimes (e.g., pre- and post-2008 rate
environments) and can understate a genuine extreme. Three years is the
common convention in COT-index literature and crowdedmarketreport.com's
public methodology — long enough to span multiple full cycles, short enough
to stay regime-relevant.

### Step 2: News Failure (MANUAL — Claude guides via WebSearch)

This is the core of Shapiro's edge and the step most traders skip. Once a
market is flagged as crowded, check whether recent news that *should* have
been favorable to the crowd's direction failed to move price the expected
way.

- **Crowded long + bullish news + no rally (or a fade)** → the buying power
  is exhausted; the crowd has nothing left to push price higher even on good
  news. This is bearish confirmation for a contrarian short.
- **Crowded short + bearish news + no decline (or a rally)** → the selling
  power is exhausted. This is bullish confirmation for a contrarian long.

**Example (illustrative):** Large speculators are crowded long on the S&P
500 (COT Index 95+). A strong jobs report or dovish Fed surprise hits — both
textbook bullish catalysts — and the index barely budges, or sells off into
the news. That non-reaction is the tell: everyone who was going to buy on
good news already has.

**How to check:** Use WebSearch for the market's major news catalysts over
the trailing 1-2 weeks (economic releases, central bank decisions, earnings
for equity-index futures, OPEC/inventory data for energy, etc.), then compare
the news direction to the actual price reaction on that day/week. A
significant *mismatch* (good news, flat/down price; bad news, flat/up price)
is the signal, not the news itself.

### Step 3: Price-Action Confirmation (MANUAL — Claude guides via chart reading)

Look for a weekly-chart reversal signal that corroborates the crowding +
news-failure read:
- A failure to make a new high (crowded long) or new low (crowded short)
  despite the prevailing trend still being intact on paper
- A weekly reversal candle (e.g., an outside week, a key reversal, a
  failed breakout that closes back inside the prior range)
- Loss of a key trendline or moving average that the trend had respected

This step exists because news failure alone can be noisy — requiring price
to actually confirm the exhaustion reduces false positives.

### Step 4: Entry (MANUAL — Claude guides via position-sizer skill)

Enter against the crowd (short a crowded-long market, long a crowded-short
market) once steps 2 and 3 both confirm. Use a fixed, small risk-per-trade
size and place the stop at the recent swing extreme (the high the crowd
formed, for a short; the low, for a long) — if the crowd's positioning
extreme is actually still intact, the trade thesis is wrong and should be
cut quickly. Route sizing through the `position-sizer` skill for
consistent, risk-based share/contract counts.

### Step 5: Exit (MANUAL)

Two exit triggers:
- **Positioning normalizes** — the COT Index drifts back toward 50 (neutral)
  over subsequent weekly releases, indicating the crowd has unwound and the
  edge has played out.
- **Stop hit** — price reclaims the crowd's extreme, invalidating the
  exhaustion thesis.

There is no fixed profit target in Shapiro's framework; the position is
managed against the positioning data itself, re-checked weekly as new COT
reports are published.

## What This Skill Automates vs. What Stays Manual

| Step | Automated? | How |
|---|---|---|
| 1. Crowding detection | Yes | `scripts/screen_cot_crowding.py` computes COT Index per market and classifies CROWDED_LONG/SHORT/NEUTRAL |
| 2. News failure | No | Claude uses WebSearch on the flagged market's recent catalysts and compares to price reaction |
| 3. Price-action confirmation | No | Claude reads the weekly chart (via `technical-analyst` skill or user-provided chart) for a reversal signal |
| 4. Entry | No | Claude sizes via `position-sizer`, places stop at the crowd's swing extreme |
| 5. Exit | No | Claude monitors subsequent weekly COT releases for normalization, or the stop |

## The 3-Day Publication Lag

The CFTC's COT report is published every Friday at approximately 3:30pm ET,
containing positions as of the **prior Tuesday's close**. This means the
data is always at least 3 calendar days old on publication day, and up to 9
days old by the following Friday (just before the next release). Two
practical implications:

1. **Never treat COT data as a real-time signal.** A crowd can unwind
   materially in the days between the Tuesday snapshot and when you're
   reading the report.
2. **News-failure checks (step 2) should focus on news from around and after
   the Tuesday snapshot date**, not the publication date — that's the window
   the positioning data actually reflects.

## Participation and Open Interest Context

A COT Index extreme means more when it comes with meaningful participation.
Two markets can both show a 95 COT Index, but one may have 10 large
speculators holding the extreme and the other 200 — the latter is a broader,
more durable crowd. The screener surfaces `traders_long`/`traders_short`
(trader counts) and `open_interest` alongside the index so this context isn't
lost; a large but thin-participation extreme is more prone to a false
signal than a large, broad-participation one.

## Sources

- Jack D. Schwager, *Unknown Market Wizards* (2020), Chapter 2: "Jason
  Shapiro: The Contrarian"
- crowdedmarketreport.com — public COT Index methodology and market
  commentary (Shapiro's own site)
