# Supported OS / Python Compatibility Matrix

**Source of truth.** This document is the canonical statement of which operating systems and
Python versions this repository supports, and how that promise is enforced. It was added by
[issue #333](https://github.com/tradermonty/claude-trading-skills/issues/333).

The rule of thumb is **"supported = CI-enforced."** A combination is *supported* only if the
project's CI actively exercises it on a runner. Combinations that are declared but **not**
CI-tested are called *best-effort* and are kept deliberately distinct so no one reads best-effort
as equivalent to supported.

## Runtime promise

`pyproject.toml` declares:

```toml
requires-python = ">=3.9,<3.14"
```

Python **3.9** is the floor and **3.13** is the ceiling. The upper bound is intentional: it makes
the promise closed rather than open-ended, so a future 3.14 cannot silently ship as "supported"
without the CI matrix being extended first.

## Supported (CI-enforced)

Actively tested in CI:

| OS | Python | Where |
|----|--------|-------|
| Linux (`ubuntu-latest`) | 3.9 | existing `test` / `coverage` / `workflow-replay` / `market-calendar-compat` jobs |
| Linux (`ubuntu-latest`) | 3.11 | existing `lint` / `metadata` / `security` / `supply-chain` jobs |
| Linux (`ubuntu-latest`) | 3.13 | `compat-smoke` (PR) |
| Windows (`windows-latest`) | 3.13 | `compat-smoke` (PR) |
| Windows (`windows-latest`) | 3.9 | `compat-nightly` (daily) |
| macOS (`macos-latest`) | 3.13 | `compat-smoke` (PR) |
| macOS (`macos-latest`) | 3.9 | `compat-nightly` (daily) |

The macOS runner uses the `macos-latest` label. `actions/setup-python` provisions the requested
Python version independently of the base runner image, so the 3.9 leg is available on that label.

## Best-effort (NOT CI-enforced)

Any combination whose Python version satisfies `>=3.9,<3.14` on
`ubuntu-latest` / `windows-latest` / `macos-latest`, **except** the CI-enforced rows above.

Defined as the set-complement of the supported rows, so the two tiers never overlap. Nothing in
this tier is claimed to "just work" — it is simply not ruled out at the package level.

## Policy

Every job in `.github/workflows/ci.yml` and `.github/workflows/compat-nightly.yml` must satisfy
the following (validated statically by `scripts/check_compat_matrix.py`):

1. Its OS is in `{ubuntu-latest, windows-latest, macos-latest}`.
2. Its Python version (where a `actions/setup-python` step is present) is in `[3.9, 3.14)`.

`dependency-review` is a third-party-action job with no `setup-python` step, so it is OS-checked
only. `fmp-contract-canary.yml` and `packaged-deps-nightly.yml` are separate targeted workflows and
are explicitly **out of scope** for this drift guard.

## Job → (os, python) mapping

The compatibility-defining jobs are declared here and must match the actual workflow YAML:

```yaml
compat_matrix:
  python: ">=3.9,<3.14"
  supported_os: [ubuntu-latest, windows-latest, macos-latest]
  jobs:
    compat-smoke:
      os: [ubuntu-latest, windows-latest, macos-latest]
      python: ["3.13"]
    compat-nightly:
      os: [windows-latest, macos-latest]
      python: ["3.9"]
```

`scripts/check_compat_matrix.py` parses this block and compares it to the axis sets it infers from
`ci.yml` / `compat-nightly.yml`. Workflow environments are **not** (and cannot be) exercised by the
static checker.

## Enforcement scope

The issue title asks to *define and enforce* the matrix. Enforcement here is static and has two
parts:

1. **A drift guard** (`scripts/check_compat_matrix.py`, run in the `metadata` CI job and as a
   pre-commit hook) that fails a change if the documented matrix diverges from the workflow YAML, or
   if any workflow job leaves the supported OS set / Python range.
2. **Declaring only supported combinations** in the workflow itself.

A *runtime* rejection of "this unsupported combination reached a runner" is **out of scope** for a
static checker: a static tool cannot observe the live runner. This is a deliberate, documented
reduction so the gap between "enforce" and the current implementation is explicit.

## Why this matrix

Two past failure classes motivated bounding the promise and testing cross-platform:

- **#64** — a Windows default-encoding Markdown failure that would not have surfaced if the suite
  had run on a Windows runner.
- **#311** — a standalone dependency gap discovered by running the risk/state/navigator skills
  outside the main project venv.

The cross-platform jobs (`compat-smoke`, `compat-nightly`) exercise the compatibility-sensitive
suites — `position-sizer`, `futures-position-sizer`, `trader-memory-core`,
`drawdown-circuit-breaker`, `trading-skills-navigator` — plus the UTF-8 / path / line-ending /
temp-dir / subprocess-quoting regressions in `scripts/tests/test_compat_regressions.py`, so these
classes no longer ship silently.

## Verification record

Local verification on a macOS (aarch64) host, using `uv sync --locked`:

- Python 3.9: resolves the locked environment successfully (`scipy==1.13.1`, `statsmodels==0.14.6`).
- Python 3.13: resolves the locked environment successfully (`scipy==1.17.1`, `statsmodels==0.14.6`).
- Result: the `>=3.9,<3.14` range is viable for `--extra dev --extra ci` on this machine.

Windows and macOS runner outcomes are validated by the PR's GitHub Actions; they cannot be
reproduced locally from a macOS host.
