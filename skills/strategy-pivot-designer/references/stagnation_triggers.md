# Stagnation Triggers

Four deterministic triggers detect when a strategy's backtest iteration loop has stalled. Each trigger maps directly to fields in `evaluate_backtest.py` output accumulated in an iteration history file.

## Field Reference Mapping

| Data Point | JSON Path | Type |
|---|---|---|
| total_score | `eval.total_score` | int |
| Expectancy dim score | `eval.dimensions` (lookup by `name == "Expectancy"`) | int |
| Risk Management dim score | `eval.dimensions` (lookup by `name == "Risk Management"`) | int |
| Robustness dim score | `eval.dimensions` (lookup by `name == "Robustness"`) | int |
| red_flag IDs | `[f["id"] for f in eval.red_flags]` | list[str] |
| expectancy | `eval.expectancy` | float |
| profit_factor | `eval.profit_factor` | float |
| slippage_tested | `eval.inputs.slippage_tested` | bool |
| max_drawdown_pct | `eval.inputs.max_drawdown_pct` | float |

**Note**: Dimension scores are looked up by `name` field, not by array index. This makes the system resilient to future dimension reordering or additions.

---

## Trigger 1: Improvement Plateau

**ID**: `improvement_plateau`
**Severity**: high

**Condition**: Over the last K iterations (default K=3), the range of `total_score` values is less than threshold (default 3).

**Rationale**: When score stops moving despite parameter changes, the strategy architecture itself has reached a local maximum.

**Evidence fields**:
- `last_k_scores`: list of total_score values for the last K iterations
- `score_range`: max - min of last_k_scores
- `threshold`: the configured threshold

**Minimum iterations**: K (default 3). Cannot fire with fewer iterations.

---

## Trigger 2: Overfitting Proxy

**ID**: `overfitting_proxy`
**Severity**: medium

**Condition**: ALL of the following must be true:
1. Expectancy dimension score >= 15
2. Risk Management dimension score >= 15
3. Robustness dimension score < 10
4. red_flags IDs contain `over_optimized` OR `short_test_period`

**Rationale**: High in-sample performance combined with low robustness and red flags for curve-fitting suggests the strategy is optimized to historical noise rather than genuine edge.

**Minimum iterations**: 2 (needs at least some iteration history to be meaningful).

---

## Trigger 3: Cost Defeat

**ID**: `cost_defeat`
**Severity**: medium

**Condition**: ALL of the following must be true:
1. `eval.expectancy` < 0.3
2. `eval.profit_factor` < 1.3
3. `eval.inputs.slippage_tested` == True

**Rationale**: When expectancy and profit factor are thin AND slippage has already been modeled, the edge is too narrow to survive real-world execution costs. Further parameter tuning cannot create edge that isn't there.

**Minimum iterations**: 2 (requires slippage to have been tested, which implies at least one refinement cycle).

---

## Trigger 4: Tail Risk

**ID**: `tail_risk`
**Severity**: high

**Condition**: EITHER of the following:
1. `eval.inputs.max_drawdown_pct` > 35
2. Risk Management dimension score <= 5

**Rationale**: Extreme drawdown or catastrophically low risk management scores indicate structural risk problems that parameter tuning alone cannot fix. Requires architectural changes to risk module.

**Minimum iterations**: 1 (can fire on the very first evaluation — if drawdown is extreme, early pivot is warranted).

---

## Recommendation Decision Table

Evaluated in priority order (first match wins):

| Priority | Condition | Recommendation |
|----------|-----------|---------------|
| 1 | Latest `total_score` < 30 AND `iterations >= 3` AND score trajectory (last 3) is monotonically non-increasing | `abandon` |
| 2 | `triggers_fired` has at least 1 entry | `pivot` |
| 3 | None of the above | `continue` |

**Note**: `abandon` is evaluated first. This catches cases where scores are consistently terrible but may not trip any specific trigger threshold (e.g., all scores hovering around 25 with no single trigger matching).
