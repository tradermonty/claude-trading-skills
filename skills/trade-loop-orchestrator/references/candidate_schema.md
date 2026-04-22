# Candidate Schema

Every screener adapter must emit candidates in this shape. The orchestrator
does not re-parse individual screener reports; it reads the adapter output.

```json
{
  "ticker": "AAPL",
  "side": "buy",
  "entry_type": "market",
  "entry_price": 185.50,
  "stop_loss": 179.20,
  "target": 198.00,
  "primary_screener": "vcp-screener",
  "supporting_screeners": ["canslim-screener"],
  "strategy_score": 78,
  "confidence": 0.85,
  "sector": "Technology",
  "atr": 3.12,
  "source_report": "reports/vcp_screener_2026-04-21.json",
  "as_of": "2026-04-21T14:15:00Z",
  "notes": "7-week VCP base, 52-wk high pivot"
}
```

## Required fields

| Field | Type | Notes |
|-------|------|-------|
| ticker | str | Uppercase |
| side | "buy" \| "sell" | Short sales require profile.allow_shorts=true |
| entry_type | "market" \| "limit" | If limit, entry_price is binding |
| entry_price | float | For market orders, used only for sizing estimate |
| stop_loss | float | Mandatory. Direction validated downstream. |
| target | float | Mandatory. Drives R/R check (min 1.5) |
| primary_screener | str | Matches key in screener_weights.yaml |
| strategy_score | 0-100 | Internal screener score |
| confidence | 0.0-1.0 | Adapter-computed confidence |

## Optional fields

| Field | Purpose |
|-------|---------|
| supporting_screeners | Signals confluence - adds weight in ranking |
| sector | If absent, orchestrator resolves via sector_map.yaml |
| atr | Used by position-sizer as alternative to fixed stop |
| source_report | Traceability - path to the screener report |
| notes | Human-readable context for the audit log |
| trend_state | "uptrend" \| "sideways" \| "downtrend" |

## Composite Ranking Formula

```
weight = screener_weights[primary_screener]
supporting_bonus = 0.15 * min(len(supporting_screeners), 3)
composite = (strategy_score / 100) * weight * (1 + supporting_bonus) * confidence
```

Max composite at strategy_score=100, confidence=1.0, with 3 supporting = weight * 1.45.
