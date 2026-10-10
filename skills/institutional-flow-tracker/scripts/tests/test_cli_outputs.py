"""Offline CLI regressions that exercise real analysis and persisted reports."""

import json
import sys

import analyze_single_stock as single
import pytest
import requests
import track_institutional_flow as flow


def _summary(shares=6_000_000, investors=220, previous_investors=200):
    return {
        "date": "2026-03-31",
        "investorsHolding": investors,
        "lastInvestorsHolding": previous_investors,
        "investorsHoldingChange": investors - previous_investors,
        "numberOf13Fshares": shares,
        "lastNumberOf13Fshares": 5_000_000,
        "numberOf13FsharesChange": shares - 5_000_000,
        "increasedPositions": 120,
        "reducedPositions": 50,
        "newPositions": 20,
        "closedPositions": 10,
        "ownershipPercent": 65.0,
        "ownershipPercentChange": 1.5,
    }


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("CLI regression attempted a live HTTP request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(flow, "current_quarter", lambda _: (2026, 1))
    monkeypatch.setattr(single, "current_quarter", lambda _: (2026, 1))
    monkeypatch.setattr(flow.time, "sleep", lambda _: None)


@pytest.mark.parametrize("module,arguments", [(flow, []), (single, ["test"])])
def test_missing_key_exits_without_provider_or_files(
    module, arguments, monkeypatch, tmp_path, capsys
):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing-key CLI reached provider boundary")

    cls = flow.InstitutionalFlowTracker if module is flow else single.SingleStockAnalyzer
    monkeypatch.setattr(cls, "_get", forbidden)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [module.__file__, *arguments])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "Error: FMP API key required",
        "Set FMP_API_KEY environment variable or pass --api-key argument",
        "Get free API key at: https://financialmodelingprep.com/developer/docs",
    ]
    assert list(tmp_path.iterdir()) == []


def test_screen_cli_persists_filtered_ranked_json_and_markdown(monkeypatch, tmp_path, capsys):
    calls = []

    def provider(self, path, **params):
        calls.append((path, params))
        if path == "company-screener":
            return [
                {
                    "symbol": symbol,
                    "companyName": f"{symbol} Corp",
                    "marketCap": 2_000_000_000,
                    "sector": sector,
                }
                for symbol, sector in [
                    ("ALPHA", "Technology"),
                    ("BETA", "Technology"),
                    ("OTHER", "Healthcare"),
                    ("THIN", "Technology"),
                    ("LOWCHANGE", "Technology"),
                    ("LOWCOUNT", "Technology"),
                ]
            ]
        if path.endswith("symbol-positions-summary"):
            # Both boundary candidates would outrank BETA if the CLI used
            # default thresholds instead of the explicitly supplied values.
            summaries = {
                "THIN": _summary(previous_investors=0),
                "LOWCHANGE": _summary(shares=5_600_000, investors=500),
                "LOWCOUNT": _summary(investors=200, previous_investors=100),
            }
            return [
                summaries.get(
                    params["symbol"], _summary(investors=250 if params["symbol"] == "BETA" else 220)
                )
            ]
        assert path.endswith("extract-analytics/holder")
        return []

    monkeypatch.setattr(flow.InstitutionalFlowTracker, "_get", provider)
    reports = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            flow.__file__,
            "--api-key",
            "synthetic-key",
            "--top",
            "1",
            "--min-change-percent",
            "15",
            "--min-market-cap",
            "2000000000",
            "--sector",
            "technology",
            "--min-institutions",
            "210",
            "--sort-by",
            "institution_count_change",
            "--limit",
            "7",
            "--output",
            "nested/results",
            "--output-dir",
            str(reports),
        ],
    )
    flow.main()

    results = json.loads((reports / "results.json").read_text())
    assert [row["symbol"] for row in results] == ["BETA"]
    assert results[0]["percent_change"] == 20.0
    assert results[0]["institution_count_change"] == 50
    assert results[0]["reliability_grade"] == "A"
    assert calls[0] == ("company-screener", {"marketCapMoreThan": 2_000_000_000, "limit": 7})
    assert "OTHER" not in {params.get("symbol") for _, params in calls}
    assert not any(
        params.get("symbol") == "THIN" and path.endswith("holder") for path, params in calls
    )
    report_paths = list(reports.glob("*.md"))
    assert len(report_paths) == 1
    report = report_paths[0].read_text()
    assert "Stocks Analyzed:** 1" in report
    assert "BETA Corp" in report and "ALPHA" not in report and "THIN" not in report
    assert "+20.0%" in report
    output = capsys.readouterr().out
    assert "TOP 10 INSTITUTIONAL FLOW CHANGES" in output
    assert "BETA" in output and "50" in output


def test_empty_screen_cli_writes_empty_json_without_markdown(monkeypatch, tmp_path, capsys):
    calls = []

    def provider(self, path, **params):
        calls.append(path)
        return []

    monkeypatch.setattr(flow.InstitutionalFlowTracker, "_get", provider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            flow.__file__,
            "--api-key",
            "synthetic-key",
            "--output",
            "empty.json",
            "--output-dir",
            str(tmp_path),
        ],
    )
    flow.main()
    assert calls == ["company-screener"]
    assert json.loads((tmp_path / "empty.json").read_text()) == []
    assert list(tmp_path.glob("*.md")) == []
    output = capsys.readouterr().out
    assert "No results to report" in output
    assert "TOP 10 INSTITUTIONAL FLOW CHANGES" not in output


@pytest.mark.parametrize("enough_history", [True, False])
def test_single_stock_cli_report_or_insufficient_history(
    monkeypatch, tmp_path, capsys, enough_history
):
    calls = []

    def provider(self, path, **params):
        calls.append((path, params))
        assert params["symbol"] == "TEST"
        if path == "profile":
            return [
                {
                    "companyName": "Synthetic Corp",
                    "sector": "Technology",
                    "marketCap": 2_000_000_000,
                }
            ]
        if path.endswith("symbol-positions-summary"):
            if (params["year"], params["quarter"]) == (2026, 1):
                return [_summary()]
            return [_summary(shares=5_000_000, investors=200)] if enough_history else []
        assert path.endswith("extract-analytics/holder")
        return []

    monkeypatch.setattr(single.SingleStockAnalyzer, "_get", provider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            single.__file__,
            "test",
            "--api-key",
            "synthetic-key",
            "--quarters",
            "2",
            "--output-dir",
            str(tmp_path),
        ],
    )
    if enough_history:
        single.main()
        report_paths = list(tmp_path.glob("institutional_analysis_TEST_*.md"))
        assert len(report_paths) == 1
        report = report_paths[0].read_text()
        assert "Institutional Ownership Analysis: TEST" in report
        assert "Synthetic Corp" in report and "2026-03-31" in report
        output = capsys.readouterr().out
        assert "Data Reliability: Grade A" in output
        assert "Trend (2 quarters): +20.00% shares, +20 institutions" in output
        assert "New Positions: 0" in output
    else:
        with pytest.raises(SystemExit) as exc:
            single.main()
        assert exc.value.code == 1
        assert list(tmp_path.iterdir()) == []
        output = capsys.readouterr().out
        assert "need at least 2 quarters" in output and "Unable to complete analysis" in output
        assert not any(path.endswith("holder") for path, _ in calls)
    assert any(params.get("quarter") == 4 and params.get("year") == 2025 for _, params in calls)
