---
layout: default
title: "Trade Loop Orchestrator"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/trade-loop-orchestrator/
permalink: /ja/skills/trade-loop-orchestrator/
---

# Trade Loop Orchestrator
{: .no_toc }

Main automated trading loop. Every 5 minutes during US market hours, this skill (1) checks the kill-switch, (2) reads macro regime + exposure scale, (3) runs all configured screeners, (4) ranks/dedupes signals, (5) sizes positions via position-sizer, (6) submits bracket orders via alpaca-executor with full safety gates, and (7) writes a per-iteration audit log. Invoke when the user asks "run the loop", "execute the trader", "start the bot", "scan and place trades".
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trade-loop-orchestrator){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/trade-loop-orchestrator/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/trade-loop-orchestrator/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
