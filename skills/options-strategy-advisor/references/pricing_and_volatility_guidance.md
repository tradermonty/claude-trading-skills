# Pricing and Volatility Guidance

Key principles on theoretical pricing limits and volatility, moved verbatim from `SKILL.md`.

### Theoretical Pricing Limitations

**What Users Should Know:**
1. **Black-Scholes Assumptions:**
   - European-style options (can't exercise early)
   - Constant volatility (IV changes in reality)
   - No transaction costs
   - Continuous trading

2. **Real vs Theoretical:**
   - Bid-ask spread: Actual cost higher than theoretical
   - American options: Can be exercised early (especially ITM puts)
   - Liquidity: Wide markets on illiquid options
   - Dividends: Ex-dividend dates affect pricing

3. **Best Practices:**
   - Use as educational tool and comparative analysis
   - Get real quotes from broker before trading
   - Understand theoretical price ≈ mid-market price
   - Account for commissions and slippage

### Volatility Guidance

**Historical vs Implied Volatility:**

```
Historical Volatility (HV): What happened
- Calculated from past price movements
- Objective, based on data
- Available for free (FMP API)

Implied Volatility (IV): What market expects
- Derived from option prices
- Subjective, based on supply/demand
- Requires live options data (user provides)

Comparison:
- IV > HV: Options expensive (consider selling)
- IV < HV: Options cheap (consider buying)
- IV = HV: Fairly priced
```

**IV Percentile:**

User provides current IV, we calculate percentile:
```python
# Fetch 1-year HV data
historical_hvs = calculate_hv_series(prices_1yr, window=30)

# Calculate IV percentile
iv_percentile = percentileofscore(historical_hvs, current_iv)

if iv_percentile > 75:
    guidance = "High IV - consider selling premium (credit spreads, iron condors)"
elif iv_percentile < 25:
    guidance = "Low IV - consider buying options (long calls/puts, debit spreads)"
else:
    guidance = "Normal IV - any strategy appropriate"
```
