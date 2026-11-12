# Common Use Cases

Moved verbatim from `SKILL.md`.

**Use Case 1: Technology Sector Pairs**
```
User: "Find pair trading opportunities in tech stocks"

Workflow:
1. Screen Technology sector for stocks with market cap > $10B
2. Calculate all pairwise correlations
3. Filter pairs with correlation ≥ 0.75
4. Run cointegration tests
5. Identify current z-score extremes (|z| > 2.0)
6. Generate top 10 pairs report
```

**Use Case 2: Specific Pair Analysis**
```
User: "Analyze AAPL and MSFT as a pair trade"

Workflow:
1. Fetch 2-year price history for AAPL and MSFT
2. Calculate correlation and beta
3. Test for cointegration
4. Calculate current spread and z-score
5. Generate entry/exit recommendation
6. Provide position sizing guidance
```

**Use Case 3: Regional Bank Pairs**
```
User: "Screen for pairs among regional banks"

Workflow:
1. Filter Financials sector for industry = "Regional Banks"
2. Exclude banks with <$5B market cap
3. Calculate pairwise statistics
4. Rank by cointegration strength
5. Focus on pairs with half-life < 45 days
6. Report top 5 mean-reverting pairs
```
