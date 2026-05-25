# Risk Review Checklist

## Purpose

This checklist gives the skill a risk-manager style review framework. It compares
actual actions with the user's own documented rules. It does not create financial
advice or decide whether a trade should be taken.

## Checks

| Check | Required Evidence | Warning | Critical |
|---|---|---|---|
| Per-trade risk | planned max R and actual R | actual > planned by <=25% | actual > planned by >25% |
| Portfolio heat | max heat and actual heat | actual near max | actual > max |
| Weekly loss limit | max weekly loss and current weekly loss | within 10% of limit | breached limit |
| Consecutive losses | count and threshold | near threshold | at/above threshold |
| Regime gate | market regime and allowed trade types | unclear gate | trade taken against restrictive/cash-priority gate |
| Stop discipline | planned stop and actual stop changes | unclear stop change | unplanned stop move |
| Adds/trims | original add/trim rules | discretionary add/trim unclear | add to loser or add without plan |
| Correlation cluster | holdings and sector/theme exposure | concentrated exposure | new trade increases high-risk cluster |

## Severity Guidance

`info`: observation only. No rule concern.

`warning`: possible issue or incomplete evidence. Human should review.

`critical`: explicit user rule violation or repeated pattern. Should produce
`RULE_VIOLATION` or `COOL_DOWN` depending on recurrence.

## Risk Manager Language

Use objective rule language:

- Good: "Actual risk was 1.8R versus a stated max of 1.0R."
- Bad: "This was a stupid trade."
- Good: "This is a rule-adherence issue, not proof that the setup had no edge."
- Bad: "Never trade this pattern again."

## Incomplete Data

If a risk plan is missing:

- mark risk findings as `unclear`
- ask for the missing risk plan
- avoid claiming a rule violation
- still flag actual risk values if they are present
