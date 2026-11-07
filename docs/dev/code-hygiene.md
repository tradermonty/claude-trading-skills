# Code Hygiene

## Code hygiene budget

Ruff enforces B904 (explicit exception context), B007 (unused loop variables),
B017 (specific expected exceptions), and C901. The current complexity ceiling
is 128, matching the existing maximum; it prevents growth rather than certifying
that existing complex functions are maintainable. Lower `max-complexity` in
`pyproject.toml` as those functions are simplified. The policy regression rejects
increases above 128 and global/per-file suppression of these rules.

Pytest loads `scripts.pytest_firstparty_warnings` through the shared `addopts`,
including each canonical CI matrix row. Unexpected `DeprecationWarning` instances
attributed to production files under `skills/` or `scripts/` fail the session and
appear in a dedicated terminal summary. Classification uses source filenames so
flat skill imports are covered. Warnings from dependencies and test fixtures
remain visible; explicitly expected warnings captured with `pytest.warns` remain
valid. Keep the normal pytest warnings plugin enabled for this audit.
