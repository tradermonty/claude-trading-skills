---
layout: default
title: "Ticker Enricher"
grand_parent: 日本語
parent: スキルガイド
nav_order: 71
lang_peer: /en/skills/ticker-enricher/
permalink: /ja/skills/ticker-enricher/
generated: true
---

# Ticker Enricher
{: .no_toc }

Enrich ticker signals with company metadata (name, sector, industry) and prices (recommendation-date price, current price) from Yahoo Finance. Reads the social-signal vault index and emits a records file ready for a generic writer (e.g. write-supabase); the dashboard derives gain % and days held from the stored prices/dates. Reusable by any producer that has tickers.
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/ticker-enricher.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/ticker-enricher){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/ticker-enricher/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/ticker-enricher/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
