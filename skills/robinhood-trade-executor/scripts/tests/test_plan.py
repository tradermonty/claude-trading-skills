"""Offline checks for the source-agnostic execution planner — the part that must not misfire."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan_executions import (  # noqa: E402
    adapt_josh,
    adapt_social,
    build_plan,
    detect_source,
    load_intents,
)

# --- source detection + adapters ----------------------------------------------------------


def test_detect_source():
    assert detect_source({"intents": []}) == "canonical"
    assert detect_source({"events": []}) == "josh"
    assert detect_source({"signals": []}) == "social"


def test_adapt_josh_open_and_close_share_match_key():
    doc = {
        "trader_id": 29,
        "events": [
            {
                "action": "open",
                "trade_id": 631,
                "ticker": "AMD",
                "instrument": "option",
                "direction": "call",
                "strike_price": 180.0,
                "expiration": "2026-07-17",
                "entry_price": 2.1,
            },
            {
                "action": "close",
                "trade_id": 629,
                "ticker": "SKHYV",
                "instrument": "equity",
                "direction": "long",
                "entry_price": 170,
            },
        ],
    }
    ints = adapt_josh(doc)
    assert ints[0]["match_key"] == "josh:29:631" and ints[0]["reference_price"] == 2.1
    assert ints[1]["match_key"] == "josh:29:629" and ints[1]["action"] == "close"


def test_adapt_social_long_stock_only():
    doc = {
        "signals": [
            {"ticker": "AAA", "direction": "long", "instrument": "stock"},
            {"ticker": "BBB", "direction": "short", "instrument": "stock"},
            {"ticker": "CCC", "direction": "long", "instrument": "option"},  # multi-leg → deferred
            {"ticker": "DDD", "direction": "long", "watch": {"trigger": 1}},  # conditional
        ]
    }
    ints, skipped = adapt_social(doc)
    assert [i["ticker"] for i in ints] == ["AAA"]
    assert {s["reason"].split(" ")[0] for s in skipped} == {
        "direction",
        "social",
        "conditional/watch",
    }


# --- planning -----------------------------------------------------------------------------


def _canon(mk, action, instrument, ticker, **kw):
    d = {
        "match_key": mk,
        "action": action,
        "instrument": instrument,
        "ticker": ticker,
        "direction": kw.get("direction", "long"),
        "strike": kw.get("strike"),
        "expiration": kw.get("expiration"),
        "reference_price": kw.get("reference_price"),
        "notional": kw.get("notional"),
    }
    return d


def test_mixed_equity_and_option_in_one_feed():
    intents = [
        _canon("k1", "open", "equity", "MSFT"),
        _canon(
            "k2",
            "open",
            "option",
            "NVDA",
            direction="call",
            strike=200.0,
            expiration="2026-12-31",
            reference_price=1.71,
        ),
    ]
    plan = build_plan(intents, [], 300.0, as_of="2026-07-12")
    kinds = {o["kind"] for o in plan["orders"]}
    assert kinds == {"equity_buy", "option_buy"}
    opt = next(o for o in plan["orders"] if o["kind"] == "option_buy")
    assert opt["contracts"] == 1


def test_option_too_expensive_and_expired_are_skipped():
    pricey = _canon(
        "k3",
        "open",
        "option",
        "META",
        direction="call",
        strike=610.0,
        expiration="2026-12-31",
        reference_price=7.65,
    )
    expired = _canon(
        "k4",
        "open",
        "option",
        "AAPL",
        direction="put",
        strike=200.0,
        expiration="2026-07-08",
        reference_price=1.0,
    )
    plan = build_plan([pricey, expired], [], 300.0, as_of="2026-07-12")
    assert plan["orders"] == []
    reasons = " ".join(s["reason"] for s in plan["skipped"])
    assert "1 contract" in reasons and "expired" in reasons


def test_dedup_on_intent_id():
    ledger = [
        {
            "intent_id": "k1:open",
            "match_key": "k1",
            "action": "open",
            "instrument": "equity",
            "status": "filled",
            "quantity": 2.0,
        }
    ]
    plan = build_plan([_canon("k1", "open", "equity", "MSFT")], ledger, 300.0)
    assert plan["orders"] == [] and plan["skipped"][0]["reason"].startswith("already executed")


def test_close_matches_open_by_match_key():
    ledger = [
        {
            "intent_id": "josh:29:629:open",
            "match_key": "josh:29:629",
            "action": "open",
            "instrument": "equity",
            "status": "filled",
            "quantity": 1.76,
        }
    ]
    plan = build_plan([_canon("josh:29:629", "close", "equity", "SKHYV")], ledger, 300.0)
    assert plan["orders"] == [
        {
            "kind": "equity_sell",
            "intent_id": "josh:29:629:close",
            "match_key": "josh:29:629",
            "ticker": "SKHYV",
            "quantity": 1.76,
        }
    ]


def test_option_close_carries_recorded_contract_spec():
    ledger = [
        {
            "intent_id": "josh:29:631:open",
            "match_key": "josh:29:631",
            "action": "open",
            "instrument": "option",
            "status": "filled",
            "quantity": 1,
            "option_type": "call",
            "strike": 180.0,
            "expiration": "2026-07-17",
        }
    ]
    plan = build_plan([_canon("josh:29:631", "close", "option", "AMD")], ledger, 300.0)
    o = plan["orders"][0]
    assert o["kind"] == "option_sell" and o["contracts"] == 1 and o["strike"] == 180.0


def test_close_without_tracked_open_is_skipped():
    plan = build_plan([_canon("ghost", "close", "equity", "ZZZ")], [], 300.0)
    assert plan["orders"] == [] and "no tracked open" in plan["skipped"][0]["reason"]


# --- multi-input merge --------------------------------------------------------------------


def test_load_intents_merges_multiple_sources(tmp_path):
    import json

    j = tmp_path / "josh.json"
    j.write_text(
        json.dumps(
            {
                "trader_id": 29,
                "events": [
                    {
                        "action": "open",
                        "trade_id": 1,
                        "ticker": "AMD",
                        "instrument": "equity",
                        "direction": "long",
                    }
                ],
            }
        )
    )
    s = tmp_path / "social.json"
    s.write_text(
        json.dumps({"signals": [{"ticker": "MSFT", "direction": "long", "instrument": "stock"}]})
    )
    intents, pre_skipped = load_intents([str(j), str(s)])
    sources = {i["source"] for i in intents}
    assert sources == {"josh", "social"} and len(intents) == 2


if __name__ == "__main__":
    import inspect
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(tmp) if inspect.signature(fn).parameters else fn()
            print(f"ok {name}")
