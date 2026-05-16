# Thesis Lifecycle

## Status States

| Status | Description | Typical Trigger |
|--------|-------------|-----------------|
| `IDEA` | Screened candidate, not yet validated for entry | Ingest from screener output |
| `ENTRY_READY` | Validated, entry conditions defined, waiting for price | Manual review / deep-dive analysis |
| `ACTIVE` | Position opened (actual_price and actual_date filled) | Entry execution confirmed |
| `CLOSED` | Position exited, outcome recorded | Exit execution confirmed |
| `INVALIDATED` | Thesis killed before or during holding | Kill criteria triggered |

## Valid Transitions

```
IDEA ──────► ENTRY_READY ──────► ACTIVE ──────► CLOSED
  │               │                 │
  └───────────────┴─────────────────┴──────────► INVALIDATED
```

### Forward-Only Rule

Transitions must move forward in the lifecycle. Reverse transitions are not allowed:

- `ACTIVE → IDEA` — **blocked** (ValueError)
- `CLOSED → ACTIVE` — **blocked** (ValueError)
- `INVALIDATED → *` — **blocked** (terminal state)

### Any → INVALIDATED

Any non-terminal status can transition to `INVALIDATED`:
- `IDEA → INVALIDATED` (screener output invalidated before review)
- `ENTRY_READY → INVALIDATED` (kill criteria triggered before entry)
- `ACTIVE → INVALIDATED` (kill criteria triggered during holding)

## Status-Dependent Operations

| Operation | Required Status | Effect |
|-----------|----------------|--------|
| `register()` | — | Creates thesis with `IDEA` status (idempotent via fingerprint) |
| `transition()` | Any non-terminal (IDEA → ENTRY_READY only) | Advances status, appends to `status_history` |
| `open_position()` | `ENTRY_READY` | Sets entry data, transitions to `ACTIVE` (only path to ACTIVE) |
| `attach_position()` | Any | Attaches position sizing data |
| `link_report()` | Any | Adds linked report reference |
| `close()` | `ACTIVE` | Sets `CLOSED`, computes `outcome.pnl_*` and `holding_days` |
| `terminate()` | Any non-terminal | Transitions to `CLOSED` (delegates to close) or `INVALIDATED` with optional exit data |
| `mark_reviewed()` | Any non-terminal | Updates review dates and status based on review_date |
| `rebuild_index()` | — | Recreates `_index.json` from YAML files |
| `validate_state()` | — | Checks file ⇔ index consistency + schema validation |

**Important**:
- `transition()` only allows `IDEA → ENTRY_READY`. All terminal statuses are blocked.
- Use `open_position()` to reach `ACTIVE` (requires `actual_price` and `actual_date`).
- Use `close()` or `terminate(terminal_status="CLOSED")` to reach `CLOSED`.
- Use `terminate(terminal_status="INVALIDATED")` to reach `INVALIDATED`.

## CLI Access

Every lifecycle operation is also a `thesis_store.py` subcommand:
`transition`, `open-position`, `attach-position`, `close`, `terminate`
(alongside `list` / `get` / `review-due` / `rebuild-index` / `doctor` /
`mark-reviewed`). No Python required to walk a thesis through its lifecycle.

### Backdating an existing position (`--event-date`)

`transition`, `open-position`, `close`, and `terminate` accept `--event-date`
(sets that transition's `status_history.at`). `open-position` also takes
`--actual-date` (→ `entry.actual_date`); `close`/`terminate` take
`--actual-date` (→ `exit.actual_date`). A plain `YYYY-MM-DD` is widened to
midnight UTC; a full ISO timestamp passes through.

`transition --event-date` exists specifically so an already-open broker
position recorded via the `manual` adapter keeps a **chronological** history:
the manual adapter backdates the `IDEA` stamp to `entry_date`, then
`transition --event-date <entry_date>` and `open-position --event-date
<entry_date>` keep `ENTRY_READY` and `ACTIVE` at the same date. Without
`transition --event-date`, `ENTRY_READY` would be stamped "now" while a
backdated `open-position --event-date` puts `ACTIVE` in the past — so `ACTIVE`
lands before `ENTRY_READY`, failing the `status_history` monotonicity check on
save.

## Monitoring Cycle

1. On `register()`: `next_review_date` = `created_at + review_interval_days`
2. On review: `last_review_date` updated, `next_review_date` advanced
3. `list_review_due(as_of)` returns theses where `next_review_date <= as_of`
4. Review status: `OK` → `WARN` → `REVIEW` (escalation ladder)
