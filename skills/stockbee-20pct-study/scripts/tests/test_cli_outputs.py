import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "run_20pct_study.py"
spec = importlib.util.spec_from_file_location("run_20pct_study", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_cli_scan_writes_reports_and_state(tmp_path):
    prices_path = tmp_path / "prices.json"
    state_path = tmp_path / "state.jsonl"
    reports = tmp_path / "reports"
    bars = []
    closes = [10, 10.2, 10.3, 10.1, 10.4, 12.7]
    for i, close in enumerate(closes, start=1):
        bars.append(
            {
                "date": f"2026-01-{i:02d}",
                "open": close,
                "high": close * 1.05,
                "low": close * 0.95,
                "close": close,
                "volume": 2_000_000,
            }
        )
    prices_path.write_text(json.dumps({"prices": {"UPCO": bars}}), encoding="utf-8")

    rc = mod.main(
        [
            "scan",
            "--prices-json",
            str(prices_path),
            "--as-of",
            "2026-01-06",
            "--lookback-days",
            "5",
            "--min-price",
            "1",
            "--min-dollar-volume",
            "0",
            "--state-file",
            str(state_path),
            "--output-dir",
            str(reports),
        ]
    )

    assert rc == 0
    assert state_path.exists()
    assert list(reports.glob("stockbee_20pct_events_*.json"))
    assert list(reports.glob("stockbee_20pct_daily_report_*.md"))
    state_lines = state_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(state_lines) == 1
    assert json.loads(state_lines[0])["symbol"] == "UPCO"


def test_cli_scan_offline_does_not_require_fmp_key(tmp_path, monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    prices_path = tmp_path / "prices.json"
    state_path = tmp_path / "state.jsonl"
    reports = tmp_path / "reports"
    prices_path.write_text(
        json.dumps(
            {
                "prices": {
                    "UPCO": [
                        {
                            "date": "2026-01-01",
                            "open": 10,
                            "high": 10.5,
                            "low": 9.5,
                            "close": 10,
                            "volume": 1000,
                        },
                        {
                            "date": "2026-01-02",
                            "open": 12,
                            "high": 12.5,
                            "low": 11.5,
                            "close": 12,
                            "volume": 1000,
                        },
                    ],
                    "BAD": [
                        {
                            "date": "not-a-date",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "volume": 1,
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    rc = mod.main(
        [
            "scan",
            "--prices-json",
            str(prices_path),
            "--as-of",
            "2026-01-02",
            "--lookback-days",
            "1",
            "--min-price",
            "1",
            "--min-dollar-volume",
            "0",
            "--state-file",
            str(state_path),
            "--output-dir",
            str(reports),
        ]
    )

    assert rc == 0
    assert json.loads(state_path.read_text(encoding="utf-8").splitlines()[0])["symbol"] == "UPCO"


def write_backfill_prices(path):
    path.write_text(
        json.dumps(
            {
                "prices": {
                    "UPCO": [
                        {
                            "date": "2026-01-01",
                            "open": 10,
                            "high": 10.5,
                            "low": 9.5,
                            "close": 10,
                            "volume": 2_000_000,
                        },
                        {
                            "date": "2026-01-02",
                            "open": 12,
                            "high": 12.5,
                            "low": 11.5,
                            "close": 12,
                            "volume": 2_000_000,
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_cli_backfill_marks_current_universe_bias_by_default(tmp_path):
    prices_path = tmp_path / "prices.json"
    state_path = tmp_path / "state.jsonl"
    reports = tmp_path / "reports"
    write_backfill_prices(prices_path)

    rc = mod.main(
        [
            "backfill",
            "--from",
            "2026-01-01",
            "--to",
            "2026-01-02",
            "--prices-json",
            str(prices_path),
            "--lookback-days",
            "1",
            "--min-price",
            "1",
            "--min-dollar-volume",
            "0",
            "--state-file",
            str(state_path),
            "--output-dir",
            str(reports),
        ]
    )

    record = json.loads(state_path.read_text(encoding="utf-8").splitlines()[0])
    assert rc == 0
    assert mod.BACKFILL_SURVIVORSHIP_BIAS_FLAG in record["data_quality"]["flags"]
    assert record["scores"]["data_quality_score"] == record["data_quality"]["data_quality_score"]


def test_cli_backfill_survivorship_complete_suppresses_bias_flag(tmp_path):
    prices_path = tmp_path / "prices.json"
    state_path = tmp_path / "state.jsonl"
    reports = tmp_path / "reports"
    write_backfill_prices(prices_path)

    rc = mod.main(
        [
            "backfill",
            "--from",
            "2026-01-01",
            "--to",
            "2026-01-02",
            "--prices-json",
            str(prices_path),
            "--lookback-days",
            "1",
            "--min-price",
            "1",
            "--min-dollar-volume",
            "0",
            "--survivorship-complete",
            "--state-file",
            str(state_path),
            "--output-dir",
            str(reports),
        ]
    )

    record = json.loads(state_path.read_text(encoding="utf-8").splitlines()[0])
    assert rc == 0
    assert mod.BACKFILL_SURVIVORSHIP_BIAS_FLAG not in record["data_quality"]["flags"]
