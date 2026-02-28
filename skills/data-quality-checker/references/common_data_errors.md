# Common Data Errors in Market Analysis

Reference document cataloging frequently observed data quality issues
in market analysis documents, blog posts, and strategy reports.

## 1. FRED Data Delay Patterns

Economic data sources have varying publication delays. Using stale data
without noting the lag can mislead readers.

| Data Series | Source | Typical Delay | Notes |
|-------------|--------|---------------|-------|
| VIX Close | CBOE via FRED | T+1 business day | VIX settles after market close |
| GDP (Advance) | BEA | ~T+30 days after quarter end | First estimate; revised twice |
| GDP (Final) | BEA | ~T+90 days after quarter end | Third and final estimate |
| CPI | BLS | ~T+14 days after reference month | Released mid-month for prior month |
| PCE | BEA | ~T+30 days after reference month | Fed's preferred inflation gauge |
| NFP (Nonfarm Payrolls) | BLS | First Friday after reference month | Subject to significant revisions |
| ISM Manufacturing | ISM | First business day of the month | For the prior month |
| FOMC Rate Decision | Federal Reserve | Same day (2:00 PM ET) | Minutes released 3 weeks later |
| 10Y Treasury Yield | US Treasury | T+1 | Daily constant maturity rate |
| Consumer Sentiment | U of Michigan | Preliminary: mid-month; Final: end of month | Two releases per month |

### Common Error Pattern

Writing "VIX is at 18.5 as of today" when the FRED data is actually
from yesterday's close. Always note the data date explicitly.

## 2. ETF vs Futures Scale Ratios

A frequent error is applying a futures price to an ETF label or vice versa.
The approximate scale ratios help catch such mistakes.

| Asset | ETF Price (approx) | Futures Price (approx) | Ratio (Futures/ETF) |
|-------|--------------------|----------------------|---------------------|
| Gold | GLD ~$260 | GC ~$2,600 | ~10x |
| Silver | SLV ~$28 | SI ~$30 | ~1.1x |
| S&P 500 | SPY ~$580 | ES ~$5,800 (SPX) | ~10x |
| Crude Oil | USO ~$72 | CL ~$78 | ~1.1x |
| Treasuries | TLT ~$92 | ZB ~$118 | ~1.3x |

**Key insight**: Gold and S&P 500 have a ~10x ratio between ETF and
futures/index prices. This is the most common source of price scale errors.

## 3. Common Date Errors

### 3.1 Weekday Mismatches

The most frequent date error is stating the wrong day of the week.
This is especially common in:

- Weekly strategy reports that reference multiple future dates
- Japanese-language reports using kanji weekday notation
- Cross-year date references (December dates written in January)

**Prevention**: Always verify weekday with `calendar.weekday(year, month, day)`.

### 3.2 Holiday Oversights

Common US market holidays that are often overlooked:

| Holiday | Date | Market Status |
|---------|------|---------------|
| New Year's Day | January 1 | Closed |
| MLK Day | Third Monday in January | Closed |
| Presidents' Day | Third Monday in February | Closed |
| Good Friday | Friday before Easter (varies) | Closed |
| Memorial Day | Last Monday in May | Closed |
| Juneteenth | June 19 | Closed |
| Independence Day | July 4 | Closed (early close July 3) |
| Labor Day | First Monday in September | Closed |
| Thanksgiving | Fourth Thursday in November | Closed (early close Wed) |
| Christmas | December 25 | Closed (early close Dec 24) |

**Error pattern**: "Markets will react on Monday January 1" -- markets are
closed on New Year's Day.

### 3.3 Year Inference Errors

When dates lack an explicit year:
- "December 25" written in a January 2026 report likely refers to December 2025
- "March 15" written in a January 2026 report likely refers to March 2026
- The 6-month window heuristic: if the date is more than 6 months away from
  the reference date, consider the adjacent year

## 4. Allocation Total Error Patterns

### 4.1 Off-by-Rounding

When individual allocations are rounded, the sum may not equal 100%:

```
Stocks:  33.3%
Bonds:   33.3%
Cash:    33.3%
Total:   99.9%  (should be 100%)
```

**Fix**: Adjust one value to absorb the rounding difference (e.g., Cash: 33.4%).

### 4.2 Range Notation Pitfalls

Range-based allocations (e.g., "40-45%") require checking both the minimum
and maximum totals:

```
Stocks:  50-55%    min=50  max=55
Bonds:   25-30%    min=25  max=30
Gold:    15-20%    min=15  max=20
Cash:     5-10%    min=5   max=10
                   ------- -------
                   min=95  max=115
```

This is valid because 100% falls within [95%, 115%].

**Invalid example**:
```
A: 60-65%    min=60  max=65
B: 30-35%    min=30  max=35
C: 15-20%    min=15  max=20
             ------- -------
             min=105 max=120
```

This is invalid because the minimum (105%) already exceeds 100%.

### 4.3 Forgetting Cash or "Other"

A common mistake is listing specific allocations that sum to less than 100%
without an explicit "Cash" or "Other" category.

### 4.4 Non-Allocation Percentages

Not all percentages are allocations. The checker should ignore:
- Probability statements: "There is a 60% chance..."
- Indicator values: "RSI at 35%", "YoY growth of 3.2%"
- Trigger conditions: "If drawdown exceeds 10%..."
- Historical returns: "S&P 500 returned 12% last year"

## 5. Unit Confusion Patterns

### 5.1 Basis Points vs Percentage

| Expression | Meaning | Common In |
|-----------|---------|-----------|
| 25 bp | 0.25 percentage points | Bond yields, rate changes |
| 0.25% | 0.25 percent | Same concept, different notation |
| 25% | 25 percent | Equity returns, allocations |

**Error pattern**: "The Fed raised rates by 25%" (should be "25 bp" or "0.25%").

### 5.2 Dollar vs Cent

| Expression | Meaning |
|-----------|---------|
| $1.50 | One dollar and fifty cents |
| 150 cents | Same value |
| $0.015 | 1.5 cents (common in EPS) |

### 5.3 Missing Units

Statements like "Gold moved 50 today" are ambiguous:
- $50 (absolute price change)?
- 50 bp (basis points)?
- 0.50% (percentage change)?

Always specify the unit: "Gold moved $50 today" or "Gold moved 2.1% today."

### 5.4 Per-Unit vs Total Value

Futures contracts represent multiple units:
- Gold (GC): 100 troy ounces per contract
- Crude Oil (CL): 1,000 barrels per contract
- E-mini S&P (ES): $50 x index per contract

A "$50 move in gold" means:
- Per ounce: $50
- Per contract: $5,000 (100 oz x $50)

Always clarify which is meant.

## 6. Timezone Confusion

| Abbreviation | UTC Offset (Winter) | UTC Offset (Summer) |
|-------------|--------------------|--------------------|
| ET (Eastern) | UTC-5 | UTC-4 |
| CT (Central) | UTC-6 | UTC-5 |
| PT (Pacific) | UTC-8 | UTC-7 |
| JST (Japan) | UTC+9 | UTC+9 (no DST) |
| GMT/UTC | UTC+0 | UTC+0 |

**ET to JST conversion**:
- Winter (Nov first Sun to Mar second Sun): JST = ET + 14 hours
- Summer (Mar second Sun to Nov first Sun): JST = ET + 13 hours

**Common error**: Forgetting to account for DST transitions, especially
around the March and November changeover dates.
