# Parabolic Short Methodology

Adapted from Qullamaggie's three "timeless" short setups. The thesis:
parabolic moves end in mean-reverting blow-offs, but shorting too
early — while the move is still climbing — is the single fastest way
to lose money. The setup framework below exists to *delay* entry until
exhaustion is visibly confirmed.

## When a stock qualifies as parabolic

Daily-chart preconditions, all of which must be true:

- 5-day return ≥ +30% (`safe_largecap`) or ≥ +100% (`classic_qm`).
- Latest close ≥ +25% above the 20-day SMA, AND ≥ 4 ATR-units above it
  (volatility-normalized — small-caps with high ATR aren't penalized).
- Three or more consecutive green daily candles AND an acceleration
  ratio (3-day mean return / 10-day mean return) > 1.0.
- Latest-bar volume ratio (vs 20-day average) ≥ 1.5×.
- Liquidity floor: 20-day average dollar volume ≥ $20M
  (`safe_largecap`) or $5M (`classic_qm`).

These aren't a trade trigger — they're a watchlist filter. Entries are
intraday on one of the three trigger types below.

## The three trigger types

### 1. 5-min Opening Range Low (ORL) break

The cleanest setup when the open prints a wide first 5-minute bar.
Mark its low. If a subsequent 5-minute bar prints below ORL on
≥1.2× the ORL bar's volume, short the break. Stop above session HOD
plus 0.25 ATR.

### 2. First Red 5-minute candle

When the open is straight up — a series of green 5-minute bars
extending the parabola — wait for the first red 5-minute candle.
Short the break of *its* low. Stop above its high. This is the safest
variant when the open gaps into resistance.

### 3. VWAP fail

After a "first crack" — price collapsing off session HOD toward VWAP —
let it retest VWAP. A 5-minute close back below VWAP plus a lower-high
break is the entry. Invalidates instantly on a 5-minute close back
above VWAP (the "VWAP reclaim").

## Invalidation rules

Hard skips, applied before scoring. See `short_invalidation_rules.md`
for the full list.

## Why state caps matter

Parabolic candidates are by definition hitting fresh highs with strong
closes and expanding volume — exactly the metrics that, in a trend
template, would qualify them as bullish. The skill flags candidates
that closed near their session high at a fresh 52-week high as
`state_cap: still_in_markup` so Phase 2 can mark them
`plan_status: watch_only` until intraday weakness shows up.
