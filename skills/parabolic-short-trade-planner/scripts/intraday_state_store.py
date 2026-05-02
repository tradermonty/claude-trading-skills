"""Per-plan-id intraday state persistence for Phase 3.

Mirrors the per-symbol pattern in ``ssr_state_tracker.py`` but keyed
on ``plan_id`` so ORL / FirstRed / VWAP states for the same ticker
live in separate files. File naming includes ``as_of`` so day-N+1
runs cannot accidentally overwrite day-N state.

The Phase 3 FSM is replay-deterministic (see the idempotency contract
in the v0.5 plan), so prior_state is **only** consulted by the CLI
for diff/notification purposes — never by the FSM itself. This
module deliberately exposes a read API + a write API and nothing
that helps "advance" state, which would be the wrong abstraction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def state_path(state_dir: str | Path, plan_id: str, as_of: str) -> Path:
    """Where today's per-plan state file lives."""
    safe_plan_id = plan_id.replace("/", "_")  # defensive
    return Path(state_dir) / f"intraday_{safe_plan_id}_{as_of}.json"


def load_state(state_dir: str | Path, plan_id: str, as_of: str) -> dict | None:
    """Read today's state for this plan, or ``None`` if no run has
    persisted one yet."""
    p = state_path(state_dir, plan_id, as_of)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_state(
    state_dir: str | Path,
    plan_id: str,
    as_of: str,
    state: dict,
) -> Path:
    """Persist this run's state for the next run to read."""
    p = state_path(state_dir, plan_id, as_of)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    # ``written_at`` is wall-clock — it's metadata about *when this run
    # wrote the file*, not part of the FSM state. Idempotency tests
    # normalise this field before byte-comparing.
    payload["written_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p
