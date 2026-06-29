# Stockbee 20% Study Methodology

## Purpose

The 20% study is a daily market observation routine. Its goal is to build a durable model book of unusual price moves, not to convert every mover into a trade.

The workflow answers three research questions:

1. Which stocks moved at least +20% or -20% over the selected window?
2. What catalyst, chart context, liquidity context, and market regime were present?
3. What happened 1, 3, 5, 10, and 20 trading days later?

## Operating Principles

- Record both winners and failures. Negative examples are necessary for setup fluency.
- Separate observation, hypothesis, and execution. A 20% mover is an event, not a signal.
- Classify before optimizing. The first pass should label catalyst and setup context; strategy design comes later.
- Preserve data-quality flags. Missing bars, current-universe-only backfills, possible splits, and low liquidity change interpretation.
- Prefer broad, stable cohorts over clever one-off rules.

## Daily Review Checklist

For each high-priority mover, review:

- Catalyst: earnings, guidance, M&A, FDA/clinical, contract, analyst action, short squeeze, theme sympathy, low-float speculation, capital structure, or no clear news
- Direction: +20% upside event or -20% downside event
- Window: 1-day, 5-day, or custom lookback
- Close quality: strong close, midpoint close, weak close, reversal close
- Volume shock: current volume versus 20-day average volume
- Liquidity: current dollar volume and 20-day average dollar volume
- Position in trend: near 52-week high, extended, breaking down, or attempting reversal
- Setup type: base breakout, gap-and-go, episodic-pivot-like, climax extension, failed breakout, breakdown, or reversal candidate
- Theme clustering: whether multiple related symbols moved together
- Follow-up plan: which future horizons should be updated

## Daily Cadence

1. Run `scan` after the daily bar is complete.
2. Run `enrich` when structured catalyst data is available.
3. Run `update-outcomes` to mature prior records.
4. Run `summarize` after enough records have matured.
5. Promote only evidence-backed findings into downstream research.

## Historical Backfill Cadence

Backfills are useful for initial model-book seeding, but they require stronger data-quality notes. A current listed-symbol universe excludes delisted failures and can materially overstate continuation quality.

The CLI marks backfill records with `CURRENT_UNIVERSE_BACKFILL_SURVIVORSHIP_BIAS` by default. Use `--survivorship-complete` only when the supplied OHLCV includes delisted symbols and historical universe coverage.

Minimum backfill notes:

- Universe source
- Whether delisted symbols are included
- Split and corporate-action adjustment source
- Liquidity filter
- Date range
- Lookback window
- Forward outcome horizons

## Interpretation Boundaries

The output is valid as:

- Study material
- Event history
- Cohort evidence
- Edge-hint input
- Manual chart-review queue

The output is not valid as:

- A buy/sell signal
- A broker order template
- A guarantee of continuation or reversal
- A substitute for position sizing, stop design, or regime gating
