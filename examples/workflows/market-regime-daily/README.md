# Example: `market-regime-daily`

A canonical sample run of the
[`market-regime-daily`](../../../workflows/market-regime-daily.yaml) workflow:
a daily, no-API market-posture check that decides whether new swing-trade risk
is allowed before the session.

> ⚠️ **Illustrative only — not investment advice.** Both sample variants use
> a **fictional market snapshot** for a fixed date (`2026-01-15`) with **no
> individual tickers**. The numbers are hand-authored to be internally
> consistent and code-faithful, **not** captured from a live run.

## Two sample variants

This example ships two parallel samples that share the same date and inputs:

| Variant | Optional step | Posture outcome | Confidence | Purpose |
|---|---|---|---|---|
| [`sample-run/`](sample-run/) (**required-only**) | skipped | REDUCE_ONLY (48% ceiling) | LOW | Shows the conservative floor when critical inputs are missing |
| [`sample-run-full-path/`](sample-run-full-path/) (**full-path**) | included | NEW_ENTRY_ALLOWED (58% ceiling) | MEDIUM | Shows what the optional `market-top-detector` adds, and exercises the nested-shape parser fixed in PR #137 |

## Steps in this sample

| Step | Skill | Artifact | `sample-run/` | `sample-run-full-path/` |
|---|---|---|---|---|
| 1 | `market-breadth-analyzer` | `market_breadth_report` | ✅ included | ✅ included (nested-only) |
| 2 | `uptrend-analyzer` | `uptrend_report` | ✅ included | ✅ included (nested-only) |
| 3 | `market-top-detector` | `top_risk_report` | ⏭️ skipped (optional) | ✅ included (nested-only) |
| 4 | `exposure-coach` | `exposure_decision` | ✅ included | ✅ included |

## Files

```
sample-run/                        # required-only (raw-plus-handoff)
  prompt.md                        # the prompt you give Claude
  manifest.yaml                    # machine-readable step → artifact → file map
  01_market_breadth_report.json    # raw composite{} + top-level breadth_score
  01_market_breadth_report.md      # companion (human report)
  02_uptrend_report.json           # raw composite{} + top-level uptrend_score
  02_uptrend_report.md             # companion
  04_exposure_decision.json        # exposure-coach output
  04_exposure_decision.md          # companion (one-page posture)

sample-run-full-path/              # full-path (raw-nested-only)
  prompt.md                        # full-path prompt
  manifest.yaml                    # step → artifact → file map, no skipped steps
  01_market_breadth_report_raw.json # raw composite{}, no top-level handoff
  02_uptrend_report_raw.json        # raw composite{}, no top-level handoff
  03_top_risk_report_raw.json       # raw composite{} from market-top-detector
  04_exposure_decision.json         # exposure-coach output (computed from the 3 raw fixtures)
  04_exposure_decision.md           # companion
```

## The `raw-plus-handoff` convention (sample-run/) — historical note

`sample-run/` JSON each carry **both** the nested `composite { composite_score, … }`
block **and** a top-level hand-off field (`breadth_score` / `uptrend_score`).
The top-level field originally existed because `exposure-coach`'s
`extract_breadth_score()` only read the top-level field — the nested shape was
silently dropped, making *raw* breadth output a missing critical input.

That parser gap was **fixed by
[PR #137](https://github.com/tradermonty/claude-trading-skills/pull/137)**
(merged 2026-05-24). After PR #137, the extractor reads both shapes; the
top-level hand-off field in `sample-run/` is now a convenience rather than a
necessity. `sample-run-full-path/` deliberately omits it to exercise the
nested-only path directly.

## Why the required-only posture is `REDUCE_ONLY / LOW` (this is correct)

`exposure-coach` treats `regime`, `top_risk`, and `breadth` as **critical
inputs** and applies a **−10 composite haircut per missing critical input**.
In `sample-run/`, both `regime` (`macro-regime-detector`) and `top_risk`
(`market-top-detector`) are absent → a −20 haircut. With breadth 66 and
uptrend 72 the pre-haircut composite is `(66·0.15 + 72·0.15) / 0.30 = 69.0`,
haircut to **49.0**, mapped to a **48% exposure ceiling, REDUCE_ONLY,
LOW confidence** — even though internal participation is `BROAD`.

## Why the full-path posture is `NEW_ENTRY_ALLOWED / MEDIUM`

`sample-run-full-path/` adds step 3 (`market-top-detector` with
`composite.composite_score = 38`, a "Yellow / Early Warning" zone). The
extractor inverts that to `100 − 38 = 62` (high score = safe to be exposed)
and clears one of the two critical-input haircuts. The composite climbs to
**56.2** (58% ceiling, **NEW_ENTRY_ALLOWED, MEDIUM** confidence). This is the
honest, code-faithful demonstration of what running the optional satellite
adds — and it only works correctly *because* PR #137 fixed the nested-shape
parser for `top_risk`.

## Reproduce / verify

From the repo root, full-path sample (post-PR #137):

```bash
python3 skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth  examples/workflows/market-regime-daily/sample-run-full-path/01_market_breadth_report_raw.json \
  --uptrend  examples/workflows/market-regime-daily/sample-run-full-path/02_uptrend_report_raw.json \
  --top-risk examples/workflows/market-regime-daily/sample-run-full-path/03_top_risk_report_raw.json \
  --output-dir /tmp/verify_full_path/

# Then check the deterministic key fields:
python3 - <<'PY'
import glob, json
actual = json.load(open(sorted(glob.glob("/tmp/verify_full_path/exposure_posture_*.json"))[-1]))
expected = json.load(open("examples/workflows/market-regime-daily/sample-run-full-path/04_exposure_decision.json"))
for key in ("composite_score", "exposure_ceiling_pct", "recommendation", "confidence", "bias", "participation", "component_scores", "inputs_provided", "inputs_missing"):
    assert actual[key] == expected[key], f"{key}: {actual[key]!r} != {expected[key]!r}"
print("OK: full-path sample reproduced deterministically from raw nested fixtures")
PY
```

Required-only sample verification (read-only check that the extractors agree
with the fixture):

```bash
python3 - <<'PY'
import json, sys
sys.path.insert(0, "skills/exposure-coach/scripts")
import calculate_exposure as ce
d = "examples/workflows/market-regime-daily/sample-run"
b = json.load(open(f"{d}/01_market_breadth_report.json"))
u = json.load(open(f"{d}/02_uptrend_report.json"))
dec = json.load(open(f"{d}/04_exposure_decision.json"))
assert ce.extract_breadth_score(b) == dec["component_scores"]["breadth_score"] == 66
assert ce.extract_uptrend_score(u) == dec["component_scores"]["uptrend_score"] == 72
print("OK: real exposure-coach extractors reproduce the required-only sample scores")
PY
```

## Run it for real

See [`sample-run/prompt.md`](sample-run/prompt.md) or
[`sample-run-full-path/prompt.md`](sample-run-full-path/prompt.md). The
skills fetch public CSVs (no API key) plus optional FMP data for the
top-risk step; your live numbers will differ from these fixed samples.
