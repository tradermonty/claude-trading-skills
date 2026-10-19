# Issue #579: Correct unaffordable-contract guidance

## Selection and queue evidence

- Existing non-Dependabot PR #574: CLEAN, 89 checks passed; only the scheduled external link check skipped. No requested changes; its dashboard review finding is fixed at e0bafada. Planned files do not overlap.
- Evaluated candidates, in order: #332 (P0), #495, #496, #298, #297 (P1), then #579 (incorrect risk guidance). The first five have pre-existing local/remote Issue branches and worktrees and are skipped without modification or reuse.
- #579 has no pre-existing local/remote Issue branch or worktree. Create an isolated worktree from origin/main aec21a0 because the root checkout is on another branch. Preserve unrelated work.

## Final plan

1. Correct the two source guidance paragraphs in SKILL.md and references/sizing-methodology.md. Explain why widening a stop increases risk per contract; retain the setup-defined stop rather than changing it to fit the account.
2. Offer a smaller contract with its own symbol and correct multiplier/tick/currency inputs, a deliberate risk-policy reassessment, or no trade. Retain the mode-B same-symbol READY_FOR_PLAN gate and distinguish the CLI risk cap from a recommendation.
3. Regenerate the generator-owned English guide; manually synchronize the protected Japanese guide. Rebuild only the futures-position-sizer package. Do not change arithmetic or runtime behavior.
4. Run the Python 3.9 skill tests, scoped Ruff lint/format, package parity, repository generated/static validators, pre-commit all-files and diff checks. For this documentation/package-only change, leave the full repository test matrix to GitHub CI; skip only the local pre-push full-matrix hook if needed and disclose it.
5. Obtain independent implementation review (at most three rounds), resolve findings, commit and create one draft PR with Closes #579. Verify closing references, Issue state, draft state and CI. Do not merge.

## Independent review

- Plan review: 1 round, approved. Incorporated the concrete smaller-symbol/gate requirements and EN/JA ownership distinction before implementation.
- Implementation review: 1 round, approved with no findings. Reviewer independently checked the two packaged sources byte-for-byte, EN/JA parity and symbol/gate requirements.

## Validation

- Python 3.9 futures-position-sizer suite: 212 passed.
- Scoped Ruff lint and format checks passed (five Python files).
- Package source parity, catalog, generated skill docs, strict index/workflow metadata, skillsets, workflow docs, skillset docs and navigator snapshot checks passed.
- git diff --check passed. Full repository pytest is reserved for GitHub CI for this documentation-only change; the local full-matrix pre-push hook will be skipped.

- pre-commit run --all-files: all hooks passed.
