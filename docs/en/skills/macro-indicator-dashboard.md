---
layout: default
title: "Macro Indicator Dashboard"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/macro-indicator-dashboard/
permalink: /en/skills/macro-indicator-dashboard/
---

# Macro Indicator Dashboard
{: .no_toc }

Pull free macroeconomic data from the Federal Reserve Economic Data (FRED) API, score the current economic regime (Goldilocks, Reflation, Stagflation, Slowdown, Recession, Recovery), and emit a 0-100 risk-on score that exposure-coach uses to scale equity ceilings. Run when the user asks about macro regime, financial conditions, recession probability, FRED indicators, NFCI, yield curve, jobs report context, inflation trend, or "what does the macro say".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/macro-indicator-dashboard){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Macro Indicator Dashboard

---

## 2. When to Use

- Daily, before the trade-loop runs (the orchestrator calls this skill automatically).
- When the user asks "what does the macro say", "are we in a recession", "what's the regime",
  "is the Fed easing", "are financial conditions tight", or similar macro-context questions.
- After major economic data releases (CPI, NFP, GDP, FOMC) to refresh the regime score.

---

## 3. Prerequisites

- Python 3.9+
- `FRED_API_KEY` environment variable (free at https://fred.stlouisfed.org/docs/api/api_key.html)
- `requests`, `pyyaml` (standard install)

---

## 4. Quick Start

```bash
python3 skills/macro-indicator-dashboard/scripts/fetch_fred_data.py \
     --output reports/macro_raw_$(date +%Y-%m-%d).json
```

---

## 5. Workflow

1. Load reference documents as needed:
   - `references/series_catalog.md` for the list of FRED series and their meaning
   - `references/economic_regime_framework.md` for regime classification rules
   - `references/interpretation_guide.md` for how to read each indicator

2. Fetch the data:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/fetch_fred_data.py \
     --output reports/macro_raw_$(date +%Y-%m-%d).json
   ```

3. Compute the regime + risk-on score:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/compute_regime.py \
     --input reports/macro_raw_$(date +%Y-%m-%d).json \
     --output reports/macro_regime_$(date +%Y-%m-%d).json
   ```

4. Generate the markdown dashboard for human review:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/generate_dashboard.py \
     --input reports/macro_regime_$(date +%Y-%m-%d).json \
     --output-dir reports/
   ```

5. Optionally check for regime-change alerts vs the previous run:
   ```bash
   python3 skills/macro-indicator-dashboard/scripts/check_alerts.py \
     --current reports/macro_regime_$(date +%Y-%m-%d).json \
     --previous reports/macro_regime_latest.json \
     --output reports/macro_alerts_$(date +%Y-%m-%d).json
   ```

6. Present the regime classification, risk-on score (0-100), top 3 contributing
   indicators, and any regime-change alerts to the user.

---

## 6. Resources

**References:**

- `skills/macro-indicator-dashboard/references/economic_regime_framework.md`
- `skills/macro-indicator-dashboard/references/interpretation_guide.md`
- `skills/macro-indicator-dashboard/references/series_catalog.md`

**Scripts:**

- `skills/macro-indicator-dashboard/scripts/check_alerts.py`
- `skills/macro-indicator-dashboard/scripts/compute_regime.py`
- `skills/macro-indicator-dashboard/scripts/fetch_fred_data.py`
- `skills/macro-indicator-dashboard/scripts/generate_dashboard.py`
