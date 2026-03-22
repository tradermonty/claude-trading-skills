"""Manages runtime settings persisted to settings.json."""
from __future__ import annotations

import json
import tempfile
import os
from pathlib import Path

from config import (
    SETTINGS_FILE, DEFAULT_TRADING_MODE, DEFAULT_RISK_PCT,
    DEFAULT_MAX_POSITIONS, DEFAULT_MAX_POSITION_SIZE_PCT,
)

VALID_MODES = {"advisory", "semi_auto", "auto"}
VALID_ENVIRONMENTS = {"paper", "live"}

_DEFAULTS = {
    "mode": DEFAULT_TRADING_MODE,
    "default_risk_pct": DEFAULT_RISK_PCT,
    "max_positions": DEFAULT_MAX_POSITIONS,
    "max_position_size_pct": DEFAULT_MAX_POSITION_SIZE_PCT,
    "environment": "paper",
    "max_weekly_drawdown_pct": 10.0,
    "max_daily_loss_pct": 5.0,
    "earnings_blackout_days": 5,
    "min_volume_ratio": 1.5,
    "avoid_open_close_minutes": 30,
    "breadth_threshold_pct": 60.0,
    "breadth_size_reduction_pct": 50.0,
}


class SettingsManager:
    def load(self) -> dict:
        if not SETTINGS_FILE.exists():
            return dict(_DEFAULTS)
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return {**_DEFAULTS, **data}
        except Exception:
            return dict(_DEFAULTS)

    def save(self, settings: dict) -> None:
        mode = settings.get("mode", DEFAULT_TRADING_MODE)
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")
        environment = settings.get("environment", "paper")
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(f"Invalid environment: {environment}. Must be paper or live")
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mktemp(dir=SETTINGS_FILE.parent, suffix=".json.tmp"))
        tmp.write_text(json.dumps(settings, indent=2))
        tmp.replace(SETTINGS_FILE)

    def get_mode(self) -> str:
        return self.load().get("mode", DEFAULT_TRADING_MODE)

    def set_mode(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")
        s = self.load()
        s["mode"] = mode
        self.save(s)
