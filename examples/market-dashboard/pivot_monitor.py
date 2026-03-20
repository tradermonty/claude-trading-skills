# pivot_monitor.py
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from alpaca_client import AlpacaClient
from settings_manager import SettingsManager

NEGATIVE_KEYWORDS = {
    "sec", "fraud", "bankrupt", "lawsuit", "miss", "downgrade",
    "fda rejection", "recall", "warning", "investigation", "halt",
}
POSITIVE_KEYWORDS = {
    "beat", "upgrade", "bullish", "strong guidance", "approval",
    "partnership", "accumulation", "buy rating",
}
PIVOT_BUFFER = 1.001  # price must cross pivot × 1.001 to trigger


def _default_search_fn(symbol: str) -> list[str]:
    """No external search configured — return empty (no news = CLEAR)."""
    return []


class PivotWatchlistMonitor:
    """Monitors VCP candidates for pivot breakouts and fires bracket orders in Auto mode.

    Inject _search_fn for Stage 1/2 news checks (default = no-op).
    Inject _data_stream for tests (avoids real Alpaca WebSocket).
    """

    def __init__(
        self,
        alpaca_client: AlpacaClient,
        settings_manager: SettingsManager,
        cache_dir: Path,
        rule_store=None,
        _search_fn: Optional[Callable[[str], list[str]]] = None,
        _data_stream=None,
    ):
        self._alpaca = alpaca_client
        self._settings = settings_manager
        self._cache_dir = cache_dir
        self._rule_store = rule_store
        self._search_fn = _search_fn or _default_search_fn
        self._data_stream = _data_stream
        self._candidates: list[dict] = []
        self._triggered: set[str] = set()

    # ── Candidate loading ────────────────────────────────────────────────────

    def load_candidates(self) -> list[dict]:
        """Read VCP cache, return [{symbol, pivot_price}] list."""
        vcp_file = self._cache_dir / "vcp-screener.json"
        if not vcp_file.exists():
            return []
        try:
            data = json.loads(vcp_file.read_text())
            candidates = []
            for r in data.get("results", []):
                symbol = r.get("symbol")
                pivot_price = (r.get("vcp_pattern") or {}).get("pivot_price")
                if symbol and pivot_price:
                    candidates.append({"symbol": symbol, "pivot_price": float(pivot_price)})
            return candidates
        except Exception:
            return []

    # ── Stage 1: Pre-market confidence tagging ────────────────────────────

    def run_stage1_check(self, candidates: list[dict]) -> list[dict]:
        """Tag each candidate: HIGH_CONVICTION / CLEAR / UNCERTAIN / BLOCKED."""
        earnings_soon = self._get_earnings_soon_symbols()
        inst_flow = self._get_institutional_accumulation_symbols()

        tagged = []
        for c in candidates:
            tag = self._tag_candidate(c["symbol"], earnings_soon, inst_flow)
            tagged.append({**c, "confidence_tag": tag})

        if self._rule_store:
            tagged = self._rule_store.apply(tagged)

        return tagged

    def _tag_candidate(self, symbol: str, earnings_soon: set, inst_flow: set) -> str:
        headlines = self._search_fn(symbol)
        text = " ".join(headlines).lower()
        has_negative = any(kw in text for kw in NEGATIVE_KEYWORDS)
        has_positive = any(kw in text for kw in POSITIVE_KEYWORDS)

        if has_negative:
            return "BLOCKED"
        if symbol in inst_flow and has_positive:
            return "HIGH_CONVICTION"
        if symbol in earnings_soon:
            return "UNCERTAIN"
        if has_positive or symbol in inst_flow:
            return "HIGH_CONVICTION"
        return "CLEAR"

    def _get_earnings_soon_symbols(self) -> set:
        earnings_file = self._cache_dir / "earnings-calendar.json"
        if not earnings_file.exists():
            return set()
        try:
            from zoneinfo import ZoneInfo
            data = json.loads(earnings_file.read_text())
            today = datetime.now(ZoneInfo("America/New_York")).date()
            symbols = set()
            for e in data.get("events", []):
                try:
                    edate = datetime.fromisoformat(e["date"]).date()
                    if 0 <= (edate - today).days <= 3:
                        symbols.add(e.get("symbol", "").upper())
                except Exception:
                    continue
            return symbols
        except Exception:
            return set()

    def _get_institutional_accumulation_symbols(self) -> set:
        flow_file = self._cache_dir / "institutional-flow-tracker.json"
        if not flow_file.exists():
            return set()
        try:
            data = json.loads(flow_file.read_text())
            return {s.upper() for s in data.get("accumulation_symbols", [])}
        except Exception:
            return set()
