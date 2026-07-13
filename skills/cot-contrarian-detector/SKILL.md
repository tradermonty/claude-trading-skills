---
name: cot-contrarian-detector
description: Detect crowded speculative positioning in CFTC futures markets (COT report analysis) to find contrarian setups using Jason Shapiro's methodology. Screens large-speculator ("non-commercial") net positioning across 65 futures markets (indices, rates, FX, metals, energy, crypto) via the FMP Commitment of Traders API, computes a 3-year and 26-week COT Index per market, and classifies extremes as CROWDED_LONG / CROWDED_SHORT. Use when the user asks about COT report analysis, crowded positioning, "who is trapped", speculative positioning extremes, contrarian futures setups, or wants to run Jason Shapiro-style analysis. This skill automates crowding DETECTION only (step 1 of 5) — it does not generate trade signals by itself.
---

# COT Contrarian Detector

## Overview

Implements step 1 of Jason Shapiro's COT (Commitment of Traders) contrarian
process: detect when large speculators are crowded into one side of a futures
market. Crowded positioning is a *precondition* for a contrarian trade, not a
trade signal — a market only becomes tradable once crowding is confirmed by a
news failure and price-action reversal (steps 2-3), which this skill guides
the user through manually.

**Core thesis (Shapiro):** Large speculators (hedge funds, CTAs, momentum
traders) tend to be maximally positioned at trend exhaustion, not trend
inception. When they are already crowded onto one side, the next big move is
statistically more likely to run them over than to reward them further. Fade
the *speculators*, not the commercials (commercials hedge for structural
reasons and are not a crowd-psychology signal).

## When to Use This Skill

**English:**
- "What markets are the speculators crowded into right now?"
- "Run a COT report analysis" / "Show me COT positioning extremes"
- "Is anyone 'trapped' in gold / the dollar / bonds right now?"
- User wants to find contrarian futures setups
- User asks for a Jason Shapiro-style COT screen

**Japanese:**
- 「COTレポートで買われすぎ・売られすぎのポジションを調べて」
- 「投機筋が偏っている市場は？」
- 「ジェイソン・シャピロ式の逆張り分析をして」

**Do NOT use when:**
- The user wants a trade signal right now — crowding alone is not
  actionable; see Guardrails below
- The user is asking about individual equities — COT reports cover CFTC
  futures markets only (indices, rates, FX, metals, energy, agri, crypto),
  not single stocks

## Prerequisites

- **FMP API Key:** Required. Set `FMP_API_KEY` environment variable or pass
  `--api-key`. **COT endpoints require an FMP Premium+ plan** — a free-tier
  key will not have access.
- **Python 3.9+** with `requests` installed.
- **API Budget:** One call per market (23 for `--core`, up to ~65 for the
  full universe), plus one call for the market list when neither `--symbols`
  nor `--core` is given.

## Workflow

### Phase 1: Run the crowding screen

```bash
# Curated core futures universe (23 liquid/representative markets)
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --core --output-dir reports/

# Explicit symbols
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --symbols "ES,GC,CL" --output-dir reports/

# Full universe (all ~65 markets FMP's COT list covers)
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --output-dir reports/
```

The script fetches each market's weekly legacy COT report (large-speculator
long/short positions), computes a 156-week (3-year) and 26-week COT Index per
market, and classifies extremes:

- `CROWDED_LONG` — COT Index >= 90 (near the 3-year net-long high)
- `CROWDED_SHORT` — COT Index <= 10 (near the 3-year net-short high)
- `NEUTRAL` — everything in between

Markets with insufficient history to compute the index are never silently
dropped — they appear in a `skipped` list with the reason (e.g. "insufficient
history: 40/156 weeks").

### Phase 2: Present the crowding report

Present the generated Markdown report, highlighting:
- Which markets are `CROWDED_LONG` / `CROWDED_SHORT` and by how much
- The 26-week index for context (is the crowding fresh or aging?)
- Week-over-week net-position swings (fast-moving crowds are more fragile)
- The methodology note and disclaimer — crowding is not a trade signal

### Phase 3: Guide steps 2-5 manually (Shapiro process)

For any `CROWDED_LONG` / `CROWDED_SHORT` market the user wants to pursue,
load `references/shapiro-methodology.md` and walk through the remaining
steps — these are **not automated**:

1. ~~Crowding detection~~ (done — this skill)
2. **News failure** — use WebSearch to check whether recent news favorable to
   the crowd's direction failed to move price the way the crowd would expect
   (e.g. crowded-long market doesn't rally on bullish news). This is the core
   edge and the most important manual confirmation.
3. **Price-action confirmation** — check the weekly chart for a reversal
   pattern or a failure at a new high/low.
4. **Entry** — against the crowd, with a stop at the recent swing extreme and
   small, fixed-risk sizing (see `position-sizer` skill).
5. **Exit** — when positioning normalizes toward neutral (COT Index back
   toward 50) or the stop is hit.

Never recommend an entry from crowding alone — steps 2 and 3 must both
confirm first.

## Output

- **JSON:** `reports/cot_crowding_<as-of-date>.json` — machine-readable, with
  a `run_context` block (schema_version, params, universe, data_date) plus
  `markets` (ranked results) and `skipped` (never silently dropped).
- **Markdown:** `reports/cot_crowding_<as-of-date>.md` — human-readable
  report with Crowded Long / Crowded Short / Full Ranking / Week-over-Week
  Swings / Skipped Markets / Methodology sections.

## Cadence

CFTC publishes the COT report **Fridays ~3:30pm ET**, with positions as of
the **prior Tuesday** — data is always 3+ days old by the time it's
published, and up to 9 days old by the following Friday. Run this skill:
- **Weekly**, after Friday's publication or over the weekend, for a fresh
  read
- **Ad hoc**, when the user asks about a specific market's positioning —
  the underlying data will be from the most recent Friday release either way

## Guardrails

- **Crowdedness alone is NOT a trade signal.** It is a precondition. Never
  suggest an entry without steps 2 (news failure) and 3 (price action) from
  `references/shapiro-methodology.md` also confirming.
- **Data is lagged.** COT positions are 3-9 days old by the time they're
  read; do not treat them as a real-time signal.
- **Fade speculators, not commercials.** This skill only looks at
  non-commercial ("large speculator") positioning — commercial hedging flows
  are structurally different and not a crowd-psychology signal.
- **Not investment advice.** All output is for research/educational purposes.

## Resources

### `references/shapiro-methodology.md`
The full 5-step process (crowding → news failure → price action → entry →
exit), why speculators (not commercials) are the fade target, the 3-day
publication lag caveat, and a table of what this skill automates vs. what
stays manual. Load this whenever guiding a user past step 1.

### `references/cot-index-calculation.md`
The COT Index formula, lookback rationale (156w primary / 26w context),
extreme threshold sensitivity, open-interest normalization rationale, the
legacy-vs-disaggregated report distinction (this skill uses the legacy
report's non-commercial = large-speculator fields), and a glossary of the FMP
COT API field names consumed by `scripts/cot_index.py`.

### When to Load References
- **First use / explaining the methodology:** Load
  `references/shapiro-methodology.md`
- **Explaining a specific number in the report:** Load
  `references/cot-index-calculation.md`
- **Regular execution:** References not needed — the script handles the
  crowding computation
