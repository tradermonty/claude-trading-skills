---
layout: default
title: "Paper Replay Harness"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/paper-replay-harness/
permalink: /ja/skills/paper-replay-harness/
---

# Paper Replay Harness
{: .no_toc }

Deterministic historical replay of the trade loop. Feeds pre-generated candidate files + local OHLCV bars through the same ranking, sizing, and bracket-fill logic used in production, without touching Alpaca. Use to validate a screener change, sanity-check a sizing tweak, or produce a walk-forward P&L curve before enabling execute mode. Invoke with "replay last 30 days", "backtest this screener", "dry-run the loop against april bars".
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/paper-replay-harness){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/paper-replay-harness/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/paper-replay-harness/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
