# VCP Screener Scoring System

## 5-Component Composite Score

| Component | Weight | Source |
|-----------|--------|--------|
| Trend Template (Stage 2) | 25% | 7-point Minervini criteria |
| Contraction Quality | 25% | VCP pattern detection |
| Volume Pattern | 20% | Volume dry-up analysis |
| Pivot Proximity | 15% | Distance from breakout level |
| Relative Strength | 15% | Minervini-weighted RS vs S&P 500 |

## Component Scoring Details

### 1. Trend Template (0-100)

Each of the 7 criteria contributes 14.3 points:

| Criteria Passed | Score | Status |
|-----------------|-------|--------|
| 7/7 | 100 | Perfect Stage 2 |
| 6/7 | 85.8 | Pass (minimum threshold) |
| 5/7 | 71.5 | Borderline |
| <= 4/7 | <= 57 | Fail |

**Pass threshold:** Score >= 85 (6+ criteria) to proceed to VCP analysis.

### 2. Contraction Quality (0-100)

| # Contractions | Base Score |
|----------------|-----------|
| 4 | 90 |
| 3 | 80 |
| 2 | 60 |
| 1 or invalid | 0-40 |

**Modifiers:**
- Tight final contraction (< 5% depth): +10
- Good average contraction ratio (< 0.4 of T1): +10
- Deep T1 (> 30%): -10

### 3. Volume Pattern (0-100)

Based on dry-up ratio (recent 10-bar avg / 50-day avg):

| Dry-Up Ratio | Base Score |
|-------------|-----------|
| < 0.30 | 90 |
| 0.30-0.50 | 75 |
| 0.50-0.70 | 60 |
| 0.70-1.00 | 40 |
| > 1.00 | 20 |

**Modifiers:**
- Breakout on 1.5x+ volume: +10
- Net accumulation > 3 days (in 20d): +10
- Net distribution > 3 days (in 20d): -10

### 4. Pivot Proximity (0-100)

| Distance from Pivot | Score | Trade Status |
|--------------------|-------|--------------|
| Above pivot + volume | 100 | Breakout Confirmed |
| Above pivot (no vol) | 85 | Above Pivot |
| Within 2% below | 90 | At Pivot |
| 2-5% below | 75 | Near Pivot |
| 5-8% below | 60 | Approaching |
| 8-10% below | 45 | Developing |
| 10-15% below | 30 | Early |
| > 15% below | 10 | Far from Pivot |

### 5. Relative Strength (0-100)

Minervini weighting (emphasizes recent performance):
- 40%: Last 3 months (63 trading days)
- 20%: Last 6 months (126 trading days)
- 20%: Last 9 months (189 trading days)
- 20%: Last 12 months (252 trading days)

| Weighted RS vs S&P 500 | Score | RS Rank Estimate |
|-------------------------|-------|------------------|
| >= +50% | 100 | ~99 (top 1%) |
| >= +30% | 95 | ~95 (top 5%) |
| >= +20% | 90 | ~90 (top 10%) |
| >= +10% | 80 | ~80 (top 20%) |
| >= +5% | 70 | ~70 (top 30%) |
| >= 0% | 60 | ~60 (top 40%) |
| >= -5% | 50 | ~50 (average) |
| >= -10% | 40 | ~40 |
| >= -20% | 20 | ~25 |
| < -20% | 0 | ~10 |

## Rating Bands

| Composite Score | Rating | Position Sizing | Action |
|-----------------|--------|-----------------|--------|
| 90-100 | Textbook VCP | 1.5-2x normal | Buy at pivot, aggressive |
| 80-89 | Strong VCP | 1x normal | Buy at pivot, standard |
| 70-79 | Good VCP | 0.75x normal | Buy on volume confirmation |
| 60-69 | Developing VCP | Wait | Watchlist only |
| 50-59 | Weak VCP | Skip | Monitor only |
| < 50 | No VCP | Skip | Not actionable |

## Pre-Filter Criteria (Phase 1)

Quick filter using quote data only (no historical needed):

| Criterion | Threshold | Purpose |
|-----------|-----------|---------|
| Price | > $10 | Exclude penny stocks |
| % above 52w low | > 20% | Roughly in uptrend |
| % below 52w high | < 30% | Not in deep correction |
| Average volume | > 200,000 | Sufficient liquidity |
