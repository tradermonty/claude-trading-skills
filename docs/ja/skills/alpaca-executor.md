---
layout: default
title: "Alpaca Executor"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/alpaca-executor/
permalink: /ja/skills/alpaca-executor/
---

# Alpaca Executor
{: .no_toc }

Execute equity trades on Alpaca (paper or live) as bracket orders with idempotency keys, mandatory stop-loss, and target. Refuses to send live orders unless config/trading_params.yaml is in live mode AND LIVE_TRADING_CHECKLIST.md is signed AND TRADE_LOOP_DRY_RUN=false. Use when the trade-loop-orchestrator needs to place an order, when the user asks to "buy/sell X", "place a bracket order", "submit trade", or "execute". Also handles flatten-all and order cancellation.
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/alpaca-executor){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/alpaca-executor/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/alpaca-executor/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
