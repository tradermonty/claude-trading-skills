---
layout: default
title: "Live Analytics Dashboard"
grand_parent: 日本語
parent: スキルガイド
nav_order: 41
lang_peer: /en/skills/live-analytics-dashboard/
permalink: /ja/skills/live-analytics-dashboard/
generated: true
---

# Live Analytics Dashboard
{: .no_toc }

Render another skill's reports/*.json (watchlist, breadth, or portfolio monitors) as a dashboard. Use when the user wants to visualize a screener/monitor result as a web page or a live-refreshing intraday monitor. Prefer the built-in Artifact tool for snapshots; escalate to a local FastAPI + polling serve stack (fixed port 8770) only when data must refresh live. Every generated page is CSP-safety gated (no inline handlers, addEventListener only) before serving.
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/live-analytics-dashboard.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/live-analytics-dashboard){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/live-analytics-dashboard/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/live-analytics-dashboard/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
