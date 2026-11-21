"""Issue #831: native sector reports, legacy compatibility, and CLI diagnostics.

The frozen fixture is an actual sector-analyst report generated on 2026-11-21
from 2026-11-20 observations. Tests never refresh it or contact a provider.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from calculate_exposure import extract_sector_score

SCRIPT = Path(__file__).resolve().parents[1] / "calculate_exposure.py"
ROOT = Path(__file__).resolve().parents[4]
FIXTURE = Path(__file__).parent / "fixtures" / "sector_rotation_2026-11-21.json"
OMITTED = object()


@pytest.fixture
def native_report():
    """Read a fresh copy so malformed-input cases cannot contaminate each other."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run_cli(tmp_path, report=OMITTED, *, raw=None, missing_file=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "out"
    args = [sys.executable, str(SCRIPT), "--output-dir", str(output_dir)]
    if report is not OMITTED or raw is not None or missing_file:
        sector_path = tmp_path / "sector.json"
        if raw is not None:
            sector_path.write_bytes(raw)
        elif not missing_file:
            sector_path.write_text(json.dumps(report), encoding="utf-8")
        args += ["--sector", str(sector_path)]
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
    markdown = next(output_dir.glob("*.md")).read_text(encoding="utf-8")
    return completed, payload, markdown


def test_actual_native_sector_report_is_a_score(native_report):
    # Approved integration result for this frozen report. groups.score=53 is
    # relative rotation balance, not absolute sector health or its complement.
    assert extract_sector_score(native_report) == 3


def test_producer_format_json_flows_into_actual_cli(tmp_path, monkeypatch, native_report):
    """Exercise the real producer serializer, not a hand-made consumer schema."""
    module_name = "native_sector_contract_producer"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "skills/sector-analyst/scripts/analyze_sector_rotation.py"
    )
    producer = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, producer)
    spec.loader.exec_module(producer)
    produced = json.loads(
        producer.format_json(
            native_report["ranking"],
            native_report["groups"],
            native_report["overbought"],
            native_report["oversold"],
            native_report["trends"],
            native_report["cycle_phase"],
            native_report["meta"]["freshness"],
        )
    )
    completed, payload, markdown = run_cli(tmp_path, produced)
    assert payload["component_scores"]["sector_score"] == 3
    assert "sector" in payload["inputs_provided"]
    assert "sector" not in payload["inputs_missing"]
    assert "sector" not in payload.get("inputs_unparseable", [])
    assert "| Sector |" in markdown
    assert "unparsable" not in completed.stderr.lower()
    integration = payload["sector_integration"]
    assert integration["mapping_version"] == "sector_uptrend_health_v1"
    assert integration["score"] == 3
    assert integration["sector_count"] == 11
    assert integration["positive_slope_count"] == 0
    assert 0.06 < integration["mean_ratio"] < 0.07
    assert integration["source_freshness"] == produced["meta"]["freshness"]
    assert integration["freshness_verified"] is False
    assert isinstance(integration["scope"], str) and integration["scope"].strip()
    assert len(integration["sector_health"]) == 11


def test_canonical_score_and_context_ignore_rotation_and_legacy_aliases(tmp_path, native_report):
    _, original, _ = run_cli(tmp_path / "original", native_report)
    native_report.update(
        {
            "groups": {"score": 100},
            "cycle_phase": {"phase": "early", "confidence": "high"},
            "overbought": ["arbitrary derived annotation"],
            "oversold": [],
            "sector_score": 100,
            "dispersion": 0.05,
            "leadership": "Technology",
        }
    )
    _, with_aliases, _ = run_cli(tmp_path / "aliases", native_report)
    assert with_aliases["component_scores"]["sector_score"] == 3
    for field in ("composite_score", "exposure_ceiling_pct", "bias", "participation"):
        assert with_aliases[field] == original[field], field


@pytest.mark.parametrize("marker", ["ranking", "groups", "trends", "cycle_phase"])
def test_each_canonical_marker_prevents_unsupported_legacy_fallback(marker):
    assert extract_sector_score({marker: None, "sector_score": 100}) is None


@pytest.mark.parametrize(
    "report,expected",
    [
        ({"sector_score": 0}, 0),
        ({"sector_score": 65.9}, 65),
        ({"sector_score": 100}, 100),
        ({"dispersion": 0.05, "leadership": "Technology"}, 85),
        ({"dispersion": 0.05, "leadership": "Consumer Discretionary"}, 85),
        ({"dispersion": 0.15, "leadership": "Financials"}, 65),
        ({"dispersion": 0.25, "leadership": "Healthcare"}, 35),
        ({"dispersion": 0.25, "leadership": "Energy"}, 50),
    ],
)
def test_valid_legacy_sector_contract_is_preserved(report, expected):
    assert extract_sector_score(report) == expected


@pytest.mark.parametrize("report", [None, [], True, 42, "sector", {}])
def test_non_object_or_unknown_input_is_not_a_score(report):
    assert extract_sector_score(report) is None


@pytest.mark.parametrize(
    "bad_ratio",
    [None, True, False, "0.5", -0.01, 1.01, float("nan"), float("inf"), -float("inf")],
)
def test_invalid_canonical_ratio_cannot_fall_back_to_legacy(native_report, bad_ratio):
    native_report["ranking"][0]["ratio"] = bad_ratio
    native_report["sector_score"] = 100
    assert extract_sector_score(native_report) is None


@pytest.mark.parametrize(
    "defect", ["unknown", "unhashable", "duplicate", "missing", "row", "empty", "absent"]
)
def test_incomplete_or_unknown_sector_universe_is_rejected(native_report, defect):
    if defect == "unknown":
        native_report["ranking"][0]["sector"] = "Unrecognized Sector"
    elif defect == "unhashable":
        native_report["ranking"][0]["sector"] = []
    elif defect == "duplicate":
        native_report["ranking"][0]["sector"] = native_report["ranking"][1]["sector"]
    elif defect == "missing":
        native_report["ranking"].pop()
    elif defect == "row":
        native_report["ranking"][0] = "not a sector row"
    elif defect == "empty":
        native_report["ranking"] = []
    else:
        native_report.pop("ranking")
    native_report.update({"dispersion": 0.05, "leadership": "Technology"})
    assert extract_sector_score(native_report) is None


@pytest.mark.parametrize(
    "value", [True, "-0.01", -1.01, 1.01, float("nan"), float("inf"), -float("inf")]
)
def test_invalid_canonical_slope_invalidates_whole_report(native_report, value):
    native_report["ranking"][0]["slope"] = value
    native_report["sector_score"] = 100
    assert extract_sector_score(native_report) is None


def _sector_input(report):
    from sector_contract import parse_sector_input

    return parse_sector_input(report)


def _row_health(result, sector):
    return next(r for r in result.details["sector_health"] if r["sector"] == sector)


def _relabel(report, index, trend):
    """Keep the trends lists consistent with an edited label, as the producer would."""
    name = report["ranking"][index]["sector"]
    for direction in ("up", "down"):
        key = f"{direction}trend_sectors"
        names = [n for n in report["trends"][key] if n != name]
        if trend.lower().strip() == direction:
            names.append(name)
        report["trends"][key] = names
        report["trends"][f"{direction}trend_count"] = len(names)
    return name


def test_null_slope_is_accepted_without_trend_adjustment(native_report):
    """The producer emits slope=None for a blank CSV cell (the provider contract allows it)."""
    from sector_contract import _ratio_to_score

    row = native_report["ranking"][0]
    row["slope"] = None
    result = _sector_input(native_report)
    assert result.error is None and result.score is not None
    expected = min(100, max(0, _ratio_to_score(row["ratio"])))
    assert _row_health(result, row["sector"])["health_score"] == pytest.approx(expected)
    assert any("slope unavailable" in w for w in result.warnings)


@pytest.mark.parametrize("slope,trend", [(0.01, "Down"), (-0.01, "Up"), (0, "Up"), (-0.01, "Flat")])
def test_trend_label_disagreeing_with_slope_gets_no_adjustment(native_report, slope, trend):
    """Mirror Uptrend Analyzer: +5 only for Up with slope>0, -5 only for Down with slope<0."""
    from sector_contract import _ratio_to_score

    native_report["ranking"][0].update({"slope": slope, "trend": trend})
    name = _relabel(native_report, 0, trend)
    result = _sector_input(native_report)
    assert result.error is None
    ratio = native_report["ranking"][0]["ratio"]
    assert _row_health(result, name)["health_score"] == pytest.approx(
        min(100, max(0, _ratio_to_score(ratio)))
    )
    assert any("does not match slope" in w for w in result.warnings)


@pytest.mark.parametrize("slope,trend,adjustment", [(0.02, "Up", 5), (-0.02, "Down", -5)])
def test_agreeing_label_and_slope_keep_adjustment(native_report, slope, trend, adjustment):
    from sector_contract import _ratio_to_score

    native_report["ranking"][0].update({"slope": slope, "trend": trend})
    name = _relabel(native_report, 0, trend)
    result = _sector_input(native_report)
    ratio = native_report["ranking"][0]["ratio"]
    assert _row_health(result, name)["health_score"] == pytest.approx(
        min(100, max(0, _ratio_to_score(ratio) + adjustment))
    )


def test_all_null_slopes_reject_like_the_provider_contract(native_report):
    for row in native_report["ranking"]:
        row["slope"] = None
    assert extract_sector_score(native_report) is None


def test_row_warning_reaches_json_markdown_and_stderr(tmp_path, native_report):
    native_report["ranking"][0]["slope"] = None
    completed, payload, markdown = run_cli(tmp_path, native_report)
    assert "sector" in payload["inputs_provided"]
    assert "slope unavailable" in json.dumps(payload)
    assert "slope unavailable" in markdown
    assert "slope unavailable" in completed.stderr
    assert "Upstream sector warnings remain." in json.dumps(payload)


def test_non_string_trend_still_rejects(native_report):
    native_report["ranking"][0].update({"slope": -0.01, "trend": []})
    assert extract_sector_score(native_report) is None


def test_producer_pipeline_with_blank_slope_flows_into_score(monkeypatch, native_report):
    """Build the report through the producer's own row parsing, including a blank Slope."""
    module_name = "native_sector_pipeline_producer"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "skills/sector-analyst/scripts/analyze_sector_rotation.py"
    )
    producer = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, producer)
    spec.loader.exec_module(producer)
    raw_rows = [
        {
            "Sector": row["sector"],
            "Ratio": str(row["ratio"]),
            "10MA": "",
            "Slope": "" if i == 0 else str(row["slope"]),
            "Trend": row["trend"],
            "Status": row.get("status") or "",
        }
        for i, row in enumerate(native_report["ranking"])
    ]
    sectors = producer.parse_sector_rows(raw_rows)
    assert sectors[0].slope is None
    produced = json.loads(
        producer.format_json(
            producer.rank_sectors(sectors),
            native_report["groups"],
            native_report["overbought"],
            native_report["oversold"],
            producer.analyze_trends(sectors),
            native_report["cycle_phase"],
            native_report["meta"]["freshness"],
        )
    )
    result = _sector_input(produced)
    assert result.error is None and result.score is not None
    assert any("slope unavailable" in w for w in result.warnings)


def test_zero_slope_with_down_trend_is_valid(native_report):
    native_report["ranking"][0]["slope"] = 0
    assert type(extract_sector_score(native_report)) is int


def test_improving_slopes_increase_health_with_same_ratios(native_report):
    initial_score = extract_sector_score(native_report)
    for row in native_report["ranking"]:
        row["slope"] = abs(row["slope"])
        row["trend"] = "Up"
    native_report["trends"] = {
        "uptrend_count": 11,
        "downtrend_count": 0,
        "uptrend_sectors": [row["sector"] for row in native_report["ranking"]],
        "downtrend_sectors": [],
    }
    assert extract_sector_score(native_report) > initial_score


@pytest.mark.parametrize(
    "defect", ["absent", "not_object", "bool_count", "float_count", "count", "names", "duplicate"]
)
def test_trend_summary_must_match_the_complete_ranking(native_report, defect):
    if defect == "absent":
        native_report.pop("trends")
    elif defect == "not_object":
        native_report["trends"] = []
    elif defect == "bool_count":
        native_report["trends"]["uptrend_count"] = False
    elif defect == "float_count":
        native_report["trends"]["uptrend_count"] = 0.0
    elif defect == "count":
        native_report["trends"]["downtrend_count"] = 10
    elif defect == "names":
        native_report["trends"]["downtrend_sectors"][0] = "Unrecognized Sector"
    else:
        native_report["trends"]["downtrend_sectors"][0] = "Energy"
    native_report["sector_score"] = 100
    assert extract_sector_score(native_report) is None


@pytest.mark.parametrize("meta", [None, [], "meta"])
def test_canonical_meta_must_be_an_object(native_report, meta):
    native_report["meta"] = meta
    assert extract_sector_score(native_report) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("date", "2026-13-20"),
        ("date", None),
        ("is_fresh", "true"),
        ("is_fresh", 1),
        ("warning", []),
    ],
)
def test_declared_freshness_must_be_well_formed(native_report, field, value):
    native_report["meta"]["freshness"][field] = value
    assert extract_sector_score(native_report) is None


@pytest.mark.parametrize("missing", [False, True])
def test_unknown_freshness_is_scored_with_visible_warning(tmp_path, native_report, missing):
    if missing:
        native_report["meta"].pop("freshness")
    else:
        native_report["meta"]["freshness"] = None
    completed, payload, markdown = run_cli(tmp_path, native_report)
    assert payload["component_scores"]["sector_score"] == 3
    assert payload["sector_integration"]["freshness_verified"] is False
    warnings = payload["input_warnings"]["sector"]
    assert warnings and "fresh" in " ".join(warnings).lower()
    for warning in warnings:
        assert warning in completed.stderr
        assert warning in markdown


def test_native_stale_warning_reaches_cli_outputs(tmp_path, native_report):
    warning = "Sector source data is stale: observation date 2026-11-01."
    native_report["meta"]["freshness"] = {
        "date": "2026-11-01",
        "is_fresh": False,
        "warning": warning,
    }
    completed, payload, markdown = run_cli(tmp_path, native_report)
    assert payload["component_scores"]["sector_score"] == 3
    assert payload["sector_integration"]["source_freshness"] == native_report["meta"]["freshness"]
    assert payload["sector_integration"]["freshness_verified"] is False
    assert warning in payload["input_warnings"]["sector"]
    assert warning in completed.stderr
    assert warning in markdown


def test_stale_declaration_without_message_still_warns(tmp_path, native_report):
    native_report["meta"]["freshness"]["is_fresh"] = False
    completed, payload, markdown = run_cli(tmp_path, native_report)
    assert payload["component_scores"]["sector_score"] == 3
    warnings = payload["input_warnings"]["sector"]
    assert warnings and "stale" in " ".join(warnings).lower()
    for warning in warnings:
        assert warning in completed.stderr
        assert warning in markdown


@pytest.mark.parametrize(
    "value", [None, True, False, "80", -1, 101, float("nan"), float("inf"), -float("inf")]
)
def test_invalid_legacy_sector_number_does_not_crash_or_become_a_score(value):
    assert extract_sector_score({"sector_score": value}) is None


@pytest.mark.parametrize(
    "context",
    [
        {"dispersion": True},
        {"dispersion": float("nan")},
        {"dispersion": float("inf")},
        {"dispersion": "0.05"},
        {"leadership": []},
        {"leadership": None},
    ],
)
def test_bad_optional_legacy_context_cannot_leak_into_posture(context):
    assert extract_sector_score({"sector_score": 80, **context}) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"report": {}},
        {"report": []},
        {"report": None},
        {"report": True},
        {"report": 42},
        {"report": "sector"},
        {"report": {"sector_score": float("nan")}},
        {"report": {"sector_score": True}},
        {"missing_file": True},
        {"raw": b"not json"},
        {"raw": b"\xff\xfe"},
    ],
)
def test_supplied_invalid_sector_is_diagnosed_not_omitted(tmp_path, kwargs):
    completed, payload, markdown = run_cli(tmp_path, **kwargs)
    assert payload.get("inputs_unparseable") == ["sector"]
    assert "sector" not in payload["inputs_missing"]
    assert "sector" not in payload["inputs_provided"]
    assert "sector_score" not in payload["component_scores"]
    assert "### Unparsable Inputs\nsector" in markdown
    assert "sector" in completed.stderr.lower()
    assert "unparsable" in completed.stderr.lower()


@pytest.mark.parametrize(
    "kwargs,reason_parts",
    [
        pytest.param(
            {"missing_file": True},
            ("file read failed", "filenotfounderror"),
            id="missing-file",
        ),
        pytest.param(
            {"raw": b"not json"},
            ("json parse failed", "line", "column"),
            id="invalid-json",
        ),
        pytest.param(
            {"raw": b"\xff\xfe"},
            ("text decoding failed", "utf-8"),
            id="invalid-utf8",
        ),
        pytest.param(
            {"report": None},
            ("sector json must be an object",),
            id="json-null",
        ),
        pytest.param(
            {"report": {}},
            ("unsupported sector schema",),
            id="unsupported-object",
        ),
    ],
)
def test_sector_rejection_reason_survives_all_output_formats(tmp_path, kwargs, reason_parts):
    completed, payload, markdown = run_cli(tmp_path, **kwargs)
    assert payload["inputs_unparseable"] == ["sector"]
    assert "sector" not in payload["inputs_missing"]
    assert "sector" not in payload["inputs_provided"]
    messages = {
        "JSON warnings": "\n".join(payload["input_warnings"]["sector"]),
        "Markdown": markdown,
        "stderr": completed.stderr,
    }
    for output_format, message in messages.items():
        for reason_part in reason_parts:
            assert reason_part in message.lower(), (
                f"{output_format} lost {reason_part!r}: {message}"
            )


def test_omitted_sector_remains_missing(tmp_path):
    completed, payload, markdown = run_cli(tmp_path)
    assert "sector" in payload["inputs_missing"]
    assert "sector" not in payload.get("inputs_unparseable", [])
    assert "unparsable" not in completed.stderr.lower()
    assert "Unparsable Inputs" not in markdown
    assert "sector_integration" not in payload
    assert "input_warnings" not in payload


def test_valid_legacy_sector_cli_keeps_existing_output_shape(tmp_path):
    _, payload, _ = run_cli(tmp_path, {"sector_score": 65})
    assert payload["component_scores"]["sector_score"] == 65
    assert "sector" in payload["inputs_provided"]
    assert "sector_integration" not in payload
    assert "inputs_unparseable" not in payload
    assert "input_warnings" not in payload


def test_rejected_canonical_sector_does_not_change_posture_through_legacy_fields(
    tmp_path, native_report
):
    native_report["ranking"].pop()
    native_report.update({"sector_score": 100, "dispersion": 0.05, "leadership": "Technology"})
    _, rejected, _ = run_cli(tmp_path / "rejected", native_report)
    _, omitted, _ = run_cli(tmp_path / "omitted")
    assert rejected.get("inputs_unparseable") == ["sector"]
    for field in (
        "confidence",
        "composite_score",
        "exposure_ceiling_pct",
        "recommendation",
        "bias",
        "participation",
    ):
        assert rejected[field] == omitted[field], field
