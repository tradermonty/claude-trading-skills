# Tier 1: Capital Protection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three capital protection guard rails: PDT counter with selectivity tiers, drawdown circuit breaker, and earnings blackout.

**Architecture:** Three new classes in `learning/` (PDTTracker, DrawdownTracker, EarningsBlackout) following the MultiplierStore constructor-injection pattern. All three are wired into `_guard_rails_allow()` in `pivot_monitor.py` and instantiated in `main.py`. Tasks 1-3 are independent and can be dispatched in parallel.

**Tech Stack:** Python 3.11+, FastAPI, Alpaca-py, standard library only (json, datetime)

**Parallelization note:** Tasks 1, 2, and 3 modify different files and can be executed by independent subagents simultaneously. Task 4 depends on all three completing first.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `learning/pdt_tracker.py` | Create | Track day trades in rolling 5-business-day window |
| `learning/drawdown_tracker.py` | Create | Track weekly/daily portfolio drawdown |
| `learning/earnings_blackout.py` | Create | Check earnings calendar for upcoming reports |
| `tests/test_pdt_tracker.py` | Create | PDTTracker unit tests |
| `tests/test_drawdown_tracker.py` | Create | DrawdownTracker unit tests |
| `tests/test_earnings_blackout.py` | Create | EarningsBlackout unit tests |
| `pivot_monitor.py` | Modify | Add 3 new optional params + guard rail checks |
| `tests/test_pivot_monitor.py` | Modify | Add guard rail integration tests |
| `main.py` | Modify | Instantiate 3 new classes, pass to pivot_monitor |
| `settings_manager.py` | Modify | Add 5 new default settings fields |
| `templates/fragments/settings_modal.html` | Modify | Add new settings form fields |
| `tests/test_routes.py` | Modify | Add settings round-trip tests |

---

## Task 1: PDTTracker

**Files touched:** `learning/pdt_tracker.py` (create), `tests/test_pdt_tracker.py` (create)

### Background

The Pattern Day Trader rule limits retail accounts to 3 day trades in a rolling 5-business-day window. As slots fill up, the system becomes progressively more selective — preserving remaining slots for higher-conviction setups. A day trade is defined as opening and closing the same position on the same calendar day.

Business day calculation skips weekends (Saturday = weekday 5, Sunday = weekday 6). No holiday handling is required to keep the implementation simple and dependency-free.

### Class design

```python
# learning/pdt_tracker.py
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_TRADES_FILE = LEARNING_DIR / "pdt_trades.json"


class PDTTracker:
    def __init__(self, trades_file: Path = DEFAULT_TRADES_FILE):
        self._trades_file = trades_file

    def record_day_trade(self, symbol: str, trade_date: date) -> None:
        """Append a day trade record to the JSON file."""

    def day_trades_used(self, as_of_date: date) -> int:
        """Count day trades in last 5 business days (inclusive of as_of_date)."""

    def slots_remaining(self, as_of_date: date) -> int:
        """Returns max(0, 3 - day_trades_used)."""

    def get_allowed_tags(self, as_of_date: date) -> set[str]:
        """Returns set of allowed confidence tags based on slots remaining.
        0 slots: empty set (no new entries)
        1 slot: {"HIGH_CONVICTION"}
        2 slots: {"HIGH_CONVICTION", "CLEAR"}
        3 slots: {"HIGH_CONVICTION", "CLEAR", "UNCERTAIN"}
        """
```

### Persistence format

File: `learning/pdt_trades.json`

```json
{"trades": [{"symbol": "AAPL", "date": "2026-03-22"}]}
```

If the file does not exist or is corrupt, treat as zero trades (fail open — never block trading due to a missing log file).

### Business day logic

To find the 5-business-day window ending on `as_of_date`, walk backwards from `as_of_date`, counting only weekdays (weekday 0–4), until you have collected 5 business days. All trades whose date falls on or after the earliest day in that window are counted.

### Step-by-step

- [ ] **Step 1 — Write failing tests**

  Create `tests/test_pdt_tracker.py` with all 8 tests listed below. At this point `learning/pdt_tracker.py` does not exist — all tests will fail with `ModuleNotFoundError` or `AttributeError`.

  ```python
  # tests/test_pdt_tracker.py
  import sys
  import json
  import tempfile
  from pathlib import Path
  from datetime import date, timedelta
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  from learning.pdt_tracker import PDTTracker


  def test_no_trades_returns_3_slots():
      with tempfile.TemporaryDirectory() as d:
          tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
          assert tracker.slots_remaining(date.today()) == 3


  def test_record_and_count_day_trade():
      with tempfile.TemporaryDirectory() as d:
          tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
          today = date.today()
          tracker.record_day_trade("AAPL", today)
          assert tracker.day_trades_used(today) == 1


  def test_rolling_5_business_days_excludes_older():
      with tempfile.TemporaryDirectory() as d:
          tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
          today = date(2026, 3, 20)  # Friday
          # 5 business days back from Friday 2026-03-20: Mon 16, Tue 17, Wed 18, Thu 19, Fri 20
          # A trade on Mon 2026-03-09 (10 business days ago) must not be counted
          old_trade_date = date(2026, 3, 9)  # Monday, well outside window
          tracker.record_day_trade("TSLA", old_trade_date)
          assert tracker.day_trades_used(today) == 0


  def test_weekends_not_counted_as_business_days():
      with tempfile.TemporaryDirectory() as d:
          tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
          # Saturday and Sunday are not business days — a 5-business-day window
          # measured from Friday must reach back to the prior Monday, not include weekends.
          friday = date(2026, 3, 20)
          prior_monday = date(2026, 3, 16)
          tracker.record_day_trade("AAPL", prior_monday)
          tracker.record_day_trade("TSLA", friday)
          # Both are within the 5-business-day window (Mon–Fri)
          assert tracker.day_trades_used(friday) == 2


  def test_slots_remaining_decrements_correctly():
      with tempfile.TemporaryDirectory() as d:
          tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
          today = date.today()
          assert tracker.slots_remaining(today) == 3
          tracker.record_day_trade("AAPL", today)
          assert tracker.slots_remaining(today) == 2
          tracker.record_day_trade("TSLA", today)
          assert tracker.slots_remaining(today) == 1
          tracker.record_day_trade("NVDA", today)
          assert tracker.slots_remaining(today) == 0


  def test_get_allowed_tags_0_slots_empty_set():
      with tempfile.TemporaryDirectory() as d:
          tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
          today = date.today()
          for sym in ("A", "B", "C"):
              tracker.record_day_trade(sym, today)
          assert tracker.get_allowed_tags(today) == set()


  def test_get_allowed_tags_1_slot_high_conviction_only():
      with tempfile.TemporaryDirectory() as d:
          tracker = PDTTracker(trades_file=Path(d) / "pdt_trades.json")
          today = date.today()
          for sym in ("A", "B"):
              tracker.record_day_trade(sym, today)
          tags = tracker.get_allowed_tags(today)
          assert tags == {"HIGH_CONVICTION"}


  def test_corrupt_file_returns_3_slots():
      with tempfile.TemporaryDirectory() as d:
          f = Path(d) / "pdt_trades.json"
          f.write_text("NOT VALID JSON {{{{")
          tracker = PDTTracker(trades_file=f)
          # Corrupt file must not block trading — fail open
          assert tracker.slots_remaining(date.today()) == 3
  ```

- [ ] **Step 2 — Run tests (expect failure)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_pdt_tracker.py -v
  ```

  Expected: all 8 tests fail with `ModuleNotFoundError: No module named 'learning.pdt_tracker'`.

- [ ] **Step 3 — Implement `learning/pdt_tracker.py`**

  Create the file. Key implementation notes:

  - `_load()` reads the JSON file; returns `{"trades": []}` on any error (missing file, corrupt JSON, wrong structure).
  - `_business_days_window(as_of_date, n=5)` returns the list of `n` most recent business days ending on and including `as_of_date`. Walk backwards from `as_of_date`, appending only days where `d.weekday() < 5`, until the list has length `n`.
  - `day_trades_used(as_of_date)` loads the file, computes the window, then counts trades whose date string parses to a date inside the window. Wrap in try/except and return 0 on any error.
  - `record_day_trade(symbol, trade_date)` loads, appends `{"symbol": symbol, "date": trade_date.isoformat()}`, writes back atomically using a temp file + rename (same pattern as `MultiplierStore`).
  - `slots_remaining(as_of_date)` returns `max(0, 3 - day_trades_used(as_of_date))`.
  - `get_allowed_tags(as_of_date)` maps slots to tag sets using a simple lookup.

  Follow `MultiplierStore` exactly for file I/O: `Path.write_text(json.dumps(..., indent=2))`. The file's parent directory is created with `mkdir(parents=True, exist_ok=True)` before writing.

- [ ] **Step 4 — Run tests (expect all pass)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_pdt_tracker.py -v
  ```

  Expected: all 8 tests pass.

- [ ] **Step 5 — Commit**

  ```bash
  git add learning/pdt_tracker.py tests/test_pdt_tracker.py
  git commit -m "feat: add PDTTracker with rolling 5-business-day window and selectivity tiers"
  ```

---

## Task 2: DrawdownTracker

**Files touched:** `learning/drawdown_tracker.py` (create), `tests/test_drawdown_tracker.py` (create)

### Background

Tracks portfolio value at the start of each trading week and each trading day. If the current portfolio value has dropped more than the configured percentage from either reference point, auto trading pauses. Setting either threshold to 100 disables that check (since a 100% drawdown is impossible in practice).

### Class design

```python
# learning/drawdown_tracker.py
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_FILE = LEARNING_DIR / "drawdown_state.json"


class DrawdownTracker:
    def __init__(self, state_file: Path = DEFAULT_STATE_FILE):
        self._state_file = state_file

    def update(self, portfolio_value: float, as_of_date: date) -> None:
        """Record current portfolio value. Updates week_start if Monday,
        updates day_start whenever the date changes."""

    def is_weekly_limit_breached(self, portfolio_value: float, max_pct: float) -> bool:
        """Returns True if drop from week_start exceeds max_pct.
        Returns False if max_pct >= 100 (disabled) or no state recorded."""

    def is_daily_limit_breached(self, portfolio_value: float, max_pct: float) -> bool:
        """Returns True if drop from day_start exceeds max_pct.
        Returns False if max_pct >= 100 (disabled) or no state recorded."""
```

### Persistence format

File: `learning/drawdown_state.json`

```json
{
  "week_start_value": 10000.0,
  "week_start_date": "2026-03-17",
  "day_start_value": 9800.0,
  "day_start_date": "2026-03-22"
}
```

`update()` logic:
- Load current state (or empty dict if missing/corrupt).
- If `as_of_date.weekday() == 0` (Monday) and `week_start_date` is not already today, set `week_start_value = portfolio_value` and `week_start_date = as_of_date.isoformat()`.
- If `day_start_date` is not `as_of_date.isoformat()`, set `day_start_value = portfolio_value` and `day_start_date = as_of_date.isoformat()`.
- Write updated state back to disk.

Drawdown calculation: `drop_pct = (reference_value - current_value) / reference_value * 100`. If `drop_pct > max_pct`, the limit is breached.

If the state file is missing, `is_weekly_limit_breached` and `is_daily_limit_breached` both return `False` (no history = no block).

### Step-by-step

- [ ] **Step 1 — Write failing tests**

  Create `tests/test_drawdown_tracker.py` with all 6 tests listed below.

  ```python
  # tests/test_drawdown_tracker.py
  import sys
  import json
  import tempfile
  from pathlib import Path
  from datetime import date
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  from learning.drawdown_tracker import DrawdownTracker


  def test_weekly_limit_not_breached_when_above_threshold():
      with tempfile.TemporaryDirectory() as d:
          tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
          monday = date(2026, 3, 16)  # a Monday
          tracker.update(10000.0, monday)
          # 9100 is only a 9% drop — under the 10% limit
          assert tracker.is_weekly_limit_breached(9100.0, max_pct=10.0) is False


  def test_weekly_limit_breached_when_below_threshold():
      with tempfile.TemporaryDirectory() as d:
          tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
          monday = date(2026, 3, 16)
          tracker.update(10000.0, monday)
          # 8900 is an 11% drop — over the 10% limit
          assert tracker.is_weekly_limit_breached(8900.0, max_pct=10.0) is True


  def test_disabled_at_100_pct():
      with tempfile.TemporaryDirectory() as d:
          tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
          monday = date(2026, 3, 16)
          tracker.update(10000.0, monday)
          # Even a catastrophic drop must not block when max_pct=100
          assert tracker.is_weekly_limit_breached(1.0, max_pct=100.0) is False
          assert tracker.is_daily_limit_breached(1.0, max_pct=100.0) is False


  def test_daily_limit_breached():
      with tempfile.TemporaryDirectory() as d:
          tracker = DrawdownTracker(state_file=Path(d) / "drawdown_state.json")
          today = date(2026, 3, 22)  # a Saturday — not Monday, so only day_start is set
          tracker.update(10000.0, today)
          # 9400 is a 6% drop — over the 5% daily limit
          assert tracker.is_daily_limit_breached(9400.0, max_pct=5.0) is True


  def test_week_start_resets_on_monday():
      with tempfile.TemporaryDirectory() as d:
          state_file = Path(d) / "drawdown_state.json"
          tracker = DrawdownTracker(state_file=state_file)
          friday = date(2026, 3, 20)
          tracker.update(10000.0, friday)
          monday = date(2026, 3, 23)
          tracker.update(9500.0, monday)
          # week_start_value is now 9500 — a further 10% drop to 8550 should breach
          assert tracker.is_weekly_limit_breached(8550.0, max_pct=10.0) is True
          # But 8600 is only ~9.5% — should not breach
          assert tracker.is_weekly_limit_breached(8600.0, max_pct=10.0) is False


  def test_missing_state_file_returns_false():
      with tempfile.TemporaryDirectory() as d:
          tracker = DrawdownTracker(state_file=Path(d) / "does_not_exist.json")
          # No history = no block (fail open)
          assert tracker.is_weekly_limit_breached(1.0, max_pct=5.0) is False
          assert tracker.is_daily_limit_breached(1.0, max_pct=5.0) is False
  ```

- [ ] **Step 2 — Run tests (expect failure)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_drawdown_tracker.py -v
  ```

  Expected: all 6 tests fail with `ModuleNotFoundError: No module named 'learning.drawdown_tracker'`.

- [ ] **Step 3 — Implement `learning/drawdown_tracker.py`**

  Create the file. Key implementation notes:

  - `_load()` reads the JSON file; returns `{}` on any error.
  - `_save(state: dict)` writes the file atomically.
  - `update()` uses the Monday-detection and date-change logic described above. If the file did not previously exist, it initialises both `week_start` and `day_start` to `portfolio_value` / `as_of_date`.
  - `is_weekly_limit_breached()` and `is_daily_limit_breached()` guard with `max_pct >= 100` first (return False), then load state and compute drop.
  - Never raises — wrap all I/O in try/except and return False on any error.

- [ ] **Step 4 — Run tests (expect all pass)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_drawdown_tracker.py -v
  ```

  Expected: all 6 tests pass.

- [ ] **Step 5 — Commit**

  ```bash
  git add learning/drawdown_tracker.py tests/test_drawdown_tracker.py
  git commit -m "feat: add DrawdownTracker with weekly/daily circuit breaker"
  ```

---

## Task 3: EarningsBlackout

**Files touched:** `learning/earnings_blackout.py` (create), `tests/test_earnings_blackout.py` (create)

### Background

Prevents opening new positions in stocks reporting earnings within a configurable window. Reads from the existing `cache/earnings-calendar.json` file, which is already populated by the earnings-calendar skill. The design fails open — a missing cache never blocks trading.

### Earnings cache format

The existing file (`cache/earnings-calendar.json`) uses `"events"` as the top-level key, matching what `pivot_monitor.py` already parses in `_get_earnings_soon_symbols()`:

```json
{
  "events": [
    {"symbol": "AAPL", "date": "2026-03-25T07:00:00", "time": "BMO"}
  ]
}
```

The `date` field is an ISO-8601 datetime string. Parse with `datetime.fromisoformat(e["date"]).date()`.

### Class design

```python
# learning/earnings_blackout.py
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


class EarningsBlackout:
    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir

    def is_blacked_out(self, symbol: str, as_of_date: date, blackout_days: int) -> bool:
        """Returns True if symbol has earnings within blackout_days calendar days.
        Returns False if blackout_days == 0 or cache missing/corrupt (fail open)."""
```

`is_blacked_out` logic:
1. If `blackout_days == 0`: return False (disabled).
2. Load `self._cache_dir / "earnings-calendar.json"`. If missing or corrupt: return False.
3. For each event where `event["symbol"].upper() == symbol.upper()`, parse the date and check if `0 <= (event_date - as_of_date).days <= blackout_days - 1`. If any match: return True.
4. Return False.

### Step-by-step

- [ ] **Step 1 — Write failing tests**

  Create `tests/test_earnings_blackout.py` with all 5 tests listed below.

  ```python
  # tests/test_earnings_blackout.py
  import sys
  import json
  import tempfile
  from pathlib import Path
  from datetime import date, timedelta
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  from learning.earnings_blackout import EarningsBlackout


  def _write_calendar(cache_dir: Path, events: list) -> None:
      (cache_dir / "earnings-calendar.json").write_text(
          json.dumps({"events": events})
      )


  def test_symbol_within_blackout_returns_true():
      with tempfile.TemporaryDirectory() as d:
          cache = Path(d)
          today = date(2026, 3, 22)
          earnings_in_3_days = (today + timedelta(days=3)).isoformat() + "T07:00:00"
          _write_calendar(cache, [{"symbol": "AAPL", "date": earnings_in_3_days}])
          eb = EarningsBlackout(cache_dir=cache)
          assert eb.is_blacked_out("AAPL", today, blackout_days=5) is True


  def test_symbol_outside_blackout_returns_false():
      with tempfile.TemporaryDirectory() as d:
          cache = Path(d)
          today = date(2026, 3, 22)
          earnings_in_10_days = (today + timedelta(days=10)).isoformat() + "T07:00:00"
          _write_calendar(cache, [{"symbol": "AAPL", "date": earnings_in_10_days}])
          eb = EarningsBlackout(cache_dir=cache)
          assert eb.is_blacked_out("AAPL", today, blackout_days=5) is False


  def test_disabled_at_0_days():
      with tempfile.TemporaryDirectory() as d:
          cache = Path(d)
          today = date(2026, 3, 22)
          tomorrow = (today + timedelta(days=1)).isoformat() + "T07:00:00"
          _write_calendar(cache, [{"symbol": "AAPL", "date": tomorrow}])
          eb = EarningsBlackout(cache_dir=cache)
          # blackout_days=0 means disabled — never block
          assert eb.is_blacked_out("AAPL", today, blackout_days=0) is False


  def test_missing_cache_returns_false():
      with tempfile.TemporaryDirectory() as d:
          cache = Path(d)
          # No earnings-calendar.json written — must fail open
          eb = EarningsBlackout(cache_dir=cache)
          assert eb.is_blacked_out("AAPL", date.today(), blackout_days=5) is False


  def test_symbol_not_in_calendar_returns_false():
      with tempfile.TemporaryDirectory() as d:
          cache = Path(d)
          today = date(2026, 3, 22)
          tomorrow = (today + timedelta(days=1)).isoformat() + "T07:00:00"
          _write_calendar(cache, [{"symbol": "TSLA", "date": tomorrow}])
          eb = EarningsBlackout(cache_dir=cache)
          # AAPL not in the calendar — must not be blocked
          assert eb.is_blacked_out("AAPL", today, blackout_days=5) is False
  ```

- [ ] **Step 2 — Run tests (expect failure)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_earnings_blackout.py -v
  ```

  Expected: all 5 tests fail with `ModuleNotFoundError: No module named 'learning.earnings_blackout'`.

- [ ] **Step 3 — Implement `learning/earnings_blackout.py`**

  Create the file following the logic described above. Key notes:

  - Symbol comparison must be case-insensitive: `e.get("symbol", "").upper() == symbol.upper()`.
  - Date parsing: `datetime.fromisoformat(e["date"]).date()` — wrap in try/except to skip malformed entries.
  - The blackout window is inclusive on both ends: today through `today + timedelta(days=blackout_days - 1)`. So `blackout_days=5` covers today + next 4 days.
  - Never raises — any exception returns False.

- [ ] **Step 4 — Run tests (expect all pass)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_earnings_blackout.py -v
  ```

  Expected: all 5 tests pass.

- [ ] **Step 5 — Commit**

  ```bash
  git add learning/earnings_blackout.py tests/test_earnings_blackout.py
  git commit -m "feat: add EarningsBlackout guard using earnings-calendar.json cache"
  ```

---

## Task 4: Wire into pivot_monitor.py + guard rails chain

**Files touched:** `pivot_monitor.py` (modify), `tests/test_pivot_monitor.py` (modify)

**Prerequisite:** Tasks 1, 2, and 3 must be complete.

### Overview of changes

1. **`__init__`** — add three new optional parameters: `pdt_tracker`, `drawdown_tracker`, `earnings_blackout`.
2. **`_guard_rails_allow`** — add `tag: str = "CLEAR"` parameter and three new guard checks after the existing max-positions check.
3. **`_check_breakout`** — pass `tag` to `_guard_rails_allow`.

### 4a — New `__init__` signature

```python
def __init__(
    self,
    alpaca_client: AlpacaClient,
    settings_manager: SettingsManager,
    cache_dir: Path,
    rule_store=None,
    multiplier_store=None,
    pdt_tracker=None,
    drawdown_tracker=None,
    earnings_blackout=None,
    _search_fn: Optional[Callable[[str], list[str]]] = None,
    _data_stream=None,
):
    self._alpaca = alpaca_client
    self._settings = settings_manager
    self._cache_dir = cache_dir
    self._rule_store = rule_store
    self._multiplier_store = multiplier_store
    self._pdt_tracker = pdt_tracker
    self._drawdown_tracker = drawdown_tracker
    self._earnings_blackout = earnings_blackout
    self._search_fn = _search_fn or _default_search_fn
    self._data_stream = _data_stream
    self._candidates: list[dict] = []
    self._triggered: set[str] = set()
    self._lock = threading.Lock()
```

### 4b — Updated `_guard_rails_allow` signature and new checks

```python
def _guard_rails_allow(self, candidate: dict, tag: str = "CLEAR") -> tuple[bool, str]:
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
                return False, f"Market Top risk={risk_score} >= 65 — Auto paused"
        except (json.JSONDecodeError, OSError):
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

    # PDT selectivity
    if self._pdt_tracker is not None:
        from datetime import date as _date
        allowed_tags = self._pdt_tracker.get_allowed_tags(_date.today())
        if not allowed_tags:
            return False, "PDT: 3 day trades used — no new entries"
        if tag not in allowed_tags:
            return False, f"PDT: {len(allowed_tags)} slot(s) left — {tag} not allowed"

    # Drawdown circuit breaker
    if self._drawdown_tracker is not None:
        settings = self._settings.load()
        try:
            acct = self._alpaca.get_account()
            portfolio_value = float(acct["portfolio_value"])
            max_weekly = settings.get("max_weekly_drawdown_pct", 10.0)
            max_daily = settings.get("max_daily_loss_pct", 5.0)
            from datetime import date as _date
            self._drawdown_tracker.update(portfolio_value, _date.today())
            if self._drawdown_tracker.is_weekly_limit_breached(portfolio_value, max_weekly):
                return False, f"drawdown: weekly limit {max_weekly}% breached"
            if self._drawdown_tracker.is_daily_limit_breached(portfolio_value, max_daily):
                return False, f"drawdown: daily limit {max_daily}% breached"
        except Exception as e:
            print(f"[pivot_monitor] drawdown check error: {e}", file=sys.stderr)

    # Earnings blackout
    if self._earnings_blackout is not None:
        settings = self._settings.load()
        blackout_days = settings.get("earnings_blackout_days", 5)
        symbol = candidate.get("symbol", "")
        from datetime import date as _date
        if self._earnings_blackout.is_blacked_out(symbol, _date.today(), blackout_days):
            return False, f"earnings blackout: {symbol} reports within {blackout_days} days"

    return True, ""
```

### 4c — Update `_check_breakout` to pass `tag`

In `_check_breakout`, the existing call to `_guard_rails_allow` must be updated to pass the tag:

```python
allowed, reason = self._guard_rails_allow(c, tag=tag)
```

`tag` is already extracted earlier in `_check_breakout` as `tag = c.get("confidence_tag", "CLEAR")`.

### Step-by-step

- [ ] **Step 1 — Write failing tests**

  Append the following 6 tests to `tests/test_pivot_monitor.py`. These tests will fail because the current `_guard_rails_allow` does not accept a `tag` parameter and the new tracker attributes do not exist yet.

  ```python
  # ── Task 4: Capital protection guard rail tests ──────────────────────────


  def make_monitor_with_trackers(tmp_path, pdt_tracker=None, drawdown_tracker=None, earnings_blackout=None):
      alpaca = MagicMock()
      alpaca.is_configured = True
      alpaca.get_positions.return_value = []
      alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
      settings = MagicMock()
      settings.load.return_value = {
          "mode": "auto",
          "default_risk_pct": 1.0,
          "max_positions": 5,
          "max_position_size_pct": 10.0,
          "max_weekly_drawdown_pct": 10.0,
          "max_daily_loss_pct": 5.0,
          "earnings_blackout_days": 5,
      }
      return PivotWatchlistMonitor(
          alpaca_client=alpaca,
          settings_manager=settings,
          cache_dir=tmp_path,
          pdt_tracker=pdt_tracker,
          drawdown_tracker=drawdown_tracker,
          earnings_blackout=earnings_blackout,
      )


  def test_pdt_0_slots_blocks_all_tags():
      """When 3 day trades used, no new entries allowed regardless of tag."""
      with tempfile.TemporaryDirectory() as d:
          from learning.pdt_tracker import PDTTracker
          from datetime import date
          tracker = PDTTracker(trades_file=Path(d) / "pdt.json")
          today = date.today()
          for sym in ("A", "B", "C"):
              tracker.record_day_trade(sym, today)

          monitor = make_monitor_with_trackers(Path(d), pdt_tracker=tracker)
          import pivot_monitor as pm
          pm._market_is_open_now = lambda: True

          allowed, reason = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="HIGH_CONVICTION")
          assert allowed is False
          assert "PDT" in reason


  def test_pdt_1_slot_blocks_clear_allows_high_conviction():
      """With 1 slot left, CLEAR is blocked, HIGH_CONVICTION is allowed."""
      with tempfile.TemporaryDirectory() as d:
          from learning.pdt_tracker import PDTTracker
          from datetime import date
          tracker = PDTTracker(trades_file=Path(d) / "pdt.json")
          today = date.today()
          for sym in ("A", "B"):
              tracker.record_day_trade(sym, today)

          monitor = make_monitor_with_trackers(Path(d), pdt_tracker=tracker)
          import pivot_monitor as pm
          pm._market_is_open_now = lambda: True

          allowed_clear, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
          allowed_hc, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="HIGH_CONVICTION")

          assert allowed_clear is False
          assert allowed_hc is True


  def test_pdt_2_slots_blocks_uncertain():
      """With 2 slots left (1 trade used), UNCERTAIN is blocked."""
      with tempfile.TemporaryDirectory() as d:
          from learning.pdt_tracker import PDTTracker
          from datetime import date
          tracker = PDTTracker(trades_file=Path(d) / "pdt.json")
          today = date.today()
          tracker.record_day_trade("A", today)

          monitor = make_monitor_with_trackers(Path(d), pdt_tracker=tracker)
          import pivot_monitor as pm
          pm._market_is_open_now = lambda: True

          allowed_uncertain, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="UNCERTAIN")
          allowed_clear, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")

          assert allowed_uncertain is False
          assert allowed_clear is True


  def test_drawdown_weekly_limit_blocks_guard():
      """Weekly drawdown exceeding threshold must block new orders."""
      with tempfile.TemporaryDirectory() as d:
          from learning.drawdown_tracker import DrawdownTracker
          from datetime import date
          tracker = DrawdownTracker(state_file=Path(d) / "dd.json")
          monday = date(2026, 3, 16)
          tracker.update(10000.0, monday)

          alpaca = MagicMock()
          alpaca.is_configured = True
          alpaca.get_positions.return_value = []
          # Portfolio dropped 11% — breaches the 10% weekly limit
          alpaca.get_account.return_value = {"portfolio_value": 8900.0}
          settings = MagicMock()
          settings.load.return_value = {
              "mode": "auto", "default_risk_pct": 1.0,
              "max_positions": 5, "max_position_size_pct": 10.0,
              "max_weekly_drawdown_pct": 10.0, "max_daily_loss_pct": 5.0,
              "earnings_blackout_days": 5,
          }
          monitor = PivotWatchlistMonitor(
              alpaca_client=alpaca,
              settings_manager=settings,
              cache_dir=Path(d),
              drawdown_tracker=tracker,
          )

          import pivot_monitor as pm
          pm._market_is_open_now = lambda: True

          allowed, reason = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
          assert allowed is False
          assert "drawdown" in reason.lower()


  def test_drawdown_disabled_at_100_pct_always_allows():
      """max_weekly_drawdown_pct=100 must never block."""
      with tempfile.TemporaryDirectory() as d:
          from learning.drawdown_tracker import DrawdownTracker
          from datetime import date
          tracker = DrawdownTracker(state_file=Path(d) / "dd.json")
          monday = date(2026, 3, 16)
          tracker.update(10000.0, monday)

          alpaca = MagicMock()
          alpaca.is_configured = True
          alpaca.get_positions.return_value = []
          alpaca.get_account.return_value = {"portfolio_value": 1.0}  # catastrophic drop
          settings = MagicMock()
          settings.load.return_value = {
              "mode": "auto", "default_risk_pct": 1.0,
              "max_positions": 5, "max_position_size_pct": 10.0,
              "max_weekly_drawdown_pct": 100.0, "max_daily_loss_pct": 100.0,
              "earnings_blackout_days": 0,
          }
          monitor = PivotWatchlistMonitor(
              alpaca_client=alpaca,
              settings_manager=settings,
              cache_dir=Path(d),
              drawdown_tracker=tracker,
          )

          import pivot_monitor as pm
          pm._market_is_open_now = lambda: True

          allowed, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
          assert allowed is True


  def test_earnings_blackout_blocks_when_reporting_soon():
      """Symbol reporting within blackout window must be blocked."""
      with tempfile.TemporaryDirectory() as d:
          from learning.earnings_blackout import EarningsBlackout
          from datetime import date, timedelta
          import json as _json
          cache = Path(d)
          today = date.today()
          earnings_in_3_days = (today + timedelta(days=3)).isoformat() + "T07:00:00"
          (cache / "earnings-calendar.json").write_text(
              _json.dumps({"events": [{"symbol": "AAPL", "date": earnings_in_3_days}]})
          )
          eb = EarningsBlackout(cache_dir=cache)
          monitor = make_monitor_with_trackers(Path(d), earnings_blackout=eb)

          import pivot_monitor as pm
          pm._market_is_open_now = lambda: True

          allowed, reason = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
          assert allowed is False
          assert "earnings" in reason.lower()
  ```

- [ ] **Step 2 — Run tests (expect failure)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_pivot_monitor.py -v -k "pdt or drawdown or earnings_blackout"
  ```

  Expected: the 6 new tests fail (existing tests should continue to pass).

- [ ] **Step 3 — Implement changes to `pivot_monitor.py`**

  Apply the three changes described in 4a, 4b, and 4c above:

  1. Add `pdt_tracker=None`, `drawdown_tracker=None`, `earnings_blackout=None` to `__init__` and assign them to `self._pdt_tracker`, `self._drawdown_tracker`, `self._earnings_blackout`.
  2. Change `_guard_rails_allow(self, candidate: dict)` to `_guard_rails_allow(self, candidate: dict, tag: str = "CLEAR")` and append the three new guard blocks.
  3. In `_check_breakout`, update the `_guard_rails_allow` call to `self._guard_rails_allow(c, tag=tag)`.

- [ ] **Step 4 — Run tests (expect all pass)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_pivot_monitor.py -v
  ```

  Expected: all tests in `test_pivot_monitor.py` pass (existing + 6 new).

- [ ] **Step 5 — Commit**

  ```bash
  git add pivot_monitor.py tests/test_pivot_monitor.py
  git commit -m "feat: wire PDTTracker, DrawdownTracker, EarningsBlackout into _guard_rails_allow"
  ```

---

## Task 5: main.py + settings_manager.py + settings_modal.html + test_routes.py

**Files touched:** `main.py` (modify), `settings_manager.py` (modify), `templates/fragments/settings_modal.html` (modify), `tests/test_routes.py` (modify)

**Prerequisite:** Tasks 1–4 must be complete.

### Overview of changes

- `settings_manager.py`: add 3 new fields to `_DEFAULTS`.
- `main.py`: import the 3 new classes, instantiate them, pass to `PivotWatchlistMonitor`.
- `templates/fragments/settings_modal.html`: add 3 new form fields matching the existing field pattern.
- `tests/test_routes.py`: add 3 settings round-trip tests.

### 5a — settings_manager.py

Add to `_DEFAULTS` (after `"environment": "paper"`):

```python
"max_weekly_drawdown_pct": 10.0,
"max_daily_loss_pct": 5.0,
"earnings_blackout_days": 5,
```

No other changes are needed. The `save()` method does not validate these fields — they are stored as-is, which is intentional (the route handler will need updating in a future task to accept the new form fields).

### 5b — main.py

Add imports after the existing `learning` imports:

```python
from learning.pdt_tracker import PDTTracker
from learning.drawdown_tracker import DrawdownTracker
from learning.earnings_blackout import EarningsBlackout
```

Instantiate before `pivot_monitor`:

```python
pdt_tracker = PDTTracker()
drawdown_tracker = DrawdownTracker()
earnings_blackout = EarningsBlackout(cache_dir=CACHE_DIR)
```

Update `PivotWatchlistMonitor(...)` to add the three new keyword arguments:

```python
pivot_monitor = PivotWatchlistMonitor(
    alpaca_client=alpaca,
    settings_manager=settings_manager,
    cache_dir=CACHE_DIR,
    rule_store=rule_store,
    multiplier_store=multiplier_store,
    pdt_tracker=pdt_tracker,
    drawdown_tracker=drawdown_tracker,
    earnings_blackout=earnings_blackout,
)
```

Also update `post_settings` in `main.py` to accept and save the three new form fields. Add them as optional `Form` parameters with defaults matching `_DEFAULTS`:

```python
@app.post("/api/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    mode: str = Form(...),
    default_risk_pct: float = Form(...),
    max_positions: int = Form(...),
    max_position_size_pct: float = Form(...),
    environment: str = Form(...),
    live_confirm: str = Form(""),
    max_weekly_drawdown_pct: float = Form(10.0),
    max_daily_loss_pct: float = Form(5.0),
    earnings_blackout_days: int = Form(5),
):
    ...
    settings_manager.save({
        "mode": mode,
        "default_risk_pct": default_risk_pct,
        "max_positions": max_positions,
        "max_position_size_pct": max_position_size_pct,
        "environment": environment,
        "max_weekly_drawdown_pct": max_weekly_drawdown_pct,
        "max_daily_loss_pct": max_daily_loss_pct,
        "earnings_blackout_days": earnings_blackout_days,
    })
```

### 5c — templates/fragments/settings_modal.html

Add three new `<div class="form-row">` blocks inside the `<form>` element, after the existing `max_position_size_pct` row and before the Save/Cancel buttons. Follow the exact existing field pattern:

```html
      <!-- Capital Protection -->
      <div class="form-row">
        <div class="form-label">Max Weekly Drawdown % (100 = off)</div>
        <input type="number" name="max_weekly_drawdown_pct" class="form-input"
               value="{{ settings.max_weekly_drawdown_pct }}" min="1" max="100" step="0.5">
      </div>
      <div class="form-row">
        <div class="form-label">Max Daily Loss % (100 = off)</div>
        <input type="number" name="max_daily_loss_pct" class="form-input"
               value="{{ settings.max_daily_loss_pct }}" min="1" max="100" step="0.5">
      </div>
      <div class="form-row">
        <div class="form-label">Earnings Blackout Days (0 = off)</div>
        <input type="number" name="earnings_blackout_days" class="form-input"
               value="{{ settings.earnings_blackout_days }}" min="0" max="30">
      </div>
```

### Step-by-step

- [ ] **Step 1 — Write failing tests**

  Append the following 3 tests to `tests/test_routes.py`:

  ```python
  def test_new_settings_fields_save_and_load_round_trip():
      """New capital-protection fields must persist through POST and appear in GET."""
      client = make_client()
      r = client.post("/api/settings", data={
          "mode": "advisory",
          "default_risk_pct": "1.0",
          "max_positions": "5",
          "max_position_size_pct": "10.0",
          "environment": "paper",
          "max_weekly_drawdown_pct": "8.0",
          "max_daily_loss_pct": "3.5",
          "earnings_blackout_days": "7",
      })
      assert r.status_code == 200
      # Verify via SettingsManager directly
      from settings_manager import SettingsManager
      s = SettingsManager().load()
      assert s["max_weekly_drawdown_pct"] == 8.0
      assert s["max_daily_loss_pct"] == 3.5
      assert s["earnings_blackout_days"] == 7


  def test_new_settings_fields_have_defaults_when_not_set():
      """When settings.json is absent, new fields must return their defaults."""
      from settings_manager import SettingsManager
      s = SettingsManager().load()
      assert s["max_weekly_drawdown_pct"] == 10.0
      assert s["max_daily_loss_pct"] == 5.0
      assert s["earnings_blackout_days"] == 5


  def test_settings_form_includes_new_fields():
      """GET /api/settings HTML must contain the three new input field names."""
      client = make_client()
      r = client.get("/api/settings")
      assert r.status_code == 200
      assert b"max_weekly_drawdown_pct" in r.content
      assert b"max_daily_loss_pct" in r.content
      assert b"earnings_blackout_days" in r.content
  ```

- [ ] **Step 2 — Run tests (expect failure)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_routes.py -v -k "new_settings or settings_form"
  ```

  Expected: all 3 new tests fail. `test_new_settings_fields_have_defaults_when_not_set` fails because `_DEFAULTS` does not yet have the keys. `test_settings_form_includes_new_fields` fails because the HTML does not include the fields. `test_new_settings_fields_save_and_load_round_trip` fails because the POST route does not accept the new fields.

- [ ] **Step 3 — Implement all changes**

  Apply changes in this order to avoid import errors:

  1. Update `settings_manager.py` — add 3 fields to `_DEFAULTS`.
  2. Update `main.py` — add imports, instantiation, `pivot_monitor` kwargs, `post_settings` params.
  3. Update `templates/fragments/settings_modal.html` — add 3 form rows.

- [ ] **Step 4 — Run tests (expect all pass)**

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/test_routes.py -v
  ```

  Expected: all tests in `test_routes.py` pass (existing + 3 new).

- [ ] **Step 5 — Full test suite**

  Run the complete test suite to confirm no regressions:

  ```bash
  cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
  uv run pytest tests/ -v
  ```

  Expected: all tests pass.

- [ ] **Step 6 — Commit**

  ```bash
  git add main.py settings_manager.py templates/fragments/settings_modal.html tests/test_routes.py
  git commit -m "feat: wire capital protection settings into main.py, settings_manager, and settings form"
  ```

---

## Summary

| Task | New files | Modified files | Tests written |
|------|-----------|----------------|---------------|
| 1 — PDTTracker | `learning/pdt_tracker.py` | — | `tests/test_pdt_tracker.py` (8 tests) |
| 2 — DrawdownTracker | `learning/drawdown_tracker.py` | — | `tests/test_drawdown_tracker.py` (6 tests) |
| 3 — EarningsBlackout | `learning/earnings_blackout.py` | — | `tests/test_earnings_blackout.py` (5 tests) |
| 4 — Guard rails | — | `pivot_monitor.py`, `tests/test_pivot_monitor.py` | 6 new tests in existing file |
| 5 — Wiring | — | `main.py`, `settings_manager.py`, `templates/fragments/settings_modal.html`, `tests/test_routes.py` | 3 new tests in existing file |

**Total new tests:** 28 (8 + 6 + 5 + 6 + 3)

**Verification command (run after all tasks complete):**

```bash
cd /Users/eirikrskole/work/trading-claude-code/claude-trading-skills/examples/market-dashboard
uv run pytest tests/ -v
```
