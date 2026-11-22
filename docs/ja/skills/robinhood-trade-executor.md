---
layout: default
title: "Robinhood Trade Executor"
grand_parent: 日本語
parent: スキルガイド
nav_order: 53
lang_peer: /en/skills/robinhood-trade-executor/
permalink: /ja/skills/robinhood-trade-executor/
generated: true
---

# Robinhood Trade Executor
{: .no_toc }

Downstream Robinhood execution skill. Consumes trade recommendations from upstream skills (josh-trade-monitor events, social-signal-ingestor signals, or any skill emitting the canonical order-intent) and places real orders via the Robinhood MCP connector — fixed-notional buys to open and sells to close, for both long stock (place_equity_order) and single-leg options (place_option_order). A single feed may mix equity and options. Use as the execution step of any pipeline that surfaces Robinhood-tradable entries/exits. Do NOT use for shorts, multi-leg option spreads, or crypto.
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/robinhood-trade-executor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/robinhood-trade-executor){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/robinhood-trade-executor/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/robinhood-trade-executor/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
