# Quality dashboard publication recovery

The weekly `.github/workflows/quality-dashboard-refresh.yml` collects and uploads
proposed dashboard evidence before trying to open a review PR. Publication runs
through `scripts/propose_quality_dashboard.sh`. Its offline tests use temporary
local Git remotes and a fake GitHub CLI; they never contact GitHub.

The script exits successfully when a dashboard PR is already open or the three
tracked dashboard files have no changes. Otherwise it creates only the numeric
run/attempt branch `automation/quality-dashboard-<run-id>-<attempt>`. Existing
local or remote refs are rejected. A create-only ref lease also protects against
a branch appearing between the check and push. Only the snapshot and the EN/JA
dashboard pages enter the commit, even if other paths were already staged.

If either push or PR creation fails, recovery queries PRs for that exact head in
all states. A lost response may have created the branch or PR successfully.
Recovery preserves the branch if any PR references it or the query cannot be
trusted. Otherwise a delete with a lease to the committed SHA removes only that
run's ref. A concurrently advanced ref or a denied deletion is preserved and
reported in the Actions summary. A network error or cancellation can also prevent
recovery; inspect the exact ref before any manual action. Recovery always retains
a failed exit status. The uploaded evidence remains available for 30 days.

## Maintainer prerequisites and remaining acceptance

Issue #609 remains open. A code-only change cannot configure PR creation rights
or prove that the next scheduled run succeeds. No settings, secrets, historical
remote refs, releases, or scheduled dispatches are changed by this remediation.

Before expecting publication to succeed, a maintainer must configure an approved
PR creation path: allow GitHub Actions to create PRs, or separately configure an
approved GitHub App token with the required repository access. The current
workflow uses `github.token` for both checkout credentials and `GH_TOKEN`.
Do not replace only one of these if using an alternative identity. Treat token
configuration as a separate reviewed change; never place a token in source.
There is no mandatory permissions-API preflight, because reading repository
Actions permission settings requires administration access that the scheduled
workflow token may lack.

PRs created with `GITHUB_TOKEN` normally do not trigger other workflows. The
refresh workflow runs collector/generator/publication tests, lint, drift and docs
source checks before publication. Remaining required checks and human review are
still needed before merge.

After a failed run, use its summary to find the exact retained branch. Review
both open and closed PR references and the current remote SHA before deciding
whether to delete it. Historical branches need separate maintainer approval;
this script never sweeps the `automation/quality-dashboard-*` namespace. On the
2026-11-04 read-only audit, three historical run branches existed (runs
39286940300, 40357719555, and 41512810909). This is a snapshot, not permission to
delete those refs. The next scheduled run, historical cleanup, and configured
publication permission must be checked separately to close #609.
