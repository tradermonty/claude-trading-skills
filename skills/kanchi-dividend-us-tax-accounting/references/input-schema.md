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
- `hold_days_in_window`: non-negative integer holding days in the applicable
  ex-dividend window. Missing or `null` values remain unknown: stock rows emit
  `assumption_required`, while REIT/BDC/MLP rows retain their instrument-specific
  planning labels. Strings, booleans, floats, and negative counts are rejected;
  the CLI exits 1 with an error on stderr before writing reports.

For a not-yet-owned candidate, create a hypothetical row using the intended
account type and leave `hold_days_in_window` absent. Treat the resulting advice
as planning support, not a confirmed tax classification.
