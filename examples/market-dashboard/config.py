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
