---
layout: default
title: "Robinhood Trade Executor"
grand_parent: English
parent: Skill Guides
nav_order: 53
lang_peer: /ja/skills/robinhood-trade-executor/
permalink: /en/skills/robinhood-trade-executor/
generated: true
---

# Robinhood Trade Executor
{: .no_toc }

Downstream Robinhood execution skill. Consumes trade recommendations from upstream skills (josh-trade-monitor events, social-signal-ingestor signals, or any skill emitting the canonical order-intent) and places real orders via the Robinhood MCP connector — fixed-notional buys to open and sells to close, for both long stock (place_equity_order) and single-leg options (place_option_order). A single feed may mix equity and options. Use as the execution step of any pipeline that surfaces Robinhood-tradable entries/exits. Do NOT use for shorts, multi-leg option spreads, or crypto.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/robinhood-trade-executor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/robinhood-trade-executor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

The **downstream execution step** for Robinhood. Upstream skills surface *what* to trade; this
skill places the orders. It reads one or more recommendation files, adapts each to a canonical
**order intent**, and executes via the Robinhood MCP connector:

- **open** intents → BUY (fixed dollar notional). Equity → `place_equity_order`; single-leg
  option → `place_option_order` (contracts sized to the notional).
- **close** intents → SELL / sell-to-close exactly what the matching open filled.

A single feed may mix equity and options; several feeds can be merged in one run. The per-open
dollar amount — the **buy amount** — is supplied by the caller; never assume one.

⚠️ **This places real orders with real money and has NO human confirmation gate — buys *and*
sells, equity *and* options, fully automated.** You are responsible for every order. Run it only
against a funded Robinhood Agentic account intended for this purpose. The blast radius is wider
than a buy-only equity bot: the safety rails below are what keep it in its lane.

---

## 2. When to Use

- As the execution step after any upstream that emits Robinhood-tradable recommendations:
  `josh-trade-monitor` (`<state>_events.json`), `social-signal-ingestor`
  (`signals/index_last.json`), or any skill that writes the canonical `{"intents": [...]}`.
- When the user asks to "execute / place / mirror" those recommendations on Robinhood.

Do **not** use for shorts, multi-leg option spreads, or crypto — those are skipped with a reason.

---

## 3. Prerequisites

- **Robinhood MCP connector** (Robinhood Agentic Trading, `agent.robinhood.com`) available to the
  session. Tools:

  | Tool | Use |
  |------|-----|
  | `place_equity_order` | Market BUY/SELL for equity (long-stock) intents |
  | `place_option_order` | Buy-to-open / sell-to-close for single-leg option intents |
  | quote tools | Optional: live ask for precise sizing |

  **If the connector is not available, stop and tell the user — do not use any other broker.**
- `scripts/plan_executions.py` (stdlib only) for the deterministic selection + idempotency ledger.

---

## 4. Quick Start

```bash
python3 skills/robinhood-trade-executor/scripts/plan_executions.py plan \
  --input state/josh-trade-monitor/trader_29_this_week_events.json \
  --input data/social/vault/current/signals/index_last.json \
  --ledger state/robinhood-trade-executor/ledger.json \
  --buy-amount <DOLLARS>       # caller-supplied; e.g. 300
  # --as-of YYYY-MM-DD         # optional; defaults to today (option expiration check)
  # --source josh|social|canonical   # optional; only if auto-detect is wrong
```

---

## 5. Workflow

### Step 1: Plan the executions (deterministic, no broker)

Point the planner at one or more upstream files (`--input` repeatable; source auto-detected):

```bash
python3 skills/robinhood-trade-executor/scripts/plan_executions.py plan \
  --input state/josh-trade-monitor/trader_29_this_week_events.json \
  --input data/social/vault/current/signals/index_last.json \
  --ledger state/robinhood-trade-executor/ledger.json \
  --buy-amount <DOLLARS>       # caller-supplied; e.g. 300
  # --as-of YYYY-MM-DD         # optional; defaults to today (option expiration check)
  # --source josh|social|canonical   # optional; only if auto-detect is wrong
```

It emits `{orders, skipped}`. Each order has a `kind`:
- `equity_buy` — long-stock open → market BUY of `dollar_amount`.
- `option_buy` — option open → BUY `contracts` (`floor(buy_amount / (premium × 100))`) of
  `option_type` / `strike` / `expiration`.
- `equity_sell` / `option_sell` — a close → sell exactly the `quantity` / `contracts` recorded
  for that intent's matching open.

`skipped` lists everything not traded, each with a `reason`: already-executed intents, expired or
unaffordable options, incomplete option specs, closes with no tracked open, non-long equity, and
deferred cases (shorts, multi-leg spreads, options with no premium to size). **Report skipped
items; never trade them.**

The planner spends no money and touches no broker. **Execute exactly its `orders` — nothing more.**

### Step 2: Place the orders (Robinhood MCP), mapped by `kind`

- `equity_buy` → `place_equity_order` market BUY, `dollar_amount` of `ticker`.
- `equity_sell` → `place_equity_order` market SELL, `quantity` of `ticker`.
- `option_buy` → `place_option_order` buy-to-open, `contracts` of `ticker` `strike` `option_type`
  expiring `expiration`.
- `option_sell` → `place_option_order` sell-to-close, same contract spec, `contracts`.

One order per intent. **Never auto-retry a rejected order** — surface it.

### Step 3: Record each result to the ledger (idempotency)

Immediately after each order returns, append it — copy the fields straight from the order:

```bash
python3 skills/robinhood-trade-executor/scripts/plan_executions.py record \
  --ledger state/robinhood-trade-executor/ledger.json \
  --intent-id josh:29:631:open --match-key josh:29:631 \
  --action open --instrument option --ticker AMD \
  --status filled --order-id <rh-id> --quantity 1 \
  --option-type call --strike 180 --expiration 2026-07-17
```

Record the filled `--quantity` (shares for equity, **contracts** for options) and, for options,
`--option-type/--strike/--expiration` so the matching close sells the exact contract.

### Step 4: Write the confirmations report

Save `reports/robinhood_orders_<YYYY-MM-DD>.json` — orders placed (with `kind`, spec, `order_id`,
`status`, timestamp) plus the `skipped` list. Print a one-line-per-order summary; report
rejections plainly.

---

## 6. Resources

**Scripts:**

- `skills/robinhood-trade-executor/scripts/plan_executions.py`
