#!/usr/bin/env python3
"""Validate config/trading_params.yaml.

Run this after editing the config to catch errors before they hit the trade loop.

Usage:
    python3 scripts/validate_trading_params.py
    python3 scripts/validate_trading_params.py --config path/to/trading_params.yaml

Exit codes:
    0 - config is valid
    1 - config has errors
    2 - config not found / unreadable
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("error: PyYAML not installed. Run: pip3 install --break-system-packages pyyaml", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "trading_params.yaml"


def _err(msg: str, errors: list[str]) -> None:
    errors.append(f"  [ERROR] {msg}")


def _warn(msg: str, warnings: list[str]) -> None:
    warnings.append(f"  [WARN]  {msg}")


def validate_global(g: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if g.get("mode") not in ("paper", "live"):
        _err(f"global.mode must be 'paper' or 'live', got {g.get('mode')!r}", errors)

    if g.get("mode") == "live" and not g.get("dry_run", True):
        _warn("global.mode=live with dry_run=false — orders WILL be sent. Confirm checklist is signed.", warnings)

    hours = g.get("trading_hours", {})
    if not hours.get("start") or not hours.get("end"):
        _err("global.trading_hours.start and .end must be set", errors)

    if g.get("min_rr_ratio", 0) < 1.0:
        _warn(f"global.min_rr_ratio={g.get('min_rr_ratio')} is unusually low", warnings)

    if g.get("max_trades_per_day", 0) > 50:
        _warn(f"global.max_trades_per_day={g.get('max_trades_per_day')} is high", warnings)


def validate_profile(name: str, p: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    required = [
        "account_size_usd",
        "risk_per_trade_pct",
        "max_daily_loss_pct",
        "max_positions",
        "max_sector_exposure_pct",
        "max_position_size_pct",
        "min_position_size_usd",
    ]
    for key in required:
        if key not in p:
            _err(f"profile {name!r} missing required key: {key}", errors)
            return

    # Sanity ranges (errors)
    if not 0 < p["risk_per_trade_pct"] <= 100:
        _err(f"profile {name!r}: risk_per_trade_pct must be in (0, 100], got {p['risk_per_trade_pct']}", errors)
    if not 0 < p["max_daily_loss_pct"] <= 100:
        _err(f"profile {name!r}: max_daily_loss_pct must be in (0, 100]", errors)
    if p["max_positions"] < 1:
        _err(f"profile {name!r}: max_positions must be >= 1", errors)
    if not 0 < p["max_sector_exposure_pct"] <= 100:
        _err(f"profile {name!r}: max_sector_exposure_pct must be in (0, 100]", errors)

    # Soft warnings (don't block but flag)
    if name == "YOLO_DO_NOT_USE":
        return  # known-bad reference profile, skip warnings

    if p["risk_per_trade_pct"] > 3.0:
        _warn(f"profile {name!r}: risk_per_trade_pct={p['risk_per_trade_pct']} exceeds standard 2% ceiling", warnings)
    if p["max_daily_loss_pct"] > 6.0:
        _warn(f"profile {name!r}: max_daily_loss_pct={p['max_daily_loss_pct']} is high - kill-switch may rarely fire", warnings)
    if p["max_sector_exposure_pct"] > 50:
        _warn(f"profile {name!r}: max_sector_exposure_pct={p['max_sector_exposure_pct']} reduces diversification", warnings)
    if p["max_positions"] > 15:
        _warn(f"profile {name!r}: max_positions={p['max_positions']} may dilute conviction", warnings)

    # Mathematical sanity: simultaneous risk if all stops hit
    simultaneous_risk = p["risk_per_trade_pct"] * p["max_positions"]
    if simultaneous_risk > 25:
        _warn(
            f"profile {name!r}: max_positions ({p['max_positions']}) x risk_per_trade ({p['risk_per_trade_pct']}%) "
            f"= {simultaneous_risk}% simultaneous risk if correlated stops hit",
            warnings,
        )


def validate(config_path: Path) -> int:
    if not config_path.exists():
        print(f"error: config file not found: {config_path}", file=sys.stderr)
        return 2

    try:
        with config_path.open() as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        print(f"error: failed to parse YAML: {e}", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []

    active = cfg.get("active_profile")
    profiles = cfg.get("profiles", {})

    if not active:
        _err("active_profile must be set", errors)
    elif active not in profiles:
        _err(f"active_profile {active!r} does not exist in profiles section", errors)
    elif active == "YOLO_DO_NOT_USE":
        _err("active_profile is YOLO_DO_NOT_USE — refusing to validate as 'pass'. Pick a real profile.", errors)

    validate_global(cfg.get("global", {}), errors, warnings)

    for name, p in profiles.items():
        validate_profile(name, p, errors, warnings)

    print(f"Validating: {config_path}")
    print(f"Active profile: {active}")
    print()

    if warnings:
        print(f"{len(warnings)} warning(s):")
        for w in warnings:
            print(w)
        print()

    if errors:
        print(f"{len(errors)} error(s):")
        for e in errors:
            print(e)
        print()
        print("FAIL")
        return 1

    print("OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = ap.parse_args()
    return validate(args.config)


if __name__ == "__main__":
    sys.exit(main())
