# Scenario Playbooks

This reference provides templates and best practices for constructing 18-month scenarios.
Use it during scenario analysis to produce consistent, high-quality scenarios.

## Basic Principles of Scenario Construction

### 1. MECE (Mutually Exclusive, Collectively Exhaustive)

Scenarios should satisfy:
- **Mutually exclusive**: Scenarios do not overlap
- **Collectively exhaustive**: Cover the principal possibilities

### 2. Probability-Allocation Guidelines

| Scenario | Typical range | Rationale |
|----------|---------------|-----------|
| Base Case | 50-65% | Most likely path |
| Bull Case | 15-25% | Positive upside |
| Bear Case | 20-30% | Negative downside |
| Total | 100% | Must sum to 100% |

**When asymmetric allocation is appropriate:**
- Bull > Bear: environment with abundant bullish drivers
- Bear > Bull: environment with abundant risk factors
- Base > 60%: low-uncertainty situation
- Base < 50%: extremely high-uncertainty situation (Base Case itself uncertain)

### 3. Timeline Phases

**Three-phase structure:**
- **0-6 months**: Short-term reaction, initial moves
- **6-12 months**: Medium-term developments, trend formation
- **12-18 months**: Long-term outcomes, new equilibrium

---

## Scenario Templates

### Base Case Template

```markdown
### Base Case (XX% probability)

**Summary**:
[1-2 sentence summary. Describe the most likely path]

**Assumptions**:
- [Assumption 1]: [Specific condition]
- [Assumption 2]: [Specific condition]
- [Assumption 3]: [Specific condition]

**Timeline**:

**0-6 months:**
- [Key development 1]
- [Key development 2]
- [Expected market reaction]

**6-12 months:**
- [Medium-term development 1]
- [Medium-term development 2]
- [Trend direction]

**12-18 months:**
- [Long-term outcome 1]
- [New equilibrium state]
- [Structural changes (if any)]

**Impact on economic indicators**:
| Indicator | Current | 6-month forecast | 12-month forecast | 18-month forecast |
|-----------|---------|------------------|-------------------|-------------------|
| GDP growth | X% | X% | X% | X% |
| Inflation | X% | X% | X% | X% |
| Policy rate | X% | X% | X% | X% |
| Unemployment | X% | X% | X% | X% |

**Key catalysts**:
- [Factor that supports this scenario 1]
- [Factor that supports this scenario 2]

**Invalidation signals**:
- [Sign that this scenario is breaking down 1]
- [Sign that this scenario is breaking down 2]
```

### Bull Case Template

```markdown
### Bull Case (XX% probability)

**Summary**:
[1-2 sentence summary of the optimistic scenario; what kind of upside materializes]

**Assumptions**:
- [Optimistic assumption 1]: [Specific condition]
- [Optimistic assumption 2]: [Specific condition]
- [Optimistic assumption 3]: [Specific condition]

**Timeline**:

**0-6 months:**
- [Positive development 1]
- [Positive development 2]
- [Expected favorable market reaction]

**6-12 months:**
- [Continuation of upside trend]
- [Additional positive factors]
- [Improving market sentiment]

**12-18 months:**
- [Outcome of the optimistic scenario]
- [State achieved]
- [Sustainability assessment]

**Impact on economic indicators**:
[Assume better numbers than the Base Case]

**Upside catalysts**:
- [Factor that drives this scenario 1]
- [Factor that drives this scenario 2]

**Conditions that raise this scenario's probability**:
- [Condition 1]
- [Condition 2]
```

### Bear Case Template

```markdown
### Bear Case (XX% probability)

**Summary**:
[1-2 sentence summary of the risk scenario; what kind of downside materializes]

**Assumptions**:
- [Risk assumption 1]: [Specific condition]
- [Risk assumption 2]: [Specific condition]
- [Risk assumption 3]: [Specific condition]

**Timeline**:

**0-6 months:**
- [Negative development 1]
- [Negative development 2]
- [Expected adverse market reaction]

**6-12 months:**
- [Continuation / deepening of the downside trend]
- [Emergence of secondary problems]
- [Deteriorating market sentiment]

**12-18 months:**
- [Outcome of the risk scenario]
- [Worst-case state]
- [Path to recovery (if any)]

**Impact on economic indicators**:
[Assume worse numbers than the Base Case]

**Downside risk factors**:
- [Factor that triggers this scenario 1]
- [Factor that triggers this scenario 2]

**Conditions that raise this scenario's probability**:
- [Condition 1]
- [Condition 2]

**Mitigating factors**:
- [Factor that may soften this scenario 1]
- [Factor that may soften this scenario 2]
```

---

## Scenario Playbooks by Event Type

### 1. Monetary Policy Event (Rate Hike)

**Base Case (55%):**
- Rate hike delivered as expected
- Largely priced in by the market
- Mild equity weakness; modest rise in bond yields

**Bull Case (20%):**
- Smaller-than-expected hike
- Dovish forward guidance
- Equity rally

**Bear Case (25%):**
- Larger-than-expected hike
- Hawkish forward guidance
- Sharp equity sell-off; wider credit spreads

### 2. Geopolitical Event (Outbreak of Conflict)

**Base Case (50%):**
- Conflict expands only modestly
- Short-term commodity price rise
- Situation stabilizes within a few months

**Bull Case (15%):**
- Early ceasefire / peace agreement
- Commodity prices normalize
- Markets recover quickly

**Bear Case (35%):**
- Conflict prolongs or expands
- Significant disruption to commodity supply
- Accelerating global inflation; recession risk

### 3. Technology Shift (AI Regulation)

**Base Case (50%):**
- Gradual introduction of regulation
- Industry self-regulation predominates
- Limited impact on innovation

**Bull Case (25%):**
- Regulation written favorably for the industry
- Greater clarity actually accelerates investment
- Higher entry barriers favoring incumbents

**Bear Case (25%):**
- Strict regulation introduced
- Significant restrictions on AI development
- US firms lose competitiveness

### 4. Corporate Event (Large M&A)

**Base Case (60%):**
- Regulatory approval obtained
- Closing as scheduled
- Synergies realized in stages

**Bull Case (15%):**
- Synergies exceed expectations
- Smooth integration
- Follow-on M&A strategy succeeds

**Bear Case (25%):**
- Regulators block or impose conditions
- Integration delays / failure
- Synergies not achieved

---

## Scenario Quality Checklist

### Internal Consistency
- [ ] Are the assumptions in each scenario logically consistent?
- [ ] Are causal relationships in the timeline clear?
- [ ] Are the projected economic indicators internally consistent?

### External Validity
- [ ] Consistent with similar past events?
- [ ] Does it appropriately reflect the current market environment?
- [ ] Does it not diverge significantly from expert consensus?

### Practical Utility
- [ ] Specific enough to inform investment decisions?
- [ ] Are monitorable catalysts identified?
- [ ] Are invalidation signals clear?

### Coverage
- [ ] Are key risk scenarios included?
- [ ] Is upside potential adequately considered?
- [ ] Are tail risks mentioned?

---

## Common Mistakes and How to Avoid Them

### 1. Status-Quo Bias
**Problem**: Assigning excessive probability to the Base Case (70%+)
**Avoidance**: Recognize that historically, "nothing changing" has low probability

### 2. Recency Bias
**Problem**: Overweighting the impact of very recent events
**Avoidance**: Maintain a long-term perspective; refer to past patterns

### 3. Confirmation Bias
**Problem**: Adopting only interpretations that align with the headline
**Avoidance**: Deliberately seek opposing views

### 4. Overprecision
**Problem**: Forecasting 18-month figures to multiple decimal places
**Avoidance**: Acknowledge uncertainty; express in ranges

### 5. Overlapping Scenarios
**Problem**: Base / Bull / Bear partially overlap
**Avoidance**: Make the boundary conditions of each scenario explicit

---

## Probability-Update Guidelines

When new information arrives, adjust probabilities:

| Nature of new information | Probability adjustment |
|---------------------------|------------------------|
| Data supporting a scenario | +5-15% |
| Data contradicting a scenario | -5-15% |
| Decisive evidence | +20-30% or -20-30% |
| Emergence of a new risk factor | Bear Case +5-10% |
| Removal of a risk factor | Bear Case -5-10% |

**After any adjustment, always rebalance the total back to 100%**

---

## Output-Quality Standards

Hallmarks of a high-quality scenario:
1. **Specificity**: Includes numbers, dates, and names rather than abstractions
2. **Logic**: Causal relationships are clear
3. **Verifiability**: Correctness can be judged after the fact
4. **Practical utility**: Contains information directly relevant to investment decisions
5. **Humility**: Expresses uncertainty appropriately
