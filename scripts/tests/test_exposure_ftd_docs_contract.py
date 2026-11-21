"""Issue #832: Exposure Coach's hand-maintained FTD instructions match the code.

FTD is Follow-Through Day quality, used directly (higher = stronger rally
confirmation), with no failure-to-deliver reading, no inversion and no
standalone ceiling cut. ``generate_skill_docs.py --check`` skips the English
guide and the references, so this reads the text itself, both in the sources
and in the installable package.
"""

from __future__ import annotations

import importlib.util
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "exposure-coach"
PACKAGE = ROOT / "skill-packages" / "exposure-coach.skill"
GUIDE = ROOT / "docs" / "en" / "skills" / "exposure-coach.md"
FRAMEWORK = "references/exposure_framework.md"
REGIME_MAP = "references/regime_exposure_map.md"
FTD_PRODUCER = ROOT / "skills" / "ftd-detector" / "scripts" / "post_ftd_monitor.py"

STALE = re.compile(
    r"failure.to.deliver|FTD Score \(Inverted\)|FTD Anomal|systemic stress"
    r"|Stress indicator|Critical FTD level",
    re.IGNORECASE,
)


def _texts() -> list[tuple[str, str]]:
    texts = [("docs/en/skills/exposure-coach.md", GUIDE.read_text(encoding="utf-8"))]
    for rel in (FRAMEWORK, REGIME_MAP):
        texts.append((f"skills/exposure-coach/{rel}", (SKILL / rel).read_text(encoding="utf-8")))
    with zipfile.ZipFile(PACKAGE) as package:
        for rel in (FRAMEWORK, REGIME_MAP):
            texts.append(
                (f"{PACKAGE.name}:{rel}", package.read(f"exposure-coach/{rel}").decode("utf-8"))
            )
    return texts


TEXTS = _texts()


def _ftd_section(text: str) -> str:
    match = re.search(r"^### FTD Score.*?(?=^### )", text, re.MULTILINE | re.DOTALL)
    assert match, "exposure_framework.md has no FTD Score section"
    return match.group(0)


def _load_calculator(monkeypatch):
    scripts = SKILL / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "issue832_calculate_exposure", scripts / "calculate_exposure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name,text", TEXTS, ids=[name for name, _ in TEXTS])
def test_no_failure_to_deliver_or_inverted_reading(name: str, text: str) -> None:
    stale = [line for line in text.splitlines() if STALE.search(line)]
    assert not stale, f"{name}: {stale}"


@pytest.mark.parametrize("name,text", TEXTS, ids=[name for name, _ in TEXTS])
def test_ftd_is_described_as_follow_through_day(name: str, text: str) -> None:
    if name.endswith("exposure-coach.md"):
        rows = [line for line in text.splitlines() if line.startswith("| ftd-detector |")]
        assert rows and all("Follow-Through Day" in row for row in rows), rows
    elif name.endswith(FRAMEWORK):
        section = _ftd_section(text)
        assert "Follow-Through Day" in section
        assert "quality_score.total_score" in section
        assert "no inversion" in section
    else:
        assert "no ceiling adjustment of its own" in text


@pytest.mark.parametrize(
    "name,text", [t for t in TEXTS if t[0].endswith(FRAMEWORK)], ids=["source", "package"]
)
def test_framework_numbers_match_the_calculator(monkeypatch, name: str, text: str) -> None:
    calc = _load_calculator(monkeypatch)
    row = re.search(r"^\| FTD \| (\d+)% \|", text, re.MULTILINE)
    assert row and int(row.group(1)) / 100 == calc.WEIGHTS["ftd"]

    legacy = dict(re.findall(r"`(none|low|moderate|elevated|critical)` (\d+)", _ftd_section(text)))
    assert set(legacy) == {"none", "low", "moderate", "elevated", "critical"}
    for level, score in legacy.items():
        assert calc.extract_ftd_score({"anomaly_level": level}) == int(score), level
    assert calc.extract_ftd_score({"quality_score": {"total_score": 82}}) == 82


def test_documented_zero_signals_are_what_ftd_detector_emits() -> None:
    section = _ftd_section((SKILL / FRAMEWORK).read_text(encoding="utf-8"))
    zero_cases = re.findall(r"^- `([^`]+)`", section, re.MULTILINE)
    assert len(zero_cases) == 4, zero_cases
    producer = FTD_PRODUCER.read_text(encoding="utf-8")
    for signal in zero_cases:
        assert f'"{signal}"' in producer, signal


@pytest.mark.parametrize(
    "name,text", [t for t in TEXTS if t[0].endswith(FRAMEWORK)], ids=["source", "package"]
)
def test_framework_explains_lifecycle_warning_override(monkeypatch, name, text):
    monkeypatch.syspath_prepend(str(FTD_PRODUCER.parent))
    spec = importlib.util.spec_from_file_location("issue832_post_ftd_monitor", FTD_PRODUCER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = {
        "sp500": {
            "ftd": {
                "ftd_detected": True,
                "ftd_day_number": 4,
                "gain_pct": 2.0,
                "volume_above_avg": True,
            }
        },
        "nasdaq": {},
        "dual_confirmation": False,
        "post_ftd_distribution": {"days_monitored": 5, "distribution_count": 0},
        "ftd_invalidation": {"invalidated": False, "warning": False},
    }
    healthy = module.calculate_ftd_quality_score(state)
    assert healthy["total_score"] == 95 and healthy["signal"] == "Strong FTD"
    state["ftd_invalidation"]["warning"] = True
    warning = module.calculate_ftd_quality_score(state)
    assert warning["total_score"] == 59 and warning["signal"] == "FTD under pressure"
    section = _ftd_section(text)
    assert "base bands" in section
    assert "ftd_invalidation.warning" in section
    assert "FTD under pressure" in section
    assert re.search(r"cap[^\n]*59", section)
