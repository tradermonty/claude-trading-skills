# Errata — Kanchi Dividend Screening Runs (2026-05-16 / 2026-05-17)

Tracked audit trail. The verdict reports themselves live under the
gitignored `reports/`; this corrections ledger is **git-tracked** so the
"what / when / why" of every reversed call is permanently auditable
(improvement-plan v2 MJ-9, 4th-review point 2).

- Issued: 2026-05-17
- Root-cause defects: D1 freeze · D2 GAAP-payout distortion · D3 forward
  M&A miss · D4 special/variable trap · D5 stale-dividend false-negative
- Status: corrected calls below; the engine fix ships in this branch
  (WS-1..WS-8). Until merged, **do not re-run the old reports for orders**.

## 4%-floor run (2026-05-16, income-now, tight bias)

| Ticker | Original | Corrected | Root cause | Evidence |
|---|---|---|---|---|
| CMCSA | PASS | PASS-SAFETY / HOLD-GROWTH (income cash-cow) | D1 | 2026 dividend maintained $1.32 (Comcast IR) |
| MKC | PASS | HOLD-REVIEW | D2,D3 | Aristocrat≠King; Q1-26 GAAP +$3.22 non-cash; Unilever Foods $44.8B |
| EIX | HOLD-REVIEW | HOLD-REVIEW (retain) | — | Eaton-Fire tail; normalize 2025 EPS |
| ES | HOLD-REVIEW | HOLD-REVIEW (reason updated) | — | FERC ROE + leverage + offshore-wind |
| ORI | HOLD-REVIEW | HOLD-REVIEW (regular yield <4% floor) | D4 | 9% headline = special-inclusive; regular ≈3.2% |
| CALM | FAIL | FAIL (retain) | D4 | variable dividend policy |

## 3%-floor run (2026-05-17, balanced, medium bias)

| Ticker | Original | Corrected | Root cause | Evidence |
|---|---|---|---|---|
| CMCSA | PASS | CONDITIONAL-PASS (income cash-cow) | D1 | freeze; FCF safety strong |
| MKC | PASS | HOLD-REVIEW | D2,D3 | as above (Unilever close ~mid-2027) |
| OZK | PASS | PASS-CAUTION | — | latest $0.47→4.02%; NPL 0.20→0.90%, NCO 0.25→0.57% |
| HOMB | PASS | CLEAN-PASS | — | cleanest; Mountain Commerce minor-monitor |
| RF | PASS | PASS / WAIT | — | simplest bank; not at Step-5 trigger |
| FULT | PASS | PASS-CAUTION / WAIT | — | Blue Foundry integration |
| FITB | PASS | PASS-CAUTION / WAIT | D2 | Comerica merger completed → GAAP EPS distorted |
| FBP | PASS¹ | PASS-CAUTION / WAIT | D5 | latest $0.20→3.44% (was 3.18%); PR concentration |
| WTRG | PASS² | HOLD-REVIEW (merger event) | D3 | AWK all-stock merger pending |
| EXC | PASS² | PASS-CAUTION / WAIT | — | regulated T&D; monitor capex/ROE/issuance |
| HTO | PASS² | HOLD-REVIEW (low-priority) | D3 | Quadvest + ~$2.7B capex funding |
| CFR | **FAIL (<3%)** | **STEP1-RECHECK** | **D5** | latest declared $1.03 → 3.06% > floor (FMP-verified) |
| ORI | HOLD-REVIEW (below floor) | HOLD-REVIEW (insurer module) | D4 | regular yield ≈3.2% clears 3% floor → insurer review |
| EIX / ES | HOLD-REVIEW | HOLD-REVIEW (retain) | — | unchanged structural issues |
| CALM / MTB / CPK | FAIL | FAIL (retain) | — | variable / below-floor |

Net actionable read (post-correction): **CLEAN-PASS: HOMB · small/conditional:
CMCSA, OZK · alert-only: RF, FULT, FBP, EXC, CFR(after recheck) ·
event-review-first: MKC, WTRG, HTO, FITB · deep-dive: EIX, ES, ORI ·
exclude: CALM, MTB, CPK.** "11 PASS" → realistically 2–3 immediate.

> Unconditional clean buy after correction: HOMB only. The original
> "2 PASS" (4%) / "11 PASS" (3%) overstated actionability.
