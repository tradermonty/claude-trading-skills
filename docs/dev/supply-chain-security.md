# PR dependency integrity

Issue #334 adds three complementary checks to pull requests:

- CI orchestration and tests use `uv sync --locked --no-install-project
  --extra dev --extra ci`. A stale `uv.lock` fails instead of being rewritten.
  The scripts-only project itself is not installed, avoiding an independently
  resolved setuptools build environment. Matrix-specific requirements are
  checked against installed versions instead of installed again.
- The full-lock audit queries PyPI advisories for every registry package/version
  in `uv.lock`, including alternative Python/platform resolutions. All known
  vulnerabilities are blocking regardless of severity. Auditing uses exact pins
  and disables pip resolution; packages are not installed by the scanner.
- GitHub Dependency Review blocks newly introduced vulnerabilities at severity
  `low` or higher, across all dependency scopes. It uses read-only permissions
  and does not post PR comments. It is independent of the full-lock audit.

The standalone market-calendar and nightly packaged-dependency smoke tests still
install their own `requirements.txt` into fresh environments. They intentionally
test the published standalone dependency ranges, not the root project's locked
environment. Their install results are compatibility evidence, not lockfile
reproducibility evidence. Release checksums and SBOMs remain outside this change.

## Audit and exceptions

Run from the repository root with the locked Python 3.11 environment:

```sh
uv sync --locked --no-install-project --extra dev --extra ci --python 3.11
uv run --no-sync python scripts/check_supply_chain.py check
uv run --no-sync python scripts/check_supply_chain.py audit --report supply-chain-audit.json
```

`check` is offline. `audit` calls the advisory service but needs no credentials.
The audit covers each marker alternative by splitting packages into batches
with at most one version per normalized name. It verifies the exact report
inventory; skipped packages, missing reports and scanner/service errors fail.
The JSON report is uploaded by CI even when the audit fails.

`config/security-exceptions.json` records seven exact advisory exceptions for
five existing Python 3.9 dependency versions: curl-cffi 0.13.0, filelock 3.19.1,
pytest 8.4.2, requests 2.32.5 and urllib3 2.6.3. Their first patched releases
require Python >=3.10 (verified against PyPI release metadata on 2026-09-06).
All expire on **2026-10-06**, are owned by `tradermonty`, and track the compatibility
decision in #333. These remain known vulnerabilities; a passing policy result
does not mean the lockfile is vulnerability-free. Compatible resolutions are
upgraded rather than exempted.

A vulnerability exception must identify an exact package, version and advisory, plus its owner,
reason and expiry. Expiry is evaluated against the UTC date; an exception expires
at the start of its expiry date. Malformed, duplicate, unknown or expired entries
fail the offline check. An advisory alias is accepted only for the same exact
package and version.

### Approaching-expiry diagnostics

Both `check` and `audit` evaluate all exception entries against one captured UTC
date. Starting **14 days before expiry**, each affected entry is printed to
stderr with its package/version, advisory, owner, UTC expiry date and remaining
days. The inclusive thresholds are:

| Days remaining | Status | Policy behavior |
|---|---|---|
| More than 14 | `active` | No expiry warning |
| 8 through 14 | `warning` | Warn; exception remains valid |
| 1 through 7 | `urgent` | Warn; exception remains valid |
| 0 or fewer | `expired` | Fail with exit 1; do not run the advisory scanner |

For an expiry date of October 6, warning begins September 22, urgency begins
September 29, and the exception becomes invalid at **October 6 00:00 UTC**.
Expiry status describes the exception deadline, not vulnerability severity or
whether a dependency is safe.

When `audit` runs, its JSON report includes `exception_expiry` with
`schema_version: 1`, `evaluated_on` (UTC date), the most urgent overall `status`,
and an `exceptions` array. Each row contains `package`, `version`, `advisory`,
`owner`, `expires_on`, `days_remaining` and `status`. Rows sort by expiry date,
normalized package name, exact version and advisory; separate advisories for the
same package/version remain separate rows. An empty policy produces an empty
array and `active` status. This block is present on successful scans, blocked
vulnerability results and scanner errors; inspect the existing `errors` and
`blocked` fields as well as the command exit code for the actual audit result.

A direct `audit` invocation with an expired policy writes a failure report with
`exception_expiry` and `errors`, exits 1, and performs no scanner calls. Invalid
policy structure also produces an error report, without partial expiry entries.
The output replaces any previous report at `--report`; a report-write failure
is reported on stderr and returns exit 1.

In CI, `check` runs **before** `audit`. Approaching-expiry reports are included in
the existing audit artifact when the audit step runs. On or after expiry,
`check` fails first and the audit step is skipped: the CI log contains the
expiry diagnostics, but no new audit JSON artifact is guaranteed in that case.
These are per-invocation diagnostics; they do not add a scheduled notification.

This implements only the reporting part of **#387**. The reviewed supported-Python
and dependency remediation decision, lockfile remediation, full-lock audit and
affected standalone/compatibility validation remain open work. No deadlines are
extended or exceptions renewed by this reporting feature.

These exceptions can document existing debt for the full-lock audit. They never
populate GitHub's global `allow-ghsas` setting: a PR introducing a vulnerability
remains blocked by Dependency Review even if a full-lock exception exists.
Prefer upgrading a vulnerable dependency over adding an exception. Changes to
exception policy are ordinary reviewed source changes, not automatic approvals.

No new license-denial policy is imposed here. Dependency Review's license check
is disabled, and license exceptions are unsupported. A passing result therefore
does not assert license compliance.

## Actions and updates

Remote Actions and reusable workflows use full commit SHAs, with version
comments for readability. The offline checker also inspects local action
definitions. Docker actions must use a SHA-256 digest. Workflow tokens default
to `contents: read`; this change does not alter branch-protection settings.

Weekly Dependabot updates cover the root `uv` project, GitHub Actions and
`docs/Gemfile` (Bundler). Dependency updates are proposed as PRs, never auto-merged.
The setup-uv Action and the uv executable version are both fixed explicitly.

## References

- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [pip-audit CLI and advisory behavior](https://github.com/pypa/pip-audit)
- [Dependency Review configuration](https://github.com/actions/dependency-review-action)
- [Dependabot supported ecosystems](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories)
