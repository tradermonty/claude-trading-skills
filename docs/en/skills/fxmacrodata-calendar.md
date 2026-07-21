---
layout: default
title: "Fxmacrodata Calendar"
grand_parent: English
parent: Skill Guides
nav_order: 34
lang_peer: /ja/skills/fxmacrodata-calendar/
permalink: /en/skills/fxmacrodata-calendar/
generated: true
---

# Fxmacrodata Calendar
{: .no_toc }

Fetch official FXMacroData macro release-calendar events for trade planning, macro regime checks, and event-risk filters. Use before CPI, NFP, GDP, PCE, retail sales, PMI, and central-bank decision windows.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/fxmacrodata-calendar.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/fxmacrodata-calendar){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# FXMacroData Calendar

---

## 2. Prerequisites

- FXMacroData REST API; public USD calendar rows work without a key
- Python 3.9+ recommended

---

## 3. Quick Start

```bash
python3 skills/fxmacrodata-calendar/scripts/fetch_calendar.py --currency usd --min-tier 1
```

---

## 4. Workflow

1. Run the calendar script:

   ```bash
   python3 skills/fxmacrodata-calendar/scripts/fetch_calendar.py --currency usd --min-tier 1
   ```

2. Review `events[]` for top-tier releases.

   Treat a nonzero exit as an unverified event-risk state, never as an empty
   calendar. Only a successful response containing `events: []` establishes
   that no matching events were returned. The client accepts results only when
   the response currency matches the request and `data_quality` confirms an
   official, current, non-proxy, non-fallback, timestamp-complete,
   point-in-time-safe source. Each event must include an announcement timestamp
   and a non-empty release identifier.

3. Fold the event timing into the trade plan:
   - pause new entries around high-impact releases;
   - reduce leverage or position size;
   - schedule follow-up review after the actual value is available;
   - explain which event and timestamp drove the adjustment.

---

## 5. Resources

**Scripts:**

- `skills/fxmacrodata-calendar/scripts/fetch_calendar.py`
