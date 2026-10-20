# Offline CSV holdings review (Issue #512 foundation)

Run from the repository root with Python 3.9+; no API keys or third-party imports:

```bash
python3 skills/portfolio-manager/scripts/review_csv.py \
  --input skills/portfolio-manager/assets/fictional_holdings.csv \
  --as-of 2026-10-20T12:00:00Z --output-dir reports
```

For a standalone package, run `python3 scripts/review_csv.py --input
assets/fictional_holdings.csv --as-of 2026-10-20T12:00:00Z --output-dir reports`
from the extracted skill directory. The fixture contains fictional USD equities.
Supply the actual source snapshot timestamp for your own CSV; the script does
not verify prices, ownership, completeness or freshness. It never fetches quotes.

## Input contract

UTF-8 CSV (optional BOM), one header row, comma separator, at most 10,000 holdings.
Required headers: `symbol,asset_type,quantity,direction,price,currency`.
Optional headers: `cost_basis,account`. Header order is arbitrary; unknown,
missing and duplicate headers are errors. Every record must match the header width.

| Field | Contract |
|---|---|
| symbol | Strip surrounding spaces, uppercase; `[A-Z][A-Z0-9.-]{0,23}`. Operator asserts this identifies the intended instrument. |
| asset_type | Exactly `equity`; options, futures and other instruments are unsupported. |
| quantity | Positive share count; fractional shares supported. |
| direction | Exactly `LONG` or `SHORT`; quantities are always positive. |
| price | Positive snapshot price per share, supplied by operator. |
| currency | Exactly `USD`; currency conversion is unavailable. |
| cost_basis | Optional nonnegative acquisition price per share; blank/missing means unknown. Excludes fees, dividends and tax adjustments. |
| account | Optional ignored field, discarded before reporting. Review one account at a time; never use this column to infer account completeness. |

Numbers use plain unsigned decimal notation, at most 32 characters and 12
fractional digits, and cannot exceed 1e12. Exponents, signs, whitespace, NaN,
infinity and zero quantity/price are invalid. A zero cost basis is permitted.
Duplicate normalized symbols, including separate tax lots or long/short rows,
are rejected: consolidate them manually into the intended single holding first;
do not net hedges merely to bypass the validator. Empty/header-only files fail;
this tool does not establish that an account is empty.

## Output contract

Writes `portfolio_csv_review.json` and `portfolio_csv_review.md` into the output
directory, replacing previous reports with those names. Use a new directory to
retain history. Validation errors return exit 1, write a safe stderr diagnostic
with row/field context, and create no reports. Argument errors return exit 2.
I/O errors return exit 1; if writing fails midway, discard both report files and
rerun. Existing reports are not proof that the latest invocation succeeded.

JSON `schema_version: 1`, `report_type: holdings_allocation_only` contains:

- `provenance`: `source: local_csv`, UTC `as_of`, `freshness: operator_asserted`.
- `gross_holdings_value`: sum of quantity × price across all positions.
- `net_holdings_value`: signed sum (shorts negative). Neither is account equity.
- `positions`: sorted sanitized symbols, asset_type, direction, quantity, price,
  currency, nullable cost_basis, gross_market_value, net_market_value,
  gross_weight_pct and nullable unrealized_pnl. Decimal values are strings to
  preserve precision. Weights use gross holdings value, rounded to six decimal
  percentage places; rounded weights may not sum exactly to 100.
- `unrealized_pnl`: quantity × (price − cost_basis), sign reversed for shorts.
  Unknown costs yield null, rendered `unavailable`. No aggregate P&L is emitted.
- `limitations`: explicit unavailable analyses and integration boundaries.

The fictional fixture yields gross value 80, signed net value 20, gross weights
62.5% and 37.5%, and per-position unrealized P&L of 12.5 and 10 USD.
Cash, equity, margin/leverage, sector allocations, beta, historical returns,
dividend health and trading recommendations are unavailable. Gross weights can
look benign in a leveraged account: never use them as account exposure or as
authorization to trade.

## Privacy and integration boundary

No network, broker access, orders, memory edits or reconciliation gate. The input
filename/path and account column are excluded from script diagnostics and output.
Reports still contain potentially sensitive holdings, quantities and cost data;
keep inputs/reports local and do not commit or upload personal data. This is
field minimization, not anonymization. CLI arguments/paths can remain in shell
history. Never pass secrets in a command or CSV.

This standalone allocation foundation does **not** make `core-portfolio-weekly`
runnable from CSV. Navigator retains its honest unshipped-workflow diagnostic.
Workflow/skillset integration, replay and an API/CSV shared analysis contract
remain outstanding under #512. Broker reports currently have a broader contract;
do not present this report as equivalent or bypass broker/memory reconciliation.
