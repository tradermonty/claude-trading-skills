"""COT provenance uses observed vintages and the real UTC collection clock."""

import importlib.util
import json
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import pytest
import screen_cot_crowding as screener

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "cot_test_shared_provenance", ROOT / "scripts/validate_provenance.py"
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class Clock(datetime):
    current = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


def args_for(tmp_path):
    return Namespace(
        symbols="ES",
        core=False,
        as_of="2026-07-07",
        lookback_weeks=2,
        short_lookback_weeks=2,
        threshold_high=90,
        threshold_low=10,
        api_key="fictional-private-key",  # pragma: allowlist secret (offline fixture)
        sleep_seconds=0,
        output_dir=str(tmp_path),
        format="both",
    )


def write_report(tmp_path, monkeypatch, results):
    monkeypatch.setattr(screener, "datetime", Clock)
    args = args_for(tmp_path)
    context = screener.build_run_context(args, ["ES", "GC"], "explicit_symbols", "2026-07-07")
    path = tmp_path / "report.json"
    screener.generate_json_report(results, context, str(path))
    return json.loads(path.read_text())


def market(symbol, data_date):
    return {"symbol": symbol, "status": "ok", "data_date": data_date, "extremity": 50}


def test_provenance_preserves_actual_retrieval_and_oldest_market_vintage(tmp_path, monkeypatch):
    rows = [market("ES", "2026-07-07"), market("GC", "2026-06-30")]
    payload = write_report(tmp_path, monkeypatch, rows)
    block = payload["data_provenance"]
    assert validator.validate_provenance(block) == []
    assert block["provider"] == "fmp"
    assert block["endpoint"] == "commitment-of-traders-report"
    assert block["retrieved_at"] == "2026-11-06T12:00:00Z"
    assert block["as_of"] == "2026-06-30"
    assert block["as_of_basis"] == "oldest_analyzed_market_report"
    assert block["market_data_dates"] == {"ES": "2026-07-07", "GC": "2026-06-30"}
    assert block["timezone"] == "America/New_York"
    for name in ("adjusted", "point_in_time", "survivorship_free", "corporate_actions_handled"):
        assert block[name] is False
    assert payload["markets"] == rows
    assert payload["run_context"]["as_of"] == "2026-07-07"
    assert payload["run_context"]["data_date"] == "2026-07-07"
    assert "fictional-private-key" not in json.dumps(payload)
    assert "apikey=" not in json.dumps(payload)


@pytest.mark.parametrize("rows", [[], [{"symbol": "ES", "status": "skipped", "reason": "no data"}]])
def test_no_observations_are_explicit_without_fabricating_market_dates(tmp_path, monkeypatch, rows):
    payload = write_report(tmp_path, monkeypatch, rows)
    block = payload["data_provenance"]
    assert validator.validate_provenance(block) == []
    assert block["as_of"] == "2026-07-07"
    assert block["as_of_basis"] == "request_cutoff_no_analyzed_data"
    assert block["market_data_dates"] == {}
    assert payload["markets"] == []
    assert payload["skipped"] == rows


@pytest.mark.parametrize("data_date", [None, "", "not-a-date", "2026-02-30", "2026-7-7"])
def test_invalid_analyzed_vintage_does_not_overwrite_json(tmp_path, monkeypatch, data_date):
    target = tmp_path / "report.json"
    target.write_bytes(b"previous checkpoint")
    with pytest.raises(ValueError, match="data_date"):
        write_report(tmp_path, monkeypatch, [market("ES", data_date), market("GC", "2026-07-07")])
    assert target.read_bytes() == b"previous checkpoint"


@pytest.mark.parametrize("data_date", [None, "not-a-date"])
def test_cli_invalid_vintage_is_controlled_and_preserves_both_reports(
    tmp_path, monkeypatch, capsys, data_date
):
    args = args_for(tmp_path)
    monkeypatch.setattr(screener, "parse_arguments", lambda: args)
    monkeypatch.setattr(screener, "CotClient", lambda **kwargs: object())
    monkeypatch.setattr(
        screener,
        "collect_results",
        lambda *args: ([market("ES", data_date)], ["ES"], "explicit_symbols"),
    )
    paths = [tmp_path / f"cot_crowding_2026-07-07.{suffix}" for suffix in ("json", "md")]
    for path in paths:
        path.write_bytes(b"previous checkpoint")
    with pytest.raises(SystemExit) as error:
        screener.main()
    assert error.value.code == 1
    assert "data_date" in capsys.readouterr().err
    assert all(path.read_bytes() == b"previous checkpoint" for path in paths)


def test_cli_records_clock_after_actual_collection(tmp_path, monkeypatch):
    args = args_for(tmp_path)
    monkeypatch.setattr(screener, "parse_arguments", lambda: args)
    monkeypatch.setattr(screener, "datetime", Clock)
    monkeypatch.setattr(Clock, "current", datetime(2026, 11, 6, 11, 59, tzinfo=timezone.utc))
    calls = []

    class Client:
        api_calls_made = 1

        def __init__(self, **kwargs):
            pass

        def get_report(self, symbol, from_date, to_date):
            calls.append((symbol, from_date, to_date))
            Clock.current = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
            return [
                {
                    "date": "2026-06-30",
                    "noncommPositionsLongAll": 20,
                    "noncommPositionsShortAll": 10,
                },
                {
                    "date": "2026-07-07",
                    "noncommPositionsLongAll": 21,
                    "noncommPositionsShortAll": 10,
                },
            ], None

    monkeypatch.setattr(screener, "CotClient", Client)
    screener.main()
    block = json.loads((tmp_path / "cot_crowding_2026-07-07.json").read_text())["data_provenance"]
    assert block["retrieved_at"] == "2026-11-06T12:00:00Z"
    assert block["as_of"] == "2026-07-07"
    assert calls == [("ES", "2026-04-28", "2026-07-07")]
    assert (tmp_path / "cot_crowding_2026-07-07.md").exists()


def test_cli_rejects_malformed_provider_vintage_before_report_writes(tmp_path, monkeypatch, capsys):
    args = args_for(tmp_path)
    monkeypatch.setattr(screener, "parse_arguments", lambda: args)

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_report(self, *args):
            return [
                {
                    "date": "2026-06-30",
                    "noncommPositionsLongAll": 20,
                    "noncommPositionsShortAll": 10,
                },
                {
                    "date": "not-a-date",
                    "noncommPositionsLongAll": 21,
                    "noncommPositionsShortAll": 10,
                },
            ], None

    monkeypatch.setattr(screener, "CotClient", Client)
    with pytest.raises(SystemExit) as error:
        screener.main()
    assert error.value.code == 1
    assert "data_date" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_cli_duplicate_symbols_keep_oldest_observed_vintage(tmp_path, monkeypatch):
    args = args_for(tmp_path)
    args.symbols = "ES,ES"
    monkeypatch.setattr(screener, "parse_arguments", lambda: args)
    calls = []

    class Client:
        api_calls_made = 2

        def __init__(self, **kwargs):
            pass

        def get_report(self, symbol, *args):
            dates = ["2026-06-23", "2026-06-30"] if not calls else ["2026-06-30", "2026-07-07"]
            calls.append(symbol)
            return [
                {"date": dates[0], "noncommPositionsLongAll": 20, "noncommPositionsShortAll": 10},
                {"date": dates[1], "noncommPositionsLongAll": 21, "noncommPositionsShortAll": 10},
            ], None

    monkeypatch.setattr(screener, "CotClient", Client)
    screener.main()
    payload = json.loads((tmp_path / "cot_crowding_2026-07-07.json").read_text())
    assert calls == ["ES", "ES"]
    assert [row["data_date"] for row in payload["markets"]] == ["2026-06-30", "2026-07-07"]
    assert payload["data_provenance"]["as_of"] == "2026-06-30"
    assert payload["data_provenance"]["market_data_dates"] == {"ES": "2026-06-30"}


def test_compact_date_is_rejected(tmp_path, monkeypatch):
    # Python 3.11+ fromisoformat accepts "20260707"; the canonical check must not.
    with pytest.raises(ValueError, match="data_date"):
        write_report(tmp_path, monkeypatch, [market("ES", "20260707")])


def test_invalid_vintage_error_names_symbol_and_truncated_value(tmp_path, monkeypatch):
    rows = [market("ES", "2026-07-07"), market("GC", "x" * 100), market("CL", "2026-07-07")]
    with pytest.raises(ValueError) as error:
        write_report(tmp_path, monkeypatch, rows)
    message = str(error.value)
    assert "GC" in message
    assert "ES" not in message and "CL" not in message
    assert "x" * 41 not in message


def test_cli_invalid_vintage_error_on_stderr_names_symbol(tmp_path, monkeypatch, capsys):
    args = args_for(tmp_path)
    monkeypatch.setattr(screener, "parse_arguments", lambda: args)
    monkeypatch.setattr(screener, "CotClient", lambda **kwargs: object())
    rows = [market("ES", "2026-07-07"), market("GC", "not-a-date"), market("CL", "2026-07-07")]
    monkeypatch.setattr(
        screener, "collect_results", lambda *a: (rows, ["ES", "GC", "CL"], "explicit_symbols")
    )
    with pytest.raises(SystemExit) as error:
        screener.main()
    assert error.value.code == 1
    assert "GC" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_all_skipped_provenance_as_of_is_canonical(tmp_path, monkeypatch):
    monkeypatch.setattr(screener, "datetime", Clock)
    args = args_for(tmp_path)
    args.as_of = "2026-7-7"
    context = screener.build_run_context(args, ["ES"], "explicit_symbols", None)
    block = screener.build_data_provenance([], context)
    assert block["as_of"] == "2026-07-07"
    assert block["as_of_basis"] == "request_cutoff_no_analyzed_data"
    assert validator.validate_provenance(block) == []
    assert context["as_of"] == "2026-7-7"


def test_cli_markdown_only_keeps_previous_behavior_with_bad_date(tmp_path, monkeypatch):
    args = args_for(tmp_path)
    args.format = "md"
    monkeypatch.setattr(screener, "parse_arguments", lambda: args)

    class Client:
        api_calls_made = 1

        def __init__(self, **kwargs):
            pass

        def get_report(self, *args):
            return [
                {
                    "date": "2026-06-30",
                    "noncommPositionsLongAll": 20,
                    "noncommPositionsShortAll": 10,
                },
                {
                    "date": "not-a-date",
                    "noncommPositionsLongAll": 21,
                    "noncommPositionsShortAll": 10,
                },
            ], None

    monkeypatch.setattr(screener, "CotClient", Client)
    screener.main()
    assert (tmp_path / "cot_crowding_2026-07-07.md").exists()
    assert not (tmp_path / "cot_crowding_2026-07-07.json").exists()
