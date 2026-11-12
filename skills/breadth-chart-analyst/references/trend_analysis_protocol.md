# Latest Data Point Trend Analysis Protocol

Step 4.1.5 detail, moved verbatim from `SKILL.md`. The step is mandatory for chart-image analysis.

**CRITICAL WARNING**: Charts can be deceptive. The MAJORITY of analysis errors occur because the analyst:
1. Confuses the 8MA (orange) with the 200MA (green)
2. Reads historical trends instead of the CURRENT rightmost data points
3. Misidentifies which line is rising vs falling

**BEFORE analyzing trend direction, FIRST confirm line colors**:
- ✓ **8MA = ORANGE line** (fast-moving, more volatile)
- ✓ **200MA = GREEN line** (slow-moving, smoother)
- If unsure which is which, STOP and re-examine the chart legend/colors

Focus intensively on the **rightmost 3-5 data points** of the chart (most recent weeks):

**For 8MA (Orange Line) - Analyze the very latest trajectory**:
1. **Identify the absolute latest position**: Where is the 8MA at the rightmost edge of the chart?
2. **Trace back 3-5 data points** (approximately 3-5 weeks):
   - What was the 8MA level 1 week ago?
   - What was the 8MA level 2 weeks ago?
   - What was the 8MA level 3 weeks ago?
3. **Calculate the directional change**:
   - Is the latest value HIGHER or LOWER than 1 week ago?
   - Is the latest value HIGHER or LOWER than 2 weeks ago?
   - What is the trend: consistently rising, consistently falling, or mixed?
4. **Determine the CURRENT slope** (not historical slope):
   - **Rising**: Latest data point is higher than previous 2-3 points AND shows upward curvature
   - **Falling**: Latest data point is lower than previous 2-3 points AND shows downward curvature
   - **Flat**: Latest data point is approximately equal to previous points (within 2-3%)

**Critical Questions to Answer**:
- [ ] Is the 8MA currently moving UP or DOWN at the rightmost edge?
- [ ] If there was a recent trough, has the 8MA **sustained** the upward move, or has it rolled over?
- [ ] Count consecutive periods of increase: How many consecutive periods has 8MA risen? (Need 2-3 for confirmation)
- [ ] Count consecutive periods of decrease: How many consecutive periods has 8MA fallen? (Indicates failed reversal if declining after trough)

**For 200MA (Green Line) - Analyze the very latest trajectory**:
1. **Identify the absolute latest position**: Where is the 200MA at the rightmost edge?
2. **Trace back 4-6 weeks**:
   - What was the 200MA level 2 weeks ago?
   - What was the 200MA level 4 weeks ago?
3. **Determine the CURRENT slope**:
   - Is it rising, falling, or flat in the most recent period?

**Failed Reversal Detection** (CRITICAL):
If an 8MA trough (purple ▼) was recently identified:
- [ ] Did the 8MA rise for only 1-2 periods and then turn back down?
- [ ] Did the 8MA fail to reach 60% before turning down?
- [ ] Is the 8MA currently declining again after the bounce?
- **If YES to any**: This is a **FAILED REVERSAL** - DO NOT ENTER, signal is INVALID

**Example Analysis Format**:
```
Latest 8MA Data Points (rightmost to left):
- Current (Week 0): 48%
- 1 week ago: 52%
- 2 weeks ago: 55%
- 3 weeks ago: 50%

Analysis: 8MA is FALLING. It rose from 50% to 55% (weeks 3-2), but has since declined to 48%.
This shows a failed reversal pattern - bounce was temporary, downtrend has resumed.
SLOPE: Falling (not rising!)
```

**MANDATORY CROSS-CHECK** (to catch misreadings):
After determining the trend, ask yourself:
- [ ] "If I claimed 8MA is RISING, but it's actually been FALLING for weeks, what would that look like?"
  - Answer: The rightmost data points would be LOWER than previous points (confirming FALLING)
- [ ] "Does my analysis match the visual slope of the orange line at the rightmost edge?"
  - If orange line visually slopes DOWN at the right edge → It's FALLING
  - If orange line visually slopes UP at the right edge → It's RISING
- [ ] "Is there any pink background shading (downtrend) near the rightmost edge?"
  - If YES → This confirms downtrend conditions, 8MA is likely FALLING
- [ ] "Are the 8MA and 200MA converging (getting closer) or diverging?"
  - Converging from below → Potential death cross forming → BEARISH
  - Converging from above → Potential golden cross forming → BULLISH
