---
layout: default
title: "Alpaca Executor"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/alpaca-executor/
permalink: /en/skills/alpaca-executor/
---

# Alpaca Executor
{: .no_toc }

Execute equity trades on Alpaca (paper or live) as bracket orders with idempotency keys, mandatory stop-loss, and target. Refuses to send live orders unless config/trading_params.yaml is in live mode AND LIVE_TRADING_CHECKLIST.md is signed AND TRADE_LOOP_DRY_RUN=false. Use when the trade-loop-orchestrator needs to place an order, when the user asks to "buy/sell X", "place a bracket order", "submit trade", or "execute". Also handles flatten-all and order cancellation.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/alpaca-executor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Alpaca Executor

---

## 2. When to Use

- The trade-loop-orchestrator emits a SIGNAL_READY trade plan and needs to execute it.
- The user manually says "buy X shares of TICKER with stop at Y, target at Z".
- The kill-switch needs to flatten all positions.
- You need to cancel an open order or replace a stop.

---

## 3. Prerequisites

- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER` env vars (loaded via `scripts/with_env.sh`)
- `pyyaml`, `requests`
- `config/trading_params.yaml` exists and validates
- For live mode: `LIVE_TRADING_CHECKLIST.md` exists and contains `signed: true` line

---

## 4. Quick Start

```bash
python3 skills/alpaca-executor/scripts/execute_trade.py \
  --ticker AAPL \
  --side buy \
  --quantity 50 \
  --entry-type market \
  --stop-loss 145.00 \
  --target 165.00 \
  --signal-id vcp-2026-04-21-aapl \
  --output reports/orders/aapl_2026-04-21.json
```

---

## 5. Workflow

```bash
python3 skills/alpaca-executor/scripts/execute_trade.py \
  --ticker AAPL \
  --side buy \
  --quantity 50 \
  --entry-type market \
  --stop-loss 145.00 \
  --target 165.00 \
  --signal-id vcp-2026-04-21-aapl \
  --output reports/orders/aapl_2026-04-21.json
```

The script:
1. Loads trading_params.yaml.
2. Reads `ALPACA_PAPER`, `TRADE_LOOP_DRY_RUN`.
3. If global.mode == "live" and ALPACA_PAPER != "false": refuse.
4. If TRADE_LOOP_DRY_RUN == "true": log the order but do NOT call Alpaca; return a synthetic
   acknowledgement.
5. Validate position size against risk_per_trade_pct and max_position_size_pct.
6. Compute the client_order_id as `sha1(ticker|signal_id|date)`.
7. Call Alpaca's `/v2/orders` endpoint with bracket parameters.
8. Persist the response JSON to the output path.

---

## 6. Resources

**Scripts:**

- `skills/alpaca-executor/scripts/execute_trade.py`
- `skills/alpaca-executor/scripts/flatten_all.py`
