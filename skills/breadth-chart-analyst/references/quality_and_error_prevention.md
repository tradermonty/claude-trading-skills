# Quality Standards and Common Errors

Moved verbatim from `SKILL.md`.

## Quality Standards

### Objectivity Requirements

- Base all analysis strictly on observable chart data
- Do not incorporate external information (news, fundamentals) unless specifically relevant
- Use precise technical terminology consistently
- Distinguish clearly between factual observations and probabilistic forecasts
- Acknowledge uncertainty when signals are ambiguous

### Completeness Requirements

- Address all relevant sections of the analysis template
- Provide specific numerical values for all key metrics
- Justify probability estimates with technical factors
- Include invalidation levels for each scenario
- Compare current readings to historical patterns visible on the charts

### Clarity Requirements

- Write in professional, analytical English
- Use clear section headings and structure
- Present information in tables where appropriate
- Make recommendations specific and actionable
- Avoid jargon without explanation

### Strategy Adherence Requirements

- Apply backtested strategy rules correctly
- Distinguish between strategic (Chart 1) and tactical (Chart 2) signals
- Provide clear position status (Long/Flat/Entering/Exiting)
- Include specific entry/exit levels when applicable
- Address risk management (stop losses, position sizing)

## Common Analysis Errors and How to Avoid Them

### Error 1: Confusing 8MA with 200MA

**Symptom**: Report claims 8MA is rising when it's actually the 200MA that's rising

**Prevention**:
- ALWAYS verify: 8MA = ORANGE, 200MA = GREEN
- Check line volatility: 8MA moves faster with more volatility
- If unsure, state: "Based on line color, I identify the [orange/green] line as [8MA/200MA]"

### Error 2: Reading Historical Trends Instead of Current Direction

**Symptom**: Report describes what happened 1-2 months ago, not what's happening NOW

**Prevention**:
- Focus ONLY on rightmost 3-5 data points
- Explicitly write: "At the CURRENT rightmost edge, 8MA is at X% and is [rising/falling]"
- Ignore what happened in September if we're analyzing November

### Error 3: Missing Death Cross or Golden Cross Formation

**Symptom**: Report is bullish when 8MA and 200MA are about to death cross (bearish)

**Prevention**:
- ALWAYS check: "Are 8MA and 200MA getting closer (converging) or further apart (diverging)?"
- If converging with 8MA above 200MA → Potential death cross → BEARISH
- If converging with 8MA below 200MA → Potential golden cross → BULLISH
- Explicitly state: "8MA is currently [above/below] 200MA, and they are [converging/diverging]"

### Error 4: Ignoring Pink Background Shading

**Symptom**: Report claims bullish setup when chart shows pink downtrend background

**Prevention**:
- Check for pink shading at the rightmost edge
- Pink background = Downtrend period = Bearish conditions
- If pink shading present, report MUST acknowledge bearish conditions

### Error 5: Claiming Reversal Too Early

**Symptom**: Report says "BUY signal confirmed" after only 1 week of increase

**Prevention**:
- Require 2-3 CONSECUTIVE weeks of 8MA increase for confirmation
- If only 1 week: Signal is "DEVELOPING", not "CONFIRMED"
- If 8MA rises then falls again: Signal is "FAILED", not valid
