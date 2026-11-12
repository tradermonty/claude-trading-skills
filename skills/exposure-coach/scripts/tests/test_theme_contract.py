"""Native theme report ingestion, legacy compatibility and input diagnostics."""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from calculate_exposure import extract_theme_score

SCRIPT = Path(__file__).resolve().parents[1] / "calculate_exposure.py"
ROOT = Path(__file__).resolve().parents[4]


def canonical(rows=None):
    return {
        "report_type": "theme_detector",
        "themes": {"all": rows if rows is not None else [{"direction": "bullish", "heat": 80}]},
        "data_quality": {"status": "ok", "flags": []},
    }


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([{"direction": "bullish", "heat": 80}], 90),
        ([{"direction": "bearish", "heat": 80}], 10),
        ([{"direction": "bullish", "heat": 80}, {"direction": "bearish", "heat": 80}], 50),
        ([{"direction": "bullish", "heat": 80}, {"direction": "bearish", "heat": 20}], 65),
        ([{"direction": "bullish", "heat": 0}], 50),
        ([{"direction": "bullish", "heat": 100}], 100),
        ([{"direction": "bearish", "heat": 100}], 0),
    ],
)
def test_canonical_theme_directional_heat(rows, expected):
    report = canonical(rows)
    report["themes"]["bullish"] = [{"direction": "bearish", "heat": 100}] * 3
    report["theme_score"] = 1  # Canonical shape owns the score, not stray aliases.
    assert extract_theme_score(report) == expected


@pytest.mark.parametrize(
    "row",
    [
        None,
        "row",
        {},
        {"direction": "unknown", "heat": 80},
        {"direction": "bullish"},
        {"direction": "bullish", "heat": None},
        *[
            {"direction": "bullish", "heat": v}
            for v in [True, "80", -1, 101, float("nan"), float("inf")]
        ],
    ],
)
def test_bad_canonical_row_invalidates_entire_input(row):
    assert extract_theme_score(canonical([{"direction": "bullish", "heat": 100}, row])) is None


@pytest.mark.parametrize(
    "quality",
    [
        None,
        [],
        {},
        {"status": "invalid", "flags": []},
        {"status": "ok", "flags": "warning"},
        {"status": "warning", "flags": [1]},
    ],
)
def test_canonical_quality_is_required_and_validated(quality):
    report = canonical()
    report["data_quality"] = quality
    assert extract_theme_score(report) is None
    report.pop("data_quality")
    assert extract_theme_score(report) is None


@pytest.mark.parametrize(
    "report",
    [
        canonical([]),
        {"report_type": "theme_detector"},
        {"report_type": "theme_detector", "themes": []},
        [],
        True,
        None,
    ],
)
def test_unrecognized_or_empty_theme_input_is_not_a_score(report):
    assert extract_theme_score(report) is None


@pytest.mark.parametrize(
    "report,expected",
    [
        ({"theme_score": 85}, 85),
        ({"theme_score": 65.9}, 65),
        ({"theme_strength": "strong"}, 85),
        ({"theme_strength": "stable"}, 65),
        ({"theme_strength": "rotating"}, 40),
        ({"theme_strength": "collapsing"}, 20),
    ],
)
def test_supported_legacy_theme_contract(report, expected):
    assert extract_theme_score(report) == expected


@pytest.mark.parametrize(
    "report",
    [
        {"theme_strength": "unknown"},
        {"theme_strength": []},
        *[{"theme_score": v} for v in [None, True, "80", -1, 101, float("nan"), float("inf")]],
    ],
)
def test_invalid_legacy_theme_inputs_are_unparseable(report):
    assert extract_theme_score(report) is None


def run_cli(tmp_path, report=None, missing_file=False, raw=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, str(SCRIPT), "--output-dir", str(tmp_path / "out")]
    if report is not None or missing_file or raw is not None:
        theme = tmp_path / "theme.json"
        if raw is not None:
            theme.write_bytes(raw)
        elif not missing_file:
            theme.write_text(json.dumps(report), encoding="utf-8")
        args += ["--theme", str(theme)]
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(next((tmp_path / "out").glob("*.json")).read_text())
    markdown = next((tmp_path / "out").glob("*.md")).read_text()
    return completed, payload, markdown


def test_supplied_canonical_theme_is_provided_not_missing(tmp_path):
    _, payload, _ = run_cli(tmp_path, canonical())
    assert payload["component_scores"]["theme_score"] == 90
    assert "theme" in payload["inputs_provided"]
    assert "theme" not in payload["inputs_missing"]
    assert "theme" not in payload.get("inputs_unparseable", [])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"report": {}},
        {"report": []},
        {"missing_file": True},
        {"raw": b"not json"},
        {"raw": b"\xff\xfe"},
    ],
)
def test_supplied_unusable_theme_is_diagnosed_not_omitted(tmp_path, kwargs):
    completed, payload, markdown = run_cli(tmp_path, **kwargs)
    assert payload["inputs_unparseable"] == ["theme"]
    assert "theme" not in payload["inputs_missing"]
    assert "theme" not in payload["inputs_provided"]
    assert "theme_score" not in payload["component_scores"]
    assert "Unparsable Inputs" in markdown
    assert "theme" in completed.stderr.lower()
    assert "unparsable" in completed.stderr.lower()


def test_omitted_theme_remains_missing(tmp_path):
    completed, payload, markdown = run_cli(tmp_path)
    assert "theme" in payload["inputs_missing"]
    assert payload.get("inputs_unparseable", []) == []
    assert "unparsable" not in completed.stderr.lower()
    assert "Unparsable Inputs" not in markdown


def test_native_producer_warning_report_to_actual_cli(tmp_path, monkeypatch):
    producer_dir = ROOT / "skills/theme-detector/scripts"
    monkeypatch.syspath_prepend(str(producer_dir))
    spec = importlib.util.spec_from_file_location(
        "native_theme_report_contract", producer_dir / "report_generator.py"
    )
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    native = producer.generate_json_report(
        [{"name": "Synthetic leader", "direction": "bullish", "heat": 80}],
        {"top": [], "bottom": []},
        {},
        {"generated_at": "2026-11-08T12:00:00Z"},
        as_of_date=date(2026, 11, 8),
    )
    assert native["data_quality"]["status"] == "warning"
    completed, payload, markdown = run_cli(tmp_path, native)
    assert payload["component_scores"]["theme_score"] == 90
    for flag in native["data_quality"]["flags"]:
        assert flag in payload["input_warnings"]["theme"]
        assert flag in completed.stderr
        assert flag in markdown


@pytest.mark.parametrize(
    "field,value", [("status", []), ("status", {}), ("direction", []), ("direction", {})]
)
def test_unhashable_canonical_enum_is_unparseable(field, value):
    report = canonical()
    if field == "status":
        report["data_quality"][field] = value
    else:
        report["themes"]["all"][0][field] = value
    assert extract_theme_score(report) is None


def test_unparseable_theme_does_not_raise_completeness_confidence(tmp_path):
    _, bad, _ = run_cli(tmp_path / "bad", {})
    _, omitted, _ = run_cli(tmp_path / "omitted")
    assert bad["confidence"] == omitted["confidence"]
    assert bad["composite_score"] == omitted["composite_score"]


@pytest.mark.parametrize("report", [None, {"theme_score": 65}, canonical()])
def test_empty_diagnostics_preserve_existing_output_shape(tmp_path, report):
    _, payload, _ = run_cli(tmp_path, report)
    assert "inputs_unparseable" not in payload
    assert "input_warnings" not in payload
