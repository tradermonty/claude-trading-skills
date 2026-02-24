# Pivot Techniques

Three systematic techniques for generating structurally different strategy proposals when the backtest iteration loop stalls.

---

## Technique 1: Assumption Inversion

**Principle**: Identify the core assumptions of the current strategy and invert them based on which stagnation trigger fired.

### Inversion Rules by Trigger

| Trigger | Module | Inversion |
|---------|--------|-----------|
| `cost_defeat` | horizon | Shorten holding period (reduce friction exposure) |
| `cost_defeat` | universe | Shift to higher-liquidity names (reduce slippage) |
| `tail_risk` | risk | Tighten stops, reduce position size, add max drawdown cap |
| `tail_risk` | structure | Move toward market-neutral or hedged approach |
| `improvement_plateau` | signal | Change signal source (price-based → volume/fundamental) |
| `improvement_plateau` | entry | Change entry timing mechanism |
| `overfitting_proxy` | complexity | Reduce parameters, use simpler entry model |
| `overfitting_proxy` | validation | Extend test period, add regime subsamples |

### Application Process

1. Read the trigger(s) fired from the diagnosis
2. Look up the corresponding inversion rules
3. Apply each inversion to the current strategy's modules
4. Generate a new draft with the inverted assumptions

---

## Technique 2: Archetype Switch

**Principle**: Jump to a structurally different strategy archetype that addresses the same market inefficiency from a different angle.

### Process

1. Identify the current strategy's archetype from its `hypothesis_type`, `mechanism_tag`, and `entry_family`
2. Look up compatible pivot targets in the archetype catalog's `compatible_pivots_from` mapping
3. For each compatible target, generate a draft using the target archetype's default modules
4. Preserve the original concept_id and thesis where applicable

### Archetype Identification Rules

| hypothesis_type | mechanism_tag | entry_family | Archetype |
|----------------|---------------|--------------|-----------|
| breakout | behavior | pivot_breakout | trend_following_breakout |
| breakout | structural | pivot_breakout | volatility_contraction |
| mean_reversion | statistical | * | mean_reversion_pullback OR statistical_pairs |
| mean_reversion | information | * | event_driven_fade |
| earnings_drift | information | gap_up_continuation | earnings_drift_pead |
| momentum | behavior | * | sector_rotation_momentum |
| regime | macro | * | regime_conditional_carry |

When multiple archetypes match, prefer the one whose `entry_family` matches the current draft.

---

## Technique 3: Objective Reframe

**Principle**: Change what "success" means for the strategy, shifting the optimization target.

### Reframe Options

| Current Objective | Reframed To | Rationale |
|-------------------|-------------|-----------|
| Maximize Sharpe ratio | Minimize max drawdown | Better tail risk control |
| Maximize expectancy | Maximize win rate | More consistent (smaller but more frequent wins) |
| Maximize total return | Maximize risk-adjusted return per unit exposure | Capital efficiency focus |

### Application

1. Read the current strategy's `success_criteria` from `validation_plan`
2. Select a reframe based on the trigger:
   - `tail_risk` → drawdown minimization
   - `cost_defeat` → win rate maximization (smaller targets, tighter stops)
   - `improvement_plateau` → risk-adjusted return (different efficiency lens)
   - `overfitting_proxy` → simpler criteria (fewer optimization targets)
3. Adjust exit rules and risk parameters to align with the new objective
4. Update `success_criteria` in the generated draft

---

## Technique Selection by Trigger

| Trigger | Primary Technique | Secondary Technique |
|---------|-------------------|---------------------|
| `improvement_plateau` | Archetype Switch | Assumption Inversion |
| `overfitting_proxy` | Assumption Inversion | Objective Reframe |
| `cost_defeat` | Assumption Inversion | Archetype Switch |
| `tail_risk` | Assumption Inversion | Objective Reframe |

The generate_pivots script applies all applicable techniques and lets scoring determine the best candidates.

---

## Scoring

### Quality Potential (0-1)

Heuristic score based on how well a target archetype addresses the specific trigger. Defined in `QUALITY_TABLE` dictionary mapping `(trigger, archetype) → score`.

### Novelty (0-1)

Jaccard distance between the module sets of the original strategy and the proposed pivot:

```
novelty = 1 - |A ∩ B| / |A ∪ B|
```

Where A and B are sets of (key, value) pairs constructed from:
- `("hypothesis_type", <value>)`
- `("mechanism_tag", <value>)`
- `("regime", <value>)`
- `("entry_family", <value>)`
- `("horizon", <"short"|"medium"|"long">)` — time_stop_days ≤ 7: short, ≤ 30: medium, else: long
- `("risk_style", <"tight"|"normal"|"wide">)` — stop_loss_pct ≤ 0.04: tight, ≤ 0.08: normal, else: wide

### Combined Score

```
combined = 0.6 * quality_potential + 0.4 * novelty
```

### Tiebreak Rules (deterministic)

1. Combined score descending
2. Novelty descending (prefer more novel proposals)
3. Proposal ID alphabetical ascending (deterministic final sort)

### Diversity Constraint

Maximum 1 proposal per target archetype. If multiple techniques produce candidates for the same archetype, keep the one with the highest combined score.
