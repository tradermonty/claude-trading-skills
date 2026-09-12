# Platform support

The versioned source of truth is
[`config/platform-compatibility.yaml`](../../config/platform-compatibility.yaml).
Contributor tooling requires CPython `>=3.9,<3.15` and recognizes Linux,
Windows, and macOS. CPython 3.10, 3.11, and 3.12 are inside the installable
range but are best-effort because the boundary matrix does not run them
continuously. PyPy and Python 3.8 or 3.15+ are unsupported and fail the runtime
check with an explicit message.

Run the local checks from the repository root:

```console
python scripts/check_platform_compatibility.py check
python scripts/check_platform_compatibility.py probe
python scripts/check_platform_compatibility.py validate
```

## Continuously tested rows

The `pull_request` profile is the fast merge gate. The scheduled and manually
dispatchable `nightly` profile is the complete supported boundary/regression
matrix. The nightly profile must contain every configured row; the validator
rejects policy drift.

| Row ID | Runner | Python | pull_request | nightly | Purpose |
| --- | --- | --- | :---: | :---: | --- |
| `ubuntu-py39` | `ubuntu-latest` | 3.9 | yes | yes | Minimum supported Python |
| `ubuntu-py314` | `ubuntu-latest` | 3.14 | yes | yes | Latest supported Python |
| `windows-py313` | `windows-latest` | 3.13 | yes | yes | Exact #311 standalone regression axis |
| `windows-py314` | `windows-latest` | 3.14 | no | yes | Latest Windows boundary |
| `macos-py314` | `macos-latest` | 3.14 | no | yes | Latest macOS boundary |

Each row runs selected critical package, state, risk, routing, path, encoding,
and subprocess contracts. The full dynamically discovered skill suite remains
on the primary Ubuntu/Python 3.9 axis; CI intentionally does not multiply every
skill suite across every OS.

The Windows rows include the actual regressions behind #64 and #311: UTF-8
macro-regime Markdown output, packaged dependency failure, and fail-closed
consumption of a 0/6 macro report by exposure-coach.

## Shell and automation boundaries

- `python scripts/run_all_tests.py` is the cross-platform per-skill test-matrix
  runner. `scripts/run_all_tests.sh` is only a POSIX convenience wrapper.
- `scripts/run_skill_generation.sh` and `scripts/run_skill_improvement.sh` are
  guarded macOS `launchd` wrappers. On Linux or Windows, use the Python
  orchestrators documented in [Skill Automation Quickstart](skill-automation.md).
- Run `run_skill_improvement_loop.py` directly only from an isolated clean
  checkout. Direct execution does not reproduce the wrapper's checkout reset,
  ignored-state preservation, or log/report links.
