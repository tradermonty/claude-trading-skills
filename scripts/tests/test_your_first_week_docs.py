"""Contract tests for the bilingual Your First Week onboarding guide."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EN_GUIDE = ROOT / "docs" / "en" / "your-first-week.md"
JA_GUIDE = ROOT / "docs" / "ja" / "your-first-week.md"

MANUAL_JSON_RE = re.compile(
    r"<!-- first-week-manual-json:start -->\s*"
    r"```json\n(?P<payload>.*?)\n```\s*"
    r"<!-- first-week-manual-json:end -->",
    re.DOTALL,
)
MANUAL_HEREDOC_RE = re.compile(
    r"cat > first-week-inputs/manual-idea\.json <<'JSON'\n"
    r"(?P<payload>.*?)\nJSON",
    re.DOTALL,
)
NAVIGATOR_COMMAND_RE = re.compile(
    r"<!-- first-week-navigator-command:start -->\s*"
    r"```bash\n(?P<command>.*?)\n```\s*"
    r"<!-- first-week-navigator-command:end -->",
    re.DOTALL,
)
INGEST_COMMAND_RE = re.compile(
    r"<!-- first-week-ingest-command:start -->\s*"
    r"```bash\n(?P<command>.*?)\n```\s*"
    r"<!-- first-week-ingest-command:end -->",
    re.DOTALL,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: Path) -> dict:
    text = _read(path)
    assert text.startswith("---\n")
    _, raw, _ = text.split("---", 2)
    return yaml.safe_load(raw)


def _command_tokens(pattern: re.Pattern[str], guide: Path) -> list[str]:
    match = pattern.search(_read(guide))
    assert match is not None
    command = match.group("command").replace("\\\n", " ")
    return shlex.split(command)


@pytest.mark.parametrize(
    ("path", "peer", "permalink"),
    [
        (EN_GUIDE, "/ja/your-first-week/", "/en/your-first-week/"),
        (JA_GUIDE, "/en/your-first-week/", "/ja/your-first-week/"),
    ],
)
def test_frontmatter_contract(path: Path, peer: str, permalink: str) -> None:
    metadata = _frontmatter(path)
    assert metadata["nav_order"] == 8
    assert metadata["lang_peer"] == peer
    assert metadata["permalink"] == permalink


def test_guides_cover_all_seven_days_and_readmes_link_them() -> None:
    english = _read(EN_GUIDE)
    japanese = _read(JA_GUIDE)

    for day in range(1, 8):
        assert f"## Day {day} " in english
        assert f"## {day}日目 " in japanese

    assert "[Your First Week](docs/en/your-first-week.md)" in _read(ROOT / "README.md")
    assert "[最初の1週間](docs/ja/your-first-week.md)" in _read(ROOT / "README.ja.md")


@pytest.mark.parametrize("guide", [EN_GUIDE, JA_GUIDE])
def test_navigator_command_returns_the_documented_no_api_workflow(guide: Path) -> None:
    documented = _command_tokens(NAVIGATOR_COMMAND_RE, guide)
    assert documented[:3] == ["uv", "run", "python"]

    result = subprocess.run(
        [sys.executable, *documented[3:]],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    recommendation = json.loads(result.stdout)
    assert recommendation["primary_workflow"]["id"] == "market-regime-daily"
    assert recommendation["primary_workflow"]["api_profile"] == "no-api-basic"
    assert recommendation["no_api_path"] is True


@pytest.mark.parametrize("guide", [EN_GUIDE, JA_GUIDE])
def test_manual_journal_json_is_valid_and_complete(guide: Path, tmp_path: Path) -> None:
    text = _read(guide)
    displayed_match = MANUAL_JSON_RE.search(text)
    heredoc_match = MANUAL_HEREDOC_RE.search(text)
    assert displayed_match is not None
    assert heredoc_match is not None

    payload = json.loads(displayed_match.group("payload"))
    assert json.loads(heredoc_match.group("payload")) == payload

    assert payload["ticker"]
    assert payload["thesis_statement"]
    assert payload["thesis_type"] in {
        "dividend_income",
        "growth_momentum",
        "mean_reversion",
        "earnings_drift",
        "pivot_breakout",
    }

    documented = _command_tokens(INGEST_COMMAND_RE, guide)
    assert documented == [
        "uv",
        "run",
        "python",
        "skills/trader-memory-core/scripts/trader_memory_cli.py",
        "ingest",
        "--source",
        "manual",
        "--input",
        "first-week-inputs/manual-idea.json",
        "--state-dir",
        "state/first-week-theses",
    ]

    input_path = tmp_path / "manual-idea.json"
    state_dir = tmp_path / "theses"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    executable = [sys.executable, *documented[3:]]
    executable[executable.index("first-week-inputs/manual-idea.json")] = str(input_path)
    executable[executable.index("state/first-week-theses")] = str(state_dir)

    environment = os.environ.copy()
    environment["TRADER_MEMORY_CLI_INNER"] = "1"
    result = subprocess.run(
        executable,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert "Registered 1 thesis(es)" in result.stdout
    assert len(list(state_dir.glob("th_*.yaml"))) == 1


def test_timestamp_selector_excludes_breadth_history() -> None:
    pattern = "market_breadth_????-??-??_??????.json"
    assert fnmatch.fnmatch("market_breadth_2026-07-22_203519.json", pattern)
    assert not fnmatch.fnmatch("market_breadth_history.json", pattern)

    for guide in (EN_GUIDE, JA_GUIDE):
        text = _read(guide)
        assert f"-name '{pattern}'" in text
        assert "-name 'uptrend_analysis_????-??-??_??????.json'" in text


@pytest.mark.parametrize(
    ("breadth_score", "uptrend_score", "expected_recommendation"),
    [(80, 80, "REDUCE_ONLY"), (20, 20, "CASH_PRIORITY")],
)
def test_partial_exposure_inputs_are_fail_safe(
    tmp_path: Path,
    breadth_score: int,
    uptrend_score: int,
    expected_recommendation: str,
) -> None:
    breadth = tmp_path / "breadth.json"
    uptrend = tmp_path / "uptrend.json"
    output = tmp_path / "reports"
    breadth.write_text(json.dumps({"breadth_score": breadth_score}), encoding="utf-8")
    uptrend.write_text(json.dumps({"uptrend_score": uptrend_score}), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            "skills/exposure-coach/scripts/calculate_exposure.py",
            "--breadth",
            str(breadth),
            "--uptrend",
            str(uptrend),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report_path = next(output.glob("exposure_posture_*.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["inputs_provided"] == ["breadth", "uptrend"]
    assert report["confidence"] == "LOW"
    assert report["recommendation"] == expected_recommendation
    assert report["recommendation"] != "NEW_ENTRY_ALLOWED"


def test_empty_weekly_digest_is_a_valid_first_review(tmp_path: Path) -> None:
    state_dir = tmp_path / "theses"
    output_dir = tmp_path / "reports"
    state_dir.mkdir()

    subprocess.run(
        [
            sys.executable,
            "skills/weekly-performance-digest/scripts/generate_weekly_digest.py",
            "--state-dir",
            str(state_dir),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report_path = next(output_dir.glob("weekly_digest_*.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["total_trades"] == 0
