---
layout: default
title: Playbooks
parent: English
nav_order: 7
has_children: true
lang_peer: /ja/playbooks/
permalink: /en/playbooks/
---

# Playbooks
{: .no_toc }

Usage guides for whole multi-skill workflows, not individual skills. Each playbook walks a pipeline end to end: when to run it, the steps in order, how gates decide, how positions are sized, and how the trade is registered in `trader-memory-core`. Read the relevant playbook before running any of its skills in isolation.

---

## Available Playbooks

| Playbook | Horizon | What it covers |
|---|---|---|
| [Cross-Asset Quant Strategy Framework]({{ '/en/playbooks/quant-strategy-framework/' | relative_url }}) | Spans all horizons | The Pre / During / Post framework that wires every asset-class playbook and skill together |
| [Stockbee Momentum Burst]({{ '/en/playbooks/stockbee-momentum-burst/' | relative_url }}) | 2-5 sessions | Short-term breakout/range-expansion swing entries from `stockbee-momentum-burst-screener` |
| [PEAD (Post-Earnings Announcement Drift)]({{ '/en/playbooks/pead/' | relative_url }}) | 2-6 weeks | Earnings-drift entries from `pead-screener`'s red-candle pullback pattern |
| [Shapiro COT Contrarian]({{ '/en/playbooks/shapiro-contrarian/' | relative_url }}) | Weekly | Fading crowded CFTC futures positioning after two independent confirmations |

Each playbook is a **decision-support pipeline, not an auto-execution system**. Every order is placed manually; every screener output is a candidate list, not a signal to trade blindly. None of the eight skills behind these four playbooks (`stockbee-momentum-burst-screener`, `pead-screener`, `earnings-trade-analyzer`, `technical-analyst`, `position-sizer`, `trader-memory-core`, `pre-trade-discipline-gate`, `cot-contrarian-detector` and its Shapiro-pipeline peers) places orders, cancels orders, calls a broker API, or runs a realtime monitor.

## Don't confuse the two short-horizon playbooks

Stockbee Momentum Burst and PEAD both produce swing candidates in liquid US stocks, but they are separate cohorts with different holding horizons and different catalysts:

- **Momentum Burst** is a pure price/volume breakout play — 2-5 sessions, no earnings requirement, exit on a trigger-day-low failure or lack of follow-through.
- **PEAD** requires an actual earnings gap-up and a weekly red-candle pullback before entry — 2-6 weeks, exit on a weekly-close stop or thesis invalidation.

Do not extend a Momentum Burst hold into PEAD-length time just because the stock also happened to report earnings — register it as a separate thesis with its own `setup_type` if that pivot happens. See each playbook's "Don't confuse this with" section for the full boundary.

## See also

- [Skill Guides]({{ '/en/skills/' | relative_url }}) for the reference documentation of each individual skill
- [Workflows]({{ '/en/workflows/' | relative_url }}) for the auto-generated manifest reference
