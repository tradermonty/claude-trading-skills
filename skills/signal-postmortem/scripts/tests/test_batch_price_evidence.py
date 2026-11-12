"""Missing market observations must not become measured outcomes."""

import copy
import json
import sys
from types import SimpleNamespace

import postmortem_recorder as recorder
import pytest


@pytest.fixture
def signal():
    return {
        "signal_id": "sig_fiction_1",
        "ticker": "FICTION",
        "signal_date": "2026-09-01",
        "entry_price": 100.0,
        "predicted_direction": "LONG",
        "source_skill": "fictional",
    }


def process(monkeypatch, signal, prices, periods=None):
    monkeypatch.setattr(recorder, "fetch_price_data", lambda *args: copy.deepcopy(prices))
    return recorder.process_signal(
        signal,
        periods or [5, 20],
        api_key="fictional-key",  # pragma: allowlist secret
    )


@pytest.mark.parametrize("prices", [{}, {"2026-09-21": 110}, {"2026-09-11": 110}])
def test_unobserved_primary_is_skipped(monkeypatch, signal, prices):
    assert process(monkeypatch, signal, prices) is None


@pytest.mark.parametrize("price", [True, "110", None, 0, -1, float("nan"), float("inf"), 10**400])
def test_invalid_exit_is_skipped(monkeypatch, signal, price):
    assert process(monkeypatch, signal, {"2026-09-06": price}) is None


@pytest.mark.parametrize("price", [True, "100", None, -1, float("nan"), float("inf"), 10**400])
def test_invalid_entry_is_skipped(monkeypatch, signal, price):
    signal["entry_price"] = price
    assert process(monkeypatch, signal, {"2026-09-06": 110}) is None


def test_observed_flat_is_still_neutral_and_secondary_is_optional(monkeypatch, signal):
    record = process(monkeypatch, signal, {"2026-09-07": 100.0})
    assert record["outcome_category"] == "NEUTRAL"
    assert record["realized_returns"] == {"5d": 0.0}
    assert (record["exit_price"], record["exit_date"], record["holding_days"]) == (
        100,
        "2026-09-07",
        6,
    )


def test_primary_exit_matches_classification_when_periods_reordered(monkeypatch, signal):
    record = process(monkeypatch, signal, {"2026-09-06": 110, "2026-09-21": 90}, [20, 5])
    assert (record["exit_price"], record["exit_date"]) == (110, "2026-09-06")
    assert record["outcome_category"] == "TRUE_POSITIVE"
    assert record["realized_returns"] == pytest.approx({"5d": 0.1, "20d": -0.1})
    assert process(monkeypatch, signal, {"2026-09-21": 110}, [20]) is None


def test_resolved_entry_preserved_without_input_mutation(monkeypatch, signal):
    signal.pop("entry_price")
    before = copy.deepcopy(signal)
    record = process(monkeypatch, signal, {"2026-09-01": 50, "2026-09-06": 55})
    assert record["entry_price"] == 50
    assert record["realized_returns"]["5d"] == pytest.approx(0.1)
    assert signal == before


def test_primary_overflow_skipped_secondary_overflow_omitted(monkeypatch, signal):
    signal["entry_price"] = 1e-308
    assert process(monkeypatch, signal, {"2026-09-06": 1e308}) is None
    record = process(monkeypatch, signal, {"2026-09-06": 1e-308, "2026-09-21": 1e308})
    assert record["realized_returns"] == {"5d": 0.0}
    json.dumps(record, allow_nan=False)


@pytest.mark.parametrize("shape", ["stable", "legacy", "stocklist"])
def test_fetch_accepts_observed_provider_shapes(monkeypatch, shape):
    rows = [{"date": "2026-09-06", "close": 110}]
    data = {
        "stable": rows,
        "legacy": {"historical": rows},
        "stocklist": {"historicalStockList": [{"symbol": "FICTION", "historical": rows}]},
    }[shape]
    monkeypatch.setattr(
        recorder.requests,
        "get",
        lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: data),
    )
    assert recorder.fetch_price_data("FICTION", "2026-09-01", "2026-09-26", "fictional-key") == {
        "2026-09-06": 110
    }


@pytest.mark.parametrize(
    "rows",
    [
        [{"date": "bad", "close": 110}],
        [{"date": "2026-09-06", "close": None}],
        [{"date": "2026-09-06", "close": float("nan")}],
        [{"date": "2026-09-06", "close": True}],
        [{"date": "2026-09-06", "close": -1}],
        ["malformed"],
    ],
)
def test_fetch_rejects_bad_evidence(monkeypatch, rows):
    monkeypatch.setattr(
        recorder.requests,
        "get",
        lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"historical": rows}),
    )
    assert recorder.fetch_price_data("FICTION", "2026-09-01", "2026-09-26", "fictional-key") == {}


def test_mixed_batch_preserves_skipped_existing_record(monkeypatch, tmp_path, signal, capsys):
    source = tmp_path / "signals.json"
    unavailable = {**signal, "signal_id": "sig_no_data", "ticker": "MISSING"}
    source.write_text(json.dumps([signal, unavailable]))
    stored = tmp_path / "out/postmortems/pm_sig_no_data.json"
    stored.parent.mkdir(parents=True)
    stored.write_text('{"historical":"preserve"}')
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(
        recorder,
        "fetch_price_data",
        lambda ticker, *a: {"2026-09-06": 110} if ticker == "FICTION" else {},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            recorder.__file__,
            "--signals-file",
            str(source),
            "--api-key",
            "fictional-key",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    assert recorder.main() is None
    summary = json.loads(next((tmp_path / "out").glob("postmortem_batch_*.json")).read_text())
    assert (summary["processed"], summary["skipped"]) == (1, 1)
    assert len(summary["postmortems"]) == 1
    assert stored.read_text() == '{"historical":"preserve"}'
    assert "No observed 5d exit" in capsys.readouterr().err


@pytest.mark.parametrize("periods", ["", "no", "0", "-5", "5,,20"])
def test_invalid_periods_are_cli_errors_without_records(monkeypatch, tmp_path, periods):
    monkeypatch.setattr(
        sys,
        "argv",
        [recorder.__file__, "--holding-periods", periods, "--output-dir", str(tmp_path)],
    )
    with pytest.raises(SystemExit) as error:
        recorder.main()
    assert error.value.code == 2
    assert not list(tmp_path.rglob("*.json"))


def test_later_date_cannot_mask_primary_return_overflow(monkeypatch, signal):
    signal["entry_price"] = 1e-308
    assert process(monkeypatch, signal, {"2026-09-06": 1e308, "2026-09-07": 1e-308}) is None


def test_later_date_cannot_mask_secondary_return_overflow(monkeypatch, signal):
    signal["entry_price"] = 1e-308
    record = process(
        monkeypatch, signal, {"2026-09-06": 1e-308, "2026-09-21": 1e308, "2026-09-22": 1e-308}
    )
    assert record["realized_returns"] == {"5d": 0.0}
