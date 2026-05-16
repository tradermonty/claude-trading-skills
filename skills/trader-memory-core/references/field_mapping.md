# Field Mapping: Source Skill → Thesis Canonical Fields

## Mapping Table

| Source Skill | Raw Field | Canonical Field | Notes |
|---|---|---|---|
| kanchi-dividend-sop | `ticker` | `ticker` | Direct |
| kanchi-dividend-sop | `buy_target_price` | `entry.target_price` | |
| kanchi-dividend-sop | `current_yield_pct` | `origin.raw_provenance.current_yield_pct` | Preserved in raw |
| kanchi-dividend-sop | `signal` | `origin.raw_provenance.signal` | Preserved in raw |
| earnings-trade-analyzer | `symbol` | `ticker` | Renamed |
| earnings-trade-analyzer | `grade` | `origin.screening_grade` | A/B/C/D |
| earnings-trade-analyzer | `composite_score` | `origin.screening_score` | 0-100 |
| earnings-trade-analyzer | `gap_pct` | `origin.raw_provenance.gap_pct` | Preserved in raw |
| earnings-trade-analyzer | `sector` | `market_context.sector` | |
| vcp-screener | `symbol` | `ticker` | Renamed |
| vcp-screener | `entry_ready` | `origin.raw_provenance.entry_ready` | Boolean |
| vcp-screener | `distance_from_pivot_pct` | `origin.raw_provenance.distance_from_pivot_pct` | |
| vcp-screener | `composite_score` | `origin.screening_score` | |
| pead-screener | `symbol` | `ticker` | Renamed |
| pead-screener | `entry_price` | `entry.target_price` | |
| pead-screener | `stop_loss` | `exit.stop_loss` | |
| pead-screener | `status` | `origin.raw_provenance.pead_status` | SIGNAL_READY/BREAKOUT/etc |
| canslim-screener | `symbol` | `ticker` | Renamed |
| canslim-screener | `rating` | `origin.screening_grade` | |
| canslim-screener | `composite_score` | `origin.screening_score` | |
| edge-candidate-agent | `id` | `origin.raw_provenance.edge_id` | |
| edge-candidate-agent | `hypothesis_type` | `origin.raw_provenance.hypothesis_type` | |
| edge-candidate-agent | `mechanism_tag` | `mechanism_tag` | behavior/structure/uncertain |
| manual | `ticker` | `ticker` | Required |
| manual | `thesis_statement` | `thesis_statement` | Required |
| manual | `thesis_type` | `thesis_type` | Required; must be a valid enum value |
| manual | `stop_price` / `stop_loss` | `exit.stop_loss` | Optional |
| manual | `target_price` / `take_profit` | `exit.take_profit` | Optional |
| manual | `entry_price` | `origin.raw_provenance.entry_price` | Authoritative `entry.actual_price` set by `open-position` |
| manual | `entry_date` | `origin.raw_provenance.entry_date` | Also drives `_source_date` (date-only `[:10]`) so the IDEA stamp is backdated |
| manual | `shares` | `origin.raw_provenance.shares` | Fractional ok; authoritative `position.shares` set by `open-position` |
| manual | `setup_type` | `setup_type` | Optional passthrough |
| manual | (all other keys) | `origin.raw_provenance.*` | Preserved |

## Position Sizer (Update Operation, not Register)

| Raw Field | Canonical Field | Notes |
|---|---|---|
| `final_recommended_shares` | `position.shares` + `position.shares_remaining` | shares_remaining seeded == shares |
| `final_position_value` | `position.position_value` | |
| `final_risk_dollars` | `position.risk_dollars` | |
| `final_risk_pct` | `position.risk_pct_of_account` | |
| `mode` | — | Must be "shares" (budget mode rejected) |

`position.shares` is schema type `number`, `exclusiveMinimum: 0` — **fractional
shares are valid** (IBKR / Robinhood / IBI Smart / Alpaca etc.). Existing
integer-share theses remain valid (`number` ⊇ `integer`).

## Partial close (`trim`)

`position.shares` = the **original** opened quantity (immutable).
`position.shares_remaining` (`number`, `minimum: 0`) = currently-open
quantity. Each `trim()` and the final close write a `status_history` ledger
entry:

| Ledger field (status_history item) | Meaning |
|---|---|
| `shares_sold` | quantity sold in this leg |
| `price` | execution price of this leg |
| `proceeds` | `round(price × shares_sold, 2)` |
| `realized_pnl` | `round((price − entry_price) × shares_sold, 2)` |

`outcome.pnl_dollars = Σ realized_pnl` over all ledger entries;
`outcome.pnl_pct = pnl_dollars / (entry_price × original_shares) × 100`. The
ledger fields are optional in the schema, so legacy (non-trim) status_history
entries stay valid; `shares_remaining` is optional too (absent ⇒ treated as
fully open for legacy ACTIVE/CLOSED).

## Manual Entry (free-form, non-screener)

The `manual` source ingests hand-entered positions. Input is free-form JSON —
a single object **or** an array. Like every adapter it creates an `IDEA`
thesis only; the authoritative entry price/date and (fractional) share count
are set later by the `open-position` lifecycle step, not at ingest.
`entry_date` is normalized to a date-only `_source_date` so the IDEA
`status_history` entry is stamped at the entry date — keeping a backdated
IDEA → ENTRY_READY → ACTIVE chain chronological.

## Phase 1 Constraints

- **Single ticker only**: Each thesis tracks exactly one stock symbol
- **edge-candidate-agent**: Only tickets with `research_only=False` and a single `ticker`/`symbol` field are accepted. `MARKET_BASKET` or `research_only` tickets are skipped with a warning log.
- **pair-trade-screener** and **options-strategy-advisor** are Phase 2 (multi-leg)

## Raw Provenance

All adapter-specific fields not listed in the canonical mapping are preserved in `origin.raw_provenance`. This allows:
1. No data loss during transformation
2. Recovery of original values if canonical mapping changes
3. Skill-specific analysis using raw data
