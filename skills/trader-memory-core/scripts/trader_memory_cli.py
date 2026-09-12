#!/usr/bin/env python3
"""Stdlib-only launcher for the trader-memory-core CLI scripts.

Resolves a usable Python environment for ``thesis_store.py`` /
``thesis_ingest.py`` / ``thesis_review.py`` so the CLI works unattended
under environments that don't have the repo's ``jsonschema`` available
to the plain ``python3`` interpreter (e.g. Hermes cron from a profile cwd).

Resolution order:

1. Repo root = ``$CLAUDE_TRADING_SKILLS_REPO`` if set, else derived from
   ``__file__`` (this script lives at
   ``<repo>/skills/trader-memory-core/scripts/trader_memory_cli.py``).
2. If ``uv`` is on ``PATH`` and the recursion-guard env var
   ``TRADER_MEMORY_CLI_INNER`` is not ``"1"``, re-exec via
   ``uv run --project <repo-root> python <target> [args...]`` with the
   guard set, so dependencies declared in ``pyproject.toml`` (including
   ``jsonschema``) are available.
3. Otherwise (no uv, or inside the guarded inner run): use the current
   interpreter. If ``jsonschema`` cannot be imported, emit an actionable
   error pointing at uv / ``CLAUDE_TRADING_SKILLS_REPO`` / pip — not
   just "install jsonschema".

The launcher is stdlib-only on purpose: it must run before the project's
dependencies are reachable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

RECURSION_GUARD_ENV = "TRADER_MEMORY_CLI_INNER"
REPO_ENV = "CLAUDE_TRADING_SKILLS_REPO"

SUBCOMMAND_TO_SCRIPT = {
    "store": "thesis_store.py",
    "ingest": "thesis_ingest.py",
    "review": "thesis_review.py",
}


def find_repo_root() -> Path:
    env = os.environ.get(REPO_ENV)
    if env:
        return Path(env).resolve()
    # <repo>/skills/trader-memory-core/scripts/trader_memory_cli.py
    return Path(__file__).resolve().parents[3]


def _usage() -> str:
    subs = "|".join(SUBCOMMAND_TO_SCRIPT)
    return (
        f"usage: trader_memory_cli.py {{{subs}}} [args...]\n"
        f"  store  -> thesis_store.py   (e.g. store --state-dir state/theses list)\n"
        f"  ingest -> thesis_ingest.py  (register screener output as thesis)\n"
        f"  review -> thesis_review.py  (review-due / postmortem / summary)"
    )


def _missing_deps_error(repo_root: Path) -> str:
    return (
        "trader-memory-core: 'jsonschema' is not importable in this Python "
        f"interpreter ({sys.executable}), and 'uv' was not found on PATH.\n"
        f"Resolution options:\n"
        f"  1. (recommended) Install uv (https://docs.astral.sh/uv/) and re-run "
        f"this launcher; it will use the repo at\n"
        f"        {repo_root}\n"
        f"     via `uv run --project <repo> python <target>`. Set "
        f"{REPO_ENV}=<repo> if the launcher cannot derive the repo path.\n"
        f"  2. Install the project's dependencies into the current interpreter, "
        f"e.g. `uv pip install -e {repo_root}` or `python3 -m pip install jsonschema`.\n"
        f"Do NOT skip schema validation — thesis state integrity depends on it."
    )


def _subprocess_env() -> dict[str, str]:
    """Keep CLI output UTF-8 even when Windows uses a legacy console code page."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(_usage(), file=sys.stderr)
        return 0 if argv and argv[0] in ("-h", "--help") else 2

    sub, *rest = argv
    target_script_name = SUBCOMMAND_TO_SCRIPT.get(sub)
    if target_script_name is None:
        print(
            f"trader_memory_cli.py: unknown subcommand {sub!r}; "
            f"expected one of: {', '.join(SUBCOMMAND_TO_SCRIPT)}\n\n{_usage()}",
            file=sys.stderr,
        )
        return 2

    repo_root = find_repo_root()
    target = repo_root / "skills" / "trader-memory-core" / "scripts" / target_script_name
    if not target.is_file():
        print(
            f"trader_memory_cli.py: target script not found at {target}\n"
            f"(repo root resolved as {repo_root}; "
            f"set {REPO_ENV} to override)",
            file=sys.stderr,
        )
        return 2

    inner = os.environ.get(RECURSION_GUARD_ENV) == "1"
    uv = shutil.which("uv") if not inner else None

    if uv is not None:
        env = _subprocess_env()
        env[RECURSION_GUARD_ENV] = "1"
        cmd = [uv, "run", "--project", str(repo_root), "python", str(target), *rest]
        return subprocess.call(cmd, env=env)

    # No uv (or inside guarded inner run): need jsonschema in this interpreter.
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print(_missing_deps_error(repo_root), file=sys.stderr)
        return 3

    return subprocess.call([sys.executable, str(target), *rest], env=_subprocess_env())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
