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

| Result | Meaning | Manual gate |
| --- | --- | --- |
| MATCH | Every equity has the same remaining quantity and direction | Allocation review may continue after verifying provenance |
| BROKER_ONLY | Broker holding has no matching memory position | Stop and review |
| MEMORY_ONLY | Open memory position is absent from broker | Stop and review |
| QUANTITY_MISMATCH | Remaining share counts differ | Stop and review |
| DIRECTION_MISMATCH | Broker and memory sides differ | Stop and review |
| INVALID_INPUT | Incomplete, malformed, duplicate, unsupported or incompatible inputs | Stop; no report files are written |

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
Automatic broker export, automatic complete memory export/account attribution,
and machine-enforced replay gating remain follow-up work under Issue #493.
The existing `core-portfolio-weekly` replay fixtures demonstrate the earlier
holdings/allocation/dividend/rebalance/journal contracts; they do **not** execute
or verify this new reconciliation gate. Passing those historical replays is
regression evidence only. Keep Issue #493 open until those remaining integration
and end-to-end requirements are verified.
