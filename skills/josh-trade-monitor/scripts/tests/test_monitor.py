"""Offline checks for the diff logic + target parsing — the pieces with real branching."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitor_josh_trades import (  # noqa: E402
    diff_trades,
    instrument,
    parse_target,
    read_targets_file,
    to_event,
)


def _t(tid, status="closed"):
    return {"id": tid, "ticker": "X", "status": status}


def _open_ids(state):
    return [p["trade_id"] for p in state["open_positions"]]


def test_first_run_reports_nothing_but_records_baseline_with_detail():
    trades = [_t(10), _t(12, "open")]
    new, closed, state = diff_trades(trades, {})
    assert new == [] and closed == []  # baseline: no flood on first run
    assert state["max_seen_id"] == 12
    assert _open_ids(state) == [12]  # detail stored, not just an id
    assert state["open_positions"][0]["ticker"] == "X"


def test_only_higher_ids_are_new():
    state = {"max_seen_id": 12, "open_positions": [{"trade_id": 12}]}
    new, _, next_state = diff_trades([_t(12, "open"), _t(13), _t(15)], state)
    assert sorted(t["id"] for t in new) == [13, 15]
    assert next_state["max_seen_id"] == 15


def test_open_then_closed_is_reported():
    state = {"max_seen_id": 12, "open_positions": [{"trade_id": 12}]}
    _, closed, next_state = diff_trades([_t(12, "closed")], state)
    assert [t["id"] for t in closed] == [12]
    assert _open_ids(next_state) == []


def test_legacy_open_ids_state_still_detects_close():
    state = {"max_seen_id": 12, "open_ids": [12]}  # old schema on disk
    _, closed, _ = diff_trades([_t(12, "closed")], state)
    assert [t["id"] for t in closed] == [12]


def test_no_change_is_quiet():
    state = {"max_seen_id": 15, "open_positions": []}
    new, closed, _ = diff_trades([_t(13), _t(15)], state)
    assert new == [] and closed == []


def test_instrument_classification():
    assert instrument({"direction": "call"}) == "option"
    assert instrument({"direction": "long"}) == "equity"


def test_event_contract_shape():
    e = to_event(
        {
            "id": 628,
            "ticker": "NVDA",
            "direction": "call",
            "strike": "205 CALL",
            "expiration": "2026-07-10",
            "entryPrice": 1.71,
            "status": "open",
        },
        "open",
    )
    assert e["action"] == "open" and e["instrument"] == "option" and e["strike_price"] == 205.0


def test_parse_target_forms():
    assert parse_target("13", "this_week") == (13, "this_week")
    assert parse_target("13:all_time", "this_week") == (13, "all_time")
    assert parse_target(
        "https://leaderboard.stockswithjosh.com/leaderboard/traders/13?period=all_time", "this_week"
    ) == (13, "all_time")
    assert parse_target(
        "https://leaderboard.stockswithjosh.com/api/leaderboard/traders/29?period=this_week", "x"
    ) == (29, "this_week")


def test_read_targets_file_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "targets.txt"
    f.write_text("# header\n\n29:this_week\n  \n13\n# trailing\n")
    assert read_targets_file(f) == ["29:this_week", "13"]


if __name__ == "__main__":
    import inspect
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(tmp) if inspect.signature(fn).parameters else fn()
            print(f"ok {name}")
