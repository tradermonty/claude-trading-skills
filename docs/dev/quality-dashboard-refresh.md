# Quality dashboard evidence refresh (#298)

The offline generator `scripts/generate_quality_dashboard.py` reads the committed
snapshot. `--check` tests reproducibility against that snapshot; it does not prove
that the inputs are current. A deterministic fingerprint binds static catalog
provenance to the index, policy, replay inventory and test-presence inputs. When
those inputs change, static attribution becomes unknown until a refresh; stored
historical measurements retain their separate provenance. Both dashboard pages display each measured input's
commit, time and source independently of the collection time.

## Refresh locally

With the locked development environment and authenticated read access to this
repository's Actions artifacts and issues:

```sh
uv run --locked --no-sync python scripts/refresh_quality_dashboard.py
uv run --locked --no-sync python scripts/generate_quality_dashboard.py
uv run --locked --no-sync python scripts/generate_quality_dashboard.py --check
```

The collector makes read-only GitHub API requests with `gh api`. It writes the
snapshot only after collection succeeds. API failures fail the command and leave
the old snapshot and pages untouched. Missing or expired coverage artifacts
produce unknown coverage in the new snapshot, without carrying old values forward.
The generator itself needs no network access.

Coverage is from `executable-code-coverage-report` on the latest successful
**main push** run of `ci.yml`, not necessarily the checked-out commit. The artifact
run ID and SHA are checked before its whitelisted JSON member is read. An older
CI commit remains visible as older evidence. The run update timestamp is reported
as such, not as an exact test completion timestamp.

The high-severity count uses open issues with `[P0]`/`[P1]` in their title or a
`P0`, `P1`, `priority:p0`, or `priority:p1` label, excluding PRs. This repository-wide
proxy does not clear a specific skill for release. Verification totals summarize
the catalog declarations; collecting them does not re-run skill audits.

Beta start dates, dual-axis score distribution, drift checks, executed smoke
counts and successful live-data sample time remain unmeasured until attributable
sources are wired in. Replay inventory describes configured coverage, not an
executed smoke count. Green CI does not prove that a report-only live probe ran.

## Weekly update proposals

`quality-dashboard-refresh.yml` runs weekly and on manual dispatch. It validates
the collector and generator, refreshes the snapshot, regenerates both languages,
checks deterministic drift and docs source links, and uploads the three proposed
files as `quality-dashboard-refresh` (30-day retention). It opens a PR from a
unique `automation/quality-dashboard-<run>-<attempt>` branch. If an automation PR
is already open, it retains the new artifact and skips creating another PR; merge
or close the pending PR before the next update. Branches are never force-pushed.

The job needs Actions read, contents write and pull-requests write. In repository
Settings → Actions → General, **Allow GitHub Actions to create and approve pull
requests** must be enabled for PR creation. If repository policy denies it, the
`gh pr create` step fails visibly; the uploaded evidence remains available. The
workflow does not approve or merge PRs.

`GITHUB_TOKEN`-created PRs do not normally trigger the other PR workflows. The
refresh workflow runs its own focused checks; a reviewer must arrange remaining
required checks before merging. Pages is configured to build legacy `main:/docs`;
a reviewed merge changes that source. This change does not verify a Pages deploy.

Issue #298's unknown metrics stay visible. Related #495/#496 sources are consumed
without modifying their clients, index declarations, or baseline evidence.
