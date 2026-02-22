# Valuation And One-Off Checks

Use this file for Kanchi Step 3 and Step 4 decisions.

## Step 3: Valuation Mapping By Sector

| Sector/Type | Primary metric | Secondary metric | Pass condition example |
|---|---|---|---|
| Banks/Insurers | `P/TBV` | `PER x PBR` (compatibility) + historical percentile | Reject when clearly above historical fair band |
| REIT | `P/FFO` or `P/AFFO` | Implied cap rate vs peers | Prefer below own 5y median multiple |
| Asset-light growth | Forward `P/E` | `P/FCF` and 5y range | Require at least one valuation metric near lower half of range |
| Mature cash cows | `P/FCF` | Dividend yield vs 5y average | Prefer yield above historical mean with intact fundamentals |

Note:
- Kanchi's original Japan-style filter uses `PER x PBR`.
- For US banks, `P/TBV` is typically more robust because tangible book is the standard anchor.

If metrics disagree, choose `HOLD-FOR-REVIEW` instead of forcing `PASS`.

## Step 4: One-Off Profit Checklist

Mark each item `YES/NO`. Two or more `YES` values require downgrade or reject.

1. Profit jump driven by asset sales or disposal gains.
2. EPS lifted by legal settlement or tax one-time effects.
3. Margin expansion without matching revenue quality.
4. Management repeatedly labels key profit items as "non-recurring."
5. Dividend support appears linked to debt increase or asset liquidation.

## Step 4 Output Format

Use this exact compact output in reports:

```text
Step4 verdict: FAIL
Reason: EPS uplift mostly from one-time asset sale; recurring margin trend still weak.
```

Keep each reason to one sentence.
