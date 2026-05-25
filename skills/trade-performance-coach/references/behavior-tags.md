# Trading Behavior Tags

## Principle

Behavior tags are not psychological diagnoses. They are evidence-based hypotheses
about trading behavior that may explain process drift. Always use language like
"possible pattern" and include evidence plus a reflection question.

## MVP Tags

| Tag | Meaning | Evidence Examples | Guardrail Ideas |
|---|---|---|---|
| `fomo_entry` | Entered because of fear of missing a move rather than setup confirmation. | journal says "didn't want to miss", entry before confirmation, chased above plan | require thesis + screenshot before entry; no chase after missed trigger |
| `revenge_trade` | Trade appears motivated by making back a prior loss. | journal says "make it back", trade immediately after loss, oversized after loss | review-only mode after two losses; 24h delay after max loss |
| `premature_exit` | Exited before plan due to discomfort without invalidation. | exit before stop/target; journal says "got scared" | predefine partial/exit rules; no discretionary exit without invalidation note |
| `overconfidence_after_winner` | Risk increased after a win without rule justification. | actual risk > plan after prior winner; journal says "easy money" | cap risk after large winner; require normal sizing until next review |
| `stop_moved` | Stop was moved after entry without a pre-defined plan. | `actual.stop_moved = true` and not planned | stop changes must be pre-written; unplanned move triggers review |
| `size_creep` | Actual risk or size exceeded risk plan. | actual R > planned max R (explicit comparison) | reduce next trade size; require position-size screenshot |
| `unknown_size_discipline` | Risk discipline could not be assessed because actual.risk_r or the risk plan reference is missing. | position_size warning emitted because actual or reference risk is None | record planned and actual risk on the next trade so size discipline becomes verifiable |
| `hesitation` | Valid plan was not executed due to hesitation. | missed planned entry; journal says "hesitated" | use if/then trigger checklist; define no-entry after missed trigger |
| `rule_drift` | Repeated small deviations from rules. | multiple minor deviations or unclear records | simplify rules; pick one rule to enforce next week |
| `no_pattern_detected` | No behavior pattern detected from available evidence. | clean record with no supportive evidence | no behavior-specific guardrail needed |

## Tagging Rules

1. Never infer personality traits.
2. Never claim a medical or mental-health diagnosis.
3. Use low/medium/high confidence based on evidence strength.
4. Include exactly what evidence supports each tag.
5. Include a reflection question.
6. If evidence is weak, use `confidence: low` or do not tag.

## Reflection Question Examples

- FOMO: "What evidence did you have before entry that would not have been available after waiting for confirmation?"
- Revenge: "Would you have taken this trade if the prior trade had been a winner?"
- Premature exit: "What rule did the exit satisfy, or was it driven by discomfort?"
- Overconfidence: "Did the prior win change the size or quality threshold for this trade?"
- Stop moved: "Was the new stop part of the plan before entry?"
- Size creep: "What would this trade have looked like at the planned risk size?"
