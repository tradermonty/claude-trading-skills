# Sector-Specific Step 2 Modules (WS-4)

Step 2 (growth & safety) is sector-dispatched. This file holds the
**Step 2 safety indicators by sector**. It is the companion to
`valuation-and-one-off-checks.md`, which owns **Step 3 valuation** and
**Step 4 one-off** logic. Responsibility boundary (MN-2):

| Concern | Owner file |
|---|---|
| Step 2 safety indicators by sector | `sector-step2-modules.md` (this file) |
| Step 3 valuation mapping | `valuation-and-one-off-checks.md` |
| Step 4 backward one-off checklist | `valuation-and-one-off-checks.md` |
| Step 4b forward structural-event scan | `event_scanner.py` + SKILL.md Step 4b |

The deterministic thresholds are the SSOT in `scripts/thresholds.py`; the
numbers quoted below are human-readable mirrors. The script
`scripts/payout_safety.py` implements the dispatch.

## Why a uniform triad fails

FCF payout is the right anchor for consumer/industrial cash-cows, but:

- **Banks**: FCF is not a meaningful concept; capital adequacy and credit
  quality govern dividend safety.
- **Regulated utilities**: FCF is *structurally negative* (rate-base capex
  funded by debt/equity, recovered through rates). Auto-FAIL on negative
  FCF wrongly rejects healthy regulated names — this was the income-now vs
  balanced inconsistency in the 2026-05 runs.
- **Insurers**: GAAP earnings are noisy; statutory capital, reserve
  development and the combined ratio govern dividend capacity.

## Consumer / Industrial / Communication / default

Primary: **Adjusted-EPS payout + FCF payout**.

- Adjusted-EPS payout ≤ 70% PASS; 70–85% CAUTION; > 85% FAIL.
- FCF payout ≤ 80% PASS; > 100% FAIL.
- GAAP↔Adjusted EPS divergence > 25% ⇒ Step-4 one-off flag (MKC de Mexico
  non-cash remeasurement gain is the golden case).
- `adjusted_eps_source = UNAVAILABLE` ⇒ cap HOLD-REVIEW (never silent PASS).

## Banks

Primary: **EPS payout + capital + credit trend** (FCF ignored).

| Indicator | Caution / blocker condition |
|---|---|
| CET1 ratio (fraction, e.g. 0.12 = 12%) | missing/non-finite/bool/outside [0,1] ⇒ `bank_capital_unavailable`; below `BANK_CET1_MIN` ⇒ `bank_capital_weak` (CAUTION) |
| NPL trend | deteriorating ⇒ `bank_npl_nco_deteriorating` (CAUTION) |
| NCO trend | deteriorating ⇒ same blocker |
| Criticized / classified loans | rising ⇒ CAUTION |
| CRE / construction concentration | high ⇒ `bank_cre_concentration_high`; missing/unknown ⇒ `bank_cre_concentration_unavailable` (CAUTION). Recognized labels: low, moderate/medium, high |
| Deposit cost / beta | rising sharply ⇒ CAUTION |
| Uninsured deposit % / AOCI hit | elevated ⇒ CAUTION |

Golden case: **OZK** — strong serial raiser, low payout, but NPL 0.20%→0.90%
and NCO 0.25%→0.57% (Q1-2026) ⇒ **PASS-CAUTION**, not clean PASS.

## Regulated Utilities

Primary: **EPS payout + FFO/debt + allowed ROE + rate-case + equity issuance**.
Negative FCF is **not** an auto-FAIL.

| Indicator | Caution / blocker condition |
|---|---|
| FFO / debt | missing ⇒ `utility_ffo_debt_unavailable` (CAUTION); weak ⇒ CAUTION |
| Allowed ROE | falling / adverse order ⇒ CAUTION |
| Rate-case status | adverse / pending-adverse ⇒ `utility_rate_case_adverse` (HOLD-REVIEW) |
| Equity issuance risk | high / dilutive ⇒ `utility_equity_issuance_risk` (CAUTION) |
| EPS payout | > 100% ⇒ FAIL |

Golden cases: **WTRG** (AWK all-stock merger — Step 4b event, not a clean
utility PASS), **HTO** (Quadvest + ~$2.7B capex funding ⇒ equity-issuance
risk, low-priority).

## Insurers

Primary: **Operating-EPS payout + combined ratio + reserve development +
statutory capital**. Separate regular vs special dividends (ORI pays large
specials; the headline ~9% yield is a special-inclusive artifact — Step 1
must use the regular forward yield, ≈3.2%).

| Indicator | Caution / blocker condition |
|---|---|
| Combined ratio | missing ⇒ `insurer_combined_ratio_unavailable`; > 100 ⇒ CAUTION |
| Reserve development | adverse ⇒ `insurer_reserve_development_adverse` (HOLD-REVIEW) |
| Statutory capital | weak ⇒ HOLD-REVIEW |
| Special vs regular split | specials must be excluded from the income base |

Golden case: **ORI** — regular yield clears the 3% (balanced) floor →
Step-1 PASS → insurer-module HOLD-REVIEW (lumpy specials), NOT "trap /
below floor".

### Safety input guards (Issue #768)

Non-positive or invalid supplied EPS anchors cannot be interpreted as low payout:
the assessment returns HOLD-REVIEW with explicit blocker/reason codes, and the
corresponding payout ratio is unavailable. Consumer FCF uses the same guard;
FCF remains outside the bank/utility/insurer safety anchor, preserving regulated
utilities' structural-capex exception. Missing adjusted EPS retains its existing
`adjusted_eps_unavailable` gate. No missing value is silently converted to zero.

`BANK_CET1_MIN = 0.07` is a configurable **screening floor**, not a declaration of
regulatory compliance or peer-relative adequacy. It uses fraction units. The
[Federal Reserve capital framework](https://www.federalreserve.gov/supervisionreg/large-bank-capital-requirements.htm)
describes a 4.5% minimum plus buffers of at least 2.5%, and institution-specific
requirements may be higher. Passing this generic floor does not replace review
of the issuer's applicable requirements and capital trend. High CRE concentration
always adds a caution/blocker even with adequate CET1.
