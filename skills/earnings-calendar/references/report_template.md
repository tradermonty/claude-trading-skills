# Report Template

Step 6 report structure, moved verbatim from `SKILL.md`.

```markdown
# Upcoming Earnings Calendar - Week of [START_DATE] to [END_DATE]

**Report Generated**: [Current Date]
**Data Source**: FMP API (Mid-cap and above, >$2B market cap)
**Coverage Period**: Next 7 days
**Total Companies**: [COUNT]

---

## Executive Summary

- **Total Companies Reporting**: [TOTAL_COUNT]
- **Mega/Large Cap (>$10B)**: [LARGE_CAP_COUNT]
- **Mid Cap ($2B-$10B)**: [MID_CAP_COUNT]
- **Peak Day**: [DAY_WITH_MOST_EARNINGS]

---

## [Day Name], [Full Date]

### Before Market Open (BMO)

| Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est. |
|--------|---------|------------|--------|----------|--------------|
| [TICKER] | [COMPANY] | [MCAP] | [SECTOR] | [EPS] | [REV] |

### After Market Close (AMC)

| Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est. |
|--------|---------|------------|--------|----------|--------------|
| [TICKER] | [COMPANY] | [MCAP] | [SECTOR] | [EPS] | [REV] |

### Time Not Announced (TAS)

| Ticker | Company | Market Cap | Sector | EPS Est. | Revenue Est. |
|--------|---------|------------|--------|----------|--------------|
| [TICKER] | [COMPANY] | [MCAP] | [SECTOR] | [EPS] | [REV] |

---

[Repeat for each day of week]

---

## Key Observations

### Highest Market Cap Companies This Week
1. [COMPANY] ([TICKER]) - [MCAP] - [DATE] [TIME]
2. [COMPANY] ([TICKER]) - [MCAP] - [DATE] [TIME]
3. [COMPANY] ([TICKER]) - [MCAP] - [DATE] [TIME]

### Sector Distribution
- **Technology**: [COUNT] companies
- **Healthcare**: [COUNT] companies
- **Financial**: [COUNT] companies
- **Consumer**: [COUNT] companies
- **Other**: [COUNT] companies

### Trading Considerations
- **Days with Heavy Volume**: [DATES with multiple large-cap earnings]
- **Pre-Market Focus**: [BMO companies that may move markets]
- **After-Hours Focus**: [AMC companies that may move markets]

---

## Timing Reference

- **BMO (Before Market Open)**: Announcements typically around 6:00-8:00 AM ET before market opens at 9:30 AM ET
- **AMC (After Market Close)**: Announcements typically around 4:00-5:00 PM ET after market closes at 4:00 PM ET
- **TAS (Time Not Announced)**: Specific time not yet disclosed - monitor company investor relations

---

## Data Notes

- **Market Cap Categories**:
  - Mega Cap: >$200B
  - Large Cap: $10B-$200B
  - Mid Cap: $2B-$10B

- **Filter Criteria**: This report includes companies with market cap $2B and above (mid-cap+) with earnings scheduled for the next week.

- **Data Source**: Financial Modeling Prep (FMP) API

- **Data Freshness**: Earnings dates and times can change. Verify critical dates through company investor relations websites for the most current information.

- **EPS and Revenue Estimates**: Analyst consensus estimates from FMP API. Actual results will be reported on earnings date.

---

## Additional Resources

- **FMP API Documentation**: https://site.financialmodelingprep.com/developer/docs
- **Seeking Alpha Calendar**: https://seekingalpha.com/earnings/earnings-calendar
- **Yahoo Finance Calendar**: https://finance.yahoo.com/calendar/earnings

---

*Report generated using FMP Earnings Calendar API with mid-cap+ filter (>$2B market cap). Data current as of report generation time. Always verify earnings dates through official company sources.*
```
