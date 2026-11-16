# Two-week rule experiment

Use the approved-rule ledger to observe one rule for 14 calendar days in America/New_York. Before the first occasion, define a condition you can check from information available at decision time. For example, a fictional rule about declining a breakout above the written entry range applies whenever a candidate reaches entry review above that range. Keep the condition and date window fixed.

From the repository root, use `manage_approved_rules.py list` to get a rule ID. Substitute it for `<rule-id>` in the command below. Use a fresh private directory for each experiment.

```bash
(
  umask 077
  set -C
  mkdir -p state/rules/experiment
  python3 skills/pre-trade-discipline-gate/scripts/review_rule_experiment.py start \
    --rule-id '<rule-id>' \
    --applicable-when 'A candidate reaches entry review above the written range.' \
    > state/rules/experiment/plan.json
)
```

Use the plan only if `start` exits successfully. It requires the rule to apply on the start date and through the final day. A rule awaiting review still applies according to the ledger. For a separate ledger, put `--ledger PATH` before `start` or `review`.

Create a separate `observations.json` containing an array like this fictional example. Use the experiment's New York dates.

```json
[
  {
    "occasion_id": "fictional-1",
    "date": "2026-06-02",
    "decision": "pass",
    "assessment": "followed",
    "session": "open",
    "evidence_ref": "fictional-decision-1"
  }
]
```

- Record each distinct occasion once. Use `enter`, `wait`, or `pass` for the user's confirmed decision.
- Use `followed` or `exception` when you can assess an applicable occasion. Use `not_applicable` when the condition did not apply, and `unassessed` if evidence is insufficient to classify it. A compliant pass counts as `followed`.
- Use `open`, `mid_session`, `close`, or `other` for the context. `evidence_ref` is an opaque local ID for the recorded decision and any supporting pre-trade check. The command validates the record shape and counts the assessments. The user supplies and checks the underlying evidence. A `GO` check alone only describes the pre-trade assessment.

```bash
python3 skills/pre-trade-discipline-gate/scripts/review_rule_experiment.py review \
  --plan state/rules/experiment/plan.json \
  --observations state/rules/experiment/observations.json \
  > state/rules/experiment/summary.json
```

On success, the summary identifies the approved rule and its review date, reports the total recorded and applicable samples, and groups exceptions by session. The rate is available only after the last day, with at least 10 assessed applicable occasions and zero unassessed occasions. This threshold is a reporting convention. The denominator covers the occasions you recorded. Unrecorded decisions are outside its coverage.

A changed ledger entry invalidates the plan, including an extension or a retirement followed by restoration. Keep the old observations for manual review and start a fresh plan if needed. The rule fingerprint detects changes to the ledger entry. Keep the plan separate from the working observation log to preserve the original dates and condition.

At the next monthly review, bring the summary as local evidence for keeping, modifying, or retiring the rule. The review date from the ledger lets you match it to the correct review. The existing approval process controls any rule update. The experiment uses self-reported decisions and measures adherence to a rule, independently of trade outcomes.
