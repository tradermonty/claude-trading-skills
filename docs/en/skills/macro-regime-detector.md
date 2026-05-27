---
layout: default
title: "Macro Regime Detector"
grand_parent: English
parent: Skill Guides
nav_order: 37
lang_peer: /ja/skills/macro-regime-detector/
permalink: /en/skills/macro-regime-detector/
---

# Macro Regime Detector
{: .no_toc }

Detect structural macro regime transitions (1-2 year horizon) using cross-asset ratio analysis. Analyze RSP/SPY concentration, yield curve, credit conditions, size factor, equity-bond relationship, and sector rotation to identify regime shifts between Concentration, Broadening, Contraction, Inflationary, and Transitional states. Run when user asks about macro regime, market regime change, structural rotation, or long-term market positioning.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/macro-regime-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/macro-regime-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Macro Regime Detector

---

## 2. When to Use

- User asks about current macro regime or regime transitions
- User wants to understand structural market rotations (concentration vs broadening)
- User asks about long-term positioning based on yield curve, credit, or cross-asset signals
- User references RSP/SPY ratio, IWM/SPY, HYG/LQD, or other cross-asset ratios
- User wants to assess whether a regime change is underway

---

## 3. Prerequisites

- **FMP API Key** (required): Set `FMP_API_KEY` environment variable or pass `--api-key`
- Free tier (250 calls/day) is sufficient (script uses ~10 calls)

---

## 4. Quick Start

```bash
python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
```

---

## 5. Workflow

1. Load reference documents for methodology context:
   - `references/regime_detection_methodology.md`
   - `references/indicator_interpretation_guide.md`

2. Execute the main analysis script:
   ```bash
   python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
   ```
   This fetches 600 days of data for 9 ETFs + Treasury rates (10 API calls total).

3. Read the generated Markdown report and present findings to user.

4. Provide additional context using `references/historical_regimes.md` when user asks about historical parallels.

---

## 6. Resources

**References:**

- `skills/macro-regime-detector/references/historical_regimes.md`
- `skills/macro-regime-detector/references/indicator_interpretation_guide.md`
- `skills/macro-regime-detector/references/regime_detection_methodology.md`

**Scripts:**

- `skills/macro-regime-detector/scripts/fmp_client.py`
- `skills/macro-regime-detector/scripts/macro_regime_detector.py`
- `skills/macro-regime-detector/scripts/report_generator.py`
- `skills/macro-regime-detector/scripts/scorer.py`
