# Account Location Matrix

Use this matrix to propose placement between taxable and tax-advantaged accounts.

## Baseline Placement Logic

| Instrument profile | Taxable account | Tax-advantaged account | Rationale |
|---|---|---|---|
| Qualified-dividend-heavy US equity | Usually preferred | Optional | Potentially better ongoing tax efficiency in taxable account |
| REIT-heavy income holdings | Less preferred | Often preferred | Distribution may include higher ordinary-income components |
| BDC/high-distribution structures | Less preferred | Often preferred | Tax treatment can be less favorable in taxable account |
| MLP (partnership units) | Case-by-case | Caution in tax-advantaged accounts | UBTI and K-1 complexity can make placement non-trivial |
| Broad index ETF with low turnover | Often acceptable | Also acceptable | Depends on overall asset-location design |

If MLP is outside mandate, mark it explicitly as `OUT-OF-SCOPE` and exclude from default allocation logic.

## Conflict Resolution Rules

When account-location recommendation conflicts with other needs:
1. Respect concentration and risk controls first.
2. Respect liquidity/withdrawal constraints second.
3. Optimize taxes third.

## Output Format

Return one line per holding:

```text
[Ticker] -> [Recommended Account] | Why: [one sentence]
```
