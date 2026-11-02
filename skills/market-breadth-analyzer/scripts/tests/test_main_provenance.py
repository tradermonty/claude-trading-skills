"""Real orchestration emits provenance from fetched primary rows."""

import json
from datetime import datetime, timedelta
from unittest import mock

import csv_client
import market_breadth_analyzer as analyzer
import pytest


def run_main(output, rows, run_id=None, detail_url=None):
    argv = ["market_breadth_analyzer.py", "--output-dir", str(output)]
    if detail_url is not None:
        argv += ["--detail-url", detail_url]
    if run_id is not None:
        argv += ["--run-id", run_id]
    with (
        mock.patch.object(analyzer, "fetch_detail_csv", return_value=rows),
        mock.patch.object(analyzer, "fetch_summary_csv", return_value={}),
        mock.patch("sys.argv", argv),
        mock.patch.object(
            csv_client.requests,
            "head",
            return_value=mock.Mock(headers={"Last-Modified": "Wed, 08 Jan 2025 12:30:00 GMT"}),
        ) as head,
    ):
        analyzer.main()
    head.assert_called_once()
    assert head.call_args.kwargs == {"timeout": 10, "allow_redirects": True}
    report = next(p for p in output.glob("market_breadth_*.json") if "history" not in p.name)
    return json.loads(report.read_text())["data_provenance"]


def test_main_records_primary_date_and_run(tmp_path, make_rows):
    block = run_main(tmp_path, make_rows(25), "shared-run")
    assert block["run_id"] == "shared-run"
    assert block["as_of"] == "2025-01-25"
    assert datetime.fromisoformat(block["retrieved_at"]).utcoffset() == timedelta(0)
    assert block["provider"] == "trader-monty"
    assert block["endpoint"] == analyzer.DEFAULT_DETAIL_URL
    assert "primary timeseries" in block["scope"]
    assert block["auxiliary_sources"][0]["as_of_verified"] is False
    for flag in ("adjusted", "point_in_time", "survivorship_free", "corporate_actions_handled"):
        assert block[flag] is False


@pytest.mark.parametrize("date", [None, "", "2025-99-99"])
def test_invalid_primary_date_writes_no_report(tmp_path, make_rows, date):
    rows = make_rows(25)
    rows[-1]["Date"] = date
    with pytest.raises(ValueError):
        run_main(tmp_path, rows, "shared-run")
    assert list(tmp_path.iterdir()) == []


def test_default_run_id_is_unique(tmp_path, make_rows):
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    first = run_main(tmp_path / "first", make_rows(25))
    second = run_main(tmp_path / "second", make_rows(25))
    assert first["run_id"] and second["run_id"]
    assert first["run_id"] != second["run_id"]


def test_custom_primary_source_is_identified_honestly(tmp_path, make_rows):
    block = run_main(tmp_path, make_rows(25), detail_url="https://example.com/custom.csv")
    assert block["provider"] == "custom-csv"
    assert block["endpoint"] == "https://example.com/custom.csv"
