# Read-only broker / trader-memory reconciliation

Run this manual gate after fetching holdings and **before** allocation or rebalance
review in `core-portfolio-weekly`. Compare actual remaining positions with the
trader's recorded lifecycle. Never place orders, edit theses, or silently repair
mismatches through this tool.

## Prepare comparable snapshots

Create two local JSON files with this contract (fictional example):

```json
{
  "schema_version": 1,
  "account_scope": "paper_demo",
  "as_of": "2026-10-09T12:00:00Z",
  "complete": true,
  "positions": [
    {"symbol": "FICTA", "asset_type": "equity", "direction": "LONG", "quantity": "0.125"}
  ]
}
```

- Use the **same complete account scope and snapshot instant** for both files.
  Use a non-sensitive account alias, never an account number. `as_of` must include
  a timezone; equivalent offsets are accepted. Record the actual capture instant,
  not the thesis creation date. Freeze the comparison view during export; if
  broker or memory changes during capture, capture both again. Do not relabel old
  data with a new timestamp to bypass this requirement.
- Set `complete: true` only after confirming all open equity positions in the
  selected account are represented, including positions absent from memory.
  `positions: []` means a verified empty account, never a failed/missing export.
- Map broker equity/ETF positions to `symbol`, `asset_type: equity`, explicit
  `LONG`/`SHORT`, and **positive absolute remaining share quantity**. When the
  broker encodes shorts as negative quantities, verify the broker's side field
  agrees before taking the absolute value. Resolve inconsistent signs manually.
  Omit cash; do not omit unsupported options, crypto or futures to get a pass:
  any such instrument makes this equity-only gate unsuitable and requires review.
- Obtain **both ACTIVE and PARTIALLY_CLOSED** memory records. `thesis_store.py list`
  (or `query()` / `list_active()`) returns lightweight index entries, not complete
  position records; `list_active()` alone also misses partial closes. First run
  the read-only `doctor` command to check file/index consistency, then enumerate
  both statuses and load each full thesis with `get` / `get()` and validate it
  using `validate_thesis()`. Do not run `rebuild-index` as part of this gate.
- For memory equities, map `ticker` to symbol, direction to **LONG** (the current
  equity lifecycle is long-only), and `position.shares_remaining` to quantity.
  Never use original `position.shares` for a trimmed position. Missing remaining
  quantity on a legacy ACTIVE record requires manual resolution, not a fallback.
  Exclude IDEA, ENTRY_READY, CLOSED and INVALIDATED records; futures use contracts
  and are unsupported here. Do not treat an arbitrary memory `position.direction`
  extra field as authoritative for equities.
- Trader-memory currently has no native account attribution. The operator must
  verify each thesis belongs to this account; ambiguous assignment blocks review.
  Reject duplicate symbols, including opposite directions. Resolve multi-thesis
  lots and split-account records manually before normalization; do not silently
  sum them or net longs and shorts. This tool does not automate that attribution.
- Quantities may be JSON numbers or decimal strings (strings preserve fractional
  precision). Accepted range is 1e-12 through 1e12 shares, at most 64 characters.
  Zero, negative, Boolean, non-finite and missing quantities block the gate.
  Symbol comparison trims surrounding whitespace and uppercases symbols; confirm
  symbol/asset identity manually for renamed tickers or multiple share classes.

## Normalize a saved Alpaca positions list

`normalize_alpaca_positions.py` converts a saved native `/v2/positions` JSON list
into the broker snapshot contract above. It does not fetch positions. Obtain the
complete list through your existing read-only broker connection, freeze the
comparison view, and verify the account and actual capture instant yourself.

The following uses the bundled **fictional** source. Choose an existing private
output directory; `reports/` below must already exist and the output file must
be new. Replace the source, alias and timestamp with verified values for your own
capture, rather than relabeling an older file.

```bash
python3 skills/portfolio-manager/scripts/normalize_alpaca_positions.py \
  --positions-json skills/portfolio-manager/assets/fictional_alpaca_positions.json \
  --account-scope paper_demo --as-of 2026-10-20T12:00:00Z \
  --confirm-complete --output reports/broker-normalized.json
```

- All three assertions are required: `--account-scope`, timezone-aware `--as-of`
  and `--confirm-complete`. They remain operator assertions, not evidence the
  tool authenticated the account or proved capture completeness/freshness.
- Every row must be `asset_class: us_equity`. If currency is supplied it must be
  `USD`; absent currency follows the native US-equity scope. No unsupported
  instrument is filtered out. Do not remove positions to obtain a match.
- Native `side` must be `long` or `short`, with respectively positive or negative
  `qty`. The quantity must be a plain decimal string up to 64 characters: no
  exponent, whitespace, leading plus, Boolean or JSON-number coercion. Bounds
  remain 1e-12..1e12 absolute shares. Positive absolute decimal shares are emitted
  exactly, including fractions, with no aggregation or netting.
- Prices and acquisition costs are not needed for position reconciliation.
  Symbols are normalized by the shared reconciliation contract; duplicate
  identities block export. Unknown fields, account/asset IDs and provider P&L
  are discarded. Output contains only the snapshot fields above and sorted
  symbol/asset_type/direction/quantity positions.
- `[]` is accepted only with the explicit completeness confirmation. An error
  object, missing list, malformed JSON or duplicate JSON keys is not an empty
  account. Inputs must be UTF-8 JSON and remain unchanged.
- Without `--output`, JSON goes to stdout. With `--output`, only a fixed success
  message is printed; the complete JSON is atomically published as a new file.
  Existing files, input aliases, hardlinks and symlinks are never replaced.
  The parent directory must exist and support hardlinks; otherwise writing fails
  without an overwrite fallback. Staging files are cleaned on normal failure.
- POSIX files are created with owner-only permissions (0600, subject to umask).
  Windows permissions follow inherited ACLs: use a private directory. Symbols,
  quantities and the operator alias still reveal holdings; this is field
  minimization, not anonymization. Keep source/snapshot/report files local.
- Success exits 0, validation/read/write errors exit 1, and argument errors exit
  2. Diagnostics omit paths and raw data. Check the exit code; an existing file
  is not proof a new attempt succeeded. Use a new output path for each capture.

The bundled native fixture includes a short position. It demonstrates conversion,
not a successful match against current long-only memory. Review its direction
mismatch manually; it never authorizes orders. After normalization, prepare the
complete ACTIVE/PARTIALLY_CLOSED memory snapshot above and run the comparison.

## Compare and stop on unresolved differences

```bash
python3 skills/portfolio-manager/scripts/reconcile_positions.py \
  --broker reports/broker-normalized.json \
  --memory reports/memory-normalized.json \
  --output-dir reports/portfolio-reconciliation
```

The command uses only local files, writes `reconciliation_report.json` and
`reconciliation_report.md` to the requested directory, and prints JSON to stdout.
Omit `--output-dir` for stdout-only comparison. Both source files remain unchanged.
Keep reports private: position quantities and the account alias can still reveal
sensitive trading information. Do not commit real snapshots or reports.

### Report status

| Status | Meaning | Manual gate |
| --- | --- | --- |
| MATCH | Every equity matches, including two verified empty accounts | Allocation review may continue after verifying provenance |
| REVIEW_REQUIRED | Valid snapshots contain at least one item discrepancy | Stop and review |
| INVALID_INPUT | Incomplete, malformed, duplicate, unsupported or incompatible inputs | Stop; no report files are written |

Read failures name the input side (`broker:` or `memory:`) and cause: file not
found, file read error, encoding error (expected UTF-8), invalid JSON, duplicate
JSON object key, or JSON too deeply nested. Diagnostics omit paths and input data.
If both files are unreadable, the first failure (broker) is reported.

### Item status

| Status | Meaning |
| --- | --- |
| MATCH | Remaining quantity and direction agree |
| BROKER_ONLY | Broker holding has no matching memory position |
| MEMORY_ONLY | Open memory position is absent from broker |
| QUANTITY_MISMATCH | Remaining share counts differ |
| DIRECTION_MISMATCH | Broker and memory sides differ |

Missing quantities and directions are JSON `null` and appear as `-` in Markdown.

Items are sorted by symbol and decimal quantities are emitted as strings without
rounding or tolerance. If direction and quantity both differ, direction takes
precedence; both quantities and directions remain visible in the report.
Exit status is 0 only when `can_continue: true`; discrepancies, invalid inputs or
report-write errors exit 1. Invalid inputs still print a JSON report with
`requires_review: true` and `can_continue: false`. Argument usage errors exit 2.

A MATCH relies on the operator's completeness/account/freshness assertions; the
tool cannot verify live data or detect a deliberately incomplete normalized
export. `can_continue` permits only the **manual allocation review**, never orders
or automatic thesis changes. Repair discrepancies through separately reviewed
broker or trader-memory lifecycle actions, then capture and compare again.

## Preparation status

This is an offline comparison tool plus a documented manual workflow gate.
Saved native broker lists can now be normalized locally with the explicit
operator assertions above. Live broker capture, automatic complete memory
export/account attribution, and machine-enforced replay gating remain follow-up
work under Issue #493.
The existing `core-portfolio-weekly` replay fixtures demonstrate the earlier
holdings/allocation/dividend/rebalance/journal contracts; they do **not** execute
or verify this new reconciliation gate. Passing those historical replays is
regression evidence only. Keep Issue #493 open until those remaining integration
and end-to-end requirements are verified.
