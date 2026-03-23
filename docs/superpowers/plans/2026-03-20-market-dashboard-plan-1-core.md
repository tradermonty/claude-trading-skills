# Market Dashboard — Plan 1: Core Dashboard (Level 1 Advisory)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working, always-on Level 1 Advisory market dashboard — skills run on schedule, signal panel updates via HTMX, all drill-down pages accessible, mode selector persists settings. No Alpaca, no order execution.

**Architecture:** FastAPI app at `examples/market-dashboard/`. Skills run as subprocesses via `skills_runner.py`, writing timestamped JSON to `cache/`; the runner renames to fixed `cache/<skill>.json`. APScheduler drives cadences. HTMX polls `/api/signals` every 30s for the signal panel fragment. TradingView free widgets handle all live chart rendering. Settings stored in `settings.json`.

**Tech Stack:** FastAPI, Uvicorn, Jinja2, HTMX (CDN), APScheduler, python-dotenv, pytest, FastAPI TestClient

**Spec:** `docs/superpowers/specs/2026-03-20-market-dashboard-design.md`

**Scope note:** This is Plan 1 of 3. Plan 2 adds Alpaca portfolio + Semi-Auto order execution. Plan 3 adds Auto trading (pivot monitor, confidence check, learning system).

---

## File Map

```
examples/market-dashboard/
├── config.py                      # Skill registry, cadences, constants
├── skills_runner.py               # Subprocess runner + cache writer
├── settings_manager.py            # settings.json read/write
├── scheduler.py                   # APScheduler job setup
├── main.py                        # FastAPI app, routes, startup
├── templates/
│   ├── base.html                  # Layout A shell: top bar, ticker tape, grid
│   ├── dashboard.html             # Main view: chart + signal panel + bottom strip
│   ├── fragments/
│   │   ├── signals.html           # HTMX signal panel fragment
│   │   └── settings_modal.html   # Mode selector modal
│   └── detail/
│       ├── vcp.html
│       ├── ftd.html
│       ├── breadth.html
│       ├── uptrend.html
│       ├── market_top.html
│       ├── macro_regime.html
│       ├── themes.html
│       ├── exposure.html
│       ├── economic_cal.html
│       ├── earnings_cal.html
│       ├── news.html
│       ├── canslim.html
│       ├── druckenmiller.html
│       ├── edge_signals.html
│       ├── bubble.html
│       ├── pead.html
│       └── scenario.html
├── static/
│   └── style.css
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_skills_runner.py
│   ├── test_settings_manager.py
│   ├── test_scheduler.py
│   └── test_routes.py
├── cache/                         # auto-created on startup
├── .env.example
├── requirements.txt
└── CLAUDE.md
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `examples/market-dashboard/requirements.txt`
- Create: `examples/market-dashboard/.env.example`
- Create: `examples/market-dashboard/tests/__init__.py`
- Create: `examples/market-dashboard/config.py`

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi
uvicorn[standard]
jinja2
httpx
apscheduler
python-dotenv
pytest
pytest-asyncio
```

- [ ] **Step 2: Create `.env.example`**

```env
# Alpaca (required for Plan 2 — leave blank for Plan 1 Advisory)
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_PAPER=true
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Skill API keys — injected into subprocess environments
FMP_API_KEY=
FINVIZ_API_KEY=
ANTHROPIC_API_KEY=

# Dashboard settings (initial defaults — overridden by settings.json after first save)
TRADING_MODE=advisory
DEFAULT_RISK_PCT=1.0
MAX_POSITIONS=5
MAX_POSITION_SIZE_PCT=10.0
APP_PORT=8000
```

- [ ] **Step 3: Create `config.py`**

```python
"""Dashboard configuration: paths, skill registry, cadences."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = ROOT.parents[1]  # claude-trading-skills/
CACHE_DIR = ROOT / "cache"
SETTINGS_FILE = ROOT / "settings.json"

load_dotenv(ROOT / ".env")

# API keys injected into skill subprocesses via environment
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FINVIZ_API_KEY = os.environ.get("FINVIZ_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SKILL_TIMEOUT = int(os.environ.get("SKILL_TIMEOUT", "120"))
APP_PORT = int(os.environ.get("APP_PORT", "8000"))

# Initial defaults — overridden at runtime by settings.json
DEFAULT_TRADING_MODE = os.environ.get("TRADING_MODE", "advisory")
DEFAULT_RISK_PCT = float(os.environ.get("DEFAULT_RISK_PCT", "1.0"))
DEFAULT_MAX_POSITIONS = int(os.environ.get("MAX_POSITIONS", "5"))
DEFAULT_MAX_POSITION_SIZE_PCT = float(os.environ.get("MAX_POSITION_SIZE_PCT", "10.0"))

# Skill registry: name -> script path (relative to SKILLS_ROOT), output glob, and cadence info
# args that contain "{cache_dir}" are substituted at run time by skills_runner.py
SKILL_REGISTRY: dict[str, dict] = {
    "vcp-screener": {
        "script": "skills/vcp-screener/scripts/screen_vcp.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "vcp_screener_",
        "cadence_min": None,
        "at_open_once": True,
    },
    "canslim-screener": {
        "script": "skills/canslim-screener/scripts/screen_canslim.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "canslim_",
        "cadence_min": None,
        "at_open_once": True,
    },
    "ftd-detector": {
        "script": "skills/ftd-detector/scripts/ftd_detector.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "ftd_detector_",
        "cadence_min": 30,
    },
    "market-breadth-analyzer": {
        "script": "skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "market_breadth_",
        "cadence_min": 30,
    },
    "uptrend-analyzer": {
        "script": "skills/uptrend-analyzer/scripts/uptrend_analyzer.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "uptrend_analysis_",
        "cadence_min": 30,
    },
    "sector-analyst": {
        "script": "skills/sector-analyst/scripts/analyze_sector_rotation.py",
        "args": ["--json", "--save", "--output-dir", "{cache_dir}"],
        "output_prefix": "sector_",
        "cadence_min": 30,
    },
    "theme-detector": {
        "script": "skills/theme-detector/scripts/theme_detector.py",
        "args": ["--dynamic-stocks", "--output-dir", "{cache_dir}"],
        "output_prefix": "theme_detector_",
        "cadence_min": 30,
    },
    "exposure-coach": {
        "script": "skills/exposure-coach/scripts/calculate_exposure.py",
        "args": [
            "--breadth", "{cache_dir}/market-breadth-analyzer.json",
            "--uptrend", "{cache_dir}/uptrend-analyzer.json",
            "--regime", "{cache_dir}/macro-regime-detector.json",
            "--top-risk", "{cache_dir}/market-top-detector.json",
            "--ftd", "{cache_dir}/ftd-detector.json",
            "--theme", "{cache_dir}/theme-detector.json",
            "--sector", "{cache_dir}/sector-analyst.json",
            "--output-dir", "{cache_dir}",
        ],
        "output_prefix": "exposure_",
        "cadence_min": 30,
        "depends_on": ["sector-analyst"],
    },
    "market-top-detector": {
        "script": "skills/market-top-detector/scripts/market_top_detector.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "market_top_",
        "cadence_min": 60,
    },
    "macro-regime-detector": {
        "script": "skills/macro-regime-detector/scripts/macro_regime_detector.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "macro_regime_",
        "cadence_min": 90,
    },
    "stanley-druckenmiller-investment": {
        "script": "skills/stanley-druckenmiller-investment/scripts/strategy_synthesizer.py",
        "args": ["--reports-dir", "{cache_dir}", "--output-dir", "{cache_dir}"],
        "output_prefix": "druckenmiller_strategy_",
        "cadence_min": None,
        "pre_market_once": True,
    },
    "edge-signal-aggregator": {
        "script": "skills/edge-signal-aggregator/scripts/aggregate_signals.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "edge_signals_",
        "cadence_min": None,
        "pre_market_once": True,
    },
    "us-market-bubble-detector": {
        # bubble_scorer.py writes JSON to stdout (--output json); does not accept --output-dir.
        # skills_runner handles "stdout_capture": True by piping stdout to cache/<skill>.json directly.
        "script": "skills/us-market-bubble-detector/scripts/bubble_scorer.py",
        "args": ["--output", "json"],
        "stdout_capture": True,
        "output_prefix": None,  # stdout capture — no timestamped file to rename
        "cadence_min": None,
        "pre_market_once": True,
    },
    "market-news-analyst": {
        "script": None,  # No standalone script — skill is SKILL.md only; cache written manually
        "output_prefix": "market_news_",
        "cadence_min": None,
        "pre_market_once": True,
    },
    "scenario-analyzer": {
        "script": None,  # No standalone script
        "output_prefix": "scenario_",
        "cadence_min": None,
        "pre_market_once": True,
    },
    "economic-calendar-fetcher": {
        "script": "skills/economic-calendar-fetcher/scripts/get_economic_calendar.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "economic_calendar_",
        "cadence_min": None,
        "daily_6am": True,
    },
    "earnings-calendar": {
        "script": "skills/earnings-calendar/scripts/fetch_earnings_fmp.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "earnings_",
        "cadence_min": None,
        "daily_6am": True,
    },
    "institutional-flow-tracker": {
        "script": "skills/institutional-flow-tracker/scripts/track_institutional_flow.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "institutional_flow_",
        "cadence_min": None,
        "weekly_sunday": True,
    },
    "earnings-trade-analyzer": {
        "script": "skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "earnings_trade_",
        "cadence_min": None,
        "post_market_mwf": True,
    },
    "pead-screener": {
        "script": "skills/pead-screener/scripts/screen_pead.py",
        "args": ["--output-dir", "{cache_dir}"],
        "output_prefix": "pead_",
        "cadence_min": None,
        "post_market_mwf": True,
    },
}

# Signal panel: skills shown in the right panel (in display order)
SIGNAL_PANEL_SKILLS = [
    "ftd-detector",
    "uptrend-analyzer",
    "market-breadth-analyzer",
    "vcp-screener",
    "canslim-screener",
    "market-top-detector",
    "macro-regime-detector",
    "exposure-coach",
    "stanley-druckenmiller-investment",
]

# Detail page route -> template mapping
DETAIL_ROUTES = {
    "vcp": "vcp-screener",
    "ftd": "ftd-detector",
    "breadth": "market-breadth-analyzer",
    "uptrend": "uptrend-analyzer",
    "market_top": "market-top-detector",
    "macro_regime": "macro-regime-detector",
    "themes": "theme-detector",
    "exposure": "exposure-coach",
    "economic_cal": "economic-calendar-fetcher",
    "earnings_cal": "earnings-calendar",
    "news": "market-news-analyst",
    "canslim": "canslim-screener",
    "druckenmiller": "stanley-druckenmiller-investment",
    "edge_signals": "edge-signal-aggregator",
    "bubble": "us-market-bubble-detector",
    "pead": "pead-screener",
    "scenario": "scenario-analyzer",
}
```

- [ ] **Step 4: Create `tests/__init__.py`** (empty file)

- [ ] **Step 5: Write test**

```python
# tests/test_config.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT, SKILLS_ROOT, SKILL_REGISTRY, SIGNAL_PANEL_SKILLS, DETAIL_ROUTES


def test_skills_root_exists():
    assert SKILLS_ROOT.exists(), f"SKILLS_ROOT not found: {SKILLS_ROOT}"


def test_all_signal_panel_skills_in_registry():
    for skill in SIGNAL_PANEL_SKILLS:
        assert skill in SKILL_REGISTRY, f"{skill} missing from registry"


def test_all_detail_routes_in_registry():
    for route, skill in DETAIL_ROUTES.items():
        assert skill in SKILL_REGISTRY, f"detail/{route} maps to {skill} which is not in registry"


def test_skills_with_scripts_exist():
    """Scripts listed in registry must exist on disk."""
    for name, cfg in SKILL_REGISTRY.items():
        script = cfg.get("script")
        if script is None:
            continue
        path = SKILLS_ROOT / script
        assert path.exists(), f"{name}: script not found at {path}"
```

- [ ] **Step 6: Run test (expect failures on missing scripts — that reveals gaps early)**

```bash
cd examples/market-dashboard && uv run pytest tests/test_config.py -v 2>&1 | tail -30
```

Fix any script paths that don't exist (update `output_prefix` or `script` values in `SKILL_REGISTRY`). For skills whose scripts don't exist or whose paths differ, set `"script": None` and leave a `# TODO: verify path` comment.

- [ ] **Step 7: Commit**

```bash
git add examples/market-dashboard/
git commit -m "feat(market-dashboard): project scaffold — config, requirements, .env.example"
```

---

## Task 2: Skills Runner

**Files:**
- Create: `examples/market-dashboard/skills_runner.py`
- Create: `examples/market-dashboard/tests/test_skills_runner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_skills_runner.py
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_run_skill_success_renames_to_fixed_path(tmp_path):
    """A successful run finds the newest timestamped JSON and renames it."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    # Pre-create a timestamped output file (simulating what the skill writes)
    ts_file = tmp_path / "ftd_detector_2026-03-20_120000.json"
    ts_file.write_text(json.dumps({"generated_at": "2026-03-20T12:00:00", "score": 42}))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = runner.run_skill("ftd-detector")

    assert result is True
    fixed = tmp_path / "ftd-detector.json"
    assert fixed.exists()
    assert json.loads(fixed.read_text())["score"] == 42


def test_run_skill_failure_preserves_old_cache(tmp_path):
    """A failed run leaves the previous cache file intact."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    # Write existing cache
    old_cache = tmp_path / "ftd-detector.json"
    old_cache.write_text(json.dumps({"score": 99}))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="FMP error")
        result = runner.run_skill("ftd-detector")

    assert result is False
    assert json.loads(old_cache.read_text())["score"] == 99  # unchanged


def test_run_skill_writes_stderr_log(tmp_path):
    """Stderr from a failed run is written to <skill>.stderr.log."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
        runner.run_skill("ftd-detector")

    log = tmp_path / "ftd-detector.stderr.log"
    assert log.exists()
    assert "connection refused" in log.read_text()


def test_run_skill_substitutes_cache_dir_in_args(tmp_path):
    """Args containing {cache_dir} are substituted with the real cache path."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    with patch("skills_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        runner.run_skill("ftd-detector")

    call_args = mock_run.call_args[0][0]  # first positional arg = command list
    assert str(tmp_path) in call_args


def test_run_skill_no_script_returns_false(tmp_path):
    """Skills with script=None return False immediately (nothing to run)."""
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    result = runner.run_skill("market-news-analyst")
    assert result is False


def test_is_stale_returns_true_when_file_missing(tmp_path):
    from skills_runner import SkillsRunner
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))
    assert runner.is_stale("ftd-detector") is True


def test_is_stale_reads_generated_at_from_json(tmp_path):
    from skills_runner import SkillsRunner
    import datetime
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    cache = tmp_path / "ftd-detector.json"
    old_time = (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).isoformat()
    cache.write_text(json.dumps({"generated_at": old_time}))

    # cadence_min=30, threshold=60 min — 3h old is stale
    assert runner.is_stale("ftd-detector") is True


def test_is_stale_returns_false_for_fresh_file(tmp_path):
    from skills_runner import SkillsRunner
    import datetime
    runner = SkillsRunner(cache_dir=tmp_path, skills_root=Path("/fake"))

    cache = tmp_path / "ftd-detector.json"
    now = datetime.datetime.utcnow().isoformat()
    cache.write_text(json.dumps({"generated_at": now}))

    assert runner.is_stale("ftd-detector") is False
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd examples/market-dashboard && uv run pytest tests/test_skills_runner.py -v 2>&1 | tail -5
```

Expected: `ImportError: No module named 'skills_runner'`

- [ ] **Step 3: Implement `skills_runner.py`**

```python
"""Subprocess runner for trading skills. Writes timestamped JSON to fixed cache paths."""
from __future__ import annotations

import datetime
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config import SKILL_REGISTRY, SKILL_TIMEOUT


class SkillsRunner:
    def __init__(self, cache_dir: Path, skills_root: Path):
        self.cache_dir = cache_dir
        self.skills_root = skills_root
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run_skill(self, skill_name: str) -> bool:
        """Run a skill subprocess and cache its JSON output. Returns True on success."""
        cfg = SKILL_REGISTRY.get(skill_name)
        if cfg is None:
            print(f"[runner] Unknown skill: {skill_name}", file=sys.stderr)
            return False
        if cfg.get("script") is None:
            return False  # SKILL.md-only skill, no standalone script

        script = self.skills_root / cfg["script"]
        args = [
            a.replace("{cache_dir}", str(self.cache_dir))
            for a in cfg.get("args", [])
        ]
        cmd = [sys.executable, str(script)] + args
        stdout_capture = cfg.get("stdout_capture", False)

        stderr_log = self.cache_dir / f"{skill_name}.stderr.log"
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SKILL_TIMEOUT,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            stderr_log.write_text(f"Timeout after {SKILL_TIMEOUT}s")
            print(f"[runner] {skill_name}: timeout", file=sys.stderr)
            return False

        stderr_log.write_text(result.stderr or "")

        if result.returncode != 0:
            print(f"[runner] {skill_name}: failed (exit {result.returncode})", file=sys.stderr)
            return False

        if stdout_capture:
            # Skill writes JSON to stdout — save directly to fixed cache path
            fixed = self.cache_dir / f"{skill_name}.json"
            fixed.write_text(result.stdout)
            return True

        return self._promote_latest_output(skill_name, cfg.get("output_prefix", ""))

    def _promote_latest_output(self, skill_name: str, prefix: str) -> bool:
        """Find the most-recently-modified JSON matching prefix, rename to <skill>.json."""
        pattern = str(self.cache_dir / f"{prefix}*.json")
        matches = glob.glob(pattern)
        if not matches:
            return False
        # Sort by mtime (not alphabetically) to handle any timestamp format
        newest = max(matches, key=os.path.getmtime)
        fixed = self.cache_dir / f"{skill_name}.json"
        Path(newest).rename(fixed)
        return True

    def _subprocess_env(self) -> dict:
        """Build env dict with API keys injected."""
        from config import FMP_API_KEY, FINVIZ_API_KEY, ANTHROPIC_API_KEY
        env = os.environ.copy()
        if FMP_API_KEY:
            env["FMP_API_KEY"] = FMP_API_KEY
        if FINVIZ_API_KEY:
            env["FINVIZ_API_KEY"] = FINVIZ_API_KEY
        if ANTHROPIC_API_KEY:
            env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
        return env

    def is_stale(self, skill_name: str) -> bool:
        """Return True if cache is missing or older than 2× cadence."""
        cache_file = self.cache_dir / f"{skill_name}.json"
        if not cache_file.exists():
            return True
        try:
            data = json.loads(cache_file.read_text())
            generated_at = data.get("generated_at")
            if not generated_at:
                return True
            then = datetime.datetime.fromisoformat(generated_at)
            cfg = SKILL_REGISTRY.get(skill_name, {})
            cadence_min = cfg.get("cadence_min") or 120
            threshold = datetime.timedelta(minutes=cadence_min * 2)
            return (datetime.datetime.utcnow() - then) > threshold
        except Exception:
            return True

    def load_cache(self, skill_name: str) -> Optional[dict]:
        """Load cached JSON for a skill, or None if missing."""
        cache_file = self.cache_dir / f"{skill_name}.json"
        if not cache_file.exists():
            return None
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            return None
```

- [ ] **Step 4: Run tests — expect green**

```bash
cd examples/market-dashboard && uv run pytest tests/test_skills_runner.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add examples/market-dashboard/skills_runner.py examples/market-dashboard/tests/
git commit -m "feat(market-dashboard): skills runner — subprocess execution and cache management"
```

---

## Task 3: Settings Manager

**Files:**
- Create: `examples/market-dashboard/settings_manager.py`
- Create: `examples/market-dashboard/tests/test_settings_manager.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_settings_manager.py
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_load_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    s = sm.load()
    assert s["mode"] == "advisory"
    assert isinstance(s["default_risk_pct"], float)


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    sm.save({"mode": "semi_auto", "default_risk_pct": 1.5, "max_positions": 3,
             "max_position_size_pct": 8.0, "environment": "paper"})
    loaded = sm.load()
    assert loaded["mode"] == "semi_auto"
    assert loaded["default_risk_pct"] == 1.5


def test_get_mode_default(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    assert sm.get_mode() == "advisory"


def test_set_mode_persists(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    sm.set_mode("semi_auto")
    assert sm.get_mode() == "semi_auto"


def test_set_mode_rejects_invalid(tmp_path, monkeypatch):
    from settings_manager import SettingsManager
    monkeypatch.setattr("settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    sm = SettingsManager()
    try:
        sm.set_mode("turbo")
        assert False, "should have raised"
    except ValueError:
        pass
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `settings_manager.py`**

```python
"""Manages runtime settings persisted to settings.json."""
from __future__ import annotations

import json
import tempfile
import os
from pathlib import Path

from config import (
    SETTINGS_FILE, DEFAULT_TRADING_MODE, DEFAULT_RISK_PCT,
    DEFAULT_MAX_POSITIONS, DEFAULT_MAX_POSITION_SIZE_PCT,
)

VALID_MODES = {"advisory", "semi_auto", "auto"}
VALID_ENVIRONMENTS = {"paper", "live"}

_DEFAULTS = {
    "mode": DEFAULT_TRADING_MODE,
    "default_risk_pct": DEFAULT_RISK_PCT,
    "max_positions": DEFAULT_MAX_POSITIONS,
    "max_position_size_pct": DEFAULT_MAX_POSITION_SIZE_PCT,
    "environment": "paper",
}


class SettingsManager:
    def load(self) -> dict:
        if not SETTINGS_FILE.exists():
            return dict(_DEFAULTS)
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return {**_DEFAULTS, **data}
        except Exception:
            return dict(_DEFAULTS)

    def save(self, settings: dict) -> None:
        mode = settings.get("mode", DEFAULT_TRADING_MODE)
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")
        environment = settings.get("environment", "paper")
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(f"Invalid environment: {environment}. Must be paper or live")
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mktemp(dir=SETTINGS_FILE.parent, suffix=".json.tmp"))
        tmp.write_text(json.dumps(settings, indent=2))
        tmp.replace(SETTINGS_FILE)

    def get_mode(self) -> str:
        return self.load().get("mode", DEFAULT_TRADING_MODE)

    def set_mode(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")
        s = self.load()
        s["mode"] = mode
        self.save(s)
```

- [ ] **Step 4: Run tests**

```bash
cd examples/market-dashboard && uv run pytest tests/test_settings_manager.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add examples/market-dashboard/settings_manager.py examples/market-dashboard/tests/test_settings_manager.py
git commit -m "feat(market-dashboard): settings manager — mode/risk settings in settings.json"
```

---

## Task 4: FastAPI Core + Routes

**Files:**
- Create: `examples/market-dashboard/main.py`
- Create: `examples/market-dashboard/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_routes.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient


def make_client():
    from main import app
    return TestClient(app)


def test_root_returns_200():
    client = make_client()
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_api_signals_returns_html_fragment():
    client = make_client()
    r = client.get("/api/signals")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_api_market_state_returns_json():
    client = make_client()
    r = client.get("/api/market-state")
    assert r.status_code == 200
    data = r.json()
    assert "state" in data
    assert data["state"] in ("pre_market", "market_open", "market_closed")


def test_detail_vcp_returns_200():
    client = make_client()
    r = client.get("/detail/vcp")
    assert r.status_code == 200


def test_detail_ftd_returns_200():
    client = make_client()
    r = client.get("/detail/ftd")
    assert r.status_code == 200


def test_detail_unknown_returns_404():
    client = make_client()
    r = client.get("/detail/notapage")
    assert r.status_code == 404


def test_get_settings_returns_html():
    client = make_client()
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_post_settings_updates_mode():
    client = make_client()
    r = client.post("/api/settings", data={"mode": "semi_auto", "default_risk_pct": "1.5",
                                            "max_positions": "5", "max_position_size_pct": "10.0",
                                            "environment": "paper"})
    assert r.status_code == 200


def test_skill_refresh_returns_202():
    client = make_client()
    r = client.post("/api/skill/ftd-detector/refresh")
    assert r.status_code == 202


def test_static_css_served():
    client = make_client()
    r = client.get("/static/style.css")
    assert r.status_code == 200
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Create stub templates** (needed for routes to render)

Create `templates/base.html` with one line: `{% block content %}{% endblock %}`
Create `templates/dashboard.html` with: `{% extends "base.html" %}{% block content %}<p>Dashboard</p>{% endblock %}`
Create `templates/fragments/signals.html` with: `<div id="signals">signals</div>`
Create `templates/fragments/settings_modal.html` with: `<div id="modal">settings</div>`
Create `templates/detail/vcp.html`, `ftd.html`, and all other detail pages — each with one line: `{% extends "base.html" %}{% block content %}<h2>{{ skill_name }}</h2>{% endblock %}`
Create `static/style.css` with one comment: `/* dark theme */`

- [ ] **Step 4: Implement `main.py`**

```python
"""FastAPI application — market dashboard."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import CACHE_DIR, DETAIL_ROUTES, ROOT, SKILLS_ROOT, SIGNAL_PANEL_SKILLS, SKILL_REGISTRY
from settings_manager import SettingsManager
from skills_runner import SkillsRunner

app = FastAPI(title="Market Dashboard")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

settings_manager = SettingsManager()
runner = SkillsRunner(cache_dir=CACHE_DIR, skills_root=SKILLS_ROOT)


@app.on_event("startup")
async def startup():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Scheduler started here in Task 10
    # Alpaca client started here in Plan 2


def _market_state() -> str:
    """Return current market state string based on ET time."""
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    weekday = now_et.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if weekday >= 5:
        return "market_closed"
    t = now_et.time()
    if t.hour < 7:
        return "market_closed"
    if t.hour < 9 or (t.hour == 9 and t.minute < 30):
        return "pre_market"
    if t.hour < 16:
        return "market_open"
    return "market_closed"


def _build_signals_context() -> dict[str, Any]:
    """Load signal panel data from cache."""
    signals = []
    for skill_name in SIGNAL_PANEL_SKILLS:
        data = runner.load_cache(skill_name)
        stale = runner.is_stale(skill_name)
        signals.append({
            "skill": skill_name,
            "data": data,
            "stale": stale,
        })
    return {"signals": signals}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = {
        "request": request,
        "market_state": _market_state(),
        "settings": settings_manager.load(),
        **_build_signals_context(),
    }
    return templates.TemplateResponse("dashboard.html", ctx)


@app.get("/api/signals", response_class=HTMLResponse)
async def api_signals(request: Request):
    ctx = {"request": request, **_build_signals_context()}
    return templates.TemplateResponse("fragments/signals.html", ctx)


@app.get("/api/market-state")
async def api_market_state():
    return JSONResponse({"state": _market_state()})


@app.get("/detail/{page}", response_class=HTMLResponse)
async def detail(request: Request, page: str):
    skill_name = DETAIL_ROUTES.get(page)
    if skill_name is None:
        raise HTTPException(status_code=404, detail="Unknown detail page")
    data = runner.load_cache(skill_name)
    stale = runner.is_stale(skill_name)
    ctx = {
        "request": request,
        "skill_name": skill_name,
        "page": page,
        "data": data,
        "stale": stale,
        "settings": settings_manager.load(),
    }
    return templates.TemplateResponse(f"detail/{page}.html", ctx)


@app.get("/api/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    ctx = {"request": request, "settings": settings_manager.load()}
    return templates.TemplateResponse("fragments/settings_modal.html", ctx)


@app.post("/api/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    mode: str = Form(...),
    default_risk_pct: float = Form(...),
    max_positions: int = Form(...),
    max_position_size_pct: float = Form(...),
    environment: str = Form(...),
):
    settings_manager.save({
        "mode": mode,
        "default_risk_pct": default_risk_pct,
        "max_positions": max_positions,
        "max_position_size_pct": max_position_size_pct,
        "environment": environment,
    })
    ctx = {"request": request, "settings": settings_manager.load()}
    return templates.TemplateResponse("fragments/settings_modal.html", ctx)


@app.post("/api/skill/{skill_name}/refresh")
async def skill_refresh(skill_name: str):
    if skill_name not in SKILL_REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown skill")
    asyncio.get_running_loop().run_in_executor(None, runner.run_skill, skill_name)
    return Response(status_code=202)
```

- [ ] **Step 5: Run tests**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py -v
```

Expected: all tests PASS (template stubs render, routes return correct status codes).

- [ ] **Step 6: Commit**

```bash
git add examples/market-dashboard/main.py examples/market-dashboard/templates/ examples/market-dashboard/static/ examples/market-dashboard/tests/test_routes.py
git commit -m "feat(market-dashboard): FastAPI core — routes, HTMX endpoints, settings modal"
```

---

## Task 5: Dark Theme CSS + Base Template

**Files:**
- Modify: `examples/market-dashboard/static/style.css`
- Modify: `examples/market-dashboard/templates/base.html`

- [ ] **Step 1: Replace `style.css`** with dark theme (dark navy/green monospace aesthetic, Layout A):

```css
/* Market Dashboard — Dark Theme */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg-base: #0d1117;
  --bg-surface: #161b22;
  --bg-panel: #1e2a3a;
  --border: #30363d;
  --green: #4ade80;
  --yellow: #facc15;
  --red: #f87171;
  --blue: #38bdf8;
  --muted: #8b949e;
  --text: #e6edf3;
  --font-mono: 'Consolas', 'Menlo', monospace;
}

body {
  background: var(--bg-base);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 13px;
  min-height: 100vh;
}

/* Live border for LIVE + Auto mode */
body.live-auto-mode {
  outline: 3px solid var(--red);
  outline-offset: -3px;
}

/* Top bar */
.topbar {
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}
.topbar-title { font-size: 14px; font-weight: bold; color: var(--green); }
.market-state { font-size: 11px; padding: 2px 8px; border-radius: 3px; }
.state-pre-market  { background: #1e3a2e; color: var(--yellow); border: 1px solid var(--yellow); }
.state-market-open { background: #1e3a2e; color: var(--green); border: 1px solid var(--green); }
.state-market-closed { background: #2a1a1a; color: var(--muted); border: 1px solid var(--border); }

.env-badge { font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: bold; }
.env-paper { background: #1e3a2e; color: var(--green); border: 1px solid var(--green); }
.env-live  { background: #3a2800; color: var(--yellow); border: 1px solid var(--yellow); }

.mode-badge {
  cursor: pointer; font-size: 11px; padding: 2px 10px; border-radius: 3px;
  background: var(--bg-panel); border: 1px solid var(--border); color: var(--text);
}
.mode-badge:hover { border-color: var(--green); }

/* Main grid */
.main-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 12px;
  padding: 12px;
  height: calc(100vh - 120px);
}

/* Signal panel */
.signal-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow-y: auto;
  padding: 8px;
}

.signal-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  text-decoration: none;
  color: var(--text);
  border: 1px solid transparent;
  margin-bottom: 4px;
}
.signal-row:hover { border-color: var(--green); background: var(--bg-panel); }
.signal-row.stale { opacity: 0.6; }

.signal-name { font-size: 11px; color: var(--muted); }
.signal-value { font-size: 14px; font-weight: bold; }
.signal-value.green { color: var(--green); }
.signal-value.yellow { color: var(--yellow); }
.signal-value.red { color: var(--red); }
.signal-value.muted { color: var(--muted); }

.stale-badge {
  font-size: 9px; padding: 1px 4px; border-radius: 2px;
  background: #3a2800; color: var(--yellow); border: 1px solid var(--yellow);
}

/* Bottom strip */
.bottom-strip {
  display: grid;
  gap: 12px;
  padding: 0 12px 12px;
}
.bottom-strip.market-hours { grid-template-columns: 1fr 1fr 1fr; }
.bottom-strip.pre-market   { grid-template-columns: 1fr 1fr; }

.bottom-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
}
.panel-title {
  font-size: 10px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.05em; margin-bottom: 8px;
}

/* Chart container */
.chart-container {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

/* Detail pages */
.detail-page { padding: 16px; max-width: 1200px; margin: 0 auto; }
.detail-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border);
}
.back-nav { color: var(--muted); text-decoration: none; font-size: 12px; }
.back-nav:hover { color: var(--text); }

.summary-strip {
  display: flex; gap: 24px; margin-bottom: 16px;
  background: var(--bg-surface); border: 1px solid var(--border);
  border-radius: 6px; padding: 12px;
}
.summary-metric { text-align: center; }
.summary-label { font-size: 10px; color: var(--muted); text-transform: uppercase; margin-bottom: 4px; }
.summary-value { font-size: 20px; font-weight: bold; color: var(--green); }

/* Data table */
.data-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 16px; }
.data-table th {
  padding: 6px 8px; text-align: left; color: var(--muted);
  border-bottom: 1px solid var(--border); font-weight: normal;
}
.data-table td { padding: 6px 8px; border-bottom: 1px solid #1e2a3a; }
.data-table tr:hover td { background: var(--bg-panel); }
.data-table tr.row-alt td { background: var(--bg-surface); }

.execute-btn {
  background: #1e3a2e; border: 1px solid var(--green); border-radius: 4px;
  padding: 2px 10px; color: var(--green); cursor: pointer; font-size: 11px;
  font-family: var(--font-mono);
}
.execute-btn:hover { background: var(--green); color: #000; }

/* Refresh btn */
.refresh-btn {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 4px;
  padding: 4px 12px; color: var(--muted); cursor: pointer; font-size: 11px;
  font-family: var(--font-mono);
}
.refresh-btn:hover { border-color: var(--green); color: var(--text); }

/* Settings modal overlay */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 200;
  display: flex; align-items: center; justify-content: center;
}
.modal-box {
  background: var(--bg-surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px; min-width: 360px;
}
.modal-title { font-size: 14px; color: var(--green); margin-bottom: 16px; }
.form-row { margin-bottom: 12px; }
.form-label { font-size: 10px; color: var(--muted); text-transform: uppercase; margin-bottom: 4px; }
.form-input {
  width: 100%; background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text); padding: 6px 8px; font-family: var(--font-mono);
  font-size: 12px;
}
.form-input:focus { border-color: var(--green); outline: none; }

.btn-primary {
  background: var(--green); color: #000; border: none; border-radius: 4px;
  padding: 6px 18px; font-weight: bold; cursor: pointer; font-family: var(--font-mono);
}
.btn-secondary {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 4px;
  padding: 6px 14px; color: var(--muted); cursor: pointer; font-family: var(--font-mono);
}

/* Ticker tape strip */
.ticker-tape { height: 44px; overflow: hidden; }
```

- [ ] **Step 2: Replace `templates/base.html`** with full Layout A shell:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Dashboard</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body class="{% if settings.environment == 'live' and settings.mode == 'auto' %}live-auto-mode{% endif %}">

  <!-- Top bar -->
  <div class="topbar">
    <span class="topbar-title">📊 Market Dashboard</span>
    <span class="market-state state-{{ market_state | default('market_closed') | replace('_', '-') }}">
      {% if market_state == 'pre_market' %}Pre-Market
      {% elif market_state == 'market_open' %}Market Open
      {% else %}Market Closed{% endif %}
    </span>
    <span class="env-badge {% if settings.environment == 'live' %}env-live{% else %}env-paper{% endif %}">
      {% if settings.environment == 'live' %}💰 LIVE{% else %}📄 PAPER{% endif %}
    </span>
    <span class="mode-badge"
          hx-get="/api/settings"
          hx-target="#modal-container"
          hx-swap="innerHTML">
      {% if settings.mode == 'auto' %}🤖 Auto
      {% elif settings.mode == 'semi_auto' %}✅ Semi-Auto
      {% else %}👁 Advisory{% endif %}
    </span>
    <div style="margin-left:auto; font-size:11px; color:#8b949e;" id="clock"></div>
    <script>
      (function tick(){
        const el = document.getElementById('clock');
        if(el) el.textContent = new Date().toLocaleTimeString('en-US', {timeZone:'America/New_York', hour12:false}) + ' ET';
        setTimeout(tick, 1000);
      })();
    </script>
  </div>

  <!-- TradingView Ticker Tape -->
  <div class="ticker-tape">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {
        "symbols": [
          {"proName": "FOREXCOM:SPXUSD", "title": "S&P 500"},
          {"proName": "NASDAQ:QQQ", "title": "QQQ"},
          {"proName": "CBOE:VIX", "title": "VIX"},
          {"proName": "AMEX:SPY", "title": "SPY"},
          {"proName": "NASDAQ:NVDA", "title": "NVDA"},
          {"proName": "TVC:DXY", "title": "DXY"}
        ],
        "showSymbolLogo": false,
        "colorTheme": "dark",
        "isTransparent": true,
        "displayMode": "adaptive",
        "locale": "en"
      }
      </script>
    </div>
  </div>

  {% block content %}{% endblock %}

  <!-- Modal container (settings modal appears here) -->
  <div id="modal-container"></div>

</body>
</html>
```

- [ ] **Step 3: Run routes test to confirm templates still render**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py -v
```

- [ ] **Step 4: Commit**

```bash
git add examples/market-dashboard/static/style.css examples/market-dashboard/templates/base.html
git commit -m "feat(market-dashboard): dark theme CSS and base template (Layout A)"
```

---

## Task 6: Dashboard + Signal Panel Fragment

**Files:**
- Modify: `examples/market-dashboard/templates/dashboard.html`
- Modify: `examples/market-dashboard/templates/fragments/signals.html`

- [ ] **Step 1: Write dashboard.html** (extends base, 2-col grid + bottom strip)

```html
{% extends "base.html" %}
{% block content %}

<div class="main-grid">
  <!-- Left: TradingView chart -->
  <div class="chart-container">
    <div class="tradingview-widget-container" style="height:100%">
      <div class="tradingview-widget-container__widget" style="height:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {
        "autosize": true,
        "symbol": "NASDAQ:QQQ",
        "interval": "D",
        "timezone": "America/New_York",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "hide_top_toolbar": false,
        "hide_legend": false,
        "allow_symbol_change": true,
        "support_host": "https://www.tradingview.com"
      }
      </script>
    </div>
  </div>

  <!-- Right: Signal panel (HTMX auto-refresh every 30s)
       The outer #signal-panel div is the HTMX swap target.
       /api/signals returns the inner <div class="signal-panel"> content.
       hx-swap="innerHTML" replaces the contents of #signal-panel, not the div itself,
       so the nested signal-panel div from the response lands inside #signal-panel correctly. -->
  <div id="signal-panel"
       hx-get="/api/signals"
       hx-trigger="every 30s"
       hx-swap="innerHTML"
       style="height:100%; overflow-y:auto;">
    {% include "fragments/signals.html" %}
  </div>
</div>

<!-- Bottom strip -->
<div class="bottom-strip {% if market_state == 'pre_market' %}pre-market{% else %}market-hours{% endif %}">
  {% if market_state == 'pre_market' %}
    <!-- Pre-Market: news brief + schedule -->
    <div class="bottom-panel">
      <div class="panel-title">Pre-Market Brief</div>
      {% set news = namespace(data=none) %}
      {# Load from cache in route context — see detail/news.html for full view #}
      <a href="/detail/news" style="color:#38bdf8; font-size:11px;">→ View full news analysis</a>
    </div>
    <div class="bottom-panel">
      <div class="panel-title">Today's Schedule</div>
      <a href="/detail/economic_cal" style="color:#38bdf8; font-size:11px;">→ Economic calendar</a>
      &nbsp;·&nbsp;
      <a href="/detail/earnings_cal" style="color:#38bdf8; font-size:11px;">→ Earnings</a>
    </div>
  {% else %}
    <!-- Market Hours: portfolio + themes + events -->
    <div class="bottom-panel" id="portfolio-panel">
      <div class="panel-title">Portfolio (Alpaca)</div>
      <div style="color:#8b949e; font-size:11px;">Connect Alpaca in Plan 2</div>
    </div>
    <div class="bottom-panel">
      <div class="panel-title">Top Themes</div>
      <a href="/detail/themes" style="color:#38bdf8; font-size:11px;">→ Theme Detector</a>
    </div>
    <div class="bottom-panel">
      <div class="panel-title">Today's Events</div>
      <a href="/detail/economic_cal" style="color:#38bdf8; font-size:11px;">→ Economic</a>
      &nbsp;·&nbsp;
      <a href="/detail/earnings_cal" style="color:#38bdf8; font-size:11px;">→ Earnings</a>
    </div>
  {% endif %}
</div>

{% endblock %}
```

- [ ] **Step 2: Write `fragments/signals.html`** — signal panel rows

```html
{# This fragment is the innerHTML of #signal-panel (in dashboard.html).
   Do NOT wrap in an outer div here — the parent #signal-panel is the container.
   Adding a wrapper div would cause nesting: <div id="signal-panel"><div class="signal-panel">... #}

<div style="font-size:10px; color:#8b949e; padding:4px 8px 8px; text-transform:uppercase; letter-spacing:.05em;">
    Signal Panel
  </div>

  {% macro score_color(score) %}
    {% if score is not none %}
      {% if score >= 70 %}green{% elif score >= 40 %}yellow{% else %}red{% endif %}
    {% else %}muted{% endif %}
  {% endmacro %}

  {% for item in signals %}
    {% set data = item.data %}
    {% set skill = item.skill %}
    {% set route = skill.replace('-', '_').replace('_analyzer', '').replace('_detector', '').replace('_screener', '') %}

    {# Map skill names to detail routes #}
    {% if skill == 'vcp-screener' %}{% set route = 'vcp' %}
    {% elif skill == 'ftd-detector' %}{% set route = 'ftd' %}
    {% elif skill == 'market-breadth-analyzer' %}{% set route = 'breadth' %}
    {% elif skill == 'uptrend-analyzer' %}{% set route = 'uptrend' %}
    {% elif skill == 'market-top-detector' %}{% set route = 'market_top' %}
    {% elif skill == 'macro-regime-detector' %}{% set route = 'macro_regime' %}
    {% elif skill == 'exposure-coach' %}{% set route = 'exposure' %}
    {% elif skill == 'stanley-druckenmiller-investment' %}{% set route = 'druckenmiller' %}
    {% elif skill == 'canslim-screener' %}{% set route = 'canslim' %}
    {% endif %}

    <a href="/detail/{{ route }}" class="signal-row {% if item.stale %}stale{% endif %}">
      <div>
        <div class="signal-name">
          {% if skill == 'ftd-detector' %}FTD Detector
          {% elif skill == 'uptrend-analyzer' %}Uptrend Analyzer
          {% elif skill == 'market-breadth-analyzer' %}Market Breadth
          {% elif skill == 'vcp-screener' %}VCP Screener
          {% elif skill == 'canslim-screener' %}CANSLIM
          {% elif skill == 'market-top-detector' %}Market Top Risk
          {% elif skill == 'macro-regime-detector' %}Macro Regime
          {% elif skill == 'exposure-coach' %}Exposure Coach
          {% elif skill == 'stanley-druckenmiller-investment' %}Druckenmiller
          {% else %}{{ skill }}{% endif %}
        </div>
        {% if data %}
          <div style="font-size:10px; color:#8b949e; margin-top:2px;">
            {{ data.get('generated_at', '')[:16] | replace('T', ' ') }}
          </div>
        {% endif %}
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        {% if data %}
          {% set score = data.get('composite', {}).get('score') or data.get('score') or data.get('composite_score') %}
          <span class="signal-value {{ score_color(score) }}">
            {% if score is not none %}{{ score | round(0) | int }}
            {% elif skill == 'vcp-screener' %}{{ data.get('candidates', []) | length }} cand
            {% elif skill == 'canslim-screener' %}{{ data.get('candidates', []) | length }} cand
            {% else %}—{% endif %}
          </span>
        {% else %}
          <span class="signal-value muted">—</span>
        {% endif %}
        {% if item.stale %}<span class="stale-badge">STALE</span>{% endif %}
        <span style="color:#30363d; font-size:12px;">›</span>
      </div>
    </a>
  {% endfor %}
</div>
```

- [ ] **Step 3: Run routes test**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py -v
```

- [ ] **Step 4: Manual smoke test** — start the server, open the dashboard in a browser:

```bash
cd examples/market-dashboard && uv run uvicorn main:app --port 8000
```

Open `http://localhost:8000`. Verify: TradingView widgets load, signal panel shows (with `—` values since cache is empty), bottom strip adapts to market state.

- [ ] **Step 5: Commit**

```bash
git add examples/market-dashboard/templates/
git commit -m "feat(market-dashboard): dashboard template — TradingView chart + HTMX signal panel + bottom strip"
```

---

## Task 7: Settings Modal

**Files:**
- Modify: `examples/market-dashboard/templates/fragments/settings_modal.html`

- [ ] **Step 1: Replace stub with full settings modal**

```html
<div class="modal-overlay" onclick="if(event.target===this) this.remove()">
  <div class="modal-box">
    <div class="modal-title">⚙️ Dashboard Settings</div>

    {% if settings.environment == 'live' and settings.mode == 'auto' %}
    <div style="background:#3a1a1a; border:1px solid #f87171; border-radius:4px; padding:8px; margin-bottom:12px; font-size:11px; color:#f87171;">
      ⚠️ LIVE TRADING + AUTO MODE ACTIVE — red border indicates real money is at risk
    </div>
    {% endif %}

    <form hx-post="/api/settings" hx-target="#modal-container" hx-swap="innerHTML">
      <!-- Trading Mode -->
      <div class="form-row">
        <div class="form-label">Trading Mode</div>
        <select name="mode" class="form-input">
          <option value="advisory" {% if settings.mode == 'advisory' %}selected{% endif %}>Level 1 — Advisory</option>
          <option value="semi_auto" {% if settings.mode == 'semi_auto' %}selected{% endif %}>Level 2 — Semi-Auto</option>
          <option value="auto" {% if settings.mode == 'auto' %}selected{% endif %}>Level 3 — Auto ⚠️</option>
        </select>
      </div>

      <!-- Environment -->
      <div class="form-row">
        <div class="form-label">Environment</div>
        <select name="environment" class="form-input">
          <option value="paper" {% if settings.environment == 'paper' %}selected{% endif %}>📄 Paper Trading</option>
          <option value="live" {% if settings.environment == 'live' %}selected{% endif %}>💰 Live Trading</option>
        </select>
        {% if settings.environment == 'paper' %}
        <div style="font-size:10px; color:#4ade80; margin-top:4px;">Switching to Live requires typing CONFIRM LIVE TRADING</div>
        {% endif %}
      </div>

      <!-- Risk settings -->
      <div class="form-row">
        <div class="form-label">Default Risk % per Trade</div>
        <input type="number" name="default_risk_pct" class="form-input"
               value="{{ settings.default_risk_pct }}" min="0.1" max="5.0" step="0.1">
      </div>
      <div class="form-row">
        <div class="form-label">Max Open Positions</div>
        <input type="number" name="max_positions" class="form-input"
               value="{{ settings.max_positions }}" min="1" max="20">
      </div>
      <div class="form-row">
        <div class="form-label">Max Position Size (% of account)</div>
        <input type="number" name="max_position_size_pct" class="form-input"
               value="{{ settings.max_position_size_pct }}" min="1" max="50" step="0.5">
      </div>

      <div style="display:flex; gap:8px; margin-top:16px;">
        <button type="submit" class="btn-primary">Save</button>
        <button type="button" class="btn-secondary" onclick="document.getElementById('modal-container').innerHTML=''">Cancel</button>
      </div>
    </form>
  </div>
</div>
```

- [ ] **Step 2: Add Live Trading confirmation guard to `main.py`**

In `post_settings`, add guard before saving:

The `settings_manager.save()` already validates `mode` and `environment` values — invalid values raise `ValueError` which FastAPI surfaces as a 500. The full Paper→Live guard (requiring `CONFIRM LIVE TRADING` typed by user) is added in Plan 2 via a JS confirmation dialog. In Plan 1, the environment selector is present but switches without a guard — **this is intentional** since Plan 1 has no Alpaca and no real trading risk.

- [ ] **Step 3: Run tests**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py -v
```

- [ ] **Step 4: Commit**

```bash
git add examples/market-dashboard/templates/fragments/settings_modal.html examples/market-dashboard/main.py
git commit -m "feat(market-dashboard): settings modal — mode selector, environment badge, risk controls"
```

---

## Task 8: All Drill-Down Pages

**Files:**
- Modify: all `templates/detail/*.html` files (replace one-line stubs with full content)

The detail pages all share the same structure. Replace each stub with a proper template. Build a reusable `_detail_base` pattern using Jinja2 template inheritance.

- [ ] **Step 1: Update detail pages** — Replace all stubs with full templates.

Each detail page uses this pattern:

```html
{# templates/detail/vcp.html #}
{% extends "base.html" %}
{% block content %}
<div class="detail-page">
  <div class="detail-header">
    <a href="/" class="back-nav">← Dashboard</a>
    <div style="display:flex; gap:12px; align-items:center;">
      {% if stale %}<span class="stale-badge">STALE — data may be outdated</span>{% endif %}
      <span style="font-size:11px; color:#8b949e;">
        {{ data.get('generated_at', 'Never')[:16] | replace('T', ' ') if data else 'No data' }}
      </span>
      <button class="refresh-btn"
              hx-post="/api/skill/vcp-screener/refresh"
              hx-swap="none">↻ Refresh now</button>
    </div>
  </div>

  <h2 style="font-size:14px; color:#4ade80; margin-bottom:12px;">VCP Screener</h2>

  {% if data %}
    <div class="summary-strip">
      <div class="summary-metric">
        <div class="summary-label">Candidates</div>
        <div class="summary-value">{{ data.get('candidates', []) | length }}</div>
      </div>
      <div class="summary-metric">
        <div class="summary-label">Near Pivot (&lt;3%)</div>
        <div class="summary-value" style="color:#facc15;">
          {{ data.get('candidates', []) | selectattr('pivot_distance_pct', 'lt', 3) | list | length }}
        </div>
      </div>
      <div class="summary-metric">
        <div class="summary-label">Avg Score</div>
        <div class="summary-value" style="color:#e6edf3;">
          {{ (data.get('candidates', []) | map(attribute='score') | sum) / ([data.get('candidates', []) | length, 1] | max) | round(1) if data.get('candidates') else '—' }}
        </div>
      </div>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th>Ticker</th><th>Score</th><th>Stage</th>
          <th>Pivot Dist</th><th>Entry</th><th>Stop</th><th>Size</th>
          {% if settings.mode != 'advisory' %}<th>Action</th>{% endif %}
        </tr>
      </thead>
      <tbody>
        {% for c in data.get('candidates', []) %}
        <tr class="{% if loop.index is odd %}row-alt{% endif %}">
          <td style="color:#38bdf8; font-weight:bold;">{{ c.get('ticker', '?') }}</td>
          <td style="color:{% if c.get('score', 0) >= 80 %}#4ade80{% elif c.get('score', 0) >= 60 %}#facc15{% else %}#f87171{% endif %};">
            {{ c.get('score', '—') }}
          </td>
          <td style="color:#4ade80;">{{ c.get('stage', '—') }}</td>
          <td style="color:{% if c.get('pivot_distance_pct', 99) < 3 %}#facc15{% else %}#8b949e{% endif %};">
            +{{ c.get('pivot_distance_pct', '—') }}%
          </td>
          <td>${{ c.get('entry_price', '—') }}</td>
          <td style="color:#f87171;">${{ c.get('stop_price', '—') }}</td>
          <td>{{ c.get('position_size', '—') }} sh</td>
          {% if settings.mode != 'advisory' %}
          <td><button class="execute-btn">Execute</button></td>
          {% endif %}
        </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p style="color:#8b949e; padding:16px;">No data yet — waiting for first skill run.</p>
  {% endif %}
</div>
{% endblock %}
```

Apply the same structural pattern to **all 17 detail templates**, adapting the summary metrics and table columns to each skill's JSON output. Key content per page:

| Template | Summary metrics | Table columns |
|---|---|---|
| `ftd.html` | Market state, Rally day, FTD score | Date, Index, Volume, Score, Status |
| `breadth.html` | Composite score, 200DMA %, 50DMA % | Component, Value, Score, Status |
| `uptrend.html` | Composite score, Uptrend ratio, Trend | Component, Value, Score |
| `market_top.html` | Risk score, Zone, Signals | Signal type, Value, Weight |
| `macro_regime.html` | Regime, Score, Confidence | Factor, Value, Signal |
| `themes.html` | Top theme, Theme count | Theme, Score, Stocks |
| `exposure.html` | Exposure ceiling, Bias, Recommendation | Component, Weight, Signal |
| `economic_cal.html` | Events today, High impact | Date, Event, Impact, Forecast |
| `earnings_cal.html` | Reports today, Reports this week | Ticker, Date, Time, EPS est |
| `news.html` | Top story, Impact level | Headline, Impact, Source |
| `canslim.html` | Candidates, Near pivot, Avg score | Ticker, Score, Criteria met |
| `druckenmiller.html` | Conviction, Regime, Action | Factor, Signal, Weight |
| `edge_signals.html` | Top signal, Signal count | Signal, Conviction, Source |
| `bubble.html` | Bubble risk score, Phase | Indicator, Value, Signal |
| `pead.html` | PEAD candidates, High grade | Ticker, Grade, Gap %, Setup |
| `scenario.html` | Primary scenario, 18mo horizon | Scenario, Probability, Impact |

> **Known Plan 1 limitation:** `/detail/news` and `/detail/scenario` will always show "No data yet" because `market-news-analyst` and `scenario-analyzer` have no standalone Python scripts (`script: None`). These pages are reachable and render correctly — they just display the empty-state message. Cache for these skills can only be written manually in Plan 1. Plan 2/3 may add integration if standalone scripts become available.

- [ ] **Step 2: Run routes tests for detail pages**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py::test_detail_vcp_returns_200 tests/test_routes.py::test_detail_ftd_returns_200 -v
```

- [ ] **Step 3: Verify all detail routes work**

Add a parametrized test to `test_routes.py`:

```python
import pytest
from config import DETAIL_ROUTES

@pytest.mark.parametrize("page", list(DETAIL_ROUTES.keys()))
def test_all_detail_routes_return_200(page):
    client = make_client()
    r = client.get(f"/detail/{page}")
    assert r.status_code == 200, f"/detail/{page} returned {r.status_code}"
```

Run: `cd examples/market-dashboard && uv run pytest tests/test_routes.py::test_all_detail_routes_return_200 -v`

Expected: all 17 detail routes PASS.

- [ ] **Step 4: Commit**

```bash
git add examples/market-dashboard/templates/detail/
git commit -m "feat(market-dashboard): all 17 drill-down detail templates with skill-specific tables"
```

---

## Task 9: APScheduler Integration

**Files:**
- Create: `examples/market-dashboard/scheduler.py`
- Create: `examples/market-dashboard/tests/test_scheduler.py`
- Modify: `examples/market-dashboard/main.py` (wire scheduler into startup)

- [ ] **Step 1: Write failing test**

```python
# tests/test_scheduler.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_create_scheduler_returns_scheduler_instance():
    from scheduler import create_scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    assert isinstance(sched, AsyncIOScheduler)
    # Scheduler should not be running yet (just created)
    assert not sched.running


def test_scheduler_registers_ftd_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "ftd-detector" in job_ids


def test_scheduler_registers_vcp_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "vcp-screener" in job_ids


def test_scheduler_registers_daily_6am_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "economic-calendar-fetcher" in job_ids


def test_scheduler_registers_weekly_sunday_job():
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "institutional-flow-tracker" in job_ids


def test_sector_analyst_has_no_independent_job():
    """sector-analyst must NOT have its own independent interval job.
    It runs only as a prerequisite inside the exposure-coach job to guarantee ordering.
    A separate sector-analyst interval job would race with exposure-coach."""
    from scheduler import create_scheduler
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp/test_cache"))
    job_ids = [j.id for j in sched.get_jobs()]
    assert "sector-analyst" not in job_ids, (
        "sector-analyst must not have an independent scheduler job; "
        "it runs as a dependency inside exposure-coach's job"
    )
    assert "exposure-coach" in job_ids


def test_exposure_coach_job_runs_sector_analyst_first(tmp_path):
    """The exposure-coach job function must call sector-analyst before exposure-coach."""
    from scheduler import create_scheduler
    from unittest.mock import MagicMock, call

    mock_runner = MagicMock()
    # Mock is_market_open to return True so the job body executes
    sched = create_scheduler(runner=mock_runner, cache_dir=tmp_path)
    jobs = {j.id: j for j in sched.get_jobs()}
    exposure_job = jobs["exposure-coach"]

    # Patch the market-open check so it runs during test
    import scheduler as sched_module
    original = sched_module._market_is_open
    sched_module._market_is_open = lambda: True
    try:
        exposure_job.func()
    finally:
        sched_module._market_is_open = original

    calls = [c[0][0] for c in mock_runner.run_skill.call_args_list]
    assert calls[0] == "sector-analyst", f"First call must be sector-analyst, got {calls}"
    assert "exposure-coach" in calls
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `scheduler.py`**

```python
"""APScheduler job setup for market-dashboard skill cadences."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import SKILL_REGISTRY


def _market_is_open() -> bool:
    """Check if current ET time is within market hours (Mon-Fri 9:30-16:00)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (t.hour == 9 and t.minute >= 30) or (10 <= t.hour < 16)


def _pre_market_window() -> bool:
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    t = now.time()
    return 7 <= t.hour < 9 or (t.hour == 9 and t.minute < 30)


def _make_intraday_job(runner, skill_name: str):
    """Job function that only fires during market hours."""
    def job():
        if _market_is_open():
            runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}"
    return job


def _make_30min_ordered_job(runner, skill_name: str):
    """Job that runs sector-analyst first (for exposure-coach), then the target skill.
    sector-analyst has no independent scheduled job; it only runs here as a prerequisite."""
    def job():
        if _market_is_open():
            if skill_name == "exposure-coach":
                # Spec Section 7: sector-analyst must run before exposure-coach
                runner.run_skill("sector-analyst")
            runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}"
    return job


def _make_open_once_job(runner, skill_name: str, cache_dir: Path):
    """Job that only runs once at open — checks cache's generated_at date to survive restarts."""
    def job():
        from zoneinfo import ZoneInfo
        if not _market_is_open():
            return
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        cache_file = cache_dir / f"{skill_name}.json"
        if cache_file.exists():
            try:
                import json
                data = json.loads(cache_file.read_text())
                cached_date = data.get("generated_at", "")[:10]
                if cached_date == today:
                    return  # Already ran today — skip even after restart
            except Exception:
                pass
        runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}_at_open"
    return job


def _make_pre_market_job(runner, skill_name: str):
    """Job that fires once at 7 AM (pre-market window)."""
    def job():
        runner.run_skill(skill_name)
    job.__name__ = f"run_{skill_name.replace('-', '_')}_premarket"
    return job


def create_scheduler(runner, cache_dir: Path) -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler (not yet started).

    Note: sector-analyst has no independent scheduled job. It runs only as a
    prerequisite inside the exposure-coach 30-min job to guarantee execution order
    (spec Section 7: sector-analyst must run before exposure-coach).
    """
    sched = AsyncIOScheduler(timezone="America/New_York")

    for skill_name, cfg in SKILL_REGISTRY.items():
        if cfg.get("script") is None:
            continue  # Skip SKILL.md-only skills
        if skill_name == "sector-analyst":
            continue  # Runs as dependency inside exposure-coach job only

        cadence = cfg.get("cadence_min")
        at_open = cfg.get("at_open_once", False)
        pre_market = cfg.get("pre_market_once", False)
        daily_6am = cfg.get("daily_6am", False)
        weekly_sunday = cfg.get("weekly_sunday", False)
        post_market_mwf = cfg.get("post_market_mwf", False)

        if at_open:
            sched.add_job(
                _make_open_once_job(runner, skill_name, cache_dir),
                CronTrigger(day_of_week="mon-fri", hour=9, minute=32),
                id=skill_name,
                replace_existing=True,
            )
        elif pre_market:
            sched.add_job(
                _make_pre_market_job(runner, skill_name),
                CronTrigger(day_of_week="mon-fri", hour=7, minute=0),
                id=skill_name,
                replace_existing=True,
            )
        elif daily_6am:
            sched.add_job(
                lambda sn=skill_name: runner.run_skill(sn) if runner else None,
                CronTrigger(day_of_week="mon-fri", hour=6, minute=0),
                id=skill_name,
                replace_existing=True,
            )
        elif weekly_sunday:
            sched.add_job(
                lambda sn=skill_name: runner.run_skill(sn) if runner else None,
                CronTrigger(day_of_week="sun", hour=18, minute=0),
                id=skill_name,
                replace_existing=True,
            )
        elif post_market_mwf:
            sched.add_job(
                lambda sn=skill_name: runner.run_skill(sn) if runner else None,
                CronTrigger(day_of_week="mon,wed,fri", hour=16, minute=15),
                id=skill_name,
                replace_existing=True,
            )
        elif cadence:
            if cadence <= 60:
                sched.add_job(
                    _make_30min_ordered_job(runner, skill_name),
                    IntervalTrigger(minutes=cadence),
                    id=skill_name,
                    replace_existing=True,
                )
            else:
                sched.add_job(
                    _make_intraday_job(runner, skill_name),
                    IntervalTrigger(minutes=cadence),
                    id=skill_name,
                    replace_existing=True,
                )

    return sched
```

- [ ] **Step 4: Wire scheduler into `main.py` startup**

In `main.py`, add after imports:

```python
from scheduler import create_scheduler

_scheduler = None

@app.on_event("startup")
async def startup():
    global _scheduler
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _scheduler = create_scheduler(runner=runner, cache_dir=CACHE_DIR)
    _scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
```

- [ ] **Step 5: Run all tests**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add examples/market-dashboard/scheduler.py examples/market-dashboard/tests/test_scheduler.py examples/market-dashboard/main.py
git commit -m "feat(market-dashboard): APScheduler — skill cadences, open-once jobs, dependency ordering"
```

---

## Task 10: Stale Cache Startup Refresh

**Files:**
- Modify: `examples/market-dashboard/main.py`

- [ ] **Step 1: Add startup refresh to `main.py`**

In the `startup()` function, after starting the scheduler, add a background task that checks each skill's cache and refreshes stale ones:

```python
async def _refresh_stale_on_startup():
    """On startup, refresh any cache files older than 2× their cadence."""
    loop = asyncio.get_running_loop()
    for skill_name in SKILL_REGISTRY:
        if SKILL_REGISTRY[skill_name].get("script") is None:
            continue
        if runner.is_stale(skill_name):
            loop.run_in_executor(None, runner.run_skill, skill_name)
            await asyncio.sleep(0.2)  # stagger launches to avoid API bursts

# In startup():
asyncio.create_task(_refresh_stale_on_startup())
```

- [ ] **Step 2: Add test**

```python
# In test_routes.py
def test_startup_does_not_crash():
    """Server starts without exception even with empty cache."""
    client = make_client()
    r = client.get("/")
    assert r.status_code == 200
```

- [ ] **Step 3: Run tests**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add examples/market-dashboard/main.py
git commit -m "feat(market-dashboard): refresh stale cache on startup"
```

---

## Task 11: CLAUDE.md

**Files:**
- Create: `examples/market-dashboard/CLAUDE.md`

- [ ] **Step 1: Create `CLAUDE.md`**

```markdown
# Market Dashboard — CLAUDE.md

## What this is

Always-on FastAPI + HTMX market monitoring dashboard. Runs trading analysis skills on a background schedule, displays live TradingView charts, and shows skill signals with drill-down pages. This is Plan 1 (Level 1 Advisory). Plans 2 and 3 add Alpaca integration and Auto trading.

## How to start

```bash
cd examples/market-dashboard
cp .env.example .env    # fill in API keys
uv run uvicorn main:app --port 8000
```

Use `--reload` during development only. In production, `--reload` watches the filesystem and will restart the server on every cache file write (because `cache/` is in the project directory). Do not use `--reload` in production.

## Environment setup

1. Copy `.env.example` to `.env`
2. Set `FMP_API_KEY` — required for VCP, FTD, CANSLIM, Macro Regime, calendars
3. Set `FINVIZ_API_KEY` — optional, speeds up Theme Detector
4. Set `ANTHROPIC_API_KEY` — required only if a skill internally uses Claude
5. Alpaca keys — not needed for Plan 1; required for Plan 2

## How skills are invoked

Skills run as subprocesses via `skills_runner.py`. The runner:
- Injects API keys from `.env` into the subprocess environment
- Passes `--output-dir cache/` to each skill script
- After a successful run, renames the newest timestamped JSON to `cache/<skill-name>.json`
- Captures stderr to `cache/<skill-name>.stderr.log`
- Skill scripts are resolved relative to `SKILLS_ROOT` (two directories up from `market-dashboard/`)

To manually trigger a skill: `POST /api/skill/<skill-name>/refresh`

## Cache directory

`cache/` is auto-created on startup. The files are:
- `cache/<skill-name>.json` — latest successful output
- `cache/<skill-name>.stderr.log` — last run's stderr (for debugging failures)

Delete a `.json` file to force a refresh on the next scheduler tick. Delete `.stderr.log` files to clean up logs.

## Settings

Runtime mode and risk settings are stored in `settings.json` (auto-created on first save). To reset to `.env` defaults, delete `settings.json`. Do not edit `.env` for runtime settings — it is only read at startup.

## Testing

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```

## TDD requirement

Follow the repo-wide TDD-first workflow: write the failing test first, then implement the minimal code to pass it.
```

- [ ] **Step 2: Final full test run**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add examples/market-dashboard/CLAUDE.md
git commit -m "feat(market-dashboard): CLAUDE.md — startup, skills runner, cache, settings docs"
```

---

## Plan 2 Outline: Alpaca Integration + Semi-Auto

> Write as a separate plan after Plan 1 is validated.

**Goal:** Portfolio strip shows live Alpaca P&L, Execute buttons appear in Semi-Auto, order preview with three-button slider, bracket orders placed via alpaca-py. Paper/Live environment switching with `CONFIRM LIVE TRADING` guard.

**Key tasks:**
1. `alpaca_client.py` — `TradingClient` (orders, account) + `StockHistoricalDataClient` (last-trade price) + trading stream WebSocket for fill notifications. Unit tests with mock alpaca-py.
2. `templates/fragments/portfolio.html` — live P&L strip (HTMX poll every 5s). `/api/portfolio` route reads in-memory Alpaca state.
3. Order preview UI — three-button slider in detail pages (Risk %, Shares, Dollar Amt). HTMX swap.
4. Semi-Auto execute flow — `/api/order/preview` (returns order preview HTML) + `/api/order/confirm` (places bracket order via TradingClient).
5. Paper/Live switching guard — JS confirmation dialog requiring `CONFIRM LIVE TRADING` typed before switching environment.
6. Wire AlpacaClient into `main.py` startup.

---

## Plan 3 Outline: Auto Trading + Learning System

> Write as a separate plan after Plan 2 is validated in paper trading.

**Goal:** PivotWatchlistMonitor subscribes to Alpaca data WebSocket, fires bracket orders on pivot breakout. Two-stage confidence check (pre-market news + real-time Stage 2 WebSearch). Learning system extracts rules from closed trades weekly.

**Key tasks:**
1. `pivot_monitor.py` — `PivotWatchlistMonitor` class. Loads VCP candidates from cache at open. Subscribes to Alpaca data WebSocket. Fires on `price >= pivot × 1.001`. Enforces guard rails (max positions, market hours, Market Top score). Unit tests with mock WebSocket.
2. `confidence_check.py` — Stage 1 pre-market: loads news/theme/institutional cache, applies learned rules, tags each candidate HIGH_CONVICTION / CLEAR / UNCERTAIN / BLOCKED. Stage 2 real-time: runs WebSearch for UNCERTAIN stocks at trigger time.
3. `learning/pattern_extractor.py` — Weekly Saturday job: reads closed trades from trader-memory-core, identifies patterns in losses/wins, writes `learning/learned_rules.json`.
4. `learning/rule_store.py` — Reads/writes `learned_rules.json`. Applies rules at Stage 1. Minimum 5 similar trades before a rule activates. Rules visible in settings modal.
5. Wire all three into `main.py` startup: `pivot_monitor.start()` at market open, `confidence_check.run_stage1()` at 7 AM pre-market job.
