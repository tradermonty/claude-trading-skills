---
layout: default
title: "Live Analytics Dashboard"
grand_parent: English
parent: Skill Guides
nav_order: 41
lang_peer: /ja/skills/live-analytics-dashboard/
permalink: /en/skills/live-analytics-dashboard/
generated: true
---

# Live Analytics Dashboard
{: .no_toc }

Render another skill's reports/*.json (watchlist, breadth, or portfolio monitors) as a dashboard. Use when the user wants to visualize a screener/monitor result as a web page or a live-refreshing intraday monitor. Prefer the built-in Artifact tool for snapshots; escalate to a local FastAPI + polling serve stack (fixed port 8770) only when data must refresh live. Every generated page is CSP-safety gated (no inline handlers, addEventListener only) before serving.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/live-analytics-dashboard.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/live-analytics-dashboard){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Live Analytics Dashboard

---

## 2. When to Use

- The user wants to **see** a screener / monitor result as a web page: "show me
  the watchlist as a dashboard", "chart the breadth reading", "a portfolio
  monitor from my positions JSON".
- A report needs a **live-refreshing** intraday view (a parabolic-short
  watchlist, a portfolio P&L monitor) that polls fresh numbers.

Do NOT use for: a static chart image (use matplotlib/plotly `savefig`), a plain
markdown report, or a one-line answer.

---

## 3. Prerequisites

- Local serving (static HTML snapshot or local FastAPI + polling on port 8770), no paid data and no network; consumes another skill's documented reports/*.json output shape (watchlist / breadth / portfolio / generic); Artifact-tool-first for snapshots
- Python 3.9+ recommended

---

## 4. Quick Start

1. **Locate the source report.** Take a skill's `reports/*.json` (watchlist,
   breadth, portfolio, or any record set). Confirm it exists.
2. **Pick the tier.** Snapshot -> Tier 1 (prefer the Artifact tool). Live
   intraday refresh -> Tier 2. Consult `references/serve_tiers.md` when unsure.
3. **Build.** Run `scripts/build_dashboard.py` for the chosen tier. Layout is
   auto-detected; override with `--layout` and set a heading with `--title`.
4. **The CSP gate runs automatically.** `build_dashboard.py` scans every
   generated page with `scripts/csp_check.py` and **fails the build** on any
   inline handler, `eval`, `new Function`, `javascript:` URL, or string-form
   timer. Fix the template and rebuild if it fails.

---

## 5. Workflow

1. **Locate the source report.** Take a skill's `reports/*.json` (watchlist,
   breadth, portfolio, or any record set). Confirm it exists.
2. **Pick the tier.** Snapshot -> Tier 1 (prefer the Artifact tool). Live
   intraday refresh -> Tier 2. Consult `references/serve_tiers.md` when unsure.
3. **Build.** Run `scripts/build_dashboard.py` for the chosen tier. Layout is
   auto-detected; override with `--layout` and set a heading with `--title`.
4. **The CSP gate runs automatically.** `build_dashboard.py` scans every
   generated page with `scripts/csp_check.py` and **fails the build** on any
   inline handler, `eval`, `new Function`, `javascript:` URL, or string-form
   timer. Fix the template and rebuild if it fails.
5. **Deliver.**
   - Tier 1: publish the self-contained `index.html` via the **Artifact tool**,
     or serve it with the printed `python3 -m http.server` command.
   - Tier 2: `pip install -r <output>/server/requirements.txt`, then
     `PORT=8770 bash <output>/start.sh`; the page polls `/api/data` and the
     server re-reads the report JSON on each request. Verify `/healthz` responds.

---

## 6. Resources

**References:**

- `skills/live-analytics-dashboard/references/chart_snippets.md`
- `skills/live-analytics-dashboard/references/csp_safety.md`
- `skills/live-analytics-dashboard/references/serve_tiers.md`

**Scripts:**

- `skills/live-analytics-dashboard/scripts/build_dashboard.py`
- `skills/live-analytics-dashboard/scripts/csp_check.py`
