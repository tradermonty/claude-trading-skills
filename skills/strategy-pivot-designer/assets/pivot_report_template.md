# Pivot Report: {strategy_id}

**Generated**: {generated_at_utc}
**Source Strategy**: {source_strategy_id}
**Diagnosis**: {diagnosis_summary}

---

## Stagnation Diagnosis

**Triggers Fired**: {triggers_count}
**Recommendation**: {recommendation}

{triggers_detail}

### Score Trajectory

{score_trajectory}

---

## Pivot Proposals

{pivot_proposals}

### Proposal: {proposal_id}

**Technique**: {pivot_technique}
**Target Archetype**: {target_archetype}
**Category**: {category}

**What Changed**:
- Signal: {signal_change}
- Horizon: {horizon_change}
- Risk: {risk_change}

**Why**: {why_explanation}

**Targeted Triggers**: {targeted_triggers}

**Scores**:
- Quality Potential: {quality_potential}
- Novelty: {novelty}
- Combined: {combined}

**Expected Failure Modes**:
{failure_modes}

---

## Summary

| Rank | Proposal | Archetype | Combined | Category |
|------|----------|-----------|----------|----------|
{summary_table}

---

## Next Steps

1. Review proposals and select the most promising pivot direction
2. For **exportable** proposals: ticket YAML is ready for `edge-candidate-agent` pipeline
3. For **research_only** proposals: manual strategy design needed before pipeline integration
4. Run backtest-expert on the selected pivot draft to begin the next iteration cycle
