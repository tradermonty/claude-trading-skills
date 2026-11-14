# Blind Replay of Your Own VCP Decisions

`scripts/decision_replay.py` turns the user's own enter / wait / pass decisions on `vcp-screener` candidates into a practice loop. The user records decisions the evening of the screen, later re-decides on a seeded blind sample, and sees the original decision, the replay decision, the rule result and the later price path side by side. Rule adherence and price outcome are scored separately.

The output is practice feedback, not a trade recommendation.

## Supported routine

v1 supports one routine: run the VCP screen after the US close, then capture the same evening. Recommended: capture after 16:30 ET so the screener's last bar is final.

- All calendar logic uses America/New_York, following the FMP client's `_et_today`. Missing tz data stops the run with a message naming `tzdata`.
- `metadata.generated_at` in the screener report is naive local wall-clock time. It is interpreted in the capturing machine's local timezone and converted to ET, so the report must be captured on the machine that generated it. The default `decision_date` is that ET date.
- If the ET time of `generated_at` is before 16:00, capture prints `WARNING: report generated before the close; v1 supports after-close screening` to stderr and proceeds. Pre-market and intraday routines are a follow-up. The reveal check is date-only. A pre-market capture is not reliably detected: for a report generated and captured on the same pre-market morning, no later bar precedes the capture date, so `captured_after_path_start` does not fire. The reveal as-of check then excludes the case as `as_of_unverified` only when the decision-day close differs from `snapshot.price` by more than 1%. A Friday report captured on Monday is rejected by the capture lag guard instead.
- If `generated_at` is missing, `--decision-date` is required, no after-close warning is possible, and the user is responsible for the date.
- `--decision-date` is accepted only within one day before the report's ET date through that date (local-time slack).

## Commands

| Command | Purpose |
|---|---|
| `capture` | Freeze the candidate set plus all decisions in one write-once record |
| `replay` | Draw a seeded, outcome-independent sample and write the blind view |
| `replay --abandon SESSION_ID --reason TEXT` | Drop a pending session; its cases stay unseen |
| `reveal` | Score the blind answers against the recorded rule and the later path |
| `reconcile-ledger` | Append the ledger line for an intact capture file that lacks one |

Exit codes: 0 success, 1 validation or integrity failure (`ERROR: ...` on stderr), 2 argparse usage error. There are no network or missing-dependency paths; the script is standard-library only.

## Local store layout

The default `--store-dir state/decision_replay/` is gitignored.

```
captures/<capture_id>.json            write-once; one per (screener report, decision date)
captures/ledger.jsonl                 append-only: capture_id, capture_sha256, captured_at
sessions/<session_id>.json            write-once; seed, population hash, selected case ids
sessions/<session_id>.answers.json    write-once; the blind re-decisions
sessions/<session_id>.abandoned.json  write-once; abandon reason
sessions/<session_id>.reveals.jsonl   append-only; prices hash per reveal
```

## Capture record

```json
{
  "schema_version": "1.0",
  "record_type": "decision_capture",
  "capture_id": "vcp-2026-11-06-<source_sha256[:12]>",
  "setup_type": "vcp",
  "source_skill": "vcp-screener",
  "source_report": "<file name>",
  "source_report_sha256": "<sha256 of the report bytes>",
  "decision_date": "2026-11-06",
  "captured_at": "2026-11-06T23:40:00+00:00",
  "market_gate": "open",
  "evaluation": {"horizon_days": 5, "rally_threshold_pct": 5.0, "reference": "snapshot.price", "stop": "snapshot.stop_loss_price"},
  "rule": {"version": "vcp-checklist-v1", "items": []},
  "cases": [
    {"case_id": "<capture_id>:ZZEN", "rank": 1, "symbol": "ZZEN",
     "snapshot": {}, "snapshot_sha256": "...",
     "decision": "enter", "reason": "one line",
     "screener_entry_ready": true, "v1_structural_pass": true, "rule_mismatch": false}
  ],
  "capture_sha256": "..."
}
```

- The candidate set is the report's `results` in report order, optionally the first `--limit N`. The screener, not the user, decides the order and membership before any outcome exists.
- `--decisions` must cover every candidate exactly once. Decision is `enter`, `wait` or `pass`. Reason is a non-empty single line of at most 200 characters. A `results` row without a symbol, or a duplicate symbol, exits 1 instead of being dropped. Anything else exits 1 and writes nothing.
- `capture_id` is deterministic, and a screener report can be captured only once: a second capture of the same report bytes fails with "already exists" (re-running the screener produces different bytes, so a second same-day capture of the same symbols is accepted as a separate capture), even with a different `--decision-date` (a weekend-generated report accepts two dates, and must not enter the population twice).
- `captured_at` is stored timezone-aware (UTC offset).
- Thresholds, horizon, rule spec and market gate are frozen in the record. `market_gate` is the user's own attestation and, like the other inputs, can hint at the original decision.

### Snapshot whitelist

Structured fields only: `symbol, sector, price, composite_score, rating, quality_rating, valid_vcp, execution_state, pattern_type, wide_and_loose, distance_from_pivot_pct, sma200_distance_pct, entry_ready, pivot_price, num_contractions, contractions[{label, high_date, high_price, low_date, low_price, depth_pct}], stop_loss_price, risk_pct, dry_up_ratio, rs_rank_estimate, trend_template_score`.

`entry_ready` is kept in the captured snapshot but left out of the blind view: it is the screener's own verdict on nearly the same checklist as rule v1, so showing it would let a replay answer mirror it and score as `followed`. The blind snapshot is the whitelist minus `entry_ready`.

Excluded free text: `guidance`, `rating_description`, `execution_state_reasons`, `cap_reason`, `company_name`. Unknown keys in the report are ignored by construction, so new screener coverage fields do not affect the snapshot. `pivot_price` comes from `pivot_proximity`, falling back to `vcp_pattern`.

At capture every `YYYY-MM-DD` date found anywhere inside a snapshot string (also in the middle of a longer string) must be on or before `decision_date`; otherwise the capture exits 1. Other date formats such as `11/20/2026` are not checked. Contraction dates such as `N/A` or `day-3` are not ISO dates and are ignored.

## Guarantees and their limits

| Guarantee | How | Limit |
|---|---|---|
| Records are never overwritten | `os.link` from a temp file, falling back to exclusive create; existing target raises "already exists" | The trainer is not in the Windows compatibility smoke |
| Accidental edits are detected | SHA-256 of the canonical JSON of each snapshot and of the whole record, checked on every load | A self-hash detects accidents only. Someone who edits a record and recomputes its hash is not caught |
| Deletion is detected | The append-only ledger is cross-checked against the capture files on every replay and reveal | Detects accidental or casual deletion, not deliberate tampering with both |
| No hindsight at capture | Capture must be on or after the decision date and before the next weekday (Friday through Sunday for a Friday decision), on the ET calendar | Process guard, not proof. Holidays are not modelled |
| Hindsight is flagged at reveal | A case whose capture date is on or after the date of the first later bar gets `captured_after_path_start` and is excluded | The comparison is date-only |
| Selection ignores outcomes | `select_cases(population_ids, sample_size, seed)` takes no price input. `replay` never loads prices | The seed is recorded; reproducibility is per population |

Ledger damage: a truncated or corrupt ledger line makes replay and reveal exit 1 with a message naming `reconcile-ledger`. `reconcile-ledger` can repair one unparsable **final** line (for example after a crash during the append): it first verifies every capture file, then drops that line and re-appends the entries that are missing. Every check, including the capture lag of each capture that would be re-added, runs before the ledger is touched; if any check fails, the ledger stays byte-identical. It therefore refuses when the damaged line is in the middle of the file, when any capture file fails verification, or when a capture to re-add is already past its lag window (for example the damage is noticed on Monday for a Friday capture). Restore `captures/ledger.jsonl` from a backup in those cases. If a capture file is deleted, the ledger still lists it and every subcommand exits 1; restore the file from a backup. Captures are immutable, so a mistyped decision or wrong `--market-gate` cannot be corrected, only left out by capturing the next report.

Ledger recovery: the capture file is written first, then the ledger line. If a crash leaves a capture without a ledger line, replay exits 1 naming `reconcile-ledger`. That command re-verifies the file's hashes and its capture lag before appending, so it cannot launder a late capture.

## Replay

```
decision_replay.py replay --sample-size N [--seed S] [--decided-on-or-before YYYY-MM-DD]
    [--include-seen] [--store-dir ...] [--output-dir ...]
```

- Argument combinations that make no sense exit 2 with a usage error: `--abandon` with `--sample-size`, `--seed`, `--include-seen` or `--decided-on-or-before`; `--abandon` without `--reason`; `--reason` without `--abandon`; a missing or non-positive `--sample-size`.
- The session record is written last, after the blind view files, so a failed output directory never leaves a pending session. If writing the session record itself fails, the two blind files are deleted again, so no blind view exists without a session record.
- `--store-dir` defaults to `state/decision_replay` relative to the current directory. Running from another directory silently uses a second, empty store (`replay` then reports no captured cases); run from the repository root or pass `--store-dir`.
- Population: every case in every capture, filtered only by the date-only `--decided-on-or-before`.
- Cases already revealed in an earlier session are excluded by default so the user cannot see the same case twice. `--include-seen` re-admits them, marked `seen_before`; they are left out of the replay adherence and consistency tallies.
- A new `replay` exits 1 while any earlier session has neither an answers file nor an abandon record. `replay --abandon SESSION_ID --reason TEXT` clears it. Abandoned cases stay unseen, but frequent abandoning weakens blindness, and reveal summaries report `abandoned_sessions` and `abandoned_before_this_session`.
- `session_id = "replay-" + sha256(f"{seed}:{population_sha256}:{sample_size}")[:12]`. There are no dates in it, so an identical repeat request collides and exits 1 by design.
- The blind JSON has exactly `schema_version, record_type, session_id, case_count, instructions, cases`. Each case has exactly `case_number, case_id, symbol, setup_type, decision_date, market_gate, snapshot`. No decision, reason, rule result, threshold, price bar, wall-clock time or seed is shown. Seed and population hash live only in the store's session record. A dedicated renderer writes the Markdown.
- Symbols are visible. The user should not look up the chart before answering; symbol masking is a follow-up.

## Rule `vcp-checklist-v1`

The rule is data stored in each capture. Scoring reads the recorded spec and snapshot, so later code changes never change past scores. A missing or None field fails its item with status `missing`.

| id | field | op | value |
|---|---|---|---|
| market_gate_open | market_gate | eq | "open" |
| valid_vcp | valid_vcp | is_true | |
| execution_state | execution_state | not_in | Invalid, Damaged, Overextended, Extended, Early-post-breakout |
| pivot_distance | distance_from_pivot_pct | between | [-8, 3], inclusive |
| risk | risk_pct | gt_lte | (0, 15] |
| volume_dry_up | dry_up_ratio | lte | 1.0 |

`rule_expected` is `enter` if every item passes, otherwise `not_enter`. `wait` and `pass` are both non-entry in v1.

Relation to the screener's `entry_ready` (`compute_entry_ready`): v1 uses the same reject list, bounds and checks, plus the market gate, with one difference: a missing execution state fails here, while the screener lets it pass. At capture, `v1_structural_pass` (v1 without the gate) is compared with `screener_entry_ready`; a difference, or a missing execution state, stores `rule_mismatch: true` and is shown at reveal. It is not fail-closed. When the report carries no `entry_ready` (older vcp-screener reports), `rule_mismatch` is `null` (unknown) and is not counted as a mismatch.

## Reveal and scoring

```
decision_replay.py reveal --session-id ID --answers A.json --prices-json P.json
    [--store-dir ...] [--output-dir ...]
```

Answers are `[{case_id, decision, reason}]`, validated like capture decisions and covering every selected case exactly once. They are stored write-once on first reveal. A later reveal with identical answers (order and surrounding whitespace ignored) re-scores, so pending cases can be scored once bars mature. Different answers exit 1 with "answers already recorded". Each reveal records the SHA-256 of the prices file and shows when it changed since the previous reveal. Everything is validated and scored before anything is written: the answers file and the reveal history line are created only after scoring succeeded. A prices file that is not UTF-8 JSON, has a bar date that is not `YYYY-MM-DD`, or contains none of the session's symbols exits 1 and records nothing, so the session's cases are not burned. A partial match keeps the normal behavior: missing symbols are `pending`, and a stderr warning names how many cases stay pending. The first successful reveal marks all answered cases as seen even if every case was still pending; they can only be re-scored through the same session, not re-drawn blind.

The prices JSON uses the shape of `build_model_book.py update --prices-json`. It must cover the last bar on or before `decision_date` through `horizon_days` bars after it.

Per case, the path is measured from `snapshot.price` (not from a pivot buy-stop fill) over the next `horizon_days` bars using the shared `calculate_window_outcome`.

- `rallied`: matured, no stop hit, and forward close return at least `rally_threshold_pct`. Otherwise `did_not_rally`.
- A missing stop disables the stop check and sets `stop_reference_missing: true`.
- Outcome of a decision: `enter` + rallied is favorable, `enter` + did not rally is adverse, `wait`/`pass` + rallied is adverse (a missed move), `wait`/`pass` + did not rally is favorable.
- Adherence: `followed` when the decision matches `rule_expected` (enter with enter, wait or pass with not_enter), otherwise `deviated`. A rule-compliant candidate that the user passes is therefore `deviated`; the issue's "correct decision, adverse outcome" is a pass on a `not_enter` candidate that later rallied.

| adherence | outcome | quadrant |
|---|---|---|
| followed | favorable | followed_favorable |
| followed | adverse | followed_adverse |
| deviated | favorable | deviated_favorable (lucky) |
| deviated | adverse | deviated_adverse |

Each case has at most one `exclusion_reason`, decided in this order: `pending` (no later bar at all) then `unscorable` (entry price at or below 0) then `as_of_unverified` (no bar on or before the decision date, or its close is more than 1% from `snapshot.price`) then `captured_after_path_start` then `pending` (fewer than `horizon_days` later bars). Excluded cases are counted once, kept out of both quadrant tallies, and still show adherence.

Summary: `original.quadrants` and `replay.quadrants` always list all four keys, plus `adherence_rate_pct` per side over scored cases, `consistency_rate_pct` (replay equals original), `pending`, `excluded`, `population_size`, `prior_sessions`, `abandoned_sessions` and `abandoned_before_this_session`. The disclaimer "Practice feedback, not a trade recommendation." is in both the JSON and the Markdown.

## Weekly routine

1. Each evening after the close: run the VCP screen, write `decisions_YYYY-MM-DD.json`, run `capture`.
2. At the weekend: `replay --sample-size 10 --decided-on-or-before <a date at least a week back>`. Answer every case from the blind view without looking at charts.
3. Save the answers as `answers.json`, then `reveal` with an offline prices file.
4. Review quadrants separately: `followed_adverse` is variance to accept, `deviated_favorable` is luck to distrust, and `deviated_adverse` is the discipline cost.

## Limitations

- Symbols are visible in the blind view.
- Prices are offline `--prices-json` only; a live FMP fallback at reveal is a follow-up.
- The decision date is approximate because the VCP report has no bar as-of date; the contraction-date guard and the reveal as-of check reduce the risk.
- The capture lag guard is a process guard, not cryptographic proof.
- Holidays are not modelled in the lag guard.
- Pre-market and intraday screening routines are not supported.
- Rule v2 (user-editable checklist) is a follow-up; stored specs mean it needs no migration.
