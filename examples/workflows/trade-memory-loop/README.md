# Example: `trade-memory-loop`

A canonical sample run of the
[`trade-memory-loop`](../../../workflows/trade-memory-loop.yaml) workflow: the
per-closed-trade loop that records the outcome, generates a postmortem, and
journals the lessons so the next decision is better-informed.

> ⚠️ **Illustrative only — not investment advice.** Both sample variants use
> the **fictional ticker `EXMPL`** (Example Corp) and a hand-authored trade.
> The numbers are internally consistent and schema-faithful, **not** captured
> from a real account.

## Two sample variants

This example ships two parallel samples that share the same closed thesis:

| Variant | Optional step | Lessons content |
|---|---|---|
| [`sample-run/`](sample-run/) (**required-only**) | skipped | Qualitative postmortem only ("trail under 10-EMA captured an extra ~7%") |
| [`sample-run-full-path/`](sample-run-full-path/) (**full-path**) | included | Qualitative postmortem **plus** backtest-expert re-validation (verdict + refinement candidate) |

## Steps in this sample

| Step | Skill | Artifact | `sample-run/` | `sample-run-full-path/` |
|---|---|---|---|---|
| 1 | `trader-memory-core` | `closed_thesis_record` | ✅ included | ✅ included (identical) |
| 2 | `signal-postmortem` | `postmortem_findings` | ✅ included | ✅ included (identical) |
| 3 | `backtest-expert` | `backtest_validation` | ⏭️ skipped (optional) | ✅ included |
| 4 | `trader-memory-core` | `lessons_log_entry` | ✅ included | ✅ included (updated with backtest result) |

## Files

```
sample-run/                        # required-only
  prompt.md                        # the prompt you give Claude
  manifest.yaml                    # step → artifact → file map
  01_closed_thesis_record.yaml     # trader-memory-core thesis, CLOSED
  02_postmortem_findings.json      # signal-postmortem record
  02_postmortem_summary.md         # human summary
  04_lessons_log_entry.md          # journal entry (no backtest)

sample-run-full-path/              # full-path
  prompt.md                        # full-path prompt
  manifest.yaml                    # step → artifact → file map, no skipped steps
  01_closed_thesis_record.yaml     # identical to sample-run/
  02_postmortem_findings.json      # identical to sample-run/
  02_postmortem_summary.md         # identical to sample-run/
  03_backtest_validation.json      # backtest-expert verdict (canonical)
  03_backtest_validation.md        # backtest-expert verdict (companion)
  04_lessons_log_entry.md          # journal entry with backtest cross-check
```

## The trade (fictional)

`EXMPL`, a `growth_momentum` / VCP-breakout thesis surfaced by `vcp-screener`
(grade A). Entered 2026-01-08 @ 142.10 (70 sh, 1% risk, stop 134.50), exited
2026-02-27 @ 168.40 (`target_hit`) after trailing past the initial 2R target.
Result: +18.5% / +$1,841 over 50 holding days; MAE -4.2%, MFE +21.0%.
Postmortem classifies it **`TRUE_POSITIVE`** — thesis-driven, not luck.

## What the full-path adds: `backtest-expert` re-validation

The required-only journal entry's repeatable claim is "trailing under the
rising 10-EMA after 2R captured an extra ~7% on this trade." That's a
sample-size-of-one claim. The full-path sample runs `backtest-expert` on an
**87-setup illustrative historical sample** (VCP grade A/B, RISK_ON regime,
2R reached) and gets:

| Metric | Trail rule | Fixed 2R baseline |
|--------|-----------:|------------------:|
| Avg return | **14.6%** | 10.2% |
| Avg holding days | 38.4 | 22.1 |
| Premature trail exit rate | 18% | — |

Verdict: **VALIDATED_WITH_CAVEAT** (+4.4 pp edge at the cost of ~16 extra
holding days). The lessons entry is updated to note this, plus a refinement
candidate ("widen ATR multiplier from 1 to 1.5 in choppy mid-cycle regimes").

This is the value of the optional `backtest-expert` step: it turns a one-
trade hunch into a statistically-grounded rule (or rejects it).

## Schema fidelity (this is enforced, not asserted)

- `01_closed_thesis_record.yaml` passes the **real** trader-memory-core
  validator: `jsonschema` Draft-07 against
  `skills/trader-memory-core/schemas/thesis.schema.json` **plus** the `CLOSED`
  business invariants in `thesis_store._validate_thesis()` (exit price/date
  set, valid `exit_reason`, `exit_date ≥ entry_date`, `status_history`
  monotonic and ending in `CLOSED`, RFC-3339 timestamps with timezone). Date
  strings are quoted so `yaml.safe_load` returns them as strings (the schema
  requires `type: string` + `format: date-time`/`date`). Both `sample-run/`
  and `sample-run-full-path/` use the same validated YAML.
- `02_postmortem_findings.json` is produced by the **real**
  `signal-postmortem` recorder consuming that thesis, so its
  `outcome_category` / `holding_days` are computed, not hand-typed.
- `03_backtest_validation.json` (full-path only) is an illustrative hand-
  authored backtest output; the real `backtest-expert` skill produces the
  same shape on real historical data.

## Reproduce / verify

From the repo root (read-only; `uv` provides `jsonschema`):

```bash
uv run python - <<'PY'
import json, sys, yaml
sys.path.insert(0, "skills/trader-memory-core/scripts")
import thesis_store
# Both variants share the same thesis YAML, so we validate either one
d = "examples/workflows/trade-memory-loop/sample-run-full-path"
t = yaml.safe_load(open(f"{d}/01_closed_thesis_record.yaml"))
thesis_store._validate_thesis(t)            # raises on any violation
pm = json.load(open(f"{d}/02_postmortem_findings.json"))
assert pm["outcome_category"] == "TRUE_POSITIVE"
assert pm["holding_days"] == 50
bt = json.load(open(f"{d}/03_backtest_validation.json"))
assert bt["interpretation"]["verdict"] == "VALIDATED_WITH_CAVEAT"
print("OK: thesis validates; postmortem + backtest fields reproduce")
PY
```

## Run it for real

See [`sample-run/prompt.md`](sample-run/prompt.md) (required-only) or
[`sample-run-full-path/prompt.md`](sample-run-full-path/prompt.md)
(full-path). No API key is required for the required path (FMP is optional,
only for MAE/MFE auto-calc); the full-path `backtest-expert` step depends on
your chosen data source. Your real thesis IDs, dates, and outcomes will
differ from this fixed sample.
