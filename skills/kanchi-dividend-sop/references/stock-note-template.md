# One-Page Stock Memo Template

Use one memo per ticker. Keep each section concise and evidence-based.

```markdown
# [Ticker] - Dividend Memo

## Business Model
- Revenue engine:
- Core customer segments:
- Structural moat/risk:

## Dividend Policy
- Current forward yield:
- Dividend growth track record:
- Historical cuts/suspensions:

## Dividend Safety
- EPS payout ratio:
- FCF payout ratio (or FFO/NII coverage):
- Net debt trend:
- Interest coverage:
- Verdict: PASS / CAUTION / FAIL

## Kanchi Step 3 Valuation
- Method used: (PERxPBR / P-FFO / P-FCF / forward PE)
- Current value:
- Historical reference:
- Valuation verdict:

## Kanchi Step 4 One-Off Check
- Key finding (one sentence):
- Verdict: PASS / FAIL

## Verdict (WS-5 actionable tier)
- Tier: CLEAN-PASS / PASS-CAUTION / CONDITIONAL-PASS / HOLD-REVIEW / STEP1-RECHECK / FAIL
- Verdict reasons:

## Pre-Order Blockers (WS-6)
- pre_order_blockers[]: <list, or "none">
- t1_blocked: true / false
- If any blocker is unresolved OR t1_blocked: **T1 is blocked or downsized
  to a ≤20% tracking tranche** (never the full 40%). Resolve / acknowledge
  each blocker (status: blocked → acknowledged → cleared) before sizing up.

## Entry Plan (Kanchi Step 5)
- Trigger type: Yield / Valuation / Both
  - **Yield trigger**: current yield >= 5y avg yield + alpha (default +0.5pp)
  - **Valuation trigger**: price reaches target multiple (P/E, P/FFO, P/FCF)
- Buy zone: $[lower] - $[upper]
- Split orders: 40% / 30% / 30%  (T1 gated by Pre-Order Blockers above)
- Invalidation condition:

## Maximum Risk
- "If this happens, thesis is broken":

## Provenance (audit trail)
```yaml
provenance:
  price_source:
  price_asof:
  dividend_source:        # fmp_stock_dividend | issuer_ir
  dividend_dates_used: []
  payout_source:          # FMP | issuer non-GAAP recon | UNAVAILABLE
  event_scan_result:      # CLEAN_CONFIRMED | NO_EVENT_FOUND | MAJOR_EVENT | ...
  event_scan_checked_at:
  unresolved_blockers: []
  evidence_refs:
    - claim:
      source_type:        # issuer_ir | sec_filing | exchange | wire | portal
      source_url:
      checked_at:
      raw_value:
      normalized_value:
      confidence:          # high | medium | low
```

## Run Context (profile guard — never reuse a 3%-run result in a 4%-run)
```yaml
run_context:
  profile:                # income-now | balanced | growth-first
  yield_floor_pct:
  safety_bias:            # tight | medium
  universe_source:
  excluded_asset_types: []
```
```

Do not skip the invalidation condition, the provenance block, or the
pre-order blocker gate.
