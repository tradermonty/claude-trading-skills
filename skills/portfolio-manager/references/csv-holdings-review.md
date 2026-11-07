# Offline holdings review

Run from the repository root with Python 3.9+; no API keys or third-party imports:

```bash
python3 skills/portfolio-manager/scripts/review_csv.py \
  --input skills/portfolio-manager/assets/fictional_holdings.csv \
  --as-of 2026-10-20T12:00:00Z --output-dir reports
```

For a standalone package, run `python3 scripts/review_csv.py --input
assets/fictional_holdings.csv --as-of 2026-10-20T12:00:00Z --output-dir reports`
from the extracted skill directory. The fixture contains fictional USD equities.
Supply the actual source snapshot timestamp for your own input; the script does
not verify prices, ownership, completeness or freshness. It never fetches quotes.

## CSV input contract

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

## Saved Alpaca positions input

A saved JSON list from the Alpaca `/v2/positions` endpoint can use the **same
limited analysis**. Save the positions response locally through your existing
read-only brokerage connection; this command does not connect to Alpaca:

```bash
python3 skills/portfolio-manager/scripts/review_csv.py \
  --input skills/portfolio-manager/assets/fictional_alpaca_positions.json \
  --input-format alpaca-json --as-of 2026-10-20T12:00:00Z --output-dir reports
```

The fictional JSON represents the same holdings as the fictional CSV.
Only the following fields enter the common CSV validator/calculator:

| Alpaca field | Required mapping |
|---|---|
| `symbol` | String, normalized and validated like CSV symbol |
| `asset_class` | String, exactly `us_equity`, mapped to `equity` |
| `qty` | String; strictly positive for `side=long`, strictly negative for `side=short`; its unsigned magnitude follows CSV numeric limits |
| `side` | String, exactly `long` or `short`, mapped to `LONG` or `SHORT` |
| `current_price` | String, positive USD per-share price with at most 12 decimal places, mapped to `price` |
| `avg_entry_price` | Optional string, nonnegative per-share acquisition price with at most 12 decimal places, mapped to `cost_basis`; null, empty or missing means unavailable |
| `currency` | If supplied, exactly `USD`; `us_equity` snapshots without this field are treated as USD only |

See [Alpaca's positions reference](https://docs.alpaca.markets/us/reference/getallopenpositions)
for native position fields. This adapter supports the restricted contract above,
not every instrument or currency that the endpoint can return. Numbers must be
JSON strings, not floats, so input precision is not silently altered. Contradictory
quantity signs are errors. Input must be a nonempty list of at most 10,000
objects; duplicate normalized symbols are rejected just as for CSV.

All other fields, including account/asset IDs, names, provider totals,
`cost_basis` (a position total rather than the required per-share price), weights,
and provider P&L, are ignored. Missing per-share entry price stays unavailable;
the adapter does not infer it from a position total. It recomputes all supported
analysis through the same decimal calculator as CSV. Inputs and diagnostics do
not prove that the saved response is current, complete or authentic. Supply its
actual source timestamp; historical analysis with a current saved snapshot is
not point-in-time data.

## Shared limited output contract

The default `--input-format csv` retains the existing command, JSON schema and
filenames. **Both formats** write `portfolio_csv_review.json` and
`portfolio_csv_review.md` into the output directory, replacing previous reports
with those names. The legacy filename does not identify the input source: read
`provenance.source`. Use a new directory to retain history. Validation errors
return exit 1, write a safe stderr diagnostic with row/field context, and create
no reports. Argument errors return exit 2. I/O errors return exit 1; if writing
fails midway, discard both report files and rerun. Existing reports are not
proof that the latest invocation succeeded.

The structural JSON Schema is `assets/holdings-review.schema.json`. Runtime
input validation enforces the numeric bounds and calculations described here.
JSON `schema_version: 1`, `report_type: holdings_allocation_only` contains:

- `provenance`: `source: local_csv` or `alpaca_positions_snapshot`, UTC `as_of`,
  `freshness: operator_asserted`. This is source-snapshot time supplied by the
  operator, not a fabricated fetch time.
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

Equivalent CSV and Alpaca snapshot holdings produce identical calculation
fields; only source provenance and the Markdown source label differ. Both
fictional fixtures yield gross value 80, signed net value 20, gross weights
62.5% and 37.5%, and per-position unrealized P&L of 12.5 and 10 USD.
Cash, equity, margin/leverage, sector allocations, beta, historical returns,
dividend health and trading recommendations are unavailable. Gross weights can
look benign in a leveraged account: never use them as account exposure or as
authorization to trade. Full live brokerage reports have a broader contract;
this limited contract is not a substitute for that analysis.

## Privacy and workflow boundary

No network, broker access, orders, memory edits or reconciliation gate. Input
filenames/paths, account fields and IDs are excluded from script diagnostics and
output. Reports still contain potentially sensitive holdings, quantities and
cost data; keep inputs/reports local and do not commit or upload personal data.
This is field minimization, not anonymization. CLI arguments/paths can remain in
shell history. Never pass secrets in a command, CSV or saved JSON.

The `portfolio-holdings-review` workflow and Navigator's local-file route use
this limited review. Navigator recommends the workflow without reading or
validating your file; actual execution requires `--input` and an aware `--as-of`
and may reject unsupported or malformed input. Its native replay uses fictional
holdings and executes this CLI, not a brokerage request. It does not write a
journal or trader-memory record. The broader `core-portfolio-weekly` workflow
still requires broker/memory reconciliation and brokerage access. Do not bypass
that gate or present a CSV allocation report as a completed full account review.
