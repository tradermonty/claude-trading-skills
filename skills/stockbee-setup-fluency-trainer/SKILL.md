---
name: stockbee-setup-fluency-trainer
description: Build a Stockbee-style setup model book from momentum-burst screener candidates, then update 3-day and 5-day forward outcomes with MFE/MAE, stop-hit status, outcome tags, and cohort statistics. Use when the user wants to study Stockbee Momentum Burst examples, track failed candidates, build setup fluency, review A/B setup quality, or convert screener outputs into a learning loop rather than immediate trade signals. Also supports blind replay of the user's own enter/wait/pass decisions on vcp-screener candidates, scoring rule adherence separately from outcome.
---

# Stockbee Setup Fluency Trainer

Build and maintain a model book for Stockbee-style Momentum Burst setups. This skill turns daily screener candidates into structured study records, updates them after the 3-day and 5-day windows mature, and summarizes which setup features are working or failing.

## When to Use

- User wants to study Stockbee Momentum Burst setups systematically
- User asks to build a model book from `stockbee-momentum-burst-screener` output
- User wants to review failed candidates, missed trades, or A/B setup quality
- User wants 3-day / 5-day forward returns, MFE, MAE, and stop-hit outcomes
- User wants to improve setup recognition before increasing position size
- User asks which Stockbee tags should be promoted, downgraded, or filtered
- User wants a weekly blind replay of their own VCP enter/wait/pass decisions, with rule adherence scored separately from the later price path

## Prerequisites

- Python 3.10+
- A `stockbee-momentum-burst-screener` JSON report, or compatible candidate JSON
- Optional: FMP API key for outcome updates when offline OHLCV JSON is not supplied
- Recommended local state path: `state/stockbee/model_book.jsonl`
- For blind replay: a `vcp-screener` JSON report generated after the close, and offline OHLCV JSON at reveal time (stdlib only, no API key)

## Workflow

### Step 1: Ingest Momentum Burst Candidates

Run after the Stockbee Momentum Burst screener has produced a JSON report.

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py ingest \
  --screener-json reports/stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json \
  --model-book state/stockbee/model_book.jsonl \
  --output-dir reports/
```

Use `--include-rejects` when intentionally building a negative-example set. Otherwise rejected candidates are skipped.

### Step 2: Update 3-Day and 5-Day Outcomes

Use FMP:

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py update \
  --model-book state/stockbee/model_book.jsonl \
  --horizons 3,5 \
  --output-dir reports/
```

Use offline OHLCV JSON:

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py update \
  --model-book state/stockbee/model_book.jsonl \
  --prices-json data/daily_ohlcv.json \
  --horizons 3,5 \
  --output-dir reports/
```

The update step records:

- Forward close return for each horizon
- MFE and MAE over each horizon
- Stop-hit status and first stop-hit date
- Outcome tags such as `STRONG_WINNER`, `WORKED`, `FAILED_STOP`, `FAILED_FADE`, `CHOPPY_FAILURE`, or `NEUTRAL`

### Step 3: Summarize Cohorts

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py summarize \
  --model-book state/stockbee/model_book.jsonl \
  --group-by rating,primary_trigger,setup_tags \
  --min-sample 5 \
  --output-dir reports/
```

Review the generated Markdown and JSON reports. Treat `rule_candidates` as evidence prompts, not automatic rule changes.

### Step 4: Convert Evidence Into Practice

For cohorts with enough examples:

- Promote tags with high win rate, positive 5-day expectancy, and acceptable average MAE
- Downgrade or filter tags with weak 5-day expectancy, frequent stop hits, or repeated fade failures
- Inspect representative charts manually before changing trade rules
- Log accepted lessons in `trader-memory-core` or the monthly review process

### Step 5: Blind Replay of Your Own VCP Decisions

Use `decision_replay.py` to practice on your own past VCP decisions without hindsight. It supports the "screen after the close, capture the same evening" routine only. The result is practice feedback, not a trade recommendation.

Capture after each screen. The decisions file is a JSON list of `{symbol, decision, reason}` covering every candidate in the set, with `decision` one of `enter`, `wait`, `pass` and a one-line reason. Pass `--market-gate open` or `closed` as your own attestation.

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py capture \
  --screener-json reports/vcp_screener_YYYY-MM-DD_HHMMSS.json \
  --decisions decisions_YYYY-MM-DD.json \
  --market-gate open \
  --store-dir state/decision_replay/
```

On the weekend, draw a blind sample. Set `--decided-on-or-before` at least a week back so the 5-day window has matured.

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py replay \
  --sample-size 10 \
  --decided-on-or-before YYYY-MM-DD \
  --store-dir state/decision_replay/ \
  --output-dir reports/
```

The user records enter, wait or pass plus a one-line reason for every case in `answers.json` (`[{case_id, decision, reason}]`) before running `reveal`. While answering, do not fetch charts, news or prices for these symbols and do not comment on the setups.

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py reveal \
  --session-id replay-0123456789ab \
  --answers answers.json \
  --prices-json data/daily_ohlcv.json \
  --store-dir state/decision_replay/ \
  --output-dir reports/
```

Reveal shows the original and the replay decision side by side with the recorded rule result and the later path, and counts the four quadrants separately for each: followed or deviated from the rule, favorable or adverse outcome. A rule-compliant decision with an adverse outcome is reported as such; adherence and outcome are never merged. Cases captured after the first later bar, with unverified as-of prices, or without enough bars are excluded and counted. Use `replay --abandon SESSION_ID --reason TEXT` to drop a pending session, `--include-seen` to re-admit revealed cases, and `reconcile-ledger` to repair a missing ledger line. See `references/decision_replay.md` for the schema, guarantees and limits.

## Model Book Fields

Each JSONL record includes:

- `record_id`, `symbol`, `setup_date`, `primary_trigger`
- `rating`, `setup_score`, `setup_tags`
- `entry_reference`, `stop_reference`, `risk_pct_to_stop`
- `human_label`, `human_decision`, `human_notes`
- `outcomes.3d` and `outcomes.5d`
- `overall_outcome`, `matured`, `raw_candidate`

## Interpretation Rules

- `STRONG_WINNER`: 5-day close return >= 8% or MFE >= 12%, with no stop hit
- `WORKED`: 5-day close return >= 4% or MFE >= 6%, with no stop hit
- `FAILED_STOP`: Stop was touched within the horizon
- `FAILED_FADE`: Forward return <= -2% without a recorded stop hit
- `CHOPPY_FAILURE`: Adverse excursion was large and forward progress was poor
- `NEUTRAL`: No decisive follow-through or failure
- `PENDING`: Not enough future bars yet

## Output

- `state/stockbee/model_book.jsonl` - Durable setup model book
- `stockbee_setup_fluency_ingest_YYYY-MM-DD_HHMMSS.json/md`
- `stockbee_setup_fluency_update_YYYY-MM-DD_HHMMSS.json/md`
- `stockbee_setup_fluency_summary_YYYY-MM-DD_HHMMSS.json/md`
- `state/decision_replay/` - Write-once capture and session records for blind replay (local, gitignored)
- `stockbee_setup_fluency_replay_blind_<session_id>.json/md` - Blind view without decisions or later prices
- `stockbee_setup_fluency_replay_reveal_YYYY-MM-DD_HHMMSS.json/md` - Reveal with rule adherence, path and quadrants

## Resources

- `references/model_book_schema.md` - JSONL schema and lifecycle states
- `references/outcome_tags.md` - Outcome classification and tag definitions
- `references/review_workflow.md` - Daily, 3-day, 5-day, and monthly review routine
- `references/decision_replay.md` - Blind replay schema, guarantees and limits, rule v1, scoring and weekly routine

## Shared FMP client

Live FMP access uses the bundled generated `scripts/fmp_client.py`, loaded only
when an FMP run starts, so offline modes still work without `requests`. CLI
key/environment precedence, the API-call budget and successful output shapes are
preserved. Requests use stable endpoints only; a denied, empty or failed stable
request does not fall back to retired v3 URLs. The shared client masks raw and
URL-encoded key echoes, retries malformed JSON once, and retries a 429 at most once,
after a 60-second wait, before stopping on a repeated rate limit.

If every requested symbol fails at the transport level, `update` exits 1 and
leaves the model book unchanged instead of stamping each record `missing_prices`.
