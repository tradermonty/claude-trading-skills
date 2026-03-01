# Edge Concept Schema

`edge_concepts.yaml` captures abstraction between detection and strategy design.

```yaml
generated_at_utc: "2026-02-22T12:00:00+00:00"
as_of: "2026-02-20"
source:
  tickets_dir: "/tmp/edge-auto/tickets"
  hints_path: "/tmp/hints.yaml"
  ticket_file_count: 24
  ticket_count: 24
concept_count: 3
concepts:
  - id: edge_concept_breakout_behavior_riskon
    title: Participation-backed trend breakout
    hypothesis_type: breakout
    mechanism_tag: behavior
    regime: RiskOn
    support:
      ticket_count: 7
      avg_priority_score: 71.2
      symbols: ["XP", "NOK", "FTI"]
      entry_family_distribution:
        pivot_breakout: 7
      representative_conditions:
        - close > high20_prev
        - rel_volume >= 1.5
      # Fields below appear only when synthetic tickets exist (--promote-hints):
      # real_ticket_count: 5
      # synthetic_ticket_count: 2
    abstraction:
      thesis: "When liquidity and participation expand ..."
      invalidation_signals:
        - Breakout fails quickly with volume contraction.
    strategy_design:
      playbooks: [trend_following_breakout, confirmation_filtered_breakout]
      recommended_entry_family: pivot_breakout
      export_ready_v1: true
    evidence:
      ticket_ids: [edge_auto_vcp_xp_20260220]
      matched_hint_titles: [Breadth-supported breakout regime]
      # Field below appears only when synthetic tickets exist:
      # synthetic_ticket_ids: [hint_promo_seasonal_buyback_0]
```

## Design Rule

- Abstraction must include both `thesis` and explicit `invalidation_signals`.
- `export_ready_v1` should be true only when recommended family is currently supported by pipeline interface v1.
- `hypothesis_type` valid values: breakout, earnings_drift, news_reaction, futures_trigger, calendar_anomaly, panic_reversal, regime_shift, sector_x_stock, research_hypothesis. The `research_hypothesis` value is a fallback for hint-promoted tickets where keyword inference could not determine a specific type.
