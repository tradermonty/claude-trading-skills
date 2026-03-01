# Hints Schema

Use this schema as input for downstream concept synthesis and auto detection.

```yaml
generated_at_utc: "2026-02-22T12:00:00+00:00"
as_of: "2026-02-20"
meta:
  rule_hints: 6
  llm_hints: 3
  total_hints: 9
  regime: RiskOn
hints:
  - title: "Breadth-supported breakout regime"
    observation: "Risk-on regime with pct_above_ma50=0.65"
    hypothesis_type: "breakout"              # optional
    preferred_entry_family: "pivot_breakout"  # optional
    symbols: ["NVDA", "AVGO"]              # optional
    regime_bias: "RiskOn"                    # optional
    mechanism_tag: "behavior"                # optional
```

## Field Notes

- `hypothesis_type`: optional; if present should be one of: breakout, earnings_drift, news_reaction, futures_trigger, calendar_anomaly, panic_reversal, regime_shift, sector_x_stock. Unrecognized values are first checked against keyword inference from the hint's title and observation; if no match is found, they fall back to `research_hypothesis`. Used for clustering when `--promote-hints` is enabled.
- `preferred_entry_family`: optional; if present must be `pivot_breakout` or `gap_up_continuation`.
- `symbols`: optional focus list. Empty means broad market hint.
- `regime_bias`: optional regime gate (`RiskOn`, `Neutral`, `RiskOff`).
- `mechanism_tag`: optional mechanism label (`behavior`, `flow`, `structure`, etc.).

## LLM CLI Contract

`build_hints.py --llm-ideas-cmd "<command>"` sends JSON to stdin:

```json
{
  "as_of": "YYYY-MM-DD",
  "market_summary": {...},
  "anomalies": [...],
  "news_reactions": [...],
  "instruction": "Generate concise edge hints ..."
}
```

The command must print either:

- `[{...}, {...}]`
- `{"hints": [{...}, {...}]}`
