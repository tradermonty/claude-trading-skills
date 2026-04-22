---
layout: default
title: "Eod Reconciliation"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/eod-reconciliation/
permalink: /ja/skills/eod-reconciliation/
---

# Eod Reconciliation
{: .no_toc }

End-of-day job that reconciles intraday loop decisions against actual Alpaca fills, updates trader-memory-core theses, generates a daily P&L attribution report, and triggers postmortem prompts for any closed positions. Run by launchd at 16:30 ET. Invoke when the user asks "run EOD", "reconcile today's trades", "what filled today", "daily P&L".
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/eod-reconciliation){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/eod-reconciliation/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/eod-reconciliation/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
