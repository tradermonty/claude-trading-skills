# Source, Financial and Sector Controls

Moved verbatim from `SKILL.md`. These rules apply to every selected deep dive.

## Source and Evidence Rules

Use this hierarchy:

1. SEC filings.
2. Company IR.
3. Official macro/statistical sources.
4. Market-data and consensus vendors.
5. Reputable news and third-party transcripts as supplementary context only.
6. Analyst calculations and assumptions, explicitly labeled.

Every source requires:

```text
unique source ID
tier and kind
publication timestamp
retrieval timestamp
data_as_of when different
URL
non-empty supports[] array
```

Official-source labels must match official domains. A third-party transcript is never company IR. Dynamic market fields are tested against their underlying data date, not just retrieval time.

## Financial and Forecast Controls

### Standard FCF and TTM evidence

Use:

```text
standard FCF = operating cash flow − capex cash outflow
```

Capex is a positive cash outflow. Build TTM cash flow through one documented method:

- reported TTM,
- four discrete quarters, or
- latest FY + current YTD − prior-year YTD.

Every component period must have resolving source IDs. Do not double-count cumulative 10-Q cash-flow values.

### Cash classification

For ordinary operating companies, normalize reported cash and equivalents to `corporate_cash`; separately identify eligible marketable securities. For payments, custodial, marketplace, broker, or money-movement businesses, explicitly separate corporate cash from settlement/customer funds and restricted cash. Enterprise value and net debt use only shareholder-available cash.

### Driver-derived forecast bridge

Do not validate a forecast by dividing a numerator that was merely set equal to `EPS × shares`.

For EPS, independently reconstruct:

```text
forecast operating income = forecast revenue × forecast operating margin
forecast pretax income = operating income + net interest/other income
forecast GAAP net income = pretax income × (1 − tax rate)
forecast adjusted net income = GAAP net income + sourced after-tax adjustments
forecast EPS = forecast net income ÷ forecast diluted shares
```

For FCF per share, derive standard FCF from OCF and capex or a fully sourced revenue/FCF-margin model, then divide by forecast diluted shares.

The driver result must tie to the claimed metric within tolerance. Supplied numerator/denominator fields are cross-checks only. Adjusted periods must also tie the driver-derived GAAP metric and after-tax adjustments to the GAAP reconciliation.

### GAAP and adjusted metrics

Store the basis separately for current, year 2, and year 3. Mixed bases block the formal scenario. Recurrent “one-time” exclusions, SBC, acquisition costs, and intangible amortization must be described and reflected in quality/risk assessment.

### ROIC, EBITDA, and quality evidence

ROIC and EBITDA used in scoring or leverage calculations require source-linked inputs or a transparent analyst calculation. Missing evidence caps data quality and blocks an unsupported 100 score.

## Sector and Cycle Controls

### Commercial biopharma and royalty/drug-delivery platforms

Normalize aliases such as `biopharma`, `pharma`, `biotechnology`, `royalty_biopharma`, and `drug_delivery_platform` to `commercial_biopharma` when the company has commercial product/royalty exposure.

Require:

- product or royalty concentration,
- nearest material LOE/patent event,
- years to LOE,
- resolving source IDs,
- configured 6x and 8x LOE stress scenarios when material.

Missing structural-risk evidence produces `review_required` and a quality cap.

### Cyclicals and peak-profit risk

If cyclicality is 3–5 **or** `peak_profit_risk=true`, require a sourced normalization object with mid-cycle revenue/margin/EPS/FCF or a documented reason the current economics are sustainable. A risk flag without normalization is not enough for `eligible`.
