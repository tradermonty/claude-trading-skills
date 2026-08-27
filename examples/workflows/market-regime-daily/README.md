# Executable replay: `market-regime-daily`

This directory contains deterministic required-only and full-path replays for
[`market-regime-daily`](../../../workflows/market-regime-daily.yaml). The data is
fictional, fixed at `2026-01-15T13:08:00+00:00`, and is not investment advice.

## Evidence boundary

Steps 1–3 execute the native scorer and JSON report APIs for
`market-breadth-analyzer`, `uptrend-analyzer`, and (on the full path)
`market-top-detector`. They consume complete fictional component-score fixtures.
They do **not** execute provider fetches, individual component calculators, live
API calls, or live API failure paths. The manifests therefore label those steps
`native_api`; this is workflow handoff evidence, not full production verification
of each skill.

Those three skills do not expose a literal `INSUFFICIENT_EVIDENCE` artifact
contract. The replay uses the corresponding fail-closed rule: every canonical
component must be present, available, finite, within 0–100, fresh relative to
the fixed replay timestamp, and consistent with the other fixture dates.
Insufficient or stale component evidence stops before publication.

Step 4 runs the real `exposure-coach` CLI against the artifacts generated in the
same replay. Before invocation, every handoff is revalidated against a fresh
native scorer calculation. After invocation, the harness requires exactly one
JSON report and verifies its complete schema and decision values against the
native Exposure Coach API. Invalid JSON is not treated as a merely missing
optional signal.

## Variants

| Variant | Steps | Expected posture |
|---|---|---|
| `sample-run/` | breadth → uptrend → exposure | `REDUCE_ONLY`, `LOW` confidence; optional top-risk evidence is omitted |
| `sample-run-full-path/` | breadth → uptrend → top-risk → exposure | `NEW_ENTRY_ALLOWED`, `MEDIUM` confidence |

All output trees are generated transactionally. A malformed fixture, corrupt
handoff, native scorer/report exception, CLI failure, missing or multiple CLI
reports, or decision mismatch leaves any existing destination unchanged.

## Reproduce

From the repository root:

```bash
python3 scripts/workflow_replay.py run \
  --spec examples/workflows/market-regime-daily/replay.yaml \
  --variant required-only \
  --output-dir /tmp/market-regime-required

python3 scripts/workflow_replay.py run \
  --spec examples/workflows/market-regime-daily/replay.yaml \
  --variant full-path \
  --output-dir /tmp/market-regime-full

python3 scripts/workflow_replay.py check
```

The harness removes API-key, token, secret, password, and proxy environment
variables from the Exposure Coach subprocess. It supplies no provider or API
flags. This is an offline-input contract, not an operating-system network
sandbox.
