# Performance and Cost Optimization

Moved verbatim from `SKILL.md`.

### API Call Comparison

**Two-Stage Screening (FINVIZ + FMP):**
- FINVIZ: 1 API call
- FMP Quote API: ~30-50 calls (one per pre-screened symbol)
- FMP Financial Data: ~150-250 calls (5 endpoints × 30-50 symbols)
- **Total FMP calls: ~180-300**

**FMP-Only Screening:**
- FMP Stock Screener: 1 call (returns 100-1000 stocks)
- FMP Financial Data: ~500-5000 calls (5 endpoints × 100-1000 symbols)
- **Total FMP calls: ~500-5000**

**Savings: 60-94% reduction in FMP API usage**

### Cost Analysis

**FINVIZ Elite:**
- Monthly: $39.50
- Annual: $299.50 (~$24.96/month)

**FMP API:**
- Free tier: 250 calls/day rate limit. The stock-screener endpoint used by FMP-only screening is not on the free plan (2026-11). Two-stage screening needs the per-symbol analysis endpoints too (ratios, income-statement, dividends, historical prices), which were reported returning HTTP 402 in a synthetic review for issue #777 (not verified on a live Basic key); when any of them is plan-gated, the screener reports the run as plan-gated instead of returning zero candidates. See `docs/en/getting-started.md#fmp-plans`.
- Paid plans: prices and limits change; see `site.financialmodelingprep.com/pricing-plans` in a browser

**Recommendation:**
- **For free FMP tier users**: Two-stage screening (FINVIZ + FMP free tier) fits the call budget, but only if the per-symbol analysis endpoints are included in the plan (see above); FMP-only needs the plan-gated stock screener
- **For paid FMP tier users**: Either approach works; two-stage is faster
- **Budget option**: FMP-only on a plan that includes the stock screener (the free plan does not)
- **Optimal option**: FINVIZ Elite ($330/year) + FMP free tier for two-stage screening (assuming the per-symbol analysis endpoints are included; unverified on a live Basic key)
