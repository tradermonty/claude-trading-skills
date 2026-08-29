#!/usr/bin/env python3
"""Clean-room smoke test for generated calendar modules and consumer CLIs."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATHS = {
    "breakout-trade-planner": "scripts/plan_breakout_trades.py",
    "drawdown-circuit-breaker": "scripts/check_circuit_breaker.py",
    "market-environment-analysis": "scripts/market_utils.py",
    "market-top-detector": "scripts/market_top_detector.py",
    "parabolic-short-trade-planner": "scripts/screen_parabolic.py",
    "theme-detector": "scripts/theme_detector.py",
}
RUNTIME_IMPORTS = {
    "parabolic-short-trade-planner": ("fmp_client",),
    "theme-detector": (
        "config_loader",
        "etf_scanner",
        "finviz_performance_client",
        "uptrend_client",
    ),
}


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", choices=sorted(CLI_PATHS))
    args = parser.parse_args(argv)
    consumers = [args.skill] if args.skill else list(CLI_PATHS)

    for index, skill in enumerate(consumers):
        skill_dir = REPO_ROOT / "skills" / skill
        module = _load_module(
            skill_dir / "scripts" / "_market_calendar.py",
            f"_market_calendar_smoke_{index}",
        )
        session = module.session_for_date("XNYS", date(2026, 11, 27))
        if session is None or session.market_close.strftime("%H:%M") != "13:00":
            raise RuntimeError(f"{skill}: XNYS early-close contract failed")

        result = subprocess.run(
            [sys.executable, str(skill_dir / CLI_PATHS[skill]), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or "usage:" not in result.stdout.lower():
            raise RuntimeError(
                f"{skill}: --help failed ({result.returncode})\n{result.stdout}\n{result.stderr}"
            )
        modules = RUNTIME_IMPORTS.get(skill, ())
        if modules:
            imports = "; ".join(f"import {module}" for module in modules)
            import_result = subprocess.run(
                [sys.executable, "-c", imports],
                cwd=skill_dir / "scripts",
                capture_output=True,
                text=True,
                check=False,
            )
            if import_result.returncode != 0:
                raise RuntimeError(
                    f"{skill}: runtime import failed ({import_result.returncode})\n"
                    f"{import_result.stdout}\n{import_result.stderr}"
                )
        print(f"OK: {skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
