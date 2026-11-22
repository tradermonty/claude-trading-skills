---
layout: default
title: "Write Supabase"
grand_parent: 日本語
parent: スキルガイド
nav_order: 80
lang_peer: /en/skills/write-supabase/
permalink: /ja/skills/write-supabase/
generated: true
---

# Write Supabase
{: .no_toc }

Generic Supabase table writer. Reads a records JSON file (array or {records:[...]}) and upserts or inserts the rows into a Supabase table named on the command line, with a caller-supplied conflict key. Knows nothing about any domain — every workflow points it at its own table and details, so it is reusable across the whole repo. Use as the final "persist to Supabase" step after a producer emits a records file.
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/write-supabase.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/write-supabase){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/write-supabase/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/write-supabase/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
