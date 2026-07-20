# Tax Planning Input Schema

Provide one JSON object with a non-empty `holdings` array.

```json
{
  "holdings": [
    {
      "ticker": "JNJ",
      "instrument_type": "stock",
      "account_type": "taxable",
      "security_type": "common",
      "hold_days_in_window": 75
    }
  ]
}
```

## Holding fields

- `ticker`: ticker symbol. Required operationally; missing values render as
  `UNKNOWN` and must be corrected before acting.
- `instrument_type`: `stock`, `reit`, `bdc`, or `mlp`; defaults to `stock`.
- `account_type`: account label such as `taxable` or `ira`; defaults to
  `unknown`.
- `security_type`: `common` or `preferred`; defaults to `common`.
- `hold_days_in_window`: integer holding days in the applicable ex-dividend
  window. When absent, emit `assumption_required`.

For a not-yet-owned candidate, create a hypothetical row using the intended
account type and leave `hold_days_in_window` absent. Treat the resulting advice
as planning support, not a confirmed tax classification.
