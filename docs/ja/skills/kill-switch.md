---
layout: default
title: "Kill Switch"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/kill-switch/
permalink: /ja/skills/kill-switch/
---

# Kill Switch
{: .no_toc }

Continuously watch Alpaca account state against the risk limits in trading_params.yaml and trigger a flatten-all when any hard limit is breached. Monitors daily P&L vs max_daily_loss_pct, position count vs max_positions, sector exposure vs max_sector_exposure_pct, correlated positions, and market-top distribution-day count. Run by the launchd watchdog every 2 minutes during market hours. Invoke when the user asks to "check kill-switch", "am I over limits", "what's my daily P&L".
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kill-switch){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/kill-switch/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/kill-switch/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
