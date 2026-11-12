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
- Free tier: 250 calls/day (sufficient for two-stage screening)
- Starter tier: $29.99/month for 750 calls/day
- Professional tier: $79.99/month for 2000 calls/day

**Recommendation:**
- **For free FMP tier users**: Use two-stage screening (FINVIZ + FMP free tier)
- **For paid FMP tier users**: Either approach works; two-stage is faster
- **Budget option**: FMP-only with free tier (run screening every few days)
- **Optimal option**: FINVIZ Elite ($330/year) + FMP free tier = Complete solution
