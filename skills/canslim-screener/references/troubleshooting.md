# Troubleshooting

Moved verbatim from `SKILL.md`.

### Issue 1: FMP API Rate Limit Exceeded

**Symptoms:**
```
ERROR: 429 Too Many Requests - Rate limit exceeded
Retrying in 60 seconds...
```

**Causes:**
- Running multiple screenings within short time window
- Exceeding 250 calls/day (free tier limit)
- Other applications using same API key

**Solutions:**
1. **Wait and Retry**: Script auto-retries after 60s
2. **Reduce Universe**: Use `--max-candidates 30` to lower API usage
3. **Check Daily Usage**: Free tier resets at midnight UTC
4. **Upgrade Plan**: FMP Starter ($29.99/month) provides 750 calls/day

### Issue 2: Missing Required Libraries

**Symptoms:**
```
ERROR: required libraries not found. Install with: pip install beautifulsoup4 requests lxml
```

**Solutions:**
```bash
# Install all required libraries
pip install requests beautifulsoup4 lxml

# Or install individually
pip install beautifulsoup4
pip install requests
pip install lxml
```

### Issue 3: Finviz Fallback Slow Execution

**Symptoms:**
```
Execution time: 2 minutes 30 seconds for 40 stocks (slower than expected)
```

**Causes:**
- Finviz rate limiting (2.0s per request)
- All stocks triggering fallback due to FMP data gaps

**Solutions:**
1. **Accept Delay**: 1-2 minutes for 40 stocks is normal with Finviz fallback
2. **Monitor Fallback Usage**: Check logs for "Using Finviz institutional ownership" messages
3. **Reduce Rate Limit** (advanced): Edit `finviz_stock_client.py`, change `rate_limit_seconds=2.0` to `1.5` (risk: IP ban)

**Note:** Finviz fallback adds ~2 seconds per stock but significantly improves I component accuracy (35 → 60-100 points).

### Issue 4: Finviz Web Scraping Failure

**Symptoms:**
```
WARNING: Finviz request failed with status 403 for NVDA
⚠️ Using Finviz institutional ownership data - FMP shares outstanding unavailable. Finviz fallback also unavailable. Score reduced by 50%.
```

**Causes:**
- Finviz blocking scraping requests (User-Agent detection)
- Rate limit exceeded (too many requests)
- Network issues or Finviz downtime

**Solutions:**
1. **Wait and Retry**: Rate limit resets after a few minutes
2. **Check Internet Connection**: Verify network access to finviz.com
3. **Fallback Accepted**: Script continues with FMP holder count only (I score capped at 70/100)
4. **Manual Verification**: Check Finviz website manually for blocked IP

**Graceful Degradation:**
- Script never fails due to Finviz issues
- Falls back to FMP holder count only
- User sees quality warning in report

### Issue 5: No Stocks Meet Minimum Thresholds

**Symptoms:**
```
✓ Successfully analyzed 40 stocks
Top 5 Stocks:
  1. AAPL  -  58.3 (Average)
  2. MSFT  -  55.1 (Average)
  ...
```

**Causes:**
- Bear market conditions (M component low)
- Selected universe lacks growth stocks
- Market rotation away from growth

**Solutions:**
1. **Check M Component**: If M=0 (bear market), raise cash per CANSLIM rules
2. **Expand Universe**: Try different sectors or market cap ranges
3. **Lower Expectations**: Average scores (55-65) may still be actionable in weak markets
4. **Wait for Better Setup**: CANSLIM works best in bull markets

### Issue 6: Data Quality Warnings

**Symptoms:**
```
⚠️ Revenue declining despite EPS growth (possible buyback distortion)
⚠️ Using Finviz institutional ownership data (68.3%) - FMP shares outstanding unavailable.
```

**Interpretation:**
- These are **not errors** - they are quality flags from calculators
- Revenue warning: EPS growth may be from share buybacks, not organic growth
- Finviz warning: Data source switched from FMP to Finviz (still accurate)

**Actions:**
1. Review component details in full report
2. Cross-check with fundamental analysis
3. Adjust position sizing based on risk level
4. Finviz data is reliable - no action needed for data source warnings
