# Issue #514: monthly coach decision handoff (preparation slice)

## Selection and boundary

Live queue: PRs #581, #582, #583 are draft, CLEAN, 89 checks pass and one
scheduled link check skipped each, no changes requested or review comments.
Dependabot #577/#578 excluded from queue/conflict decisions.

Evaluated candidates in order: #332, #495, #496, #297, #298 skipped because
existing local branches/worktrees already implement those issues; #524 skipped
because its acceptance needs a maintainer tag ruleset; #523 skipped because its
remote branch exists; #515 skipped because its local branch/worktree exists.
#514 selected: no matching local/live remote branch or worktree, no overlap with
existing non-Dependabot PR files. #513 was read for context but not selected.
Root checkout is on another branch and remains untouched; use an isolated
origin/main worktree. No existing worktree is reused or removed.

This PR repairs the first proposed step only. It does not complete #514:
approved-rule ledger, effective/expiry/supersession handling, pre-trade display,
and subsequent adherence review remain future work. Use **Refs #514**, keep the
issue open, and verify `closingIssuesReferences: []` after draft PR creation.

## Implementation plan

1. Declare all three optional coach artifacts as step 6 inputs in the monthly
   workflow. Explain that final human approval records accept/modify/defer/
   journal-only decisions; proposal text alone never activates a rule.
2. In the offline replay, retain source review ID with the coach decision and
   validate its action, rule list, notes, uniqueness, and action/list semantics:
   accept/modify require rules; defer/journal-only must not contain accepted rules.
   accept_rules must be an exact subset of native next_session_operating_rules;
   changed text uses modify_rules. Correct the existing fixture to modify_rules.
   Match source_review_id against the report and behavior artifact at step 6.
3. Step 6 accepts either the complete coach artifact group or none (coach skipped).
   Validate source review consistency, preserve the exact human decision in both
   final artifacts, and record hashes of all consumed coach artifacts. A missing
   handoff or stale review ID fails before publishing. Keep required-only behavior
   explicit with a null coach decision. Existing human_approved must be true. This final approval ratifies the
   separate coach_rule_decision; trade_rule_changes remain independent manual
   postmortem suggestions. Neither artifact is an active-rule ledger.
4. Add meaningful regression tests for full-path propagation and hashes, skipped
   coach, all four actions, invalid/duplicate/empty rules, stale review IDs,
   incomplete handoff (including direct step-6 tests), and atomic failure. Update replay goldens and generated
   workflow docs, plus example documentation explaining offline/manual limits.
5. Run targeted monthly/general replay and workflow/example contract tests;
   ruff check/format; all requested metadata/docs/workflow/snapshot checks;
   full suite as appropriate for shared replay changes; pre-commit and diff check.
   No skill source/package changes are planned.

## Review and completion

Plan review round 1: require accept_rules to be a native proposal subset; use
modify_rules for rewritten text; explicitly distinguish final approval from rule
activation. Plan review round 2: approved, no further findings. Final plan above. Implementation review round 1: approved, no actionable findings. Address all actionable findings before committing. Create
one draft PR only; no merge. Record actual checks and review rounds in PR body.


## Validation record

- Targeted monthly/general replay and workflow example tests: 143 passed
  (existing repository Python 3.12 environment).
- Workflow replay check: all 12 workflows / 24 variants match golden outputs.
- Ruff lint and format, all package drift checks, catalog/skill/workflow/skillset
  docs drift checks, strict index/workflow validation, skillsets and navigator
  snapshot checks, pre-commit all-files and diff whitespace checks: passed.
- Python 3.9 attempt reached existing replay code that uses
  `Path.write_text(newline=...)`, unsupported by Python 3.9; used the supported
  shared development Python 3.12 environment instead (no standalone skill edits).
- Initial full-suite attempts were blocked by sandbox uv-cache permissions,
  then dependency-fetch DNS restrictions; existing environment full pytest also
  lacked Pillow at collection. Standard suite re-run uses this isolated worktree
  and a temporary uv cache with network access: **75/75 rows passed**,
  10,678 tests passed, 5 skipped. No allowed-failure rows were needed.

No broker/API writes, tags/releases, merge, or issue closure performed.
