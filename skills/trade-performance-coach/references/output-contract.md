# Output Contract

## Top-Level JSON

```json
{
  "schema_version": 1,
  "review_type": "single_trade | partial_close | monthly_aggregate",
  "review_id": "string",
  "source_records": ["string"],
  "overall_verdict": "OK | WARN | REVIEW_REQUIRED | RULE_VIOLATION | COOL_DOWN",
  "summary": {
    "outcome": "win | loss | breakeven | open | mixed | unknown",
    "primary_root_cause": "thesis_quality | execution | risk_sizing | market_environment | rule_violation | randomness | unknown",
    "secondary_root_causes": ["string"],
    "confidence": "low | medium | high"
  },
  "scores": {
    "process_score": 0,
    "risk_score": 0,
    "execution_score": 0,
    "review_quality_score": 0
  },
  "process_adherence_findings": [],
  "risk_manager_notes": [],
  "execution_quality_assessment": [],
  "behavioral_pattern_tags": [],
  "next_session_operating_rules": [],
  "coach_questions": [],
  "human_decision_gate": {
    "question": "string",
    "allowed_actions": ["accept_rules", "modify_rules", "defer", "journal_only"],
    "default_action": "journal_only"
  },
  "disclaimer": "string"
}
```

## Findings

Each finding should include:

```json
{
  "rule": "string",
  "status": "met | missed | unclear | not_applicable",
  "evidence": "string",
  "severity": "info | warning | critical"
}
```

Risk notes use:

```json
{
  "topic": "position_size | portfolio_heat | drawdown | correlation | stop_discipline | loss_limit | regime_gate",
  "finding": "string",
  "severity": "info | warning | critical",
  "evidence": "string"
}
```

Behavior tags use:

```json
{
  "tag": "fomo_entry | revenge_trade | premature_exit | overconfidence_after_winner | loss_aversion | rule_drift | stop_moved | size_creep | unknown_size_discipline | hesitation | no_pattern_detected",
  "confidence": "low | medium | high",
  "evidence": "string",
  "reflection_question": "string"
}
```

## Markdown Report

Markdown reports should include:

1. Verdict
2. Trade / period summary
3. Process adherence
4. Risk manager notes
5. Execution quality
6. Possible behavior patterns
7. Next-session operating rules
8. Coach questions
9. Human decision gate
10. Disclaimer
