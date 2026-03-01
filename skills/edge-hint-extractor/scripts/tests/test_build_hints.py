"""Unit tests for build_hints.py."""

from datetime import date
from pathlib import Path
from subprocess import CompletedProcess

import build_hints as bh
import pytest


def test_build_rule_hints_generates_market_and_news_hints() -> None:
    hints = bh.build_rule_hints(
        market_summary={"regime_label": "RiskOn", "pct_above_ma50": 0.66, "vol_trend": 1.12},
        anomalies=[
            {"symbol": "CPRT", "metric": "gap", "z": -3.2},
            {"symbol": "NVDA", "metric": "rel_volume", "z": 3.1},
        ],
        news_rows=[
            {"symbol": "TSLA", "timestamp": "2026-02-20T21:00:00Z", "reaction_1d": -0.12},
        ],
        max_anomaly_hints=5,
        news_threshold=0.06,
    )

    titles = [hint["title"] for hint in hints]
    assert any("Breadth-supported breakout regime" in title for title in titles)
    assert any("Participation spike in NVDA" in title for title in titles)
    assert any("News shock reversal in TSLA" in title for title in titles)


def test_generate_llm_hints_parses_hints_dict(monkeypatch) -> None:
    stdout = """
hints:
  - title: LLM momentum idea
    observation: strong leaders pushing highs
    preferred_entry_family: pivot_breakout
    symbols: [NVDA]
"""

    def fake_run(*args, **kwargs):
        return CompletedProcess(args=args[0], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(bh.subprocess, "run", fake_run)
    hints = bh.generate_llm_hints(
        llm_command="fake-llm-cli",
        payload={"as_of": date(2026, 2, 20).isoformat()},
    )

    assert len(hints) == 1
    assert hints[0]["preferred_entry_family"] == "pivot_breakout"
    assert hints[0]["symbols"] == ["NVDA"]


def test_infer_regime_label_from_explicit_value() -> None:
    """Test that explicit regime_label takes precedence."""
    assert bh.infer_regime_label({"regime_label": "RiskOff"}) == "RiskOff"
    assert bh.infer_regime_label({"regime_label": "  Neutral  "}) == "Neutral"


def test_infer_regime_label_from_scores() -> None:
    """Test regime inference from risk_on/risk_off scores."""
    assert bh.infer_regime_label({"risk_on_score": 70, "risk_off_score": 30}) == "RiskOn"
    assert bh.infer_regime_label({"risk_on_score": 30, "risk_off_score": 70}) == "RiskOff"
    assert bh.infer_regime_label({"risk_on_score": 50, "risk_off_score": 50}) == "Neutral"
    assert bh.infer_regime_label({}) == "Neutral"


def test_normalize_hint_handles_missing_fields() -> None:
    """Test that normalize_hint provides defaults for missing fields."""
    hint = bh.normalize_hint({"title": "Test"})
    assert hint["title"] == "Test"
    assert hint["observation"] == "Test"
    assert hint["symbols"] == []
    assert hint["regime_bias"] == ""
    assert hint["mechanism_tag"] == "behavior"
    assert "preferred_entry_family" not in hint


def test_normalize_hint_dedupes_symbols() -> None:
    """Test that duplicate symbols are removed."""
    hint = bh.normalize_hint({"title": "Test", "symbols": ["AAPL", "aapl", "AAPL", "MSFT"]})
    assert hint["symbols"] == ["AAPL", "MSFT"]


def test_normalize_hint_validates_entry_family() -> None:
    """Test that only valid entry families are accepted."""
    hint1 = bh.normalize_hint({"title": "T", "preferred_entry_family": "pivot_breakout"})
    assert hint1["preferred_entry_family"] == "pivot_breakout"

    hint2 = bh.normalize_hint({"title": "T", "preferred_entry_family": "invalid_family"})
    assert "preferred_entry_family" not in hint2


def test_dedupe_hints_removes_duplicates() -> None:
    """Test that semantically identical hints are deduplicated."""
    hints = [
        {"title": "Test", "symbols": ["AAPL"], "regime_bias": "RiskOn", "mechanism_tag": "flow"},
        {"title": "test", "symbols": ["AAPL"], "regime_bias": "RiskOn", "mechanism_tag": "flow"},
        {
            "title": "Different",
            "symbols": ["MSFT"],
            "regime_bias": "RiskOn",
            "mechanism_tag": "flow",
        },
    ]
    result = bh.dedupe_hints(hints, max_total=10)
    assert len(result) == 2


def test_dedupe_hints_respects_max_total() -> None:
    """Test that max_total limit is respected."""
    hints = [{"title": f"Hint {i}", "symbols": []} for i in range(10)]
    result = bh.dedupe_hints(hints, max_total=3)
    assert len(result) == 3


def test_parse_as_of_valid_date() -> None:
    """Test valid date parsing."""
    assert bh.parse_as_of("2026-02-20") == date(2026, 2, 20)
    assert bh.parse_as_of(None) is None
    assert bh.parse_as_of("") is None


def test_parse_as_of_invalid_date() -> None:
    """Test that invalid date format raises HintExtractionError."""
    with pytest.raises(bh.HintExtractionError, match="invalid --as-of format"):
        bh.parse_as_of("2026/02/20")


def test_safe_float_handles_edge_cases() -> None:
    """Test safe_float conversion with various inputs."""
    assert bh.safe_float(3.14) == 3.14
    assert bh.safe_float("2.5") == 2.5
    assert bh.safe_float(None) == 0.0
    assert bh.safe_float("invalid") == 0.0
    assert bh.safe_float(None, default=-1.0) == -1.0


def test_build_rule_hints_risk_off_regime() -> None:
    """Test hint generation in RiskOff regime."""
    hints = bh.build_rule_hints(
        market_summary={"regime_label": "RiskOff"},
        anomalies=[],
        news_rows=[],
        max_anomaly_hints=5,
        news_threshold=0.06,
    )
    titles = [h["title"] for h in hints]
    assert any("Risk-off selectivity" in t for t in titles)


def test_build_rule_hints_positive_gap_anomaly() -> None:
    """Test positive gap anomaly generates correct hint."""
    hints = bh.build_rule_hints(
        market_summary={},
        anomalies=[{"symbol": "NVDA", "metric": "gap", "z": 3.5}],
        news_rows=[],
        max_anomaly_hints=5,
        news_threshold=0.06,
    )
    titles = [h["title"] for h in hints]
    assert any("Positive gap shock in NVDA" in t for t in titles)


def test_build_rule_hints_positive_news_reaction() -> None:
    """Test positive news reaction generates continuation hint."""
    hints = bh.build_rule_hints(
        market_summary={},
        anomalies=[],
        news_rows=[{"symbol": "AAPL", "reaction_1d": 0.10}],
        max_anomaly_hints=5,
        news_threshold=0.06,
    )
    titles = [h["title"] for h in hints]
    assert any("News drift continuation in AAPL" in t for t in titles)


def test_parse_hints_payload_handles_various_formats() -> None:
    """Test that parse_hints_payload handles list and dict formats."""
    # List format
    result1 = bh.parse_hints_payload([{"title": "Test"}])
    assert len(result1) == 1

    # Dict format with hints key
    result2 = bh.parse_hints_payload({"hints": [{"title": "Test"}]})
    assert len(result2) == 1

    # None
    result3 = bh.parse_hints_payload(None)
    assert result3 == []


def test_parse_hints_payload_rejects_invalid_format() -> None:
    """Test that invalid formats raise HintExtractionError."""
    with pytest.raises(bh.HintExtractionError, match="must be list or"):
        bh.parse_hints_payload("invalid string")


def test_normalize_news_row_handles_empty_symbol() -> None:
    """Test that rows with empty symbols are filtered out."""
    result = bh.normalize_news_row({"symbol": "", "timestamp": "2026-02-20"})
    assert result is None

    result2 = bh.normalize_news_row({"symbol": "AAPL", "timestamp": "2026-02-20"})
    assert result2 is not None
    assert result2["symbol"] == "AAPL"


def test_normalize_hint_preserves_hypothesis_type() -> None:
    """Test that hypothesis_type is passed through when present."""
    hint = bh.normalize_hint({"title": "Test", "hypothesis_type": "breakout"})
    assert hint["hypothesis_type"] == "breakout"


def test_normalize_hint_omits_empty_hypothesis_type() -> None:
    """Test that empty or whitespace-only hypothesis_type is excluded."""
    hint1 = bh.normalize_hint({"title": "Test", "hypothesis_type": ""})
    assert "hypothesis_type" not in hint1

    hint2 = bh.normalize_hint({"title": "Test", "hypothesis_type": "   "})
    assert "hypothesis_type" not in hint2

    hint3 = bh.normalize_hint({"title": "Test"})
    assert "hypothesis_type" not in hint3


def test_build_rule_hints_include_hypothesis_type() -> None:
    """Test that rule-generated hints include hypothesis_type."""
    hints = bh.build_rule_hints(
        market_summary={"regime_label": "RiskOn", "pct_above_ma50": 0.66, "vol_trend": 1.12},
        anomalies=[
            {"symbol": "NVDA", "metric": "gap", "z": 3.5},
            {"symbol": "CPRT", "metric": "gap", "z": -3.2},
            {"symbol": "AMD", "metric": "rel_volume", "z": 3.1},
        ],
        news_rows=[
            {"symbol": "AAPL", "reaction_1d": 0.10},
            {"symbol": "TSLA", "reaction_1d": -0.12},
        ],
        max_anomaly_hints=5,
        news_threshold=0.06,
    )

    type_map = {h["title"]: h.get("hypothesis_type") for h in hints}
    assert type_map["Breadth-supported breakout regime"] == "breakout"
    assert type_map["Positive gap shock in NVDA"] == "breakout"
    assert type_map["Downside overreaction watch in CPRT"] == "panic_reversal"
    assert type_map["Participation spike in AMD"] == "breakout"
    assert type_map["News drift continuation in AAPL"] == "news_reaction"
    assert type_map["News shock reversal in TSLA"] == "news_reaction"


def test_dedupe_hints_distinguishes_hypothesis_type() -> None:
    """Test that same title with different hypothesis_type are kept as separate hints."""
    hints = [
        {
            "title": "Test",
            "hypothesis_type": "breakout",
            "symbols": [],
            "regime_bias": "",
            "mechanism_tag": "behavior",
        },
        {
            "title": "Test",
            "hypothesis_type": "panic_reversal",
            "symbols": [],
            "regime_bias": "",
            "mechanism_tag": "behavior",
        },
    ]
    result = bh.dedupe_hints(hints, max_total=10)
    assert len(result) == 2


def test_load_llm_hints_from_file_bare_list(tmp_path: Path) -> None:
    """Test loading a bare YAML list from file."""
    yaml_content = (
        "- title: Sector rotation into industrials\n"
        "  observation: Tech underperforming\n"
        "  symbols: [CAT, DE]\n"
        "  regime_bias: Neutral\n"
        "  mechanism_tag: flow\n"
    )
    f = tmp_path / "hints.yaml"
    f.write_text(yaml_content)
    result = bh.load_llm_hints_from_file(f)
    assert len(result) == 1
    assert result[0]["title"] == "Sector rotation into industrials"
    assert result[0]["symbols"] == ["CAT", "DE"]


def test_load_llm_hints_from_file_dict_wrapper(tmp_path: Path) -> None:
    """Test loading hints wrapped in {hints: [...]} format."""
    yaml_content = (
        "hints:\n"
        "  - title: Momentum breakout\n"
        "    observation: Leaders pushing highs\n"
        "    symbols: [NVDA]\n"
    )
    f = tmp_path / "hints.yaml"
    f.write_text(yaml_content)
    result = bh.load_llm_hints_from_file(f)
    assert len(result) == 1
    assert result[0]["symbols"] == ["NVDA"]


def test_load_llm_hints_from_file_empty(tmp_path: Path) -> None:
    """Test that empty file returns empty list."""
    f = tmp_path / "empty.yaml"
    f.write_text("")
    result = bh.load_llm_hints_from_file(f)
    assert result == []


def test_load_llm_hints_from_file_invalid_yaml(tmp_path: Path) -> None:
    """Test that invalid YAML raises HintExtractionError."""
    f = tmp_path / "bad.yaml"
    f.write_text(":\n  - [invalid\n")
    with pytest.raises(bh.HintExtractionError, match="invalid YAML"):
        bh.load_llm_hints_from_file(f)


def test_main_llm_ideas_file_not_found(tmp_path: Path, monkeypatch) -> None:
    """Test that main() returns 1 when --llm-ideas-file does not exist."""
    monkeypatch.setattr(
        "sys.argv",
        ["build_hints.py", "--llm-ideas-file", str(tmp_path / "missing.yaml")],
    )
    assert bh.main() == 1


def test_llm_ideas_file_and_cmd_mutual_exclusion(monkeypatch) -> None:
    """Test that --llm-ideas-file and --llm-ideas-cmd cannot be used together."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_hints.py",
            "--llm-ideas-cmd",
            "echo hi",
            "--llm-ideas-file",
            "/tmp/hints.yaml",
        ],
    )
    with pytest.raises(SystemExit):
        bh.parse_args()


def test_parse_timestamp_to_date_handles_formats() -> None:
    """Test timestamp parsing with various formats."""
    # ISO format with Z
    assert bh.parse_timestamp_to_date("2026-02-20T12:00:00Z") == date(2026, 2, 20)
    # ISO format with offset
    assert bh.parse_timestamp_to_date("2026-02-20T12:00:00+00:00") == date(2026, 2, 20)
    # Invalid format
    assert bh.parse_timestamp_to_date("invalid") is None
    # Empty/None
    assert bh.parse_timestamp_to_date(None) is None
    assert bh.parse_timestamp_to_date("") is None
