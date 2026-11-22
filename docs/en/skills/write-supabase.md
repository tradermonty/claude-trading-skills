---
layout: default
title: "Write Supabase"
grand_parent: English
parent: Skill Guides
nav_order: 80
lang_peer: /ja/skills/write-supabase/
permalink: /en/skills/write-supabase/
generated: true
---

# Write Supabase
{: .no_toc }

Generic Supabase table writer. Reads a records JSON file (array or {records:[...]}) and upserts or inserts the rows into a Supabase table named on the command line, with a caller-supplied conflict key. Knows nothing about any domain — every workflow points it at its own table and details, so it is reusable across the whole repo. Use as the final "persist to Supabase" step after a producer emits a records file.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/write-supabase.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/write-supabase){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

A small, generic transport skill: take a records JSON file and write the rows into a Supabase
table. The table, conflict key, and mode are all supplied by the caller, so any workflow can
reuse it — `ticker-enricher → write-supabase --table recommendations`, a screener →
`--table screener_hits`, etc. It holds no domain logic; building the records is the producer's job.

---

## 2. When to Use

- As the last step of any workflow that has produced a records file and needs it persisted to Supabase.
- NOT for building/enriching records (that's the producer, e.g. `ticker-enricher`).

---

## 3. Prerequisites

- `SUPABASE_URL` + a Supabase secret key — any of `SUPABASE_SERVICE_KEY`, `SUPABASE_SECRET_KEY`,
  `SUPABASE_SECRETS_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (Supabase's newer "secret" key naming is
  accepted). Auto-loaded from a repo-root `.env` if present (so `python3 …` works without
  `source .env`); also honors a real exported env / cloud vault.
- The target table must already exist (create it via a Supabase migration).
- `requests` (already a repo dependency).

---

## 4. Quick Start

```bash
python3 skills/write-supabase/scripts/write_supabase.py \
  --table recommendations \
  --records "reports/enriched_records_*.json" \
  --conflict "ticker,recommendation_source,date_recommended"
```

---

## 5. Workflow

```bash
python3 skills/write-supabase/scripts/write_supabase.py \
  --table recommendations \
  --records "reports/enriched_records_*.json" \
  --conflict "ticker,recommendation_source,date_recommended"
```

- `--table` — target Supabase table (required).
- `--records` — path or glob to the records file(s); each is a JSON array or `{ "records": [...] }`.
- `--conflict` — comma-separated columns for `on_conflict` (upsert only).
- `--mode upsert` (default; `resolution=merge-duplicates`) or `--mode insert`.

---

## 6. Resources

**References:**

- `skills/write-supabase/references/usage.md`

**Scripts:**

- `skills/write-supabase/scripts/write_supabase.py`
