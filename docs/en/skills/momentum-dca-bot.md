---
layout: default
title: "Momentum Dca Bot"
grand_parent: English
parent: Skill Guides
nav_order: 45
lang_peer: /ja/skills/momentum-dca-bot/
permalink: /en/skills/momentum-dca-bot/
generated: true
---

# Momentum Dca Bot
{: .no_toc }

Fully mechanical daily momentum DCA system - screen momentum-pullback stocks (Yahoo Finance keyless, or Finviz Elite/CSV), buy a fixed $300 notional of the top-ranked name via Alpaca (paper by default), book profits by selling half at +20%, and exit on 50DMA break or 15% trailing stop. Use when the user wants a daily momentum buying bot, dollar-cost averaging into momentum leaders, automated profit taking, or a Finviz-style momentum pullback screen without paid APIs.
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FINVIZ Optional</span> <span class="badge badge-api">Alpaca Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/momentum-dca-bot.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/momentum-dca-bot){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

A daily, fully mechanical momentum sleeve: screen for strong uptrending stocks
pulling back within a bull regime, allocate a fixed notional every trading day,
book profits into strength, and exit on trend breaks. No discretion at any step;
every action lands in an append-only trade log.

**Strategy rules:**

| Stage | Rule |
|-------|------|
| Screen | YTD +50%, above 20/50/200 SMA, down on the week, mid-cap+ ($2B+), price > $10, avg vol > 500K, within 10% of 52-week high, analyst buy-or-better |
| Rank | Perf Month desc; tiebreak Perf Week desc (shallowest pullback = relative strength) |
| Regime gate | Buys only while SPY closes above its 50DMA; exits always active |
| Buy | $300 notional/day, top-ranked name, max 3 lots ($900) per name, one buy/day |
| Book profits | Sell HALF the first time a name closes ≥ +20% over average entry |
| Exit | Sell ALL on close < 50DMA or 15% off high-water close, whichever first |

After the scale-out, the 15% trail mathematically locks the remainder in above
breakeven on a daily-close basis (0.85 × 1.20 = 1.02): a booked winner cannot
round-trip into a loss, barring overnight gaps through the stop.

---

## 2. When to Use

- The user wants a daily momentum buying bot or fixed-dollar DCA into momentum leaders
- The user asks to run/replicate a Finviz momentum-pullback screen keyless
- The user asks to check exits or book profits on bot-managed positions

---

## 3. Prerequisites

- **FINVIZ Elite** optional (improves performance)
- **Alpaca API** account required (paper trading is free)
- Finviz Elite screener via --source finviz, or a manual screener CSV export via --csv
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
python3 skills/momentum-dca-bot/scripts/momentum_bot.py scan --top 5
```

---

## 5. Workflow

1. Run the screen and review candidates:
   ```bash
   python3 skills/momentum-dca-bot/scripts/momentum_bot.py scan --top 5
   ```
2. Execute (or preview) the daily buy — idempotent, safe to re-run:
   ```bash
   python3 skills/momentum-dca-bot/scripts/momentum_bot.py buy --dry-run
   ```
3. Near the close, book profits and check exits:
   ```bash
   python3 skills/momentum-dca-bot/scripts/momentum_bot.py manage --dry-run
   ```
4. Drop `--dry-run` only after the user has Alpaca paper keys configured.
   Report what was bought/sold/booked and why (reasons are in the output).
5. Inspect state or the audit log when asked:
   ```bash
   python3 skills/momentum-dca-bot/scripts/momentum_bot.py status
   cat state/momentum_bot/trades.jsonl
   ```

For automation, suggest cron (adjust for local timezone vs. US/Eastern):

```cron
35 9  * * 1-5  cd <repo> && set -a && . ./.env && set +a && python3 skills/momentum-dca-bot/scripts/momentum_bot.py buy    >> logs/momentum_bot.log 2>&1
50 15 * * 1-5  cd <repo> && set -a && . ./.env && set +a && python3 skills/momentum-dca-bot/scripts/momentum_bot.py manage >> logs/momentum_bot.log 2>&1
```

---

## 6. Resources

**Scripts:**

- `skills/momentum-dca-bot/scripts/momentum_bot.py`
