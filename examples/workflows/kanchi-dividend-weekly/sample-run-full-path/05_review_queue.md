# Dividend Review Queue (as_of: 2026-06-27)

- Generated at: `2026-06-27T16:00:00+00:00`
- As of: `2026-06-27`

## Summary

- OK: `1`
- WARN: `1`
- REVIEW: `1`

## Queue

| Ticker | Status | Triggers | Actions |
|---|---|---|---|
| EXMPL | OK | - | - |
| EXMPLB | WARN | T6 | pause_buy_adds_optional,append_next_earnings_checklist |
| EXMPLC | REVIEW | T1 | pause_buy_adds,create_review_ticket,human_read_full_disclosure |

## Findings

### EXMPLB (WARN)
- `T6` `WARN`: WS-1 freeze_flag set: dividend held flat (policy change); pause optional adds and re-underwrite growth thesis.

### EXMPLC (REVIEW)
- `T1` `REVIEW`: Dividend data missing; suspension or data integrity issue possible.
