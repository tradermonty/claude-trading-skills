# Catalyst Taxonomy

## Upside and Downside Catalyst Labels

| Label | Use when |
|---|---|
| `EARNINGS_REVALUATION` | Earnings, revenue, EPS, margin, or business results triggered a major repricing |
| `GUIDANCE_RAISE` | Management raised outlook, forecast, or long-term targets |
| `M&A` | Acquisition, merger, takeover, buyout, strategic alternative, or asset sale |
| `FDA_CLINICAL` | FDA, clinical trial, PDUFA, approval, rejection, or biotech study data |
| `CONTRACT_ORDER` | Large contract, government award, partnership, supply agreement, or major customer win |
| `ANALYST_UPGRADE` | Analyst upgrade, initiation, or material target-price change |
| `SHORT_SQUEEZE` | Short-interest, low float, borrow stress, squeeze narrative, or forced covering appears central |
| `THEME_SYMPATHY` | Move is primarily linked to a broader sector or theme cluster |
| `CAPITAL_STRUCTURE` | Offering, warrant, reverse split, convertible, ATM, recapitalization, or dilution issue |
| `LOW_FLOAT_SPECULATION` | Low-float / low-liquidity speculative burst without durable fundamental evidence |
| `NO_CLEAR_NEWS` | No structured catalyst is available or the move is price-only at the time of classification |

## Classification Rules

- Prefer structured catalyst data over price-only inference.
- Use `NO_CLEAR_NEWS` rather than hallucinating a catalyst.
- Keep `confidence` low when the text source is weak, vague, or stale.
- Classify the first-order catalyst, not every related news item.
- Allow human override in `human_review.label_override` when manual research finds a better label.

## Theme Context

Theme fields are separate from catalyst labels. A stock can be `EARNINGS_REVALUATION` and still belong to an AI infrastructure cluster. Use `THEME_SYMPATHY` only when the theme itself appears to be the primary driver.

## Risk Flags Often Associated With Catalysts

| Catalyst | Common risk |
|---|---|
| `FDA_CLINICAL` | Binary-event reversal after data details are digested |
| `SHORT_SQUEEZE` | Violent reversal and borrow/locate constraints |
| `CAPITAL_STRUCTURE` | Dilution, warrant overhang, reverse-split distortions |
| `LOW_FLOAT_SPECULATION` | Low liquidity, wide spreads, gap risk |
| `NO_CLEAR_NEWS` | Unexplained move, rumor risk, poor repeatability |
