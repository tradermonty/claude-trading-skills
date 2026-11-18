"""Shared fixtures: a tiny fake reports/ and state/ tree with made-up numbers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def reports_dir(tmp_path: Path) -> Path:
    d = tmp_path / "reports"
    d.mkdir()
    for day, ceiling in (("2026-11-16", 60), ("2026-11-17", 70), ("2026-11-18", 50)):
        write_json(
            d / f"exposure_posture_{day}_211500.json",
            {
                "generated_at": f"{day}T21:15:00+00:00",
                "exposure_ceiling_pct": ceiling,
                "recommendation": "REDUCE_ONLY",
                "bias": "NEUTRAL",
                "participation": "NARROW",
                "confidence": "MEDIUM",
                "composite_score": ceiling - 5.0,
                "rationale": "Sample rationale.",
            },
        )
    # An earlier run on the same day: history should keep only the latest per day.
    write_json(
        d / "exposure_posture_2026-11-18_090000.json",
        {"exposure_ceiling_pct": 90, "generated_at": "2026-11-18T09:00:00+00:00"},
    )
    (d / "exposure_posture_2026-11-18_211500.md").write_text(
        "# Exposure\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    )
    write_json(
        d / "market_breadth_2026-11-18_211000.json",
        {
            "metadata": {"generated_at": "2026-11-18 16:10:00"},
            "composite": {
                "composite_score": 55.5,
                "zone": "Neutral",
                "exposure_guidance": "60-80%",
            },
        },
    )
    write_json(
        d / "uptrend_analysis_2026-11-18_211100.json",
        {"composite": {"composite_score": 48.0, "zone": "Neutral"}},
    )
    write_json(
        d / "vcp_screener_2026-11-18_220000.json",
        {
            "metadata": {},
            "results": [
                {"symbol": "AAA", "composite_score": 81.0, "rating": "Strong VCP", "price": 10.0},
                {"symbol": "BBB", "composite_score": 66.0, "rating": "Good VCP", "price": 20.0},
            ],
            "summary": {"total": 2},
        },
    )
    write_json(
        d / "circuit_breaker_decision_2026-11-18_213000.json",
        {"as_of_date": "2026-11-18", "recommendation": "ALLOW", "warnings": []},
    )
    (d / "broken_2026-11-18.json").write_text("{not json")
    return d


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    theses = d / "theses"
    journal = d / "journal"
    theses.mkdir(parents=True)
    journal.mkdir(parents=True)
    base = {
        "created_at": "2026-11-17T14:00:00+00:00",
        "thesis_type": "momentum_breakout",
        "status_history": [],
        "thesis_statement": "Sample thesis.",
        "origin": {"skill": "vcp-screener"},
    }
    samples = [
        dict(
            base,
            thesis_id="th_aaa_1",
            ticker="AAA",
            status="ACTIVE",
            updated_at="2026-11-18T15:00:00+00:00",
            entry={"target_price": 10.0, "actual_price": 10.1},
            exit={"stop_loss": 9.5, "take_profit": 11.5},
            position={"shares": 10, "risk_dollars": 6.0},
            monitoring={"next_review_date": "2026-11-18"},
        ),
        dict(
            base,
            thesis_id="th_bbb_1",
            ticker="BBB",
            status="IDEA",
            updated_at="2026-11-17T15:00:00+00:00",
            monitoring={"next_review_date": "2026-11-30"},
        ),
        dict(
            base,
            thesis_id="th_ccc_1",
            ticker="CCC",
            status="CLOSED",
            updated_at="2026-11-16T15:00:00+00:00",
            outcome={"pnl_dollars": -4.0, "pnl_pct": -2.0},
            monitoring={"next_review_date": "2026-11-01"},
        ),
    ]
    for t in samples:
        (theses / f"{t['thesis_id']}.yaml").write_text(yaml.safe_dump(t), encoding="utf-8")
    (theses / "th_bad.yaml").write_text(": : not yaml : [", encoding="utf-8")
    (theses / "_index.json").write_text("{}", encoding="utf-8")
    (journal / "pm_th_ccc_1.md").write_text("# Postmortem CCC\n\nStopped out.\n", encoding="utf-8")
    return d
