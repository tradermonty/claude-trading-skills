# Input Schema

Use this normalized JSON schema for `build_review_queue.py`.

## Required Top-Level Fields

- `as_of`: ISO date string.
- `holdings`: array of ticker records.

## Holding Object

```json
{
  "ticker": "ABC",
  "instrument_type": "stock",
  "dividend": {
    "latest_regular": 0.50,
    "prior_regular": 0.52,
    "is_missing": false
  },
  "cashflow": {
    "fcf": 1200.0,
    "ffo": null,
    "nii": null,
    "dividends_paid": 900.0,
    "coverage_ratio_history": [0.72, 0.85]
  },
  "balance_sheet": {
    "net_debt_history": [3000.0, 3400.0, 3800.0],
    "interest_coverage_history": [4.6, 3.8, 2.9]
  },
  "capital_returns": {
    "buybacks": 250.0,
    "dividends_paid": 900.0,
    "fcf": 1200.0
  },
  "filings": {
    "recent_text": "8-K filed. No restatement language.",
    "latest_8k_text": "Item 4.02 non-reliance ...",
    "headlines": ["Company files 8-K", "Audit committee review announced"]
  },
  "operations": {
    "revenue_cagr_5y": -1.2,
    "margin_trend": "down",
    "guidance_trend": "down",
    "dividend_growth_stalled": true
  }
}
```

## Minimal Viable Input

If upstream data is partial, include at least:
- `ticker`
- `instrument_type`
- `dividend.latest_regular`
- `dividend.prior_regular`

The rule engine will still run and skip unavailable triggers.
