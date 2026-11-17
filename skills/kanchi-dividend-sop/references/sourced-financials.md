# Sourced financial inputs and order readiness

`build_entry_signals.py --financials-json financials.json` supplements FMP data
with user-asserted financial metrics. It still fetches quotes, profiles, GAAP
EPS, FCF and dividends through FMP; this flag does not enable offline screening.
Only the listed fields are accepted. No document is fetched or verified.

```json
{
  "schema_version": 1,
  "tickers": {
    "PG": {
      "adjusted_eps": {
        "value": 6.0,
        "unit": "USD/share",
        "source": "Fictional issuer annual report",
        "as_of": "2026-05-01",
        "document_ref": "Fictional report, p. 10"
      }
    },
    "DUK": {
      "utility_metrics": {
        "ffo_to_debt": {
          "value": 0.18,
          "unit": "fraction",
          "source": "Fictional issuer credit presentation",
          "as_of": "2026-05-01",
          "document_ref": "Fictional presentation, p. 5"
        }
      }
    }
  }
}
```

Each metric requires exactly `value`, `unit`, nonblank `source`, `as_of`
(`YYYY-MM-DD`, no later than the run's `--as-of`) and nonblank `document_ref`.
The source and reference are user assertions: document existence, contents,
publication availability and freshness are not verified. Confirm those manually.
EPS and AFFO are annual per-share values in the same USD basis as the dividend;
foreign-currency values and currency conversion are unsupported. Ratios use
fractions (0.12 means 12%), never percentage points. A fraction greater than 1
is accepted except for CET1, so an adverse combined ratio is still assessed.

| Field | Unit | Valid value |
|---|---|---|
| `adjusted_eps` | `USD/share` | positive finite number |
| `reit_metrics.affo_per_share` | `USD/share` | positive finite number |
| `bank_metrics.cet1` | `fraction` | finite 0 through 1 |
| `bank_metrics.deposit_beta` | `fraction` | finite, nonnegative |
| `utility_metrics.ffo_to_debt` | `fraction` | finite, nonnegative |
| `insurer_metrics.combined_ratio` | `fraction` | finite, nonnegative |
| `bank_metrics.cre_concentration` | `category` | low, moderate, medium, high |
| `bank_metrics.npl_trend`, `bank_metrics.nco_trend` | `category` | improving, stable, deteriorating |
| `utility_metrics.allowed_roe_trend` | `category` | rising, stable, falling, adverse |
| `utility_metrics.rate_case_status` | `category` | constructive, neutral, pending, adverse, pending_adverse |
| `utility_metrics.equity_issuance_risk` | `category` | low, moderate, high, dilutive |
| `insurer_metrics.reserve_development` | `category` | favorable, neutral, adverse |
| `insurer_metrics.statutory_capital` | `category` | strong, adequate, weak |

JSON numbers must be finite and cannot be booleans or strings. Valid inputs
merge into the provider financials; unrelated values are retained. Output
`provenance.manual_financials` records each accepted value and its metadata with
`input_method: MANUAL`. Adjusted EPS also sets `adjusted_eps_source: MANUAL`.
Missing ticker entries retain existing missing-data gates. Invalid metric
records, unknown fields and empty ticker records produce explicit
`manual_financials:*` blockers and `provenance.manual_financials_errors`.
They cap payout safety at HOLD-REVIEW; an existing FAIL stays FAIL. An invalid
manual value never silently restores readiness using a provider fallback.
Malformed file structure, duplicate JSON keys at any depth, or colliding ticker
names (case/whitespace normalized) exit 2 before provider calls or reports.

`order_ready` is the aggregate screening readiness field, present in JSON,
CSV and Markdown. It is true only when timing is TRIGGERED, verdict is
CLEAN-PASS or CONDITIONAL-PASS, final `t1_blocked` is false, and no
`pre_order_blockers` remain. WAIT, ASSUMPTION-REQUIRED, PASS-CAUTION and missing
Step-1/safety/event evidence are not ready. A utility with an open FFO/debt
blocker is never ready, even if its legacy T1 flag is false.

`event_t1_blocked` means the event cap alone blocks the first tranche.
`t1_blocked` retains its legacy meaning: final T1 restriction after verdict
synthesis (it may be false while a pre-order blocker remains). Neither replaces
`order_ready`. A ready screening result is not a broker authorization or trade
instruction; human review and existing order gates still apply.
