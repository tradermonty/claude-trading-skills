# Theme Detection Methodology

## Overview

The Theme Detector uses a **3-Dimensional Scoring Model** to identify, rank, and assess market themes. Unlike single-score ranking systems, this approach separates the intensity of a theme (heat), its maturity stage (lifecycle), and the reliability of the signal (confidence) into independent dimensions.

---

## Dimension 1: Theme Heat (0-100)

Theme Heat measures the **direction-neutral strength** of a theme. A high heat score means the theme is generating significant market activity, regardless of whether it is bullish or bearish.

### Components

#### 1.1 Momentum Score (weight: 30%)

Measures the average performance of constituent industries.

**Formula:**
```
momentum_score = normalize(weighted_avg_change_pct, scale=[-5%, +5%] -> [0, 100])

weighted_avg_change_pct = SUM(industry_change_pct * industry_market_cap) / SUM(industry_market_cap)
```

**Data Source:** FINVIZ industry performance (1-week change %)

**Scoring Scale:**
| Absolute Change % | Score |
|-------------------|-------|
| >= 5%             | 100   |
| 3-5%              | 80    |
| 1-3%              | 60    |
| 0.5-1%            | 40    |
| < 0.5%            | 20    |

Note: Absolute value is used so both strong bullish and strong bearish moves generate high heat.

#### 1.2 Volume Score (weight: 25%)

Measures abnormal volume activity across the theme.

**Formula:**
```
volume_score = normalize(avg_relative_volume, scale=[0.5, 3.0] -> [0, 100])

avg_relative_volume = MEAN(stock_volume / stock_avg_volume) for all stocks in theme
```

**Data Source:** FINVIZ relative volume (volume / avg volume ratio)

**Scoring Scale:**
| Relative Volume | Score |
|-----------------|-------|
| >= 3.0          | 100   |
| 2.0-3.0         | 80    |
| 1.5-2.0         | 60    |
| 1.0-1.5         | 40    |
| < 1.0           | 20    |

#### 1.3 Uptrend Ratio Score (weight: 25%)

Measures the percentage of stocks in the theme that are in technical uptrends.

**Formula:**
```
uptrend_score = normalize(uptrend_ratio, scale=[0%, 100%] -> [0, 100])

uptrend_ratio = count(stocks_in_uptrend) / count(total_stocks)
```

**Data Source:** uptrend-dashboard output (3-point evaluation: price > 50-day SMA, 50-day SMA > 200-day SMA, 200-day SMA rising)

**If uptrend data is unavailable:** Use price-above-SMA200 as proxy from FINVIZ data. Score is reduced by 20% confidence penalty.

**Scoring Scale:**
| Uptrend Ratio | Score |
|---------------|-------|
| >= 80%        | 100   |
| 60-80%        | 80    |
| 40-60%        | 60    |
| 20-40%        | 40    |
| < 20%         | 20    |

Note: For bearish themes, invert the ratio (use downtrend ratio instead).

#### 1.4 Breadth Score (weight: 20%)

Measures how broadly the theme is participating (not just a few large-cap names).

**Formula:**
```
breadth_score = normalize(participation_rate, scale=[0%, 100%] -> [0, 100])

participation_rate = count(stocks_moving_in_direction > 1%) / count(total_stocks)
```

**Data Source:** FINVIZ stock-level performance data

**Scoring Scale:**
| Participation Rate | Score |
|-------------------|-------|
| >= 80%            | 100   |
| 60-80%            | 80    |
| 40-60%            | 60    |
| 20-40%            | 40    |
| < 20%             | 20    |

### Theme Heat Composite

```
theme_heat = (momentum_score * 0.30) + (volume_score * 0.25) + (uptrend_score * 0.25) + (breadth_score * 0.20)
```

---

## Dimension 2: Lifecycle Maturity

Lifecycle assessment classifies a theme into one of four stages: **Early**, **Mid**, **Late**, or **Exhaustion**. This is critical for distinguishing emerging opportunities from crowded trades.

### Components

#### 2.1 Duration Score (weight: 25%)

How long the theme has been active (consecutive weeks of elevated heat).

**Measurement:** Count weeks where theme_heat >= 40.

| Duration | Stage Signal |
|----------|-------------|
| 1-3 weeks | Early |
| 4-8 weeks | Mid |
| 9-16 weeks | Late |
| > 16 weeks | Exhaustion |

**Limitation:** Duration tracking requires historical data. On first run, duration defaults to "Unknown" and lifecycle uses other factors only.

#### 2.2 Extremity Clustering Score (weight: 20%)

Percentage of stocks in the theme near 52-week highs or lows.

**Formula:**
```
extremity_pct = count(within_5pct_of_52wk_high_or_low) / count(total_stocks)
```

| Extremity % | Stage Signal |
|-------------|-------------|
| < 20%       | Early |
| 20-40%      | Mid |
| 40-60%      | Late |
| > 60%       | Exhaustion |

**Data Source:** FINVIZ 52-week high/low data

#### 2.3 Valuation Score (weight: 20%)

Average P/E ratio of theme constituents relative to S&P 500 P/E.

**Formula:**
```
relative_pe = avg_theme_pe / sp500_pe
```

| Relative P/E | Stage Signal |
|---------------|-------------|
| < 0.8         | Early (undervalued) |
| 0.8-1.2       | Mid (fair value) |
| 1.2-2.0       | Late (overvalued) |
| > 2.0         | Exhaustion (extreme) |

**Data Source:** FMP API for P/E ratios (optional; uses FINVIZ forward P/E as fallback)

#### 2.4 ETF Proliferation Score (weight: 20%)

Number of thematic ETFs tracking the theme. More ETFs indicate greater retail/institutional attention.

**Source:** `thematic_etf_catalog.md` (static reference)

| ETF Count | Score | Stage Signal |
|-----------|-------|-------------|
| 0         | 0     | Very Early |
| 1         | 20    | Early |
| 2-3       | 40    | Mid |
| 4-6       | 60    | Mid-Late |
| 7-10      | 80    | Late |
| > 10      | 100   | Exhaustion |

#### 2.5 Media/Narrative Saturation (weight: 15%)

Assessed via WebSearch during narrative confirmation step.

| Signal | Stage Signal |
|--------|-------------|
| No major media coverage | Early |
| Specialist/financial media only | Mid |
| Mainstream media coverage | Late |
| Magazine covers, viral social media | Exhaustion |

### Lifecycle Stage Classification

The final lifecycle stage is determined by majority vote across the five component signals:

```
stage_votes = [duration_signal, extremity_signal, valuation_signal, etf_signal, media_signal]
lifecycle_stage = mode(stage_votes)  # most frequent stage
```

If tied, use the more mature stage (conservative approach to protect against crowded trade risk).

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

Theme direction (bullish vs. bearish) is determined separately from heat:

### Algorithm

```python
weighted_perf = sum(industry_change_pct * industry_mcap) / sum(industry_mcap)
uptrend_ratio = count(uptrend_stocks) / count(total_stocks)  # if available

if weighted_perf > 0.5 and (uptrend_ratio > 0.5 or uptrend_data_unavailable):
    direction = "Bullish"
elif weighted_perf < -0.5 and (uptrend_ratio < 0.5 or uptrend_data_unavailable):
    direction = "Bearish"
else:
    direction = "Neutral"
```

### Direction Strength

| Absolute Weighted Performance | Strength |
|-------------------------------|----------|
| > 3%                          | Strong   |
| 1-3%                          | Moderate |
| 0.5-1%                        | Weak     |
| < 0.5%                        | Neutral  |

---

## Data Sources

### Primary: FINVIZ

**Elite Mode (recommended):**
- CSV export endpoint: `https://elite.finviz.com/export.ashx?v=151&f=ind_{code},cap_smallover,...&auth=KEY`
- Provides: ticker, company, sector, industry, market cap, P/E, change%, volume, avg volume, 52wk high/low, RSI, SMA20/50/200
- Rate limit: 0.5s between requests
- Coverage: Full stock universe per industry

**Public Mode (fallback):**
- HTML scraping: `https://finviz.com/screener.ashx?v=151&f=ind_{code},cap_smallover`
- Provides: Same fields but limited to page 1 (~20 stocks per industry)
- Rate limit: 2.0s between requests (aggressive scraping may trigger blocks)
- Coverage: Top 20 stocks per industry by market cap

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
        "stage": "Late",
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
