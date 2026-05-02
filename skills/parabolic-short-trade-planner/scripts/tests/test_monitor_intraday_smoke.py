"""End-to-end smoke test for monitor_intraday_trigger.

Drives the Phase 3 pipeline against a synthetic Phase 2 plan + a
fixture bar file so the schema contract (intraday_monitor phase, all
required keys, size_recipe_resolved when triggered) is verified
without a network call.
"""

from __future__ import annotations

import json
from pathlib import Path

import monitor_intraday_trigger as mit

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestSmokePipeline:
    def test_orl_clean_break_yields_triggered_plan(self, tmp_path):
        rc = mit.main(
            [
                "--plans-json",
                str(FIXTURES / "phase2_plan_smoke.json"),
                "--bars-source",
                "fixture",
                "--bars-fixture",
                str(FIXTURES / "intraday_bars" / "orl_clean_break.json"),
                "--state-dir",
                str(tmp_path / "state"),
                "--output-dir",
                str(tmp_path / "out"),
                "--as-of",
                "2026-05-05",
                "--now-et",
                "2026-05-05T10:00:00-04:00",
            ]
        )
        assert rc == 0

        out_files = list((tmp_path / "out").glob("*.json"))
        assert len(out_files) == 1
        report = json.loads(out_files[0].read_text())

        assert report["schema_version"] == "1.0"
        assert report["phase"] == "intraday_monitor"
        assert report["as_of"] == "2026-05-05"
        assert report["market_status"] == "regular_session"
        assert report["data_source"] == "fixture"
        assert len(report["monitored_plans"]) == 2  # ORL + FR plans

        orl_plan = next(p for p in report["monitored_plans"] if p["plan_id"].endswith("ORL5"))
        assert orl_plan["state"] == "triggered"
        assert orl_plan["evaluation_status"] == "evaluated"
        assert orl_plan["entry_actual"] == 148.45
        assert orl_plan["stop_actual"] == 150.35
        # size_recipe_resolved must be filled with concrete shares.
        sr = orl_plan["size_recipe_resolved"]
        assert sr is not None
        assert isinstance(sr["shares_actual"], int)
        assert sr["shares_actual"] > 0
        # The ORL fixture's bar 2 is also a red 5-min candle (open 149.45,
        # close 148.50), so First Red marks it as red_marked. There's no
        # *later* bar to trigger off, so the plan stays at red_marked.
        fr_plan = next(p for p in report["monitored_plans"] if p["plan_id"].endswith("FR5"))
        assert fr_plan["state"] == "red_marked"
        assert fr_plan["size_recipe_resolved"] is None

    def test_no_bars_yields_no_bars_status(self, tmp_path):
        rc = mit.main(
            [
                "--plans-json",
                str(FIXTURES / "phase2_plan_smoke.json"),
                "--bars-source",
                "fixture",
                "--bars-fixture",
                str(FIXTURES / "intraday_bars" / "no_bars_yet.json"),
                "--state-dir",
                str(tmp_path / "state"),
                "--output-dir",
                str(tmp_path / "out"),
                "--as-of",
                "2026-05-05",
                "--now-et",
                "2026-05-05T09:00:00-04:00",  # pre-9:30
            ]
        )
        assert rc == 0
        report = json.loads(next((tmp_path / "out").glob("*.json")).read_text())
        # monitored_plans is NOT empty even when bars are missing —
        # per v0.5c, every input plan gets an entry with no_bars status.
        assert len(report["monitored_plans"]) == 2
        for plan in report["monitored_plans"]:
            assert plan["evaluation_status"] == "no_bars"
            assert plan["state"] == "armed"  # carried forward / default
            # Schema parity (v0.5d): every monitored plan carries
            # shares_actual + size_recipe_resolved keys, even when
            # there are no bars. Downstream consumers can read them
            # uniformly.
            assert "shares_actual" in plan
            assert "size_recipe_resolved" in plan
            assert plan["shares_actual"] is None
            assert plan["size_recipe_resolved"] is None
        assert report["market_status"] == "closed"
