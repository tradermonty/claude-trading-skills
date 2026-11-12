# CSV Fetch and Two-Stage Analysis Details

Step 0 and Step 1.5 details, moved verbatim from `SKILL.md`.

## Step 0 detail: expected CSV fetch output

```
============================================================
Breadth Data (CSV) - 2026-02-13
============================================================
--- Market Breadth (S&P 500) ---
200-Day MA: 62.26% (healthy (>=60%))
8-Day MA:   67.56% (healthy_bullish (60-73%))
8MA vs 200MA: +5.30pt (8MA ABOVE -- NO dead cross)
Trend: UPTREND
--- Uptrend Ratio (All Markets) ---
Current: 33.03% GREEN (neutral_bullish)
10MA: 32.65%, Slope: +0.0055, Trend: UP
--- Sector Summary ---
...
============================================================
```

## Step 1.5 detail: Why Two-Stage Analysis is Mandatory

#### Why Two-Stage Analysis is Mandatory

| Stage | Purpose | What to Extract |
|-------|---------|-----------------|
| **Stage 1 (Full)** | Historical context, trend cycles | Overall patterns, past troughs/peaks |
| **Stage 2 (Right Edge)** | **Current values (CRITICAL)** | 8MA value, 200MA value, current color, current slope |

**Common Error This Prevents:**
- LLM reads 2025 mid-year dip (8MA ~25-30%) instead of current value (8MA ~60-65%)
- By isolating the right edge, the "current" data is unambiguous

#### Analysis Protocol

1. **Read full chart** → Document historical context
2. **Run extraction script** → Generate right edge image
3. **Read right edge image** → Document current values with HIGH CONFIDENCE
4. **Cross-check**: If Stage 1 and Stage 2 values differ significantly, **Stage 2 (right edge) takes precedence**
5. **Report both**: Include Stage 1 context AND Stage 2 current values in analysis
