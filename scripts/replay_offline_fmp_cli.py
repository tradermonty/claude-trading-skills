#!/usr/bin/env python3
"""Run an FMP-backed skill CLI against a fictional offline fixture.

Workflow replay helper (Issue #216). The earnings-trade-analyzer and
pead-screener CLIs construct an ``FMPClient`` and call three read methods. This
runner imports the skill's real ``fmp_client`` module, swaps ``FMPClient`` for a
subclass whose network methods read a local JSON fixture, blocks every HTTP
request, and then executes the skill's real ``main()`` unchanged. Argument
parsing, filtering, scoring, and report generation therefore run exactly as
they do in production; only the data source is replaced.

Usage:
    replay_offline_fmp_cli.py --skill-dir <skills/x/scripts> --script <name.py> \
        --fixture <fixture.json> -- <arguments for the skill CLI>

Fixture shape (all values fictional):
    {"earnings_calendar": [{"symbol", "date", "time", ...}],
     "profiles": {"<symbol>": {...}},
     "prices": {"<symbol>": [{"date", "open", "high", "low", "close", ...}]}}
``prices`` rows are most-recent-first, the order the FMP endpoint returns.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any

SUPPORTED_SCRIPTS = {
    "analyze_earnings_trades.py": "list",
    "screen_pead.py": "dict",
}


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("earnings_calendar", "profiles", "prices"):
        if key not in payload:
            raise SystemExit(f"fixture is missing {key!r}")
    return payload


def _block_network() -> None:
    import requests

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("offline replay forbids HTTP requests")

    requests.sessions.Session.request = forbidden  # type: ignore[method-assign]


def _fixture_client_class(fmp_module: Any, fixture: dict[str, Any], price_shape: str) -> type:
    real = fmp_module.FMPClient

    class FixtureFMPClient(real):  # type: ignore[misc, valid-type]
        """Read-only client backed by the offline fixture; makes no network call."""

        def __init__(self, api_key: str | None = None, max_api_calls: int = 200) -> None:
            self.cache = {}
            self.rate_limit_reached = False
            self.api_calls_made = 0
            self.max_api_calls = max_api_calls

        def _spend(self) -> None:
            if self.api_calls_made >= self.max_api_calls:
                raise fmp_module.ApiCallBudgetExceeded("offline fixture budget exhausted")
            self.api_calls_made += 1

        def get_earnings_calendar(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
            self._spend()
            return [
                copy.deepcopy(row)
                for row in fixture["earnings_calendar"]
                if from_date <= row["date"] <= to_date
            ]

        def get_company_profiles(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
            self._spend()
            return {
                symbol: copy.deepcopy(fixture["profiles"][symbol])
                for symbol in symbols
                if symbol in fixture["profiles"]
            }

        def get_historical_prices(self, symbol: str, days: int = 90) -> Any:
            self._spend()
            rows = fixture["prices"].get(symbol)
            if rows is None:
                return None
            rows = copy.deepcopy(rows[:days])
            if price_shape == "dict":
                return {"symbol": symbol, "historical": rows}
            return rows

    return FixtureFMPClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skill-dir", required=True, type=Path)
    parser.add_argument("--script", required=True)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("cli_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if args.script not in SUPPORTED_SCRIPTS:
        parser.error(f"unsupported script {args.script!r}; expected {sorted(SUPPORTED_SCRIPTS)}")
    cli_args = args.cli_args[1:] if args.cli_args[:1] == ["--"] else args.cli_args

    skill_dir = args.skill_dir.resolve()
    script_path = skill_dir / args.script
    if not script_path.is_file():
        parser.error(f"missing skill script: {script_path}")

    os.environ.pop("FMP_API_KEY", None)
    _block_network()
    fixture = _load_fixture(args.fixture)

    sys.path.insert(0, str(skill_dir))
    import fmp_client  # noqa: E402  (the skill's own vendored client)

    if Path(fmp_client.__file__).resolve().parent != skill_dir:
        raise SystemExit(f"refusing fmp_client imported from outside {skill_dir}")
    fmp_client.FMPClient = _fixture_client_class(
        fmp_client, fixture, SUPPORTED_SCRIPTS[args.script]
    )

    sys.argv = [str(script_path), *cli_args]
    runpy.run_path(str(script_path), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
