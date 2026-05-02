# Parabolic Short — Live API Smoke Test Runbook

This runbook is the manual verification procedure for the
`parabolic-short-trade-planner` skill against **live** FMP and Alpaca
APIs. The Phase 1 + Phase 2 unit-test suite (137 tests on dry-run
fixtures) cannot prove that the wire shapes upstream still match the
contract Phase 1 was built against, nor that the Alpaca paper account
is reachable with the configured credentials. This runbook closes that
gap.

Run it on any non-trivial change to:

- `fmp_client.py` (especially the EOD / profile normalizers)
- `adapters/alpaca_inventory_adapter.py`
- the Phase 1 → Phase 2 schema (any field rename in `parabolic_short_*`
  output JSON)
- new Alpaca account / API key rotation

It is also the one-time validation expected after merging the Phase 1+2
implementation, since the original PR shipped without any live
execution.

## 1. Prerequisites

Set the following environment variables before running anything:

```bash
export FMP_API_KEY=...           # Free tier (250 calls/day) is enough
export ALPACA_API_KEY=...
export ALPACA_SECRET_KEY=...
export ALPACA_PAPER=true         # Paper trading account; recommended
```

Other requirements:

- Python 3.10+
- `requests` available (`pip install requests` or use the repo's venv)
- Run all commands from the repository root; `screen_parabolic.py` and
  `generate_pre_market_plan.py` resolve `--ssr-state-dir` and
  `--output-dir` relative to the current working directory.

> **Cwd matters for SSR carryover.** Mixing relative and absolute
> paths across runs can leave orphan state files. The runbook below
> always passes `"$(pwd)/state/parabolic_short"` as the SSR state dir.

## 2. Connectivity check (~90 s, 5 checks / 6 HTTP calls)

```bash
python3 skills/parabolic-short-trade-planner/scripts/check_live_apis.py
```

The script runs **5 logical checks** (4 required gates + 1 optional
warning) against FMP + Alpaca. The fifth check (`alpaca_404_graceful`)
issues two HTTP requests against the same Alpaca endpoint — one raw
probe to confirm the 404 status, one through
`AlpacaInventoryAdapter.get_inventory_status()` to confirm the adapter
handles that response without raising — so the script makes
**6 HTTP calls** per run total (3 FMP + 3 Alpaca). Cost remains
trivial under both API rate limits.

Expected output (order may vary):

```
PASS fmp.historical_price_eod_full — N bars; Issue #64 shape verified
PASS fmp.profile — mktCap=...
WARN fmp.sp500_constituent — HTTP 403 — likely entitlement (skip on Free)
PASS alpaca.assets_aapl — shortable=True easy_to_borrow=True (paper=True)
PASS alpaca.assets_404_graceful — raw HTTP 404 mapped to asset_not_found dict
Required gates: 4/4 passed (sp500 is optional warning)
```

Exit code 0 means all four required gates passed. The sp500 line is a
warning, not a gate — it can be PASS or WARN depending on FMP tier.

If any gate fails, the script prints `FAIL <name> — HTTP <code> — <body
truncated>`. Common failure causes are documented in the
**Troubleshooting matrix** at the end.

## 3. Phase 1 — Tier 1 rejection smoke (`smoke_universe_diverse.csv`)

```bash
mkdir -p reports/smoke
python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
  --universe finviz-csv \
  --universe-csv skills/parabolic-short-trade-planner/references/smoke_universe_diverse.csv \
  --max-api-calls 50 --top 25 \
  --output-dir reports/smoke/ \
  --verbose
```

The diverse CSV is rejection-biased (mega-cap defensives + thin
mid-caps), so most or all tickers will reject at the soft thresholds
(`min_roc_5d`, `min_ma20_extension_pct`). **Zero candidates is a PASS
for this tier** provided `--verbose` shows at least one rejection
reason, which proves the invalidation path is live.

Output:

- `reports/smoke/parabolic_short_<as_of>.json` — v1.0 schema; `candidates`
  may be `[]`.
- `reports/smoke/parabolic_short_<as_of>.md` — human-readable report.

If candidates **is** non-empty, you can additionally run Phase 2 with
`--broker none` against this report and confirm every plan comes out
as `plan_status: watch_only` with `borrow_inventory_unavailable` in
`blocking_manual_reasons` — same checks as Tier 2 below.

## 4. Phase 1 — Tier 2 end-to-end smoke (`smoke_universe_relaxed.csv`)

```bash
python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
  --universe finviz-csv \
  --universe-csv skills/parabolic-short-trade-planner/references/smoke_universe_relaxed.csv \
  --min-roc-5d 0 --min-ma20-extension-pct 0 --min-atr-extension 0 \
  --watch-min-grade D \
  --exclude-earnings-within-days 0 --min-adv-usd 0 \
  --min-price 0 --min-market-cap 0 \
  --max-api-calls 50 --top 25 \
  --output-dir reports/smoke/ \
  --output-prefix parabolic_short_relaxed \
  --verbose
```

Two flag groups:

- **Soft** (`--min-roc-5d`, `--min-ma20-extension-pct`,
  `--min-atr-extension`): set to 0 so score components don't gate.
- **Hard** (`--exclude-earnings-within-days`, `--min-adv-usd`,
  `--min-price`, `--min-market-cap`): set to 0 so a single
  earnings-tomorrow ticker (or recent IPO) doesn't drop the whole
  CSV. All four flags already exist on `screen_parabolic.py` —
  the runbook does not need a source patch.

Expected: `candidates` length ≥ 1 (near-certain on 8–10 mega-caps with
all gates relaxed). If 0, the rejection logic itself is buggy or the
relaxed CSV is stale (re-curate the CSV — see Pitfall #5).

Output:

- `reports/smoke/parabolic_short_relaxed_<as_of>.json` — feeds Phase 2.

## 5. Phase 2 — Alpaca + manual paths

> **Important**: Steps 5a and 5b both write to `reports/smoke/` but
> with **different `--output-prefix` values**. The default prefix
> (`parabolic_short_plan`) would have the manual run silently
> overwrite the Alpaca run.

### 5a. Alpaca path

```bash
mkdir -p state/parabolic_short
PHASE1_RELAXED=reports/smoke/parabolic_short_relaxed_<as_of>.json
python3 skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py \
  --candidates-json "$PHASE1_RELAXED" \
  --broker alpaca \
  --tradable-min-grade D \
  --account-size 100000 --risk-bps 50 \
  --ssr-state-dir "$(pwd)/state/parabolic_short" \
  --output-dir reports/smoke/ \
  --output-prefix parabolic_short_plan_alpaca
```

Expected:

- ≥1 plan emitted in `parabolic_short_plan_alpaca_<as_of>.json`.
- ≥1 plan ideally has `plan_status: actionable` (ETB happy path).
  If all plans come out `watch_only`, document in the smoke report
  ("all relaxed-CSV candidates HTB today — not a code bug, log only").
- `entry_plans[*].size_recipe.shares_formula` is a **string formula**,
  not a numeric `shares` field.
- Per-ticker SSR state files written under
  `state/parabolic_short/ssr_state_<ticker>_<as_of>.json`.

### 5b. Manual fallback path

```bash
python3 skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py \
  --candidates-json "$PHASE1_RELAXED" \
  --broker none \
  --tradable-min-grade D \
  --account-size 100000 --risk-bps 50 \
  --ssr-state-dir "$(pwd)/state/parabolic_short" \
  --output-dir reports/smoke/ \
  --output-prefix parabolic_short_plan_manual
```

Expected (regression check on the manual fallback):

- Every plan has `plan_status: watch_only`.
- Every plan's `blocking_manual_reasons` contains
  `borrow_inventory_unavailable`.

## 6. Day-2 SSR carryover determinism

```bash
PHASE2_PLAN=reports/smoke/parabolic_short_plan_alpaca_<as_of>.json

# Guard: Tier 2 must have produced at least one plan.
PLAN_COUNT=$(python3 -c "import json; print(len(json.load(open('$PHASE2_PLAN'))['plans']))")
if [ "$PLAN_COUNT" -lt 1 ]; then
  echo "Step 6 skipped: Tier 2 produced 0 plans; carryover test cannot run."
  exit 1
fi

TICKER=$(python3 -c "import json; print(json.load(open('$PHASE2_PLAN'))['plans'][0]['ticker'])")
TODAY=$(python3 -c "import json; print(json.load(open('$PHASE1_RELAXED'))['as_of'])")
TOMORROW=$(python3 -c "from datetime import date,timedelta; print((date.fromisoformat('$TODAY')+timedelta(days=1)).isoformat())")
STATE_FILE="state/parabolic_short/ssr_state_${TICKER}_${TODAY}.json"

# Force the trigger flag in yesterday's state file (the MVP can't detect
# Rule 201 fires on its own because aftermarket data isn't wired in).
python3 -c "import json,pathlib; p=pathlib.Path('$STATE_FILE'); \
  d=json.loads(p.read_text()); d['ssr_triggered_today']=True; \
  p.write_text(json.dumps(d))"

python3 skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py \
  --candidates-json "$PHASE1_RELAXED" \
  --broker none \
  --tradable-min-grade D \
  --as-of "$TOMORROW" \
  --ssr-state-dir "$(pwd)/state/parabolic_short" \
  --output-dir reports/smoke/ \
  --output-prefix parabolic_short_plan_day2
```

Expected: in `reports/smoke/parabolic_short_plan_day2_<TOMORROW>.json`,
the plan for `$TICKER` has:

```json
"ssr_state": {
  "ssr_carryover_from_prior_day": true,
  "uptick_rule_active": true,
  ...
}
```

The new `test_as_of_override_advances_carryover` test in
`tests/test_generate_pre_market_plan.py` covers the same behaviour at
the CLI/main() level, so this manual step is a regression check, not
the only verification.

## 7. Success criteria — two-tier

A **FULL PASS** requires both tiers green; report a **PARTIAL PASS**
when one tier passes and the other is incomplete (e.g. "rejection tier
passed; end-to-end incomplete due to live Alpaca outage").

### Tier 1: rejection smoke (Section 3)

PASS if all of:

- `check_live_apis.py` exits 0 on the four required gates.
- Phase 1 produces a v1.0 schema JSON. Candidates may be empty.
- `--verbose` documents at least one rejection reason for at least one
  ticker.
- (If candidates non-empty) Phase 2 with `--broker none` returns every
  plan as `plan_status: watch_only` with
  `borrow_inventory_unavailable` in `blocking_manual_reasons`.

Zero Phase 1 candidates is **NOT a fail** for Tier 1 — the diverse
CSV is rejection-biased by design.

### Tier 2: minimum-one-plan smoke (Sections 4–6)

PASS if all of:

- Phase 1 produces ≥1 candidate against the relaxed CSV.
- Phase 2 with `--broker alpaca` produces ≥1 plan whose schema
  validates against `tests/test_schema_contract.py`.
- ≥1 plan has `plan_status: actionable` — if none, document in the
  smoke report ("all relaxed-CSV candidates HTB today; not a code bug").
- Phase 2 with `--broker none` flips every plan to `plan_status:
  watch_only`.
- Day-2 carryover step (Section 6) flips `ssr_carryover_from_prior_day`
  to `true`.

This tier is **incomplete, not pass** if Phase 1 returns zero
candidates against the relaxed CSV — investigate (rejection logic
buggy, CSV stale, or FMP transient error).

## 8. Pitfalls

1. **FMP `quote.previousClose` aftermarket drift** — the screener
   uses `historical-price-eod/full` for `prior_close`. Never read
   `quote.previousClose`; it returns aftermarket-adjusted values and
   breaks SSR Rule 201 math. Verify by picking a ticker with a > 5%
   post-4 PM move and confirming Phase 1 stored the regular-session
   number in `key_levels.prior_close`.
2. **Alpaca paper symbol absence** — paper accounts have a smaller
   asset universe than live. After the 404 fix (in this PR),
   missing tickers map to `error: asset_not_found` and Phase 2
   continues with that symbol marked `borrow_inventory_unavailable`.
   `--verbose` shows the per-ticker map.
3. **SSR state file path drift** — `--ssr-state-dir` defaults to
   `state/parabolic_short/` **relative to cwd**. Different cwds produce
   orphan state files and silently break carryover. Always pass
   `"$(pwd)/state/parabolic_short"` for absolute clarity. The repo's
   `.gitignore` excludes `state/` so production state cannot
   accidentally be committed; note that already-tracked files would
   need a separate `git rm --cached`, and `git add -f` can still
   force-add. Treat the ignore line as a default, not a hard guarantee.
4. **Universe selection bias is split across two CSVs** —
   `smoke_universe_diverse.csv` is intentionally rejection-biased to
   exercise the invalidation path; `smoke_universe_relaxed.csv` is
   intentionally pass-biased to exercise Phase 2 wiring. Invalid
   tickers are **not** in either CSV — that path is covered by
   `check_live_apis.py` step 5 + the `tests/test_broker_inventory.py`
   404 test. Cherry-picking only parabolic-today names is forbidden
   because it masks rejection-path bugs.
5. **Both smoke CSVs age by construction** — current high-fliers,
   ETB liquidity, and mega-cap composition all rotate. Re-curate
   both CSVs quarterly. For the diverse CSV, Tier 1 still passes
   on staleness (zero candidates is OK). For the relaxed CSV,
   staleness drops Tier 2 to "incomplete" (zero candidates) — the
   known failure mode for stale CSV maintenance, distinct from a
   real code bug.
6. **Lookback < 21 bars silent skip** — `screen_one_candidate`
   returns `None` when fewer than 21 bars are available, logged only
   at DEBUG. Recently-IPO'd or post-split tickers can produce empty
   `candidates[]` and look like an API failure. Always use
   `--verbose` for the first smoke run; empty output is not the same
   as a broken pipeline.

## 9. Troubleshooting matrix

| Symptom | Likely cause | Action |
|---|---|---|
| `check_live_apis.py` FAIL on `fmp.historical_price_eod_full` HTTP 401 | `FMP_API_KEY` invalid / expired | Re-issue key on https://site.financialmodelingprep.com/developer/docs |
| `check_live_apis.py` FAIL on `fmp.historical_price_eod_full` shape mismatch | FMP changed the EOD response shape (Issue #64 regression) | Read the body excerpt, then re-check `fmp_client._normalize_eod_flat_list` |
| `check_live_apis.py` WARN on `fmp.sp500_constituent` | FMP tier doesn't include the constituent endpoint | Ignore — not a gate. Phase 1 only uses sp500 when `--universe sp500`; finviz-csv path doesn't need it. |
| `check_live_apis.py` FAIL on `alpaca.assets_aapl` HTTP 401/403 | `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` mismatch with `ALPACA_PAPER` | Confirm the key was issued for the same account class (paper vs live) as `ALPACA_PAPER` |
| `check_live_apis.py` FAIL on `alpaca.assets_404_graceful` ("raised on 404") | Adapter regression — `raise_for_status()` triggered | Re-apply the 404 → asset_not_found mapping in `adapters/alpaca_inventory_adapter.py` |
| Phase 1 emits empty `candidates[]` against the **diverse** CSV | Expected — diverse CSV is rejection-biased | Confirm `--verbose` shows rejection reasons; **PASS** for Tier 1 |
| Phase 1 emits empty `candidates[]` against the **relaxed** CSV | (a) Rejection logic buggy, (b) CSV stale, (c) FMP transient error | Re-run with another ticker; check `--verbose`; re-curate the CSV if needed |
| Phase 2 errors on `KeyError: 'as_of'` from a custom Phase 1 JSON | Hand-edited Phase 1 JSON missing `as_of` | Pass `--as-of YYYY-MM-DD` explicitly |
| Phase 2 alpaca-step output disappears between steps 5a and 5b | `--output-prefix` defaulted to the same value in both runs | Always pass distinct `--output-prefix` per step |
| Day-2 carryover does NOT flip `ssr_carryover_from_prior_day` | (a) Wrong cwd between runs (state file in a different `state/` dir), (b) `--as-of` not advanced by exactly +1 calendar day | Run `ls state/parabolic_short/` and confirm the Day-1 state file uses the expected date and ticker |
| `state-dir permission denied` | The `state/` directory is owned by another user (e.g. root from a Docker run) | `sudo chown -R "$USER" state/` |

---

This runbook is the executable definition of "smoke passed". When in
doubt, prefer running the runbook over reasoning about whether the
upstream APIs still match the contract.
