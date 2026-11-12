# Common Use Cases

Typical request flows, moved verbatim from `SKILL.md`.

**Use Case 1: Learn Strategy**
```
User: "Explain a covered call"

Workflow:
1. Read the strategy descriptions in this document and the pricing methodology
   in references/black_scholes_methodology.md
2. Explain concept, risk/reward, when to use
3. Simulate example on AAPL
4. Show P/L diagram
5. Compare to alternatives
```

**Use Case 2: Analyze Specific Trade**
```
User: "Analyze $180/$185 bull call spread on AAPL, 30 days"

Workflow:
1. Fetch AAPL price from FMP
2. Calculate HV or ask user for IV
3. Price both options (Black-Scholes)
4. Calculate Greeks
5. Simulate P/L
6. Generate analysis report
```

**Use Case 3: Earnings Strategy**
```
User: "Should I trade options before NVDA earnings?"

Workflow:
1. Fetch NVDA earnings date (Earnings Calendar)
2. Calculate days to earnings
3. Estimate IV percentile (if user provides IV)
4. Suggest straddle/strangle vs iron condor
5. Warn about IV crush
6. Simulate both strategies
```

**Use Case 4: Portfolio Greeks Check**
```
User: "What are my total portfolio Greeks?"

Workflow:
1. User provides current positions
2. Calculate Greeks for each position
3. Sum Greeks across portfolio
4. Assess overall exposure
5. Suggest adjustments if needed
```
