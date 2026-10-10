# Stagnation Triggers

Five deterministic triggers detect when a strategy's backtest iteration loop has stalled. Each trigger maps directly to fields in `evaluate_backtest.py` output accumulated in an iteration history file.

## Field Reference Mapping

| Data Point | JSON Path | Type |
|---|---|---|
| total_score | `eval.total_score` | int |
| Expectancy dim score | `eval.dimensions` (lookup by `name == "Expectancy"`) | int |
| Risk Management dim score | `eval.dimensions` (lookup by `name == "Risk Management"`) | int |
| Robustness dim score | `eval.dimensions` (lookup by `name == "Robustness"`) | int |
| red_flag IDs | `[f["id"] for f in eval.red_flags]` | list[str] |
| expectancy | `eval.expectancy` | float |
| profit_factor | `eval.profit_factor` | float or null |
| profit_factor_status | `eval.profit_factor_status` | `FINITE`, `NO_LOSSES`, `UNDEFINED_ZERO_GROSS`, or `OVERFLOW` |
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

If `profit_factor` is null with `NO_LOSSES`, this trigger does not fire: positive gross profit with no gross losses is not evidence of cost defeat. Other null, non-finite, or unknown profit-factor values cannot support the ratio comparison and instead fire `insufficient_profit_factor` (high severity). This includes zero gross wins/losses and ratio overflow. Older evaluations without `profit_factor_status` are treated as unknown when their ratio is null.

---

## Trigger 4: Insufficient Profit Factor

**ID**: `insufficient_profit_factor`
**Severity**: high

**Condition**: At least two iterations and the latest profit factor is unavailable or non-finite, except an explicit `NO_LOSSES` result.

**Rationale**: The cost-defeat comparison cannot be made reliably. The reported status is retained as evidence for manual review. The diagnosis recommends `review_required`, with `stagnation_detected: false`, and pivot generation stops until a valid evaluation is available.

---

## Trigger 5: Tail Risk

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
| 1 | Latest evaluation has `decision: NOT_EVALUABLE` or `insufficient_profit_factor` | `review_required` |
| 2 | Latest `total_score` < 30 AND `iterations >= 3` AND score trajectory (last 3) is monotonically non-increasing | `abandon` |
| 3 | An actionable trigger fired | `pivot` |
| 4 | None of the above | `continue` |

**Note**: `abandon` is evaluated first. This catches cases where scores are consistently terrible but may not trip any specific trigger threshold (e.g., all scores hovering around 25 with no single trigger matching).
