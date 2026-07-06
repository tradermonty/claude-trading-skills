#!/usr/bin/env python3
"""Theme Detector history and acceleration metrics."""

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def load_history(path: Optional[str]) -> dict[str, list[dict]]:
    """Load history from JSON. Missing files return an empty history."""
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("themes"), dict):
        return {
            str(name): records if isinstance(records, list) else []
            for name, records in data["themes"].items()
        }
    if isinstance(data, list):
        history: dict[str, list[dict]] = {}
        for record in data:
            name = record.get("theme")
            if name:
                history.setdefault(name, []).append(record)
        return history
    return {}


def save_history(path: str, history: dict[str, list[dict]]) -> None:
    """Write history JSON atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "themes": history}
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    tmp.replace(target)


def compute_history_metrics(
    history: dict[str, list[dict]], theme_name: str, current_date: str, current_heat: float
) -> dict:
    """Compute current acceleration metrics against prior observations."""
    prior = _prior_records(history.get(theme_name, []), current_date)
    prior_heats = [_float(record.get("heat")) for record in prior]
    prior_heats = [value for value in prior_heats if value is not None]

    heat_delta_1d = current_heat - prior_heats[-1] if prior_heats else None
    heat_delta_5d = current_heat - prior_heats[-5] if len(prior_heats) >= 5 else None

    heat_z_20d = None
    acceleration_score = None
    window = prior_heats[-20:]
    if len(window) >= 2:
        mean = sum(window) / len(window)
        variance = sum((value - mean) ** 2 for value in window) / len(window)
        std = math.sqrt(variance)
        if std > 0:
            heat_z_20d = (current_heat - mean) / std
            acceleration_score = max(0.0, min(100.0, 50.0 + heat_z_20d * 15.0))

    duration_count = _duration_count(prior, current_heat)
    duration_score = min(100.0, duration_count * 10.0)

    return {
        "duration_count": duration_count,
        "duration_score": round(duration_score, 2),
        "heat_delta_1d": _round_or_none(heat_delta_1d),
        "heat_delta_5d": _round_or_none(heat_delta_5d),
        "heat_z_20d": _round_or_none(heat_z_20d),
        "acceleration_score": _round_or_none(acceleration_score),
        "prior_observations": len(prior),
    }


def append_observations(history: dict[str, list[dict]], observations: list[dict]) -> dict:
    """Return history with current observations appended."""
    updated = {name: list(records) for name, records in history.items()}
    for observation in observations:
        name = observation.get("theme")
        if not name:
            continue
        records = updated.setdefault(name, [])
        records = [r for r in records if r.get("date") != observation.get("date")]
        records.append(observation)
        records.sort(key=lambda r: r.get("date", ""))
        updated[name] = records[-260:]
    return updated


def build_observation(theme: dict, run_date: str) -> dict:
    """Build one persistent history observation for a scored theme."""
    return {
        "date": run_date,
        "theme": theme.get("name"),
        "direction": theme.get("direction"),
        "heat": theme.get("heat"),
        "base_heat": theme.get("base_heat"),
        "leadership_score": theme.get("leadership_score"),
        "leadership_counts": theme.get("leadership_counts", {}),
    }


def resolve_run_date(value: Optional[str] = None) -> str:
    """Return YYYY-MM-DD run date."""
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    return datetime.now().date().isoformat()


def _prior_records(records: list[dict], current_date: str) -> list[dict]:
    prior = [record for record in records if str(record.get("date", "")) < current_date]
    return sorted(prior, key=lambda record: record.get("date", ""))


def _duration_count(prior: list[dict], current_heat: float) -> int:
    count = 1 if current_heat >= 40.0 else 0
    if count == 0:
        return 0
    for record in reversed(prior):
        heat = _float(record.get("heat"))
        if heat is None or heat < 40.0:
            break
        count += 1
    return count


def _float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 2)
