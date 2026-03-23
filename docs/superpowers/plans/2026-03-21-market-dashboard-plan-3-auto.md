# Market Dashboard Plan 3 — Auto Trading (PivotWatchlistMonitor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Level 3 Auto trading mode: a `PivotWatchlistMonitor` subscribes to the Alpaca data WebSocket for VCP candidates, fires bracket orders when price crosses the pivot with a configurable buffer, with a two-stage news/signal confidence check, guard rails, and a learning system that extracts patterns from trade history.

**Architecture:** `pivot_monitor.py` handles candidate loading, Stage 1 pre-market confidence tagging (news + institutional flow + learned rules), real-time WebSocket breakout detection (Stage 2 for UNCERTAIN stocks), guard rails, and order placement. `learning/rule_store.py` reads/writes `learned_rules.json`. `learning/pattern_extractor.py` is a weekly Saturday job that analyses `auto_trades.json` and updates rules. `scheduler.py` gains three new jobs; `main.py` wires everything together and adds a monitor status API route. UI adds an Auto mode status banner and settings confirmation.

**Tech Stack:** alpaca-py (`StockDataStream`), FastAPI, APScheduler (AsyncIOScheduler), Jinja2, HTMX

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `examples/market-dashboard/learning/__init__.py` | Package marker (empty) |
| Create | `examples/market-dashboard/learning/rule_store.py` | Read/write `learned_rules.json`; apply active rules to candidate list |
| Create | `examples/market-dashboard/learning/learned_rules.json` | Seed empty rule store (`{"rules": []}`) |
| Create | `examples/market-dashboard/learning/pattern_extractor.py` | Weekly pattern extraction: reads `auto_trades.json`, computes win/loss by tag, generates rules |
| Create | `examples/market-dashboard/pivot_monitor.py` | `PivotWatchlistMonitor`: load VCP candidates, Stage 1 tagging, Alpaca data WebSocket, breakout detection, guard rails, order placement |
| Create | `examples/market-dashboard/tests/test_rule_store.py` | Unit tests for RuleStore |
| Create | `examples/market-dashboard/tests/test_pivot_monitor.py` | Unit tests for PivotWatchlistMonitor (Stage 1 + breakout logic) |
| Create | `examples/market-dashboard/tests/test_pattern_extractor.py` | Unit tests for PatternExtractor |
| Modify | `examples/market-dashboard/scheduler.py:87` | Add `pivot_monitor`, `pattern_extractor` optional params; three new jobs |
| Modify | `examples/market-dashboard/main.py:1-55` | Wire PivotWatchlistMonitor + PatternExtractor; add `/api/monitor/status` route |
| Modify | `examples/market-dashboard/templates/dashboard.html:1-10` | Add Auto mode status banner |
| Modify | `examples/market-dashboard/templates/fragments/settings_modal.html:58-71` | Add Auto mode confirm to `handleSettingsSubmit` |
| Modify | `examples/market-dashboard/tests/test_routes.py` | Add monitor status + auto banner route tests |

---

## Task 1: RuleStore

**Files:**
- Create: `examples/market-dashboard/learning/__init__.py`
- Create: `examples/market-dashboard/learning/rule_store.py`
- Create: `examples/market-dashboard/learning/learned_rules.json`
- Test: `examples/market-dashboard/tests/test_rule_store.py`

- [ ] **Step 1: Write failing tests**

Create `examples/market-dashboard/tests/test_rule_store.py`:

```python
# tests/test_rule_store.py
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from learning.rule_store import RuleStore, MIN_SAMPLE_COUNT


def make_store(d):
    return RuleStore(Path(d) / "learned_rules.json")


def test_load_missing_file_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(d)
        assert store.load() == {"rules": []}


def test_save_and_load_round_trip():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(d)
        data = {"rules": [{"id": "r1", "active": True, "sample_count": 5}]}
        store.save(data)
        assert store.load() == data


def test_apply_active_rule_changes_confidence_tag():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(d)
        store.save({"rules": [{
            "id": "r1",
            "condition": {"confidence_tag": "UNCERTAIN", "earnings_within_days": {"lte": 3}},
            "action": {"set_confidence_tag": "BLOCKED"},
            "confidence": 0.78, "sample_count": 10, "active": True,
        }]})
        candidates = [{"symbol": "AAPL", "confidence_tag": "UNCERTAIN", "earnings_within_days": 2}]
        result = store.apply(candidates)
        assert result[0]["confidence_tag"] == "BLOCKED"


def test_inactive_rule_not_applied():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(d)
        store.save({"rules": [{
            "id": "r1",
            "condition": {"confidence_tag": "UNCERTAIN"},
            "action": {"set_confidence_tag": "BLOCKED"},
            "confidence": 0.9, "sample_count": 10, "active": False,
        }]})
        candidates = [{"symbol": "AAPL", "confidence_tag": "UNCERTAIN"}]
        result = store.apply(candidates)
        assert result[0]["confidence_tag"] == "UNCERTAIN"


def test_low_sample_count_rule_not_applied():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(d)
        store.save({"rules": [{
            "id": "r1",
            "condition": {"confidence_tag": "UNCERTAIN"},
            "action": {"set_confidence_tag": "BLOCKED"},
            "confidence": 0.9, "sample_count": MIN_SAMPLE_COUNT - 1, "active": True,
        }]})
        candidates = [{"symbol": "AAPL", "confidence_tag": "UNCERTAIN"}]
        result = store.apply(candidates)
        assert result[0]["confidence_tag"] == "UNCERTAIN"


def test_apply_does_not_mutate_original():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(d)
        original = [{"symbol": "AAPL", "confidence_tag": "UNCERTAIN"}]
        store.apply(original)
        assert original[0]["confidence_tag"] == "UNCERTAIN"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard && uv run pytest tests/test_rule_store.py -v
```
Expected: ImportError (module not yet created)

- [ ] **Step 3: Create `learning/__init__.py`**

```python
# learning/__init__.py
```
(empty file)

- [ ] **Step 4: Create `learning/rule_store.py`**

```python
# learning/rule_store.py
from __future__ import annotations

import json
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_RULES_FILE = LEARNING_DIR / "learned_rules.json"
MIN_SAMPLE_COUNT = 5  # minimum trades before a rule activates


class RuleStore:
    """Reads, writes, and applies learned trading rules.

    Rule schema:
        {
          "id": "auto_uncertain_to_blocked",
          "description": "UNCERTAIN → BLOCKED (78% stop-out rate, n=10)",
          "condition": {"confidence_tag": "UNCERTAIN"},
          "action": {"set_confidence_tag": "BLOCKED"},
          "confidence": 0.78,
          "sample_count": 10,
          "active": true
        }

    Condition values can be scalars (equality check) or dicts with
    "lte" / "gte" keys for range checks.
    """

    def __init__(self, rules_file: Path = DEFAULT_RULES_FILE):
        self._file = rules_file

    def load(self) -> dict:
        if not self._file.exists():
            return {"rules": []}
        try:
            return json.loads(self._file.read_text())
        except Exception:
            return {"rules": []}

    def save(self, data: dict) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(data, indent=2))

    def apply(self, candidates: list[dict]) -> list[dict]:
        """Apply active, qualified rules to candidates. Returns new list (no mutation)."""
        data = self.load()
        active_rules = [
            r for r in data.get("rules", [])
            if r.get("active") and r.get("sample_count", 0) >= MIN_SAMPLE_COUNT
        ]
        result = []
        for candidate in candidates:
            c = dict(candidate)
            for rule in active_rules:
                if self._matches(c, rule["condition"]):
                    action = rule.get("action", {})
                    if "set_confidence_tag" in action:
                        c["confidence_tag"] = action["set_confidence_tag"]
            result.append(c)
        return result

    def _matches(self, candidate: dict, condition: dict) -> bool:
        for key, value in condition.items():
            if key not in candidate:
                return False
            if isinstance(value, dict):
                cval = candidate[key]
                if "lte" in value and cval > value["lte"]:
                    return False
                if "gte" in value and cval < value["gte"]:
                    return False
            else:
                if candidate[key] != value:
                    return False
        return True
```

- [ ] **Step 5: Create `learning/learned_rules.json`**

```json
{"rules": []}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd examples/market-dashboard && uv run pytest tests/test_rule_store.py -v
```
Expected: 6 PASSED

- [ ] **Step 7: Commit**

```bash
cd examples/market-dashboard && git add learning/__init__.py learning/rule_store.py learning/learned_rules.json tests/test_rule_store.py
git commit -m "feat: add RuleStore for learned trading rules"
```

---

## Task 2: PivotWatchlistMonitor — candidate loading + Stage 1 confidence tagging

**Files:**
- Create: `examples/market-dashboard/pivot_monitor.py` (Stage 1 portion)
- Test: `examples/market-dashboard/tests/test_pivot_monitor.py` (Stage 1 tests only)

Stage 1 logic:
1. Call `_search_fn(symbol)` → list of news headlines (injectable; default returns `[]`)
2. Scan headlines for negative keywords → `BLOCKED`
3. Scan for positive keywords + institutional accumulation from cache → `HIGH_CONVICTION`
4. Earnings within 3 days (from `cache/earnings-calendar.json`) → `UNCERTAIN`
5. No signal → `CLEAR`
6. Apply rule_store rules after initial tagging

- [ ] **Step 1: Write failing tests**

Create `examples/market-dashboard/tests/test_pivot_monitor.py`:

```python
# tests/test_pivot_monitor.py
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock
from pivot_monitor import PivotWatchlistMonitor


def make_monitor(tmp_path: Path, search_fn=None):
    alpaca = MagicMock()
    alpaca.is_configured = False
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
    }
    return PivotWatchlistMonitor(
        alpaca_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
        _search_fn=search_fn or (lambda s: []),
    )


def write_vcp_cache(tmp_path: Path, results: list):
    (tmp_path / "vcp-screener.json").write_text(json.dumps({
        "results": results, "generated_at": "2026-03-21T09:35:00",
    }))


def test_load_candidates_returns_empty_when_no_cache():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        assert monitor.load_candidates() == []


def test_load_candidates_parses_vcp_json():
    with tempfile.TemporaryDirectory() as d:
        write_vcp_cache(Path(d), [
            {"symbol": "AAPL", "vcp_pattern": {"pivot_price": 155.0}},
            {"symbol": "TSLA", "vcp_pattern": {"pivot_price": 200.0}},
        ])
        monitor = make_monitor(Path(d))
        candidates = monitor.load_candidates()
        assert len(candidates) == 2
        assert candidates[0] == {"symbol": "AAPL", "pivot_price": 155.0}
        assert candidates[1] == {"symbol": "TSLA", "pivot_price": 200.0}


def test_load_candidates_skips_entries_without_pivot():
    with tempfile.TemporaryDirectory() as d:
        write_vcp_cache(Path(d), [
            {"symbol": "AAPL", "vcp_pattern": {}},  # no pivot_price
            {"symbol": "TSLA", "vcp_pattern": {"pivot_price": 200.0}},
        ])
        monitor = make_monitor(Path(d))
        assert len(monitor.load_candidates()) == 1


def test_stage1_tags_clear_when_no_news():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "CLEAR"


def test_stage1_tags_blocked_on_negative_news():
    def search(sym):
        return ["AAPL: SEC investigation confirmed, stock halted"]
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d), search_fn=search)
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "BLOCKED"


def test_stage1_tags_high_conviction_on_positive_news():
    def search(sym):
        return ["AAPL: analyst upgrade to buy, strong guidance beat"]
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d), search_fn=search)
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "HIGH_CONVICTION"


def test_stage1_tags_uncertain_for_upcoming_earnings():
    with tempfile.TemporaryDirectory() as d:
        from datetime import date, timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        (Path(d) / "earnings-calendar.json").write_text(json.dumps({
            "events": [{"symbol": "AAPL", "date": tomorrow + "T07:00:00"}]
        }))
        monitor = make_monitor(Path(d))
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "UNCERTAIN"


def test_stage1_applies_rule_store_rules():
    from learning.rule_store import RuleStore
    with tempfile.TemporaryDirectory() as d:
        store = RuleStore(Path(d) / "learned_rules.json")
        store.save({"rules": [{
            "id": "r1",
            "condition": {"confidence_tag": "UNCERTAIN"},
            "action": {"set_confidence_tag": "BLOCKED"},
            "confidence": 0.8, "sample_count": 10, "active": True,
        }]})
        from datetime import date, timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        (Path(d) / "earnings-calendar.json").write_text(json.dumps({
            "events": [{"symbol": "TSLA", "date": tomorrow + "T07:00:00"}]
        }))
        alpaca = MagicMock(); alpaca.is_configured = False
        settings = MagicMock(); settings.load.return_value = {
            "mode": "auto", "default_risk_pct": 1.0, "max_positions": 5, "max_position_size_pct": 10.0,
        }
        monitor = PivotWatchlistMonitor(
            alpaca_client=alpaca, settings_manager=settings,
            cache_dir=Path(d), rule_store=store,
        )
        result = monitor.run_stage1_check([{"symbol": "TSLA", "pivot_price": 200.0}])
        # UNCERTAIN upgraded to BLOCKED by the rule
        assert result[0]["confidence_tag"] == "BLOCKED"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard && uv run pytest tests/test_pivot_monitor.py -v
```
Expected: ImportError (pivot_monitor not yet created)

- [ ] **Step 3: Create `pivot_monitor.py` (Stage 1 only)**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd examples/market-dashboard && uv run pytest tests/test_pivot_monitor.py -v
```
Expected: 8 PASSED

- [ ] **Step 5: Run full test suite to confirm nothing broken**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v
```
Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
cd examples/market-dashboard && git add pivot_monitor.py tests/test_pivot_monitor.py
git commit -m "feat: add PivotWatchlistMonitor Stage 1 confidence tagging"
```

---

## Task 3: PivotWatchlistMonitor — breakout detection, guard rails, order placement

**Files:**
- Modify: `examples/market-dashboard/pivot_monitor.py` (append breakout/order methods)
- Modify: `examples/market-dashboard/tests/test_pivot_monitor.py` (append breakout tests)

- [ ] **Step 1: Append failing tests to `test_pivot_monitor.py`**

Add after the existing tests:

```python
# ── Breakout detection and guard rails ─────────────────────────────────────

def test_check_breakout_fires_for_clear_candidate():
    """When price >= pivot × 1.001, a CLEAR candidate should trigger _fire_order."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        monitor._alpaca.get_positions.return_value = []
        monitor._alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        monitor._alpaca.get_last_price.return_value = 156.0
        monitor._alpaca.place_bracket_order.return_value = {
            "id": "ord1", "symbol": "AAPL", "qty": 10.0, "limit_price": 156.0, "status": "new"
        }

        bar = MagicMock()
        bar.symbol = "AAPL"
        bar.close = 156.0  # 156 >= 155 × 1.001 = 155.155 ✓

        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]
        monitor._candidates = candidates

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_called_once()
        assert "AAPL" in monitor._triggered


def test_check_breakout_skips_blocked_candidate():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "BLOCKED"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_check_breakout_skips_when_price_below_buffer():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        bar = MagicMock(); bar.symbol = "AAPL"
        bar.close = 155.0  # exactly at pivot, not above buffer
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        monitor._check_breakout(bar, candidates)
        monitor._alpaca.place_bracket_order.assert_not_called()


def test_guard_rail_max_positions_blocks_order():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        # 5 positions = max_positions → blocked
        monitor._alpaca.get_positions.return_value = [{}] * 5

        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_guard_rail_outside_market_hours_blocks_order():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: False
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_uncertain_with_negative_stage2_blocks_order():
    def negative_search(sym):
        return ["AAPL: SEC investigation launched"]
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d), search_fn=negative_search)
        monitor._alpaca.is_configured = True
        monitor._alpaca.get_positions.return_value = []
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "UNCERTAIN"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_high_conviction_uses_1_5x_risk():
    """HIGH_CONVICTION sizing passes risk_pct × 1.5 to qty calculation."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        monitor._alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        # account=100k, risk=1%, entry=100, stop=97 → risk_per_share=3, dollar_risk=1000 → 333 shares
        # HIGH_CONVICTION: risk=1.5%, dollar_risk=1500 → 500 shares
        qty_normal = monitor._calc_qty(100.0, 97.0, high_conviction=False)
        qty_hc = monitor._calc_qty(100.0, 97.0, high_conviction=True)
        assert qty_hc > qty_normal
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd examples/market-dashboard && uv run pytest tests/test_pivot_monitor.py -v -k "breakout or guard or stage2 or high_conviction"
```
Expected: FAIL (methods not yet implemented)

- [ ] **Step 3: Append breakout methods to `pivot_monitor.py`**

Add after `_get_institutional_accumulation_symbols` in `pivot_monitor.py`:

```python
    # ── Breakout detection ─────────────────────────────────────────────────

    def _check_breakout(self, bar, candidates: list[dict]) -> None:
        """Called for each bar event. Fires order if pivot breakout detected."""
        for c in candidates:
            if c["symbol"] != bar.symbol:
                continue
            if c["symbol"] in self._triggered:
                continue

            tag = c.get("confidence_tag", "CLEAR")
            if tag == "BLOCKED":
                continue

            trigger_price = c["pivot_price"] * PIVOT_BUFFER
            if bar.close < trigger_price:
                continue

            # Breakout detected — run guard rails
            allowed, reason = self._guard_rails_allow(c)
            if not allowed:
                print(f"[pivot_monitor] {c['symbol']} guard: {reason}", file=sys.stderr)
                continue

            # Stage 2 for UNCERTAIN
            if tag == "UNCERTAIN":
                headlines = self._search_fn(c["symbol"])
                text = " ".join(headlines).lower()
                if any(kw in text for kw in NEGATIVE_KEYWORDS):
                    print(f"[pivot_monitor] {c['symbol']} Stage 2 blocked: negative news", file=sys.stderr)
                    continue

            self._triggered.add(c["symbol"])
            self._fire_order(c, tag)

    def _guard_rails_allow(self, candidate: dict) -> tuple[bool, str]:
        """Check all guard rails. Returns (allowed, reason)."""
        if not _market_is_open_now():
            return False, "outside market hours"

        # Market Top Detector pause
        mt_file = self._cache_dir / "market-top-detector.json"
        if mt_file.exists():
            try:
                data = json.loads(mt_file.read_text())
                risk_score = data.get("risk_score", 0)
                if risk_score >= 65:
                    return False, f"Market Top risk={risk_score} ≥ 65 — Auto paused"
            except Exception:
                pass

        # Max positions
        settings = self._settings.load()
        try:
            positions = self._alpaca.get_positions()
            max_pos = settings.get("max_positions", 5)
            if len(positions) >= max_pos:
                return False, f"max_positions={max_pos} reached"
        except Exception:
            return False, "could not check positions"

        return True, ""

    def _fire_order(self, candidate: dict, tag: str) -> None:
        """Fetch live price, calculate qty, place bracket order, log to auto_trades.json."""
        symbol = candidate["symbol"]
        try:
            entry_price = self._alpaca.get_last_price(symbol)
            stop_price = round(entry_price * 0.97, 2)
            qty = self._calc_qty(entry_price, stop_price, high_conviction=(tag == "HIGH_CONVICTION"))
            if qty <= 0:
                print(f"[pivot_monitor] {symbol}: qty=0, skipping", file=sys.stderr)
                return
            result = self._alpaca.place_bracket_order(
                symbol=symbol, qty=qty, limit_price=entry_price, stop_price=stop_price,
            )
            print(f"[pivot_monitor] ORDER: {symbol} {qty}sh @ {entry_price} | {result}", file=sys.stderr)
            self._log_trade(candidate, result["id"], entry_price, stop_price, qty, tag)
        except Exception as e:
            print(f"[pivot_monitor] {symbol} order error: {e}", file=sys.stderr)

    def _calc_qty(self, entry_price: float, stop_price: float, high_conviction: bool) -> int:
        """Calculate share count based on risk % settings and account value."""
        settings = self._settings.load()
        risk_pct = settings.get("default_risk_pct", 1.0)
        if high_conviction:
            risk_pct = min(risk_pct * 1.5, 5.0)
        max_pos_pct = settings.get("max_position_size_pct", 10.0)

        try:
            portfolio_value = self._alpaca.get_account()["portfolio_value"]
        except Exception:
            return 0

        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            return 0

        dollar_risk = portfolio_value * (risk_pct / 100)
        qty = int(dollar_risk / risk_per_share)

        max_dollar = portfolio_value * (max_pos_pct / 100)
        max_qty_by_size = int(max_dollar / entry_price)
        return min(qty, max_qty_by_size)

    def _log_trade(
        self, candidate: dict, order_id: str,
        entry_price: float, stop_price: float, qty: int, tag: str,
    ) -> None:
        """Append trade context to cache/auto_trades.json for pattern extraction.

        Captures full market state snapshot at entry so PatternExtractor can
        build multi-factor rules (breadth, market top, macro regime, etc.).
        """
        trades_file = self._cache_dir / "auto_trades.json"
        try:
            trades = json.loads(trades_file.read_text()) if trades_file.exists() else {"trades": []}
        except Exception:
            trades = {"trades": []}

        # Read market state snapshot from cache files (best-effort; missing = None)
        market_top_score = self._read_cache_field("market-top-detector.json", "risk_score")
        breadth_score = self._read_cache_field("market-breadth-analyzer.json", "breadth_score")
        ftd_score = self._read_cache_field("ftd-detector.json", "ftd_score")
        macro_regime = self._read_cache_field("macro-regime-detector.json", "regime")
        settings = self._settings.load()
        risk_pct = settings.get("default_risk_pct", 1.0)
        if tag == "HIGH_CONVICTION":
            risk_pct = min(risk_pct * 1.5, 5.0)

        trades["trades"].append({
            "symbol": candidate["symbol"],
            "order_id": order_id,
            "entry_time": datetime.utcnow().isoformat(),
            "entry_price": entry_price,
            "stop_price": stop_price,
            "qty": qty,
            "confidence_tag": tag,
            "pivot_price": candidate["pivot_price"],
            "risk_pct": risk_pct,
            # Market state snapshot for multi-factor rule extraction
            "market_top_score": market_top_score,
            "breadth_score": breadth_score,
            "ftd_score": ftd_score,
            "macro_regime": macro_regime,
            # Outcome populated later by PatternExtractor.refresh_trade_outcomes()
            "outcome": None,
        })
        trades_file.write_text(json.dumps(trades, indent=2))

    def _read_cache_field(self, filename: str, field: str):
        """Read a single field from a cache JSON file. Returns None on any error."""
        try:
            data = json.loads((self._cache_dir / filename).read_text())
            return data.get(field)
        except Exception:
            return None

    # ── Alpaca data WebSocket subscription ────────────────────────────────

    async def start(self, candidates: list[dict]) -> None:
        """Subscribe to Alpaca data WebSocket for candidates and run breakout monitor."""
        self._candidates = [c for c in candidates if c.get("confidence_tag") != "BLOCKED"]
        self._triggered.clear()

        if not self._candidates:
            return
        if not self._alpaca.is_configured:
            return

        if self._data_stream is not None:
            stream = self._data_stream
        else:
            from alpaca.data.live import StockDataStream
            stream = StockDataStream(
                api_key=self._alpaca.api_key,
                secret_key=self._alpaca.secret_key,
            )

        symbols = [c["symbol"] for c in self._candidates]
        monitor = self  # capture for closure

        async def handle_bar(bar):
            monitor._check_breakout(bar, monitor._candidates)

        stream.subscribe_bars(handle_bar, *symbols)

        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, stream.run)
        except Exception as e:
            print(f"[pivot_monitor] stream disconnected: {e}", file=sys.stderr)


def _market_is_open_now() -> bool:
    """Check if current ET time is within market hours (Mon-Fri 9:30-16:00)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (t.hour == 9 and t.minute >= 30) or (10 <= t.hour < 16)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd examples/market-dashboard && uv run pytest tests/test_pivot_monitor.py -v
```
Expected: all tests PASSED

- [ ] **Step 5: Run full suite**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
cd examples/market-dashboard && git add pivot_monitor.py tests/test_pivot_monitor.py
git commit -m "feat: add PivotWatchlistMonitor breakout detection, guard rails, and order placement"
```

---

## Task 4: PatternExtractor

**Files:**
- Create: `examples/market-dashboard/learning/pattern_extractor.py`
- Test: `examples/market-dashboard/tests/test_pattern_extractor.py`

PatternExtractor reads `cache/auto_trades.json`, groups by `confidence_tag`, computes win rates from trades where `outcome` is set, and writes rules to `learned_rules.json` via `RuleStore`.

- [ ] **Step 1: Write failing tests**

Create `examples/market-dashboard/tests/test_pattern_extractor.py`:

```python
# tests/test_pattern_extractor.py
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch
from learning.pattern_extractor import PatternExtractor
from learning.rule_store import RuleStore, MIN_SAMPLE_COUNT


def make_extractor(tmp_path: Path, alpaca=None):
    if alpaca is None:
        alpaca = MagicMock()
        alpaca.is_configured = False
    store = RuleStore(tmp_path / "learned_rules.json")
    return PatternExtractor(alpaca_client=alpaca, rule_store=store, cache_dir=tmp_path), store


def write_trades(tmp_path: Path, trades: list):
    (tmp_path / "auto_trades.json").write_text(json.dumps({"trades": trades}))


def test_extract_with_no_trades_file_returns_zero():
    with tempfile.TemporaryDirectory() as d:
        extractor, _ = make_extractor(Path(d))
        result = extractor.extract()
        assert result["trades_analyzed"] == 0
        assert result["rules_updated"] == 0


def test_extract_with_zero_outcome_trades_when_alpaca_not_configured():
    """When Alpaca not configured, outcome=None trades cannot be refreshed."""
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [
            {"symbol": "AAPL", "confidence_tag": "UNCERTAIN", "outcome": None, "order_id": "abc"},
        ])
        extractor, _ = make_extractor(Path(d))
        result = extractor.extract()
        assert result["trades_analyzed"] == 0


def test_refresh_trade_outcomes_updates_loss_when_stop_fills():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "UNCERTAIN", "outcome": None,
            "order_id": "ord1", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        # Mock: stop-loss leg filled at 150 (below entry → loss)
        stop_leg = MagicMock()
        stop_leg.side = "sell"
        stop_leg.status = "filled"
        stop_leg.filled_avg_price = 150.0
        parent_order = MagicMock()
        parent_order.legs = [stop_leg]
        alpaca.trading_client.get_order_by_id.return_value = parent_order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        updated = extractor.refresh_trade_outcomes()
        assert updated == 1
        trades = json.loads((Path(d) / "auto_trades.json").read_text())["trades"]
        assert trades[0]["outcome"] == "loss"


def test_refresh_trade_outcomes_updates_win_when_takeprofit_fills():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "outcome": None,
            "order_id": "ord2", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        tp_leg = MagicMock()
        tp_leg.side = "sell"
        tp_leg.status = "filled"
        tp_leg.filled_avg_price = 163.0  # above entry → win
        parent_order = MagicMock()
        parent_order.legs = [tp_leg]
        alpaca.trading_client.get_order_by_id.return_value = parent_order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        updated = extractor.refresh_trade_outcomes()
        assert updated == 1
        trades = json.loads((Path(d) / "auto_trades.json").read_text())["trades"]
        assert trades[0]["outcome"] == "win"


def test_refresh_returns_zero_when_order_still_open():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "outcome": None,
            "order_id": "ord3", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        parent_order = MagicMock()
        parent_order.legs = []  # no filled sell legs
        alpaca.trading_client.get_order_by_id.return_value = parent_order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        updated = extractor.refresh_trade_outcomes()
        assert updated == 0


def test_extract_generates_uncertain_blocked_rule_when_high_loss_rate():
    with tempfile.TemporaryDirectory() as d:
        # 6 UNCERTAIN trades with outcomes already set (skip refresh)
        trades = [
            {"symbol": f"T{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"}
            for i in range(5)
        ] + [{"symbol": "T5", "confidence_tag": "UNCERTAIN", "outcome": "win"}]
        write_trades(Path(d), trades)
        extractor, store = make_extractor(Path(d))
        result = extractor.extract()
        rules = store.load()["rules"]
        assert any(r["id"] == "auto_uncertain_to_blocked" for r in rules)
        rule = next(r for r in rules if r["id"] == "auto_uncertain_to_blocked")
        assert rule["active"] is True
        assert rule["sample_count"] == 6


def test_extract_does_not_activate_rule_below_min_sample_count():
    with tempfile.TemporaryDirectory() as d:
        trades = [
            {"symbol": f"T{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"}
            for i in range(MIN_SAMPLE_COUNT - 1)
        ]
        write_trades(Path(d), trades)
        extractor, store = make_extractor(Path(d))
        extractor.extract()
        for r in store.load()["rules"]:
            assert r.get("active") is False or r.get("sample_count", 0) < MIN_SAMPLE_COUNT


def test_extract_does_not_create_rule_when_loss_rate_below_threshold():
    with tempfile.TemporaryDirectory() as d:
        trades = (
            [{"symbol": f"W{i}", "confidence_tag": "UNCERTAIN", "outcome": "win"} for i in range(3)] +
            [{"symbol": f"L{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"} for i in range(2)]
        )
        write_trades(Path(d), trades)
        extractor, store = make_extractor(Path(d))
        extractor.extract()
        assert not any(r["id"] == "auto_uncertain_to_blocked" for r in store.load()["rules"])


def test_extract_updates_existing_rule_confidence():
    with tempfile.TemporaryDirectory() as d:
        store = RuleStore(Path(d) / "learned_rules.json")
        store.save({"rules": [{
            "id": "auto_uncertain_to_blocked",
            "condition": {"confidence_tag": "UNCERTAIN"},
            "action": {"set_confidence_tag": "BLOCKED"},
            "confidence": 0.70, "sample_count": 7, "active": True,
        }]})
        trades = (
            [{"symbol": f"T{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"} for i in range(8)] +
            [{"symbol": "T8", "confidence_tag": "UNCERTAIN", "outcome": "win"}]
        )
        write_trades(Path(d), trades)
        alpaca = MagicMock(); alpaca.is_configured = False
        extractor = PatternExtractor(alpaca_client=alpaca, rule_store=store, cache_dir=Path(d))
        extractor.extract()
        rule = next(r for r in store.load()["rules"] if r["id"] == "auto_uncertain_to_blocked")
        assert rule["sample_count"] == 9
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd examples/market-dashboard && uv run pytest tests/test_pattern_extractor.py -v
```
Expected: ImportError

- [ ] **Step 3: Create `learning/pattern_extractor.py`**

```python
# learning/pattern_extractor.py
from __future__ import annotations

import json
from pathlib import Path

from alpaca_client import AlpacaClient
from learning.rule_store import RuleStore, MIN_SAMPLE_COUNT

LOSS_RATE_THRESHOLD = 0.60  # activate UNCERTAIN→BLOCKED rule above this stop-out rate


class PatternExtractor:
    """Weekly job: reads auto_trades.json, resolves outcomes from Alpaca, updates rule_store.

    Flow: extract() → refresh_trade_outcomes() → analyze trades with outcomes → update rules.
    Additional rule types (market top, breadth correlation) deferred to Plan 3b once
    sufficient trade history accumulates.
    """

    def __init__(self, alpaca_client: AlpacaClient, rule_store: RuleStore, cache_dir: Path):
        self._alpaca = alpaca_client
        self._rule_store = rule_store
        self._cache_dir = cache_dir

    def load_trades(self) -> list[dict]:
        trades_file = self._cache_dir / "auto_trades.json"
        if not trades_file.exists():
            return []
        try:
            return json.loads(trades_file.read_text()).get("trades", [])
        except Exception:
            return []

    def extract(self) -> dict:
        """Run extraction: refresh outcomes, analyze, update rule_store."""
        self.refresh_trade_outcomes()

        all_trades = self.load_trades()
        trades = [t for t in all_trades if t.get("outcome") is not None]

        if not trades:
            return {"rules_updated": 0, "trades_analyzed": 0}

        stats = self._compute_stats(trades)
        new_rules, updated_ids = self._generate_rules(stats)
        self._persist_rules(new_rules, updated_ids)

        return {
            "trades_analyzed": len(trades),
            "rules_updated": len(new_rules) + len(updated_ids),
        }

    def refresh_trade_outcomes(self) -> int:
        """Query Alpaca closed bracket order legs to populate outcome fields.

        For each auto trade with outcome=None: look up the bracket order in Alpaca,
        find the filled sell leg, compare exit price to entry price → 'win' or 'loss'.
        Returns number of trades updated.
        """
        trades_file = self._cache_dir / "auto_trades.json"
        if not trades_file.exists():
            return 0
        try:
            data = json.loads(trades_file.read_text())
        except Exception:
            return 0

        open_trades = [
            t for t in data.get("trades", [])
            if t.get("outcome") is None and t.get("order_id")
        ]
        if not open_trades or not self._alpaca.is_configured:
            return 0

        updated = 0
        for trade in open_trades:
            outcome = self._get_order_outcome(trade["order_id"], trade.get("entry_price", 0))
            if outcome is not None:
                trade["outcome"] = outcome
                updated += 1

        if updated:
            trades_file.write_text(json.dumps(data, indent=2))

        return updated

    def _get_order_outcome(self, order_id: str, entry_price: float) -> str | None:
        """Look up bracket order in Alpaca. Returns 'win', 'loss', or None if still open."""
        try:
            order = self._alpaca.trading_client.get_order_by_id(order_id)
            if not hasattr(order, "legs") or not order.legs:
                return None
            for leg in order.legs:
                side = str(leg.side).lower()
                status = str(leg.status).lower()
                if "sell" in side and "filled" in status:
                    exit_price = float(leg.filled_avg_price or 0)
                    if exit_price <= 0:
                        return None
                    return "win" if exit_price > entry_price else "loss"
            return None
        except Exception:
            return None

    def _compute_stats(self, trades: list[dict]) -> dict:
        stats: dict[str, dict] = {}
        for t in trades:
            tag = t.get("confidence_tag", "CLEAR")
            if tag not in stats:
                stats[tag] = {"wins": 0, "losses": 0}
            if t.get("outcome") == "win":
                stats[tag]["wins"] += 1
            else:
                stats[tag]["losses"] += 1
        return stats

    def _generate_rules(self, stats: dict) -> tuple[list[dict], set[str]]:
        """Generate or update rules. Returns (new_rules, update_ids)."""
        new_rules = []
        update_ids = set()
        existing_ids = {r["id"] for r in self._rule_store.load().get("rules", [])}

        for tag, s in stats.items():
            total = s["wins"] + s["losses"]
            if total < MIN_SAMPLE_COUNT:
                continue
            loss_rate = s["losses"] / total

            if tag == "UNCERTAIN" and loss_rate >= LOSS_RATE_THRESHOLD:
                rule_id = "auto_uncertain_to_blocked"
                rule = {
                    "id": rule_id,
                    "description": f"UNCERTAIN → BLOCKED ({loss_rate:.0%} stop-out rate, n={total})",
                    "condition": {"confidence_tag": "UNCERTAIN"},
                    "action": {"set_confidence_tag": "BLOCKED"},
                    "confidence": round(loss_rate, 3),
                    "sample_count": total,
                    "active": total >= MIN_SAMPLE_COUNT,
                }
                if rule_id in existing_ids:
                    update_ids.add(rule_id)
                    data = self._rule_store.load()
                    for r in data["rules"]:
                        if r["id"] == rule_id:
                            r.update({k: rule[k] for k in ("confidence", "sample_count", "active", "description")})
                    self._rule_store.save(data)
                else:
                    new_rules.append(rule)

        return new_rules, update_ids

    def _persist_rules(self, new_rules: list[dict], updated_ids: set) -> None:
        if not new_rules:
            return
        data = self._rule_store.load()
        data["rules"].extend(new_rules)
        self._rule_store.save(data)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd examples/market-dashboard && uv run pytest tests/test_pattern_extractor.py -v
```
Expected: 10 PASSED

- [ ] **Step 5: Run full suite**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
cd examples/market-dashboard && git add learning/pattern_extractor.py tests/test_pattern_extractor.py
git commit -m "feat: add PatternExtractor weekly rule learning from trade history"
```

---

## Task 5: Scheduler + main.py integration

**Files:**
- Modify: `examples/market-dashboard/scheduler.py`
- Modify: `examples/market-dashboard/main.py`
- Modify: `examples/market-dashboard/tests/test_scheduler.py` (append new job tests)

**scheduler.py changes:** Add three new optional jobs when `pivot_monitor` and `pattern_extractor` are passed:
1. Stage 1 pre-market check at 7:00 AM Mon–Fri
2. Monitor start at 9:32 AM Mon–Fri (creates async task; only fires if mode == 'auto')
3. Saturday 18:00 pattern extraction

**main.py changes:** Import and wire `RuleStore`, `PivotWatchlistMonitor`, `PatternExtractor`; pass them to `create_scheduler`; add a `/api/monitor/status` JSON route.

- [ ] **Step 1: Write failing scheduler tests**

Append to `tests/test_scheduler.py`:

```python
def test_scheduler_registers_stage1_job_when_pivot_monitor_given():
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    monitor = MagicMock()
    monitor.load_candidates.return_value = []
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp"), pivot_monitor=monitor)
    job_ids = [j.id for j in sched.get_jobs()]
    assert "pivot_stage1" in job_ids


def test_scheduler_registers_monitor_start_job_when_pivot_monitor_given():
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    monitor = MagicMock()
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp"), pivot_monitor=monitor)
    job_ids = [j.id for j in sched.get_jobs()]
    assert "pivot_monitor_start" in job_ids


def test_scheduler_registers_pattern_extraction_when_extractor_given():
    from scheduler import create_scheduler
    from unittest.mock import MagicMock
    extractor = MagicMock()
    sched = create_scheduler(runner=None, cache_dir=Path("/tmp"), pattern_extractor=extractor)
    job_ids = [j.id for j in sched.get_jobs()]
    assert "pattern_extraction" in job_ids
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd examples/market-dashboard && uv run pytest tests/test_scheduler.py -v -k "stage1 or monitor_start or pattern_extraction"
```
Expected: FAIL

- [ ] **Step 3: Update `create_scheduler` signature in `scheduler.py`**

Change the function signature (line 87):

```python
def create_scheduler(
    runner,
    cache_dir: Path,
    pivot_monitor=None,
    pattern_extractor=None,
) -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler (not yet started)."""
```

At the end of `create_scheduler`, before `return sched`, add:

```python
    # ── Plan 3: Pivot monitor jobs ────────────────────────────────────────
    if pivot_monitor is not None:
        def stage1_job():
            candidates = pivot_monitor.load_candidates()
            pivot_monitor._candidates = pivot_monitor.run_stage1_check(candidates)

        sched.add_job(
            stage1_job,
            CronTrigger(day_of_week="mon-fri", hour=7, minute=0),
            id="pivot_stage1",
            replace_existing=True,
        )

        async def monitor_start_job():
            settings = pivot_monitor._settings.load()
            if settings.get("mode") != "auto":
                return
            if not pivot_monitor._candidates:
                pivot_monitor._candidates = pivot_monitor.run_stage1_check(
                    pivot_monitor.load_candidates()
                )
            asyncio.create_task(pivot_monitor.start(pivot_monitor._candidates))

        sched.add_job(
            monitor_start_job,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=32),
            id="pivot_monitor_start",
            replace_existing=True,
        )

    if pattern_extractor is not None:
        sched.add_job(
            pattern_extractor.extract,
            CronTrigger(day_of_week="sat", hour=18, minute=0),
            id="pattern_extraction",
            replace_existing=True,
        )
```

- [ ] **Step 4: Run scheduler tests to verify they pass**

```bash
cd examples/market-dashboard && uv run pytest tests/test_scheduler.py -v
```
Expected: all PASSED (including the 3 new ones)

- [ ] **Step 5: Write failing route test for /api/monitor/status**

Append to `tests/test_routes.py`:

```python
def test_monitor_status_returns_json():
    client = make_client()
    r = client.get("/api/monitor/status")
    assert r.status_code == 200
    data = r.json()
    assert "active" in data
    assert "candidate_count" in data
    assert "triggered" in data
```

- [ ] **Step 6: Run to confirm failure**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py::test_monitor_status_returns_json -v
```
Expected: 404

- [ ] **Step 7: Update `main.py`**

After the existing imports add:

```python
from learning.rule_store import RuleStore
from learning.pattern_extractor import PatternExtractor
from pivot_monitor import PivotWatchlistMonitor
```

After `alpaca = AlpacaClient(...)` (around line 31), add:

```python
rule_store = RuleStore()  # defaults to learning/learned_rules.json
pivot_monitor = PivotWatchlistMonitor(
    alpaca_client=alpaca,
    settings_manager=settings_manager,
    cache_dir=CACHE_DIR,
    rule_store=rule_store,
)
pattern_extractor = PatternExtractor(
    alpaca_client=alpaca,
    rule_store=rule_store,
    cache_dir=CACHE_DIR,
)
```

Change `create_scheduler` call in `startup()` to pass the new objects:

```python
_scheduler = create_scheduler(
    runner=runner,
    cache_dir=CACHE_DIR,
    pivot_monitor=pivot_monitor,
    pattern_extractor=pattern_extractor,
)
```

Add the new route after `api_portfolio` (after line 197):

```python
@app.get("/api/monitor/status")
async def monitor_status():
    """Return current PivotWatchlistMonitor state for the Auto mode banner."""
    return JSONResponse({
        "active": len(pivot_monitor._candidates) > 0,
        "candidate_count": len(pivot_monitor._candidates),
        "triggered": list(pivot_monitor._triggered),
    })
```

- [ ] **Step 8: Run all tests**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
cd examples/market-dashboard && git add scheduler.py main.py tests/test_scheduler.py tests/test_routes.py
git commit -m "feat: wire PivotWatchlistMonitor + PatternExtractor into scheduler and main.py"
```

---

## Task 6: UI — Auto mode status banner + settings modal confirmation

**Files:**
- Modify: `examples/market-dashboard/templates/dashboard.html`
- Modify: `examples/market-dashboard/templates/fragments/settings_modal.html`
- Modify: `examples/market-dashboard/tests/test_routes.py` (append banner tests)

- [ ] **Step 1: Write failing UI route tests**

Append to `tests/test_routes.py`:

```python
def test_dashboard_shows_auto_banner_in_auto_mode():
    """When settings mode=auto, dashboard HTML must contain auto-banner element."""
    client = make_client()
    # Set mode to auto first
    r = client.post("/api/settings", data={
        "mode": "auto", "default_risk_pct": "1.0",
        "max_positions": "5", "max_position_size_pct": "10.0",
        "environment": "paper",
    })
    assert r.status_code == 200

    r = client.get("/")
    assert r.status_code == 200
    assert b"auto-banner" in r.content


def test_dashboard_no_auto_banner_in_advisory_mode():
    """Advisory mode must not show auto-banner."""
    client = make_client()
    r = client.get("/")
    assert b"auto-banner" not in r.content
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py -v -k "auto_banner"
```
Expected: FAIL (`auto-banner` not in content)

- [ ] **Step 3: Add Auto banner to `dashboard.html`**

Insert immediately after `{% block content %}` (before the `<div class="main-grid">`):

```html
{% if settings.mode == 'auto' %}
<div class="auto-banner">
  🤖 <strong>AUTO MODE ACTIVE</strong>
  {% if settings.environment == 'live' %}
  <span style="color:#f87171; font-weight:bold; margin-left:8px;">💰 LIVE — real money at risk</span>
  {% else %}
  <span style="color:#4ade80; margin-left:8px;">📄 PAPER — simulated only</span>
  {% endif %}
</div>
{% endif %}
```

Add the `.auto-banner` CSS rule to `static/style.css`. Insert after the `body.live-auto-mode` block:

```css
/* Auto mode status banner */
.auto-banner {
  background: #1a2a1a;
  border: 1px solid #4ade80;
  border-radius: 4px;
  padding: 6px 12px;
  margin: 6px 8px;
  font-size: 12px;
  color: #e6edf3;
}
body.live-auto-mode .auto-banner {
  background: #2a1a1a;
  border-color: #f87171;
}
```

- [ ] **Step 4: Add Auto mode confirmation to `settings_modal.html`**

Replace the existing `handleSettingsSubmit` script block (lines 58–71):

```html
<script>
function handleSettingsSubmit(form) {
  var mode = form.querySelector('[name=mode]').value;
  var env = form.querySelector('[name=environment]').value;

  if (mode === 'auto') {
    var ok = confirm(
      'Enable Level 3 Auto Trading?\n\n' +
      'The bot will place bracket orders automatically when VCP pivot ' +
      'breakouts are detected.\n\n' +
      'Recommended: test on Paper first. Click OK to enable Auto mode.'
    );
    if (!ok) return false;
  }

  if (env === 'live') {
    var typed = prompt('Type exactly to confirm:\n\nCONFIRM LIVE TRADING');
    if (typed !== 'CONFIRM LIVE TRADING') {
      alert('Confirmation did not match. Live trading not enabled.');
      return false;
    }
    document.getElementById('live-confirm-input').value = typed;
  }
  return true;
}
</script>
```

- [ ] **Step 5: Run UI tests**

```bash
cd examples/market-dashboard && uv run pytest tests/test_routes.py -v -k "auto_banner"
```
Expected: 2 PASSED

- [ ] **Step 6: Run full test suite**

```bash
cd examples/market-dashboard && uv run pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
cd examples/market-dashboard && git add templates/dashboard.html templates/fragments/settings_modal.html static/style.css tests/test_routes.py
git commit -m "feat: add Auto mode status banner and settings confirmation UI"
```

---

## Final State

After all 6 tasks:
- `pivot_monitor.py` — `PivotWatchlistMonitor` with Stage 1, Stage 2, breakout detection, guard rails, order placement, trade logging
- `learning/rule_store.py` — `RuleStore` reads/writes/applies `learned_rules.json`
- `learning/pattern_extractor.py` — `PatternExtractor` weekly rule generation
- `scheduler.py` — Stage 1 at 7 AM, monitor start at 9:32 AM, extraction Saturday 6 PM
- `main.py` — wired objects, `/api/monitor/status` route
- UI — Auto mode banner + settings Auto confirmation

**Verification:** `cd examples/market-dashboard && uv run pytest tests/ -v` — all tests pass.

**Test count:** ~95+ tests across all test files.

**Deferred to Plan 3b / Plan 4:**
- Additional rule types beyond `UNCERTAIN → BLOCKED` (market top correlation, breadth correlation, HIGH_CONVICTION theme-aligned win rate) — requires 50+ trades of history to have statistical significance. The `market_top_score`, `breadth_score`, `macro_regime` fields are now captured in `auto_trades.json` for future rule extraction.
- Async WebSocket integration tests for `PivotWatchlistMonitor.start()`.
- `auto_trades.json` outcome status UI (visible rules panel in settings modal).

**Run the dashboard:**
```bash
cd examples/market-dashboard && uv run uvicorn main:app --port 8000
```
Navigate to `http://localhost:8000`, open Settings, switch to Level 3 Auto (Paper mode). The auto banner should appear.
