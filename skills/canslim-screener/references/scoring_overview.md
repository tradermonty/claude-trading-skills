# Scoring Overview

Moved verbatim from `SKILL.md`.

**Phase 3.1 Component Weights (Original O'Neil weights):**
- C (Current Earnings): 15%
- A (Annual Growth): 20%
- N (Newness): 15%
- S (Supply/Demand): 15%
- L (Leadership/RS Rank): 20% — multi-period weighted RS (3m/6m/12m vs configurable benchmark)
- I (Institutional): 10%
- M (Market Direction): 5%

**Weighted RS Formula:**
```
Weighted RS = 0.40 × rel_3m + 0.30 × rel_6m + 0.30 × rel_12m
```
Available periods are re-normalized when some are missing. Default benchmark is `^GSPC`;
override with `--rs-benchmark SPY/QQQ/IWM/...`.

**Fallback hierarchy when multi-period data is incomplete:**
1. No benchmark → weighted absolute stock performance + 20% penalty.
2. All multi-period windows missing but >=50 bars of price history → fall back to the
   legacy 365-day full-window absolute return as the scoring input (20% penalty if no
   benchmark).
3. <50 bars of price history → score=0 with `error` set.
