---
layout: default
title: "Stockbee Exhaustion Hammer Screener"
grand_parent: English
parent: Skill Guides
nav_order: 51
lang_peer: /ja/skills/stockbee-exhaustion-hammer-screener/
permalink: /en/skills/stockbee-exhaustion-hammer-screener/
generated: false
---

# Stockbee Exhaustion Hammer Screener
{: .no_toc }

Screen US stocks for Stockbee-style selling-exhaustion hammer candidates: liquid/high-quality stocks with prior momentum, a controlled pullback, undercut/reclaim behavior, long lower-wick reversal geometry, and manageable risk to the day low.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download skill package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-exhaustion-hammer-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-exhaustion-hammer-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill screens for near-close selling-exhaustion hammer setups. It is not a generic candlestick screener; it requires context.

Main filters:

- Quality/liquidity: price, current volume, 20-day average dollar volume, and optional market-cap / holder metadata
- Prior momentum: recent high and constructive 20/60-day strength
- Pullback: controlled drawdown from the recent high
- Exhaustion: short-term undercut/reclaim, recent selling pressure, and volume confirmation
- Hammer geometry: long lower wick, small body, strong close-location, and recovery from the low
- Risk: distance from entry reference to day-low stop plus buffer

The output is candidate prioritization, not an automated trading signal.

---

## 2. When to use

Use this when you want to find:

- Stockbee / Pradeep Bonde style exhaustion setups
- Hammer reversal candidates close to the market close
- Strong stocks pulling back into a potential final shakeout
- Undercut/reclaim candidates for manual chart review
- Study examples for `stockbee-setup-fluency-trainer`

Do not use it to auto-place trades or to trade against a restrictive market-regime gate.

---

## 3. Prerequisites

For live universe and FMP data:

```bash
export FMP_API_KEY=your_api_key_here
```

For no-API operation, provide an OHLCV JSON file. For the near-close use case, the latest bar should be a provisional current-day daily bar captured near the close.

---

## 4. Quick start

```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --fmp-universe \
  --max-symbols 300 \
  --market-gate allowed \
  --output-dir reports/
```

Near-close quote override:

```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --fmp-universe \
  --use-quote-latest \
  --max-api-calls 700 \
  --market-gate allowed \
  --output-dir reports/
```

Offline / provisional feed:

```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --prices-json data/near_close_daily_ohlcv.json \
  --profiles-json data/quality_profiles.json \
  --market-gate allowed \
  --output-dir reports/
```

---

## 5. Reading the output

Each candidate includes:

- State and rating
- Pullback percentage from recent high
- Undercut/reclaim status
- Hammer geometry metrics
- Volume ratios and average dollar volume
- Entry/stop reference and risk-to-stop percentage
- Score components and reject reasons

Actionable candidates still require manual chart validation, earnings/news risk checks, and position sizing.

---

## 6. Resources

References:

- `skills/stockbee-exhaustion-hammer-screener/references/exhaustion_hammer_methodology.md`
- `skills/stockbee-exhaustion-hammer-screener/references/scoring_system.md`
- `skills/stockbee-exhaustion-hammer-screener/references/near_close_operations.md`

Script:

- `skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py`
