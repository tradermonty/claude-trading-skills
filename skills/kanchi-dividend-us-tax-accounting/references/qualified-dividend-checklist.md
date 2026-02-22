# Qualified Dividend Checklist (US)

Use this checklist for planning assumptions.

## Classification Pass

For each holding, verify:
1. Distribution is potentially eligible for qualified treatment by instrument/type.
2. Shares meet required holding-period test around the ex-dividend date window.
3. No known disqualifying condition in the current fact pattern.

If any item is uncertain, mark as `ASSUMPTION-REQUIRED`.

## Holding-Period Rules (US Federal, Common Planning Baseline)

- Common stock baseline: hold shares for **more than 60 days** during the **121-day period** that starts **60 days before** the ex-dividend date.
- Preferred stock (certain long-period dividends): often uses **more than 90 days** during a **181-day period** starting **90 days before** ex-dividend date.

Use current IRS guidance as source of truth:
- IRS Publication 550.
- IRS Form 1099-DIV instructions.

## Practical Data Fields

Track these fields for each position:
- Ticker
- Account type
- Ex-dividend date
- Purchase date(s)
- Disposal date(s), if any
- Days held in required window
- Preliminary classification (`qualified-likely`, `ordinary-likely`, `unknown`)

## Common Pitfalls

- Assuming all common-stock dividends will be qualified without holding-period verification.
- Ignoring short holding periods caused by frequent tactical trading.
- Treating REIT/BDC distributions as identical to standard qualified-dividend flows.

## Recommended Source Hierarchy

1. Broker tax documents and distribution breakdowns.
2. Official IRS publications/instructions for current-year rules (Publication 550, 1099-DIV instructions).
3. Issuer or fund notices when classification is revised.
