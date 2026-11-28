# Scoped type checking (mypy)

Issue #503. CI runs a blocking, non-strict `mypy` step in the lint job. The
configuration lives in `[tool.mypy]` in `pyproject.toml`; run it locally with:

```bash
uv run mypy
```

## Scope

`files` in `[tool.mypy]` lists the checked paths:

- `scripts/fmp_client/`
- `scripts/market_calendar/`
- `skills/trader-memory-core/scripts/`
- `skills/position-sizer/scripts/`

Tests (`tests/`, `test_*.py`, `conftest.py`) are excluded. Two further exclusions
have reasons recorded next to them in `pyproject.toml`:

- `thesis_store_parts/*.py` are source fragments exec'd into the `thesis_store`
  namespace, so they cannot be checked as standalone modules. `thesis_store`,
  `thesis_review` and `thesis_ingest` disable only `attr-defined`, because the
  fragment-defined names are invisible to mypy.
- `skills/trader-memory-core/scripts/fmp_client.py` is generated; fix its source
  in `scripts/fmp_client/` instead.

## Expanding the scope

1. Append the path to `files` in `[tool.mypy]`.
2. Run `uv run mypy` and fix the findings with real annotations or narrowing.
3. Use a targeted `# type: ignore[code]  # reason` only when a real fix is
   disproportionate. Do not add blanket `ignore_errors` overrides.
4. If the new path is a skill's `scripts/` directory, add it to `mypy_path` when
   its modules import each other by bare name.
