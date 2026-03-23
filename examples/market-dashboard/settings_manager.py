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
    "trailing_stop_enabled": True,
    "partial_exit_enabled": True,
    "partial_exit_at_r": 1.0,
    "partial_exit_pct": 50,
    "time_stop_days": 5,
    "kelly_sizing_enabled": False,   # opt-in: needs real trade history first
    "kelly_max_multiplier": 2.0,     # max Kelly can multiply base risk by
    "vix_sizing_enabled": True,      # automatic: reads from cache
    "markets": [
        {
            "id": "us",
            "label": "US (NYSE/NASDAQ)",
            "broker": "alpaca",
            "exchange": "SMART",
            "currency": "USD",
            "tz": "America/New_York",
            "open": "09:30",
            "close": "16:00",
            "pdt_enabled": True,
            "enabled": True,
        },
        {
            "id": "oslo",
            "label": "Oslo Børs",
            "broker": "ibkr",
            "exchange": "OSE",
            "currency": "NOK",
            "tz": "Europe/Oslo",
            "open": "09:00",
            "close": "16:30",
            "pdt_enabled": False,
            "enabled": True,
        },
        {
            "id": "lse",
            "label": "London Stock Exchange",
            "broker": "ibkr",
            "exchange": "LSE",
            "currency": "GBP",
            "tz": "Europe/London",
            "open": "08:00",
            "close": "16:30",
            "pdt_enabled": False,
            "enabled": True,
        },
    ],
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
        # Markets validation
        markets = settings.get("markets", [])
        if markets:
            valid_brokers = {"alpaca", "ibkr"}
            for m in markets:
                broker_val = m.get("broker", "")
                if broker_val not in valid_brokers:
                    raise ValueError(
                        f"Invalid broker '{broker_val}' in market '{m.get('id', '?')}'. "
                        f"Must be one of {valid_brokers}"
                    )
            enabled_count = sum(1 for m in markets if m.get("enabled", True))
            if enabled_count == 0:
                raise ValueError(
                    "Invalid settings: at least one market must be enabled"
                )
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mktemp(dir=SETTINGS_FILE.parent, suffix=".json.tmp"))
        tmp.write_text(json.dumps(settings, indent=2))
        tmp.replace(SETTINGS_FILE)

    def get_enabled_markets(self) -> list[dict]:
        """Return only markets where enabled=True."""
        settings = self.load()
        return [m for m in settings.get("markets", []) if m.get("enabled", True)]

    def get_mode(self) -> str:
        return self.load().get("mode", DEFAULT_TRADING_MODE)

    def set_mode(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")
        s = self.load()
        s["mode"] = mode
        self.save(s)
