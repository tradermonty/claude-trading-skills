# Theme Detection Methodology

## Overview

The Theme Detector uses a **3-Dimensional Scoring Model** to identify, rank, and assess market themes. Unlike single-score ranking systems, this approach separates the intensity of a theme (heat), its maturity stage (lifecycle), and the reliability of the signal (confidence) into independent dimensions.

---

## Dimension 1: Theme Heat (0-100)

Theme Heat measures the **direction-neutral strength** of a theme. A high heat score means the theme is generating significant market activity, regardless of whether it is bullish or bearish.

### Components

#### 1.1 Momentum Strength (weight: 35%)

Measures the direction-neutral momentum strength using a log-sigmoid function on the absolute weighted return.

**Formula:**
```
weighted_return = perf_1w * 0.10 + perf_1m * 0.25 + perf_3m * 0.35 + perf_6m * 0.30
momentum_score = 100 / (1 + exp(-2.0 * (ln(1 + |weighted_return|) - ln(16))))
```

Midpoint at |15%| weighted return. Log transform compresses extreme values for better mid-range separation. Absolute value is used so both strong bullish and strong bearish moves generate high heat.

**Data Source:** FINVIZ industry performance (1W, 1M, 3M, 6M change %)

**Example Scores (continuous, not stepped):**
| |Weighted Return| | Score |
|---------------------|-------|
| 0% | ~3 |
| 5% | ~27 |
| 15% | 50 (midpoint) |
| 30% | ~73 |
| 50% | ~86 |

#### 1.2 Volume Intensity (weight: 20%)

Measures abnormal volume using sqrt scaling on the 20-day/60-day volume ratio.

**Formula:**
```
ratio = vol_20d / vol_60d
volume_score = min(100, sqrt(max(0, ratio - 0.8)) / sqrt(1.2) * 100)
```

Returns 50.0 if either volume input is None or zero.

**Data Source:** FINVIZ relative volume (volume / avg volume ratio)

**Example Scores:**
| Volume Ratio | Score |
|-------------|-------|
| 1.0 | ~37 |
| 1.2 | ~58 |
| 1.5 | ~76 |
| 2.0 | 100 (ceiling) |

#### 1.3 Uptrend Signal (weight: 25%)

Continuous score from sector uptrend data with base + bonus structure.

**Formula per sector:**
```
base = min(80, ratio * 100)        # continuous 0-80
ma_bonus = 10 if ratio > ma_10     # MA above bonus
slope_bonus = 10 if slope > 0      # positive slope bonus
sector_score = base + ma_bonus + slope_bonus  # 0-100
```

Final score = weighted average of sector scores. For bearish themes, result is inverted (100 - score).

**Data Source:** uptrend-dashboard output (ratio, ma_10, slope per sector)

Returns 50.0 if no sector data available.

#### 1.4 Breadth Signal (weight: 20%)

Measures directionally-aligned industry participation using a power curve with industry count bonus.

**Formula:**
```
breadth_score = min(100, ratio^2.5 * 80 + count_bonus)
count_bonus = min(20, industry_count * 2)
```

The ratio is the fraction of matched industries with directionally-aligned weighted returns (positive for LEAD themes, negative for LAG themes). Power curve (exponent 2.5) suppresses low ratios and amplifies high ones.

**Data Source:** Industry-level weighted returns (not stock-level)

**Example Scores (no count bonus):**
| Breadth Ratio | Score |
|-------------|-------|
| 0.5 | ~14 |
| 0.7 | ~33 |
| 0.9 | ~61 |
| 1.0 | 80 |

Returns 50.0 if ratio is None.

### Theme Heat Composite

```
theme_heat = (momentum * 0.35) + (volume * 0.20) + (uptrend * 0.25) + (breadth * 0.20)
```

Any None sub-score defaults to 50.0. Result clamped to 0-100.

---

## Dimension 2: Lifecycle Maturity

Lifecycle assessment classifies a theme into one of five stages: **Emerging**, **Accelerating**, **Trending**, **Mature**, or **Exhausting**. This is critical for distinguishing emerging opportunities from crowded trades.

### Components

#### 2.1 Duration Score (weight: 25%)

How long the theme has been active (consecutive weeks of elevated heat).

**Measurement:** Count weeks where theme_heat >= 40.

| Duration | Stage Signal |
|----------|-------------|
| 1-3 weeks | Emerging |
| 4-8 weeks | Accelerating |
| 9-12 weeks | Trending |
| 13-16 weeks | Mature |
| > 16 weeks | Exhausting |

**Limitation:** Duration tracking requires historical data. On first run, duration defaults to "Unknown" and lifecycle uses other factors only.

#### 2.2 Extremity Clustering Score (weight: 25%)

Percentage of stocks in the theme near 52-week highs or lows.

**Formula:**
```
extremity_pct = count(within_5pct_of_52wk_high_or_low) / count(total_stocks)
```

| Extremity % | Stage Signal |
|-------------|-------------|
| < 15%       | Emerging |
| 15-30%      | Accelerating |
| 30-45%      | Trending |
| 45-60%      | Mature |
| > 60%       | Exhausting |

**Data Source:** FINVIZ 52-week high/low data

#### 2.3 Price Extreme Saturation Score (weight: 25%)

Proportion of stocks near 52-week extremes (within 5%).

**Formula:**
```
bullish: pct = count(dist_from_52w_high <= 0.05) / total
bearish: pct = count(dist_from_52w_low <= 0.05) / total
score = min(100, pct * 200)
```

#### 2.4 Valuation Score (weight: 15%)

Average P/E ratio of theme constituents relative to S&P 500 P/E.

**Formula:**
```
relative_pe = avg_theme_pe / sp500_pe
```

| Relative P/E | Stage Signal |
|---------------|-------------|
| < 0.8         | Emerging (undervalued) |
| 0.8-1.0       | Accelerating (fair value) |
| 1.0-1.4       | Trending (slightly elevated) |
| 1.4-2.0       | Mature (overvalued) |
| > 2.0         | Exhausting (extreme) |

**Data Source:** FMP API for P/E ratios (optional; uses FINVIZ forward P/E as fallback)

#### 2.5 ETF Proliferation Score (weight: 10%)

Number of thematic ETFs tracking the theme. More ETFs indicate greater retail/institutional attention.

**Source:** `thematic_etf_catalog.md` (static reference)

| ETF Count | Score | Stage Signal |
|-----------|-------|-------------|
| 0         | 0     | Emerging |
| 1         | 20    | Emerging |
| 2-3       | 40    | Accelerating |
| 4-6       | 60    | Trending |
| 7-10      | 80    | Mature |
| > 10      | 100   | Exhausting |

### Lifecycle Maturity Composite

```
maturity = (duration * 0.25) + (extremity * 0.25) + (price_extreme * 0.25) + (valuation * 0.15) + (etf_proliferation * 0.10)
```

### Lifecycle Stage Classification

The lifecycle stage is classified from the maturity score:

| Maturity Score | Stage |
|----------------|-------|
| 0-20 | Emerging |
| 20-40 | Accelerating |
| 40-60 | Trending |
| 60-80 | Mature |
| 80-100 | Exhausting |

**Note:** Media/Narrative Saturation is not included in the automated maturity calculation. Claude's WebSearch narrative confirmation can be used to qualitatively adjust the lifecycle assessment.

---

## Dimension 3: Confidence (Low / Medium / High)

Confidence measures **how reliable** the theme detection is, based on data quality and confirmation signals.

### Layers

#### 3.1 Quantitative Layer (base)

Based on data breadth and consistency:

| Condition | Level |
|-----------|-------|
| >= 4 industries matching, >= 20 stocks analyzed | High |
| 2-3 industries matching, >= 10 stocks analyzed | Medium |
| 1 industry matching or < 10 stocks | Low |

#### 3.2 Breadth Layer (modifier)

Cross-sector participation adds confidence:

| Condition | Modifier |
|-----------|----------|
| Theme spans 3+ sectors | +1 level (cap at High) |
| Theme spans 2 sectors | No change |
| Theme in 1 sector only | -1 level (floor at Low) |

#### 3.3 Narrative Layer (modifier, applied in Step 4)

WebSearch confirmation adjusts confidence:

| Narrative Finding | Modifier |
|-------------------|----------|
| Strong confirmation (multiple sources, clear catalysts) | +1 level |
| Mixed signals | No change |
| Contradictory narrative (bearish articles for bullish theme) | -1 level |

### Final Confidence

```
confidence = apply_modifiers(quantitative_base, breadth_modifier, narrative_modifier)
confidence = clamp(confidence, Low, High)
```

---

## Direction Detection

Theme direction (**leading** vs. **lagging**) is determined by relative rank, not absolute price change:

### Algorithm

1. Each industry gets a `rank_direction` based on its position in the momentum-ranked list: top half = "bullish" (leading), bottom half = "bearish" (lagging).
2. Theme direction is the majority vote of its constituent industries' `rank_direction`.

```python
# Industry-level (industry_ranker.py)
rank_direction = "bullish" if rank <= len(industries) // 2 else "bearish"

# Theme-level (theme_classifier.py)
direction = majority_vote([ind.rank_direction for ind in theme.industries])
```

### Important: Relative, Not Absolute

**LEAD/LAG direction is relative.** A "lagging" theme may still have positive absolute returns — it simply underperforms relative to other themes. This means:
- **LEAD** themes: Suitable for overweight / new positions
- **LAG** themes: Candidates for underweight reduction, **not** short signals

---

## Data Sources

### Primary: FINVIZ

**Elite Mode (recommended):**
- CSV export endpoint: `https://elite.finviz.com/export/screener?type=stocks&v=151&f=ind_{code},cap_smallover,...&c=1,6,66,67&ft=4&auth=KEY` (`type=` is required from 2026-12-07; `c=1,6,66,67` pins Ticker, Market Cap, Change, Volume)
- Provides (pinned columns): ticker, market cap, change%, volume. Elite Market Cap is converted from millions to dollars; Volume is a share count.
- Rate limit: 0.5s between requests
- Coverage: Full stock universe per industry

**Public Mode (fallback):**
- HTML scraping: `https://finviz.com/screener.ashx?v=151&f=ind_{code},cap_smallover`
- Provides: Same fields but limited to page 1 (~20 stocks per industry)
- Rate limit: 2.0s between requests (aggressive scraping may trigger blocks)
- Coverage: Top 20 stocks per industry by market cap

### Elite representative-stock ranking (#800)

With dynamic stock selection enabled and the representative-stock source set to
Elite, `c=1,6,66,67` makes Volume available to the existing composite ranking:
40% market-cap rank, 30% directional change rank and 30% volume rank. These are
representative-stock weights, separate from Theme Heat and stock-leadership
scoring. Universe filters are unchanged; the added ranking component can change
which representatives reach the per-theme limit.

Synthetic before/after example (two stocks in one industry; normalized rank scores):

| Stock | Market Cap ($) | Change | Volume (shares) | Before: no Volume | After: with Volume |
|---|---:|---:|---:|---:|---:|
| LOWVOL | 2,000,000,000 | +4% | 100,000 | 0.7857 (first) | 0.7000 (second) |
| HIGHVOL | 1,000,000,000 | +5% | 9,000,000 | 0.7143 (second) | 0.8000 (first) |

Before the fix, the missing Volume factor re-normalized cap/change weights to
4/7 and 3/7. The existing bearish change-rank rule uses absolute change; the
same example at -4%/-5% produces the same before/after scores. This is an
offline regression example, not a live observation or a trading recommendation.

A missing Volume column is logged. An empty, malformed, negative or overflowing
Elite Volume value becomes `None`; a count-only warning identifies affected rows
and the existing per-row weight re-normalization. Valid zero volume remains
available. Returned details retain `volume: null` when unknown, so consumers can
inspect the available input alongside `composite_score`. The public/FMP parsers,
scoring formula and fallback chain are unchanged.

### Secondary: FMP API (optional)

- P/E ratios for valuation analysis
- Not required; FINVIZ forward P/E used as fallback
- Useful for more granular valuation metrics

### Tertiary: uptrend-dashboard (optional)

- CSV output from the uptrend-dashboard skill
- Provides 3-point technical evaluation per stock
- Significantly improves uptrend ratio accuracy
- If unavailable, FINVIZ price-vs-SMA200 is used as proxy

### Quaternary: WebSearch (narrative layer)

- Used for narrative confirmation in Step 4
- Not automated; Claude performs searches during workflow
- Subjective assessment of media coverage and analyst sentiment

---

## Integration with uptrend-dashboard

When uptrend-dashboard data is available, the theme detector uses it for enhanced 3-point evaluation:

**3-Point Evaluation Criteria:**
1. Price > 50-day SMA (short-term trend)
2. 50-day SMA > 200-day SMA (medium-term trend, golden/death cross)
3. 200-day SMA is rising (long-term trend confirmation)

**Stocks meeting all 3 points** = in confirmed uptrend
**Stocks meeting 0 points** = in confirmed downtrend

This provides more accurate uptrend ratios than simple price-above-SMA200 proxy.

---

## Output Schema

### JSON Output Structure

```json
{
  "metadata": {
    "date": "2026-02-16",
    "mode": "elite",
    "themes_analyzed": 14,
    "industries_scanned": 145,
    "total_stocks": 5200,
    "uptrend_data_available": true,
    "execution_time_seconds": 150
  },
  "themes": [
    {
      "name": "AI & Semiconductors",
      "direction": "Bullish",
      "direction_strength": "Strong",
      "theme_heat": 82,
      "heat_components": {
        "momentum": 90,
        "volume": 75,
        "uptrend": 85,
        "breadth": 70
      },
      "lifecycle": {
        "stage": "Mature",
        "duration_weeks": 12,
        "extremity_pct": 45,
        "relative_pe": 1.8,
        "etf_proliferation_score": 100,
        "etf_count": 11
      },
      "confidence": "High",
      "confidence_components": {
        "quantitative": "High",
        "breadth_modifier": "+1",
        "narrative_modifier": "pending"
      },
      "industries": [
        {
          "name": "Semiconductors",
          "change_pct": 4.2,
          "avg_relative_volume": 1.8,
          "uptrend_ratio": 0.75,
          "stock_count": 35
        }
      ],
      "top_stocks": [
        {"ticker": "NVDA", "change_pct": 6.5, "relative_volume": 2.1},
        {"ticker": "AVGO", "change_pct": 4.8, "relative_volume": 1.9}
      ],
      "proxy_etfs": ["SMH", "SOXX", "AIQ", "BOTZ"]
    }
  ],
  "industry_rankings": {
    "top_10": [...],
    "bottom_10": [...]
  },
  "sector_summary": {
    "Technology": {"uptrend_ratio": 0.65, "avg_change_pct": 2.1},
    "Energy": {"uptrend_ratio": 0.40, "avg_change_pct": -1.5}
  }
}
```

---

## Known Limitations

1. **Static theme definitions**: Cross-sector themes are predefined in `cross_sector_themes.md`. New themes (e.g., a sudden meme-stock theme) are not automatically detected.

2. **Industry granularity**: FINVIZ industry classification may not perfectly map to investment themes. Some industries span multiple themes.

3. **Single-stock dominance**: Large-cap stocks (e.g., NVDA in AI) can skew theme-level metrics. Market-cap weighting amplifies this effect.

4. **Temporal lag**: Weekly performance data does not capture intraday or same-day momentum shifts.

5. **ETF catalog staleness**: The thematic ETF catalog is manually maintained and may not reflect recent ETF launches or closures.

6. **Public mode data limits**: Only ~20 stocks per industry are captured, which may underrepresent small/mid-cap participation.

7. **Duration tracking**: First-run analysis cannot assess theme duration without historical baseline data.

8. **Narrative subjectivity**: Confidence adjustment from WebSearch is inherently subjective and depends on search result quality.

9. **Survivorship bias**: Analysis only covers currently listed stocks and active ETFs, missing delisted or closed instruments.

10. **FINVIZ data delays**: Public FINVIZ data is 15-minute delayed; Elite provides real-time during market hours.
