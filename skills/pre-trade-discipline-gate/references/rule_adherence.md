# Monthly rule adherence review

`scripts/review_rule_adherence.py` turns the gate's per-rule acknowledgements into a local monthly report, so the next monthly review can see which approved rules were acknowledged as followed, as exceptions, or as not applicable. It reads only local files. It never changes the ledger and never places or routes orders.

The counts are self-reported at the gate. They show how the trader answered the checklist, not what the trader did. For a controlled check of one rule over 14 days, use `review_rule_experiment.py` (see `rule_experiment.md`).

## Command

Run it once the month has ended, from the repository root. Review the month in which the approved rules were in force.

```bash
python3 skills/pre-trade-discipline-gate/scripts/review_rule_adherence.py \
  --journal-dir state/journal/pre-trade-discipline \
  --ledger state/rules/approved_rules.json --month 2026-06 \
  --as-of 2026-07-05 --output-dir reports/pre-trade-discipline
```

- The defaults match the gate and the experiment: `--journal-dir state/journal/pre-trade-discipline`, `--ledger state/rules/approved_rules.json`, `--output-dir reports/pre-trade-discipline`.
- Without `--stdout` it writes `rule_adherence_<YYYY-MM>_as-of_<YYYY-MM-DD>.json` and `.md`, so a mid-month and a month-end review do not overwrite each other. Re-running with the same month and `--as-of` replaces that pair. With `--stdout` it prints the JSON and writes no file.
- `--as-of` is a New York date and defaults to today. It cannot be in the future. Journal rows dated after it, or generated after the end of that day, are left out and counted.
- Exit 1: bad `--month`, a month that starts after `--as-of`, a future `--as-of`, a missing journal directory, or an unreadable or invalid ledger. Inspect the ledger with `manage_approved_rules.py list`. Exit 2: New York timezone data is missing (`pip install tzdata`). An empty window exits 0 with the warning `no_gate_runs_in_window`. When no rule applied or was in force in the month (for example an empty ledger), the warning `no_rules_in_window` is added and the Markdown says so instead of showing an empty table.

## Approved-rule ledger and gate journal inputs

The canonical description of the ledger lifecycle and of the gate acknowledgements is the "Approved Operating Rules" section of `SKILL.md`. This report reads these fields.

Ledger `state/rules/approved_rules.json` (`schema_version: 1`, `rules[]`): `rule_id`, `text`, `status` (`active`, `superseded`, `retired`), `effective_date`, `review_after`, `expires_on`, `superseded_by`, and `history[]` events with `event` and `at`. The ledger is validated on load. State at review is computed from the current status and the `--as-of` date.

Gate journal `pre_trade_discipline_<UTC date>.jsonl`, one row per gate run. A row is used only when all of these are present: an object row; parseable `as_of` and `generated_at`; `candidate_results` as a list of objects with string `symbol` and `order_intent` and boolean `actionable`; and, when `approved_rules.status` is `loaded`, `approved_rules.applied` as a list of objects with a string `rule_id`. Any other row is counted under `input_quality.malformed_rows` with its `file:line` and is otherwise ignored. Per candidate the report reads `thesis_id`, `symbol`, `order_intent`, `actionable`, and `approved_rule_checks[]` with `rule_id`, `status`, and `note`.

The gate writes a journal row on every run (default `--journal-dir state/journal/pre-trade-discipline`). Acknowledgement data is present only when the gate was run with `--approved-rules-ledger`; other rows count under `runs_without_ledger`.

## What counts

- Window: one calendar month in New York dates. A row belongs to the month of `approved_rules.as_of_date`, or the New York date of its `as_of` when that is absent. The journal file date is never used, so a row filed under the next UTC day still counts. Every `pre_trade_discipline_*.jsonl` file in the directory is scanned.
- Occasion: one actionable candidate in a row whose ledger loaded, for each rule that row lists as applied. An occasion is a gate check, not a trade. A thesis gated on several days gives several occasions.
- Assessment: `followed`; `not_applicable`; `exception` only with a non-empty note; otherwise `unacknowledged`. A missing check, an unknown status, a noteless exception, and a malformed check list are all `unacknowledged`. Checks for rules the row did not apply are ignored, because the gate already warns about them.
- Reruns: the gate may be run again for the same candidate on the same day. Candidates are keyed by date plus `thesis_id` when present, so ENTRY_READY and MANUAL_ORDER for one thesis on one date collapse into one key. Without a thesis the key is date, symbol, and order intent. For each key the row with the latest `generated_at` wins; a tie goes to the later file name, then the later line. Every candidate sharing the key inside the winning row is kept. If the winning row has no loaded ledger, or the candidate is not actionable, it suppresses the earlier occasions for that key, because the latest gate run is the record. A rerun that leaves a candidate out entirely does not remove the earlier occasion. Candidates in losing rows are counted in `input_quality.superseded_reruns`.
- `days_in_applied`: distinct dates on which the rule was in `applied` of a loaded in-window row, counted before rerun dedupe and whether or not a candidate was actionable.

## Output

Top level: `schema_version` (1), `month`, `window` (`start`, `end`, `status`), `as_of`, `generated_at`, `inputs` (`journal_dir`, `ledger`), `source` (`pre_trade_gate_acknowledgements`), `input_quality`, `rules`, `warnings`, `human_decision_note`.

`window.status` is `open` when `--as-of` is on or before the last day of the month and `ended` afterwards.

`input_quality`: `malformed_rows` (`count`, `locations`), `ledger_unavailable_runs`, `runs_without_ledger`, `superseded_reruns`, `rows_after_as_of`, `rows_outside_window`, and `ledger_paths`, the number of rows per raw `inputs.approved_rules_ledger` string. A row that used a different ledger path string from `--ledger` raises the warning `different_ledger_path`. Nothing is filtered for it; check that the journal and the ledger belong together. The Markdown report flattens rule text to one line and escapes `|` and HTML; it lists malformed row locations and the per-rule dates and counts. A rule with no usable text shows as "(text unavailable)"; an empty rule list shows "No approved rules in the window."

Each entry in `rules`, sorted by `rule_id`:

| Field | Meaning |
|---|---|
| `rule_id`, `text` | Rule identity; text from the latest row that listed it, else the ledger |
| `followed`, `exception`, `not_applicable`, `unacknowledged`, `occasions` | Counts after rerun dedupe |
| `distinct_candidates`, `days_in_applied` | Distinct candidate keys among occasions; days the rule applied |
| `acknowledged_followed_pct` | followed divided by followed plus exception, one decimal, or `null` |
| `rate_suppressed_reason` | Why the rate is `null`, in this order: `window_open`, `unacknowledged_occasions`, `small_sample` |
| `ledger_state_at_review` | `effective`, `review_due`, `not_yet_effective`, `expired`, `superseded`, `retired`, or `missing_from_ledger` |
| `review_after`, `expires_on`, `superseded_by` | From the ledger |
| `reconsider_reasons` | In order: `review_due`, `not_applied_at_review`, `no_applicable_occasions`, `exceptions_present`, `unacknowledged_occasions` |

`small_sample` means followed plus exception is below 10, the same threshold the experiment uses (`MIN_RATE_SAMPLE`). A withheld rate is not by itself a reason to change a rule. `not_applied_at_review` applies when the state at review is not `effective` or `review_due`, including `missing_from_ledger`.

Ledger rules that no row mentions are listed with zero counts when their stored `effective_date` to `expires_on` interval overlaps the month, whatever their current state. A retired or superseded rule whose latest retirement or supersession event is dated before the month is left out.

Exception note text, symbols, and thesis IDs are not copied into the report. Only counts are.

## Limits

- State is computed from the current ledger status. Retired and superseded rules carry no end date other than their history event, so with a past `--as-of`, `ledger_state_at_review` mixes the current status with the past date. The ledger does not reconstruct an earlier state.
- Acknowledgements are answers to the gate checklist. They are not evidence of behavior and not trade outcomes.
- The report does not feed the monthly replay. A human reads it at step 6 of `monthly-performance-review` and records any decision there. Apply a decision only with `manage_approved_rules.py`: `extend`, `retire`, `supersede`, or `restore`.
