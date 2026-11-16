# Offline environment doctor

From the repository root, run:

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --json
```

The command uses the standard library and works before project dependencies are
installed. Python 3.9 can run the diagnostic, but the repository development
environment requires the range in `config/python-support.json`. Standalone
skill support is a separate policy. On Python 3.9/3.10 without `tomli`, dependency
inspection is reported as unknown. Python 3.11+ has a built-in TOML parser.
The script also works from another directory when invoked by its full path.

Each check reports `ok`, `warning`, or `unknown`, with a repair hint where needed.
Normal diagnostics exit **0 even with warnings**; this is an onboarding aid,
not a CI readiness gate. Invalid CLI arguments still exit nonzero.

The doctor checks:

- Python version against the repository policy.
- Presence of installed distributions named in `pyproject.toml`'s required
  dependencies, and of `pre-commit`, in the current interpreter's environment.
- Nonblank environment variables `FMP_API_KEY`, `FINVIZ_API_KEY`, and the pair
  `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`. Only presence is reported.

To prepare the development environment, use a supported Python version and run
`uv sync --locked --extra dev`, then `uv run python scripts/doctor.py` to inspect
that environment. The doctor itself does not install anything.

No network connections are made, `.env` files are not loaded, and credential
values are never printed. A present key may be invalid; installed distributions
may have incompatible versions or fail to import. Public-data access, broker
connectivity, pre-commit hook installation and skillset readiness are not tested.
Only simple named dependency requirements are inspected; unsupported requirement
syntax is reported as unknown without echoing its contents.

The Python range check supports the canonical patch-level minimum (for example,
`>=3.11.5,<3.14`), as well as two-component bounds, and displays the evaluated
patch version. A malformed or reversed policy remains `unknown`; no raw policy
contents are echoed in that diagnostic.

This implements the offline diagnostic portion of Issue #301. Continue with the
[EN offline quickstart](../en/offline-quickstart.md)
([日本語](../ja/offline-quickstart.md)) for the tested fictional demo and
three-question routing guide. Provider connectivity, per-skillset readiness and
one-command skillset installation remain outside this offline path.
