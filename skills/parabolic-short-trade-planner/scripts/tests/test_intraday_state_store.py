"""Tests for intraday_state_store — per-plan-id JSON persistence."""

from __future__ import annotations

import intraday_state_store as iss


class TestRoundTrip:
    def test_save_then_load_returns_payload(self, tmp_path):
        state = {"state": "armed", "session_high": 150.0}
        iss.save_state(tmp_path, "AAPL-20260505-ORL5", "2026-05-05", state)
        out = iss.load_state(tmp_path, "AAPL-20260505-ORL5", "2026-05-05")
        # written_at is added by save_state, so check the FSM-state subset.
        assert out is not None
        assert out["state"] == "armed"
        assert out["session_high"] == 150.0
        assert "written_at" in out  # metadata, ignored by FSM

    def test_load_missing_returns_none(self, tmp_path):
        assert iss.load_state(tmp_path, "MISSING-ID", "2026-05-05") is None

    def test_different_as_of_isolated(self, tmp_path):
        iss.save_state(tmp_path, "AAPL-20260505-ORL5", "2026-05-05", {"state": "triggered"})
        iss.save_state(tmp_path, "AAPL-20260505-ORL5", "2026-05-06", {"state": "armed"})
        d1 = iss.load_state(tmp_path, "AAPL-20260505-ORL5", "2026-05-05")
        d2 = iss.load_state(tmp_path, "AAPL-20260505-ORL5", "2026-05-06")
        assert d1["state"] == "triggered"
        assert d2["state"] == "armed"

    def test_creates_state_dir_if_missing(self, tmp_path):
        target = tmp_path / "nested" / "subdir"
        assert not target.exists()
        iss.save_state(target, "AAPL-20260505-ORL5", "2026-05-05", {"state": "armed"})
        assert target.exists()
        assert iss.load_state(target, "AAPL-20260505-ORL5", "2026-05-05") is not None

    def test_corrupt_state_file_returns_none(self, tmp_path):
        # Write malformed JSON manually
        p = iss.state_path(tmp_path, "AAPL-20260505-ORL5", "2026-05-05")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not valid json", encoding="utf-8")
        # Tolerated rather than raised; the FSM doesn't depend on
        # prior_state for correctness, so a corrupt file just falls
        # back to "no prior state".
        assert iss.load_state(tmp_path, "AAPL-20260505-ORL5", "2026-05-05") is None


class TestStatePathNaming:
    def test_includes_plan_id_and_as_of(self, tmp_path):
        p = iss.state_path(tmp_path, "AAPL-20260505-ORL5", "2026-05-05")
        assert p.name == "intraday_AAPL-20260505-ORL5_2026-05-05.json"

    def test_path_separator_in_plan_id_is_sanitised(self, tmp_path):
        # Defensive: a malformed plan_id with `/` would otherwise create
        # a subdirectory. Sanitise to underscore.
        p = iss.state_path(tmp_path, "FAKE/ID", "2026-05-05")
        assert "/" not in p.name
        assert p.name == "intraday_FAKE_ID_2026-05-05.json"
