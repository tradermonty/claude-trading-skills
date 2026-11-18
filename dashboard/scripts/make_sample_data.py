#!/usr/bin/env python3
"""Write made-up reports and theses to sample-data/ so you can preview the dashboard.

    python3 scripts/make_sample_data.py
    REPORTS_DIR=sample-data/reports STATE_DIR=sample-data/state flask --app app:create_app run

Every number here is invented. Nothing is read from your real account.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parents[1] / "sample-data"


def dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    reports = OUT / "reports"
    state = OUT / "state"
    start = date(2026, 10, 20)
    day = start
    i = 0
    while day <= date(2026, 11, 18):
        if day.weekday() < 5:
            breadth = 55 + 18 * math.sin(i / 5)
            uptrend = 50 + 15 * math.sin(i / 6 + 1)
            ceiling = max(10, min(100, round((breadth + uptrend) / 2 / 10) * 10))
            stamp = f"{day.isoformat()}_211500"
            dump(
                reports / f"market_breadth_{stamp}.json",
                {
                    "composite": {
                        "composite_score": round(breadth, 1),
                        "zone": "Neutral" if breadth < 60 else "Healthy",
                        "exposure_guidance": "60-80%",
                    }
                },
            )
            dump(
                reports / f"uptrend_analysis_{stamp}.json",
                {"composite": {"composite_score": round(uptrend, 1), "zone": "Neutral"}},
            )
            dump(
                reports / f"exposure_posture_{stamp}.json",
                {
                    "exposure_ceiling_pct": ceiling,
                    "recommendation": "NEW_ENTRY_ALLOWED" if ceiling >= 60 else "REDUCE_ONLY",
                    "bias": "NEUTRAL",
                    "participation": "BROAD",
                    "confidence": "LOW",
                    "composite_score": ceiling,
                    "rationale": "Sample data: breadth and uptrend inputs only, so confidence is low.",
                },
            )
            i += 1
        day += timedelta(days=1)
    dump(
        reports / "vcp_screener_2026-11-18_220000.json",
        {
            "results": [
                {
                    "symbol": "SMPL",
                    "rating": "Strong VCP",
                    "composite_score": 82.4,
                    "price": 41.2,
                    "distance_from_pivot_pct": -1.8,
                    "execution_state": "Pre-breakout",
                },
                {
                    "symbol": "DEMO",
                    "rating": "Good VCP",
                    "composite_score": 71.0,
                    "price": 118.5,
                    "distance_from_pivot_pct": -3.2,
                    "execution_state": "Pre-breakout",
                },
                {
                    "symbol": "TEST",
                    "rating": "Developing VCP",
                    "composite_score": 63.7,
                    "price": 27.9,
                    "distance_from_pivot_pct": 0.6,
                    "execution_state": "Breakout",
                },
            ]
        },
    )
    dump(
        reports / "circuit_breaker_decision_2026-11-18_213000.json",
        {"as_of_date": "2026-11-18", "recommendation": "ALLOW", "warnings": []},
    )
    theses = [
        {
            "thesis_id": "th_smpl_demo_1",
            "ticker": "SMPL",
            "status": "ACTIVE",
            "thesis_type": "momentum_breakout",
            "thesis_statement": "Sample: tight VCP base breaking out on volume.",
            "entry": {"target_price": 41.0, "actual_price": 41.3},
            "exit": {"stop_loss": 39.4, "take_profit": 45.1},
            "position": {"shares": 12, "risk_dollars": 22.8},
            "monitoring": {"next_review_date": "2026-11-18"},
            "kill_criteria": ["Close below 39.40", "Breadth zone turns Weak"],
        },
        {
            "thesis_id": "th_demo_demo_1",
            "ticker": "DEMO",
            "status": "ENTRY_READY",
            "thesis_type": "momentum_breakout",
            "thesis_statement": "Sample: waiting for a pivot break above 121.",
            "entry": {"target_price": 121.0},
            "exit": {"stop_loss": 115.0, "take_profit": 133.0},
            "monitoring": {"next_review_date": "2026-11-20"},
        },
        {
            "thesis_id": "th_test_demo_1",
            "ticker": "TEST",
            "status": "CLOSED",
            "thesis_type": "momentum_breakout",
            "thesis_statement": "Sample: failed breakout, stopped out.",
            "outcome": {"pnl_dollars": -18.0, "pnl_pct": -2.1},
        },
    ]
    for t in theses:
        t.setdefault("created_at", "2026-11-17T14:00:00+00:00")
        t.setdefault("updated_at", "2026-11-18T15:00:00+00:00")
        t.setdefault("status_history", [])
        t.setdefault("origin", {"skill": "vcp-screener"})
        path = state / "theses" / f"{t['thesis_id']}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(t, sort_keys=False), encoding="utf-8")
    journal = state / "journal" / "pm_th_test_demo_1.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        "# Postmortem: TEST (sample)\n\n- Entered on a weak-volume breakout.\n- Stop honored.\n",
        encoding="utf-8",
    )
    print(f"Sample data written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
