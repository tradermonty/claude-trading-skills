# Coverage waiver expiry notifications

The daily `coverage-waiver-expiry.yml` workflow reports coverage waivers (including
the aggregate waiver) and allowed test failures from `config/ci-test-policy.yaml`.
It maintains one active GitHub Actions bot comment on Issue #523 and mentions the repository
owner when an exception is within 14 days of expiry, including day 14 and day 0.
Expiry day remains valid; an exception becomes expired the following UTC day.
The existing CI policy remains fail-closed and is not relaxed by this monitor.

The monitor validates the policy with the canonical loader using `date.min` solely
to allow inspection of already-expired entries, then evaluates status using today's
UTC date. Malformed policies and GitHub API failures fail the workflow; they are
never interpreted as a clean report. The JSON artifact records the observation date,
each expiry, remaining days and status. Invalid policies produce no new artifact.

The managed comment uses a stable marker and bot author, paginates existing
comments, and suppresses unchanged alerts. A daily countdown does not trigger an
update. A new alert identity (kind, ID, expiry date, tracking issue) or a transition
from EXPIRING to EXPIRED retires the active comment with a distinct superseded
marker, then posts a fresh owner mention. Superseded comments remain as history
without an owner mention. Wording, row order, removals and recovery only PATCH the
active comment. This avoids relying on edited mentions to trigger notifications.
If retiring the comment fails, no POST occurs. If the subsequent POST fails, the
workflow fails and the next run retries creation because no active comment remains.
Multiple active managed comments still require manual reconciliation.
Concurrency serializes scheduled and manual runs. Recovery updates an existing
comment without creating a new comment when no alert has ever occurred.

This workflow runs only on `main` in the upstream repository, with contents read
and issues write permissions. It has no pull-request trigger. Notifications become
effective only after merge to the default branch; this PR does not demonstrate
live notification delivery. A maintainer can then run it manually and inspect the
Actions result, artifact and Issue #523 comment. GitHub scheduling can be delayed
or disabled, so maintainers should also monitor workflow failures and inactivity.

To generate the offline report without GitHub access:

```bash
python3 scripts/check_coverage_waiver_expiry.py --output /tmp/coverage-waiver-expiry.json
```

`--notify OWNER/REPO` explicitly opts into writing the tracking comment. Do not
use that option for local validation. Issue #523 stays open: the remaining waivers still
need individual coverage improvements or justified renewals, and delivery needs
verification after merge. This notification slice does not claim those are done.
