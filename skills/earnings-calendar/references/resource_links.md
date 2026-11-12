# Resource Links

Moved verbatim from `SKILL.md`.

**FMP API**:
- Main Documentation: https://site.financialmodelingprep.com/developer/docs
- Get API Key: https://site.financialmodelingprep.com/developer/docs
- Earnings Calendar API: https://site.financialmodelingprep.com/developer/docs/earnings-calendar-api
- Company Profile API: https://site.financialmodelingprep.com/developer/docs/companies-key-metrics-api
- Pricing/Rate Limits: https://site.financialmodelingprep.com/developer/docs/pricing

**Supplementary Sources** (for verification):
- Seeking Alpha: https://seekingalpha.com/earnings/earnings-calendar
- Yahoo Finance: https://finance.yahoo.com/calendar/earnings
- MarketWatch: https://www.marketwatch.com/tools/earnings-calendar

**Skill Resources**:
- FMP API Guide: `references/fmp_api_guide.md`
- Python Script: `scripts/fetch_earnings_fmp.py`
- Vendored FMP Compat: `scripts/_fmp_compat.py` (v3→stable rewrite shim)
- Vendored FMP Client: `scripts/fmp_client.py` (generated; handles rate limiting, single 429 retry, and header auth) — note: HTTP failures print one generic `ERROR: API request failed: …` client line plus the script's mapped `❌ ERROR:` message
- Report Template: `assets/earnings_report_template.md`
