# Example Usage Scenarios

Moved verbatim from `SKILL.md`.

### Example 1: CSV-Only Analysis (No Charts)

```
User: "breadth分析して" (Analyze breadth)
[No chart images provided]

Breadth Analyst:
1. Executes fetch_breadth_csv.py to get latest CSV data
2. Reads breadth_chart_methodology.md
3. Analyzes CSV data:
   - 200MA: 62.26% (healthy)
   - 8MA: 67.56% (healthy_bullish)
   - 8MA vs 200MA: +5.30pt (NO dead cross)
   - Uptrend Ratio: 33.03% GREEN (neutral_bullish)
   - Sector summary with overbought/oversold sectors
4. Assesses market regime based on CSV values
5. Generates report: breadth_combined_analysis_2026-03-16.md
```

### Example 2: Strategic Breadth Analysis (Chart 1 Only)

```
User: "Please analyze this S&P 500 breadth chart and tell me where we are in the market cycle."
[Provides Chart 1 image: 200MA Breadth Index]

Breadth Analyst (thinking in English):
1. Executes CSV fetch for authoritative numerical values
2. Confirms receipt of Chart 1 (200MA-based breadth index)
3. Reads breadth_chart_methodology.md for Chart 1 guidance
4. Two-stage analysis: full chart → right edge extraction
5. Cross-checks CSV values with chart readings
6. Generates comprehensive report in English
```

### Example 3: Combined Strategic + Tactical Analysis (Both Charts)

```
User: "Analyze both of these breadth charts and give me your overall market view."
[Provides both Chart 1 and Chart 2 images]

Breadth Analyst (thinking in English):
1. Executes CSV fetch as PRIMARY source
2. Confirms receipt of both charts
3. Reads full breadth_chart_methodology.md
4. Two-stage analysis for each chart
5. Cross-checks all values against CSV data
6. Combined assessment and unified recommendation
7. Generates comprehensive combined report
```
