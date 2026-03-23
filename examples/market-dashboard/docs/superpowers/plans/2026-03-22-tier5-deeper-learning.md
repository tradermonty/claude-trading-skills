# Tier 5: Deeper Learning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bot learn from its own trade history — time-of-day patterns, optimal stop distances, regime confidence, and paper trading experiments.

**Architecture:** Four new learning classes in `learning/` following MultiplierStore constructor-injection pattern. Regime confidence is a stateless helper in `pivot_monitor.py`. `/stats` page is a new FastAPI route + template. Tasks 1-4 (new classes) can be dispatched in parallel. Task 5 (regime confidence) and Task 6 (/stats page) are independent too.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, standard library (json, math, datetime)

**Parallelization note:** Tasks 1, 2, 3, 4, and 5 are fully independent. All 5 can be dispatched simultaneously.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `learning/time_of_day_tracker.py` | Create | Track win rates per hour of trading day |
| `learning/stop_distance_store.py` | Create | Learn optimal stop distance per bucket |
| `learning/experiment_tracker.py` | Create | Paper-only parameter variation experiments |
| `pivot_monitor.py` | Modify | Add `_get_regime_confidence_multiplier()`, apply in `_calc_qty()`, call ExperimentTracker |
| `learning/pattern_extractor.py` | Modify | Call TimeOfDayTracker, StopDistanceStore, ExperimentTracker in `_update_multipliers()` |
| `main.py` | Modify | Instantiate new classes, add `/stats` route |
| `templates/stats.html` | Create | Stats dashboard page |
| `tests/test_time_of_day_tracker.py` | Create | Unit tests |
| `tests/test_stop_distance_store.py` | Create | Unit tests |
| `tests/test_experiment_tracker.py` | Create | Unit tests |
| `tests/test_pivot_monitor.py` | Modify | Regime confidence tests |
| `tests/test_routes.py` | Modify | /stats route test |

---

## Task 1: TimeOfDayTracker

**New file:** `learning/time_of_day_tracker.py`

**Why first:** Fully independent, no dependencies on other tasks. Follows MultiplierStore constructor-injection pattern exactly.

### Interface

```python
LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_FILE = LEARNING_DIR / "time_of_day_stats.json"

class TimeOfDayTracker:
    """Tracks win rates per hour of the trading day (ET). Hours 9-15."""

    def __init__(self, stats_file: Path = DEFAULT_FILE):
        self._file = stats_file

    def record(self, entry_hour_et: int, outcome: str) -> None:
        """Record outcome for an hour. outcome must be 'win' or 'loss'."""

    def get_confidence_adjustment(self, hour_et: int) -> str:
        """Returns required min confidence tag for this hour.
        'NORMAL' if < 10 samples or win_rate >= 40%
        'HIGH_CONVICTION' if win_rate 30-40% and n >= 10
        'BLOCKED' if win_rate < 30% and n >= 10
        """

    def get_stats(self) -> dict:
        """Returns all hour stats for the /stats page."""
```

**Persistence format** (`learning/time_of_day_stats.json`):
```json
{"9": {"wins": 5, "losses": 3}, "10": {"wins": 12, "losses": 4}}
```

### TDD Steps

- [ ] **1.1 — Write failing tests** in `tests/test_time_of_day_tracker.py`:

  ```python
  import sys, json, tempfile
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  def make_tracker(tmp: Path):
      from learning.time_of_day_tracker import TimeOfDayTracker
      return TimeOfDayTracker(stats_file=tmp / "time_of_day_stats.json")

  def test_record_win_increments_win_count():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d))
          tracker.record(10, "win")
          tracker.record(10, "win")
          stats = tracker.get_stats()
          assert stats["10"]["wins"] == 2
          assert stats["10"]["losses"] == 0

  def test_record_loss_increments_loss_count():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d))
          tracker.record(11, "loss")
          stats = tracker.get_stats()
          assert stats["11"]["losses"] == 1
          assert stats["11"]["wins"] == 0

  def test_insufficient_data_returns_normal():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d))
          for _ in range(9):
              tracker.record(10, "loss")  # 9 samples, all losses — still < 10
          assert tracker.get_confidence_adjustment(10) == "NORMAL"

  def test_win_rate_30_to_40_pct_returns_high_conviction():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d))
          # 3 wins, 7 losses = 30% win rate, n=10
          for _ in range(3):
              tracker.record(9, "win")
          for _ in range(7):
              tracker.record(9, "loss")
          assert tracker.get_confidence_adjustment(9) == "HIGH_CONVICTION"

  def test_win_rate_below_30_pct_returns_blocked():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d))
          # 2 wins, 8 losses = 20% win rate, n=10
          for _ in range(2):
              tracker.record(14, "win")
          for _ in range(8):
              tracker.record(14, "loss")
          assert tracker.get_confidence_adjustment(14) == "BLOCKED"

  def test_win_rate_above_40_pct_returns_normal():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d))
          # 5 wins, 5 losses = 50% win rate, n=10
          for _ in range(5):
              tracker.record(11, "win")
          for _ in range(5):
              tracker.record(11, "loss")
          assert tracker.get_confidence_adjustment(11) == "NORMAL"
  ```

  Run `uv run pytest tests/test_time_of_day_tracker.py -v` — all 6 should fail (ImportError).

- [ ] **1.2 — Implement** `learning/time_of_day_tracker.py`:

  - `__init__`: store `self._file = stats_file`
  - `_load()`: read JSON from `self._file`, return `{}` on missing/corrupt
  - `_save(data)`: write JSON with `indent=2`, create parent dirs
  - `record(entry_hour_et, outcome)`: load, increment `data[str(hour)]["wins"]` or `["losses"]`, save
  - `get_confidence_adjustment(hour_et)`: load, look up `str(hour_et)`, compute `n = wins + losses`. If `n < 10` → `"NORMAL"`. Compute `win_rate = wins / n`. If `win_rate < 0.30` → `"BLOCKED"`. If `win_rate < 0.40` → `"HIGH_CONVICTION"`. Else → `"NORMAL"`.
  - `get_stats()`: return the loaded dict directly

  Run tests — all 6 should pass.

- [ ] **1.3 — Verify** `uv run pytest tests/test_time_of_day_tracker.py -v` passes (6/6).

---

## Task 2: StopDistanceStore

**New file:** `learning/stop_distance_store.py`

**Why independent:** No dependencies on other tasks. Follows the same constructor-injection pattern.

### Interface

```python
LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_FILE = LEARNING_DIR / "stop_distance_stats.json"
SEED_STOP_PCT = 3.0
MIN_SAMPLES = 10

class StopDistanceStore:
    """Learns optimal stop distance per bucket key."""

    def __init__(self, stats_file: Path = DEFAULT_FILE):
        self._file = stats_file

    def record(self, bucket_key: str, stop_pct: float, outcome: str) -> None:
        """Record a trade's stop distance and outcome."""

    def get_stop_pct(self, bucket_key: str) -> float:
        """Returns learned optimal stop %. Falls back to SEED_STOP_PCT if < MIN_SAMPLES."""
```

**Learning logic:** Track stop distances for winning trades. The optimal stop is the median stop distance of winning trades per bucket. Falls back to `SEED_STOP_PCT = 3.0` when fewer than `MIN_SAMPLES = 10` total trades exist for the bucket.

**Persistence format** (`learning/stop_distance_stats.json`):
```json
{"vcp+CLEAR+bull": {"stop_pcts": [3.0, 2.8, 3.2], "outcomes": ["win", "win", "loss"]}}
```

### TDD Steps

- [ ] **2.1 — Write failing tests** in `tests/test_stop_distance_store.py`:

  ```python
  import sys, json, tempfile, math
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  def make_store(tmp: Path):
      from learning.stop_distance_store import StopDistanceStore
      return StopDistanceStore(stats_file=tmp / "stop_distance_stats.json")

  def test_returns_seed_when_below_min_samples():
      from learning.stop_distance_store import SEED_STOP_PCT
      with tempfile.TemporaryDirectory() as d:
          store = make_store(Path(d))
          assert store.get_stop_pct("vcp+CLEAR+bull") == SEED_STOP_PCT

  def test_returns_median_of_winning_stops_when_enough_samples():
      with tempfile.TemporaryDirectory() as d:
          store = make_store(Path(d))
          # 10 trades: 7 wins with stop pcts [2.5, 2.7, 2.8, 3.0, 3.1, 3.3, 3.5], 3 losses
          wins = [2.5, 2.7, 2.8, 3.0, 3.1, 3.3, 3.5]
          for pct in wins:
              store.record("vcp+CLEAR+bull", pct, "win")
          for pct in [1.5, 2.0, 4.0]:
              store.record("vcp+CLEAR+bull", pct, "loss")
          result = store.get_stop_pct("vcp+CLEAR+bull")
          # median of sorted wins [2.5,2.7,2.8,3.0,3.1,3.3,3.5] = 3.0
          assert result == 3.0

  def test_record_appends_correctly():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          store = make_store(tmp)
          store.record("vcp+CLEAR+bull", 3.0, "win")
          store.record("vcp+CLEAR+bull", 2.5, "loss")
          data = json.loads((tmp / "stop_distance_stats.json").read_text())
          assert data["vcp+CLEAR+bull"]["stop_pcts"] == [3.0, 2.5]
          assert data["vcp+CLEAR+bull"]["outcomes"] == ["win", "loss"]

  def test_corrupt_file_returns_seed_default():
      from learning.stop_distance_store import SEED_STOP_PCT
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          (tmp / "stop_distance_stats.json").write_text("not valid json")
          store = make_store(tmp)
          assert store.get_stop_pct("vcp+CLEAR+bull") == SEED_STOP_PCT

  def test_unknown_bucket_returns_seed_default():
      from learning.stop_distance_store import SEED_STOP_PCT
      with tempfile.TemporaryDirectory() as d:
          store = make_store(Path(d))
          assert store.get_stop_pct("nonexistent+bucket+key") == SEED_STOP_PCT
  ```

  Run `uv run pytest tests/test_stop_distance_store.py -v` — all 5 should fail.

- [ ] **2.2 — Implement** `learning/stop_distance_store.py`:

  - `SEED_STOP_PCT = 3.0`, `MIN_SAMPLES = 10`
  - `__init__`: store `self._file = stats_file`
  - `_load()`: read JSON, return `{}` on missing/corrupt
  - `_save(data)`: write JSON with `indent=2`, create parent dirs
  - `record(bucket_key, stop_pct, outcome)`: load, append to `data[bucket_key]["stop_pcts"]` and `data[bucket_key]["outcomes"]`, save
  - `get_stop_pct(bucket_key)`:
    - load data
    - if `bucket_key` not in data → return `SEED_STOP_PCT`
    - `n = len(data[bucket_key]["stop_pcts"])`
    - if `n < MIN_SAMPLES` → return `SEED_STOP_PCT`
    - collect `winning_stops = [pct for pct, outcome in zip(stop_pcts, outcomes) if outcome == "win"]`
    - if no winning stops → return `SEED_STOP_PCT`
    - return `median(winning_stops)` — use `statistics.median` from stdlib

  Run tests — all 5 should pass.

- [ ] **2.3 — Verify** `uv run pytest tests/test_stop_distance_store.py -v` passes (5/5).

---

## Task 3: ExperimentTracker

**New file:** `learning/experiment_tracker.py`

**Why independent:** Paper-only guard is a hard gate (`is_paper` flag). No dependency on other new tasks.

### Interface

```python
import random
LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_FILE = LEARNING_DIR / "experiments.json"
EXPLORATION_RATE = 0.10  # 10% of trades try a variation

class ExperimentTracker:
    """Paper trading only. Tries parameter variations 10% of the time."""

    def __init__(self, experiments_file: Path = DEFAULT_FILE, is_paper: bool = True):
        self._file = experiments_file
        self._is_paper = is_paper

    def should_experiment(self) -> bool:
        """Returns True 10% of the time, only in paper mode."""
        if not self._is_paper:
            return False
        return random.random() < EXPLORATION_RATE

    def get_variation(self) -> dict:
        """Returns a random parameter variation dict."""
        return {
            "stop_pct": round(random.choice([2.5, 3.0, 3.5]), 1),
            "partial_exit_at_r": round(random.choice([0.75, 1.0, 1.25, 1.5]), 2),
            "min_volume_ratio": round(random.choice([1.25, 1.5, 1.75, 2.0]), 2),
        }

    def record_experiment(self, experiment_id: str, variation: dict, outcome: str, achieved_rr: float) -> None:
        """Record the outcome of an experiment."""

    def should_promote(self, variation_key: str) -> bool:
        """Returns True if variation consistently outperforms control (win_rate + 5%, n>=10)."""

    def get_stats(self) -> dict:
        """Returns all experiment stats for the /stats page."""
```

**Persistence format** (`learning/experiments.json`):
```json
{
  "experiments": {
    "stop_pct=2.5": {
      "wins": 8, "losses": 2, "achieved_rr": [2.1, 1.8, 2.5, 3.0, 1.9, 2.2, 2.8, 3.1],
      "variation": {"stop_pct": 2.5, "partial_exit_at_r": 1.0, "min_volume_ratio": 1.5}
    }
  },
  "control": {"wins": 30, "losses": 20}
}
```

**Promotion logic:** A variation's `win_rate` must exceed `control_win_rate + 0.05` with at least 10 recorded outcomes to be promoted.

### TDD Steps

- [ ] **3.1 — Write failing tests** in `tests/test_experiment_tracker.py`:

  ```python
  import sys, json, tempfile
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  def make_tracker(tmp: Path, is_paper: bool = True):
      from learning.experiment_tracker import ExperimentTracker
      return ExperimentTracker(
          experiments_file=tmp / "experiments.json",
          is_paper=is_paper,
      )

  def test_should_experiment_always_false_in_live_mode():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d), is_paper=False)
          results = [tracker.should_experiment() for _ in range(200)]
          assert all(r is False for r in results)

  def test_should_experiment_returns_true_roughly_10_pct_in_paper_mode():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d), is_paper=True)
          results = [tracker.should_experiment() for _ in range(1000)]
          rate = sum(results) / len(results)
          # Allow wide margin: 5-20% range
          assert 0.05 <= rate <= 0.20

  def test_get_variation_returns_valid_dict():
      with tempfile.TemporaryDirectory() as d:
          tracker = make_tracker(Path(d))
          variation = tracker.get_variation()
          assert "stop_pct" in variation
          assert "partial_exit_at_r" in variation
          assert "min_volume_ratio" in variation
          assert variation["stop_pct"] in [2.5, 3.0, 3.5]
          assert variation["partial_exit_at_r"] in [0.75, 1.0, 1.25, 1.5]
          assert variation["min_volume_ratio"] in [1.25, 1.5, 1.75, 2.0]

  def test_record_experiment_saves_to_file():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          tracker = make_tracker(tmp)
          variation = {"stop_pct": 2.5, "partial_exit_at_r": 1.0, "min_volume_ratio": 1.5}
          tracker.record_experiment("exp_001", variation, "win", 2.1)
          data = json.loads((tmp / "experiments.json").read_text())
          assert "experiments" in data
          # At least one experiment entry was written
          assert len(data["experiments"]) >= 1

  def test_should_promote_true_when_variation_beats_control_by_5pct_with_n10():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          tracker = make_tracker(tmp)
          variation = {"stop_pct": 2.5, "partial_exit_at_r": 1.0, "min_volume_ratio": 1.5}
          # Record 10 wins for variation → 100% win rate
          for i in range(10):
              tracker.record_experiment(f"exp_{i}", variation, "win", 2.0)
          # Control: 50% win rate (5 wins, 5 losses written directly)
          data = json.loads((tmp / "experiments.json").read_text())
          data["control"] = {"wins": 5, "losses": 5}
          (tmp / "experiments.json").write_text(json.dumps(data))
          # Determine the variation key that was actually used
          data = json.loads((tmp / "experiments.json").read_text())
          var_key = list(data["experiments"].keys())[0]
          assert tracker.should_promote(var_key) is True

  def test_should_promote_false_with_insufficient_data():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          tracker = make_tracker(tmp)
          variation = {"stop_pct": 2.5, "partial_exit_at_r": 1.0, "min_volume_ratio": 1.5}
          # Only 9 samples — below threshold
          for i in range(9):
              tracker.record_experiment(f"exp_{i}", variation, "win", 2.0)
          data = json.loads((tmp / "experiments.json").read_text())
          var_key = list(data["experiments"].keys())[0]
          assert tracker.should_promote(var_key) is False
  ```

  Run `uv run pytest tests/test_experiment_tracker.py -v` — all 6 should fail.

- [ ] **3.2 — Implement** `learning/experiment_tracker.py`:

  - `EXPLORATION_RATE = 0.10`
  - `__init__`: store `self._file`, `self._is_paper`
  - `should_experiment()`: return `False` if not paper; `random.random() < EXPLORATION_RATE`
  - `get_variation()`: return dict with random choices from specified lists
  - `_load()`: read JSON, return `{"experiments": {}, "control": {"wins": 0, "losses": 0}}` on missing/corrupt
  - `_save(data)`: write JSON with `indent=2`, create parent dirs
  - `record_experiment(experiment_id, variation, outcome, achieved_rr)`:
    - Load data
    - Compute `variation_key` = `"&".join(f"{k}={v}" for k, v in sorted(variation.items()))`
    - If key not in `data["experiments"]`, init with `{"wins": 0, "losses": 0, "achieved_rr": [], "variation": variation}`
    - Increment `wins` or `losses`, append to `achieved_rr`
    - Save
  - `should_promote(variation_key)`:
    - Load data
    - If `variation_key` not in experiments → `False`
    - `exp = data["experiments"][variation_key]`
    - `n = exp["wins"] + exp["losses"]`
    - if `n < 10` → `False`
    - `exp_win_rate = exp["wins"] / n`
    - `control = data.get("control", {})`
    - `control_n = control.get("wins", 0) + control.get("losses", 0)`
    - if `control_n == 0` → `False` (no control baseline yet)
    - `control_win_rate = control["wins"] / control_n`
    - return `exp_win_rate >= control_win_rate + 0.05`
  - `get_stats()`: return loaded data

  Run tests — all 6 should pass.

- [ ] **3.3 — Verify** `uv run pytest tests/test_experiment_tracker.py -v` passes (6/6).

---

## Task 4: Regime Confidence Multiplier

**Modify:** `pivot_monitor.py`

**Why:** `_get_current_regime()` already reads from `macro-regime-detector.json`. This adds a `score` lookup from the same file, then applies the multiplier in `_calc_qty()`. Fully independent of Tasks 1-3.

### Changes

Add `_get_regime_confidence_multiplier()` method to `PivotWatchlistMonitor`:

```python
def _get_regime_confidence_multiplier(self) -> float:
    """Returns size multiplier based on regime signal confidence (0-100 score)."""
    try:
        data = json.loads((self._cache_dir / "macro-regime-detector.json").read_text())
        regime_data = data.get("regime", {})
        score = None
        if isinstance(regime_data, dict):
            score = regime_data.get("score")
        if score is None:
            return 1.0
        score = float(score)
        if score >= 75:
            return 1.0
        elif score >= 50:
            return 0.75
        elif score >= 25:
            return 0.5
        else:
            return 0.25
    except Exception:
        return 1.0
```

Modify `_calc_qty()` — after the Kelly/VIX multiplier block, before the `return`:

```python
# Current _calc_qty returns:
#   return min(qty, max_qty_by_size)
#
# Replace that final expression with:
regime_conf_mult = self._get_regime_confidence_multiplier()
kelly_mult = 1.5 if high_conviction else 1.0
final_qty = max(1, int(min(qty, max_qty_by_size) * kelly_mult * regime_conf_mult))
return final_qty
```

**Note:** Review the exact current `_calc_qty` implementation at lines 251-275 in `pivot_monitor.py`. The `high_conviction` flag currently affects `risk_pct` and `max_pos_pct` at the top of `_calc_qty`, not a separate `kelly_mult`. Apply `regime_conf_mult` to the final `min(qty, max_qty_by_size)` result. The adjusted line is:

```python
return max(1, int(min(qty, max_qty_by_size) * regime_conf_mult))
```

### TDD Steps

- [ ] **4.1 — Write failing tests** — add to `tests/test_pivot_monitor.py` (or create if it doesn't exist):

  ```python
  # Add these tests to the existing test file, or create tests/test_pivot_monitor.py

  import sys, json, tempfile
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  def _make_monitor(tmp: Path):
      from pivot_monitor import PivotWatchlistMonitor
      from unittest.mock import MagicMock
      alpaca = MagicMock()
      alpaca.is_configured = False
      settings = MagicMock()
      settings.load.return_value = {"default_risk_pct": 1.0, "max_position_size_pct": 10.0}
      from learning.rule_store import RuleStore
      rule_store = RuleStore(rules_file=tmp / "rules.json")
      return PivotWatchlistMonitor(
          alpaca_client=alpaca,
          settings_manager=settings,
          cache_dir=tmp,
          rule_store=rule_store,
      )

  def _write_regime_cache(tmp: Path, score: float):
      (tmp / "macro-regime-detector.json").write_text(json.dumps({
          "regime": {"current_regime": "bull", "score": score}
      }))

  def test_regime_confidence_score_75_returns_1_0():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          monitor = _make_monitor(tmp)
          _write_regime_cache(tmp, 80.0)
          assert monitor._get_regime_confidence_multiplier() == 1.0

  def test_regime_confidence_score_50_to_75_returns_0_75():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          monitor = _make_monitor(tmp)
          _write_regime_cache(tmp, 60.0)
          assert monitor._get_regime_confidence_multiplier() == 0.75

  def test_regime_confidence_score_below_25_returns_0_25():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          monitor = _make_monitor(tmp)
          _write_regime_cache(tmp, 10.0)
          assert monitor._get_regime_confidence_multiplier() == 0.25

  def test_regime_confidence_missing_cache_returns_1_0():
      with tempfile.TemporaryDirectory() as d:
          tmp = Path(d)
          monitor = _make_monitor(tmp)
          # No cache file written
          assert monitor._get_regime_confidence_multiplier() == 1.0
  ```

  Run `uv run pytest tests/test_pivot_monitor.py -v -k "regime_confidence"` — all 4 should fail.

- [ ] **4.2 — Implement** `_get_regime_confidence_multiplier()` in `pivot_monitor.py` per the interface above.

- [ ] **4.3 — Apply in `_calc_qty()`** — append `regime_conf_mult` multiplication to the return statement as described above.

- [ ] **4.4 — Verify** `uv run pytest tests/test_pivot_monitor.py -v -k "regime_confidence"` passes (4/4).

---

## Task 5: Wire into PatternExtractor

**Modify:** `learning/pattern_extractor.py` and `main.py`

**Depends on:** Tasks 1, 2, 3 (all three new classes must exist)

### Changes to `pattern_extractor.py`

1. Extend `__init__` signature with optional injected stores:

   ```python
   def __init__(
       self,
       alpaca_client,
       rule_store: RuleStore,
       cache_dir: Path,
       multiplier_store=None,
       time_of_day_tracker=None,
       stop_distance_store=None,
       experiment_tracker=None,
   ):
       self._alpaca = alpaca_client
       self._rule_store = rule_store
       self._cache_dir = cache_dir
       self._multiplier_store = multiplier_store
       self._time_of_day_tracker = time_of_day_tracker
       self._stop_distance_store = stop_distance_store
       self._experiment_tracker = experiment_tracker
   ```

2. Extend `_update_multipliers()` to call new stores after the MultiplierStore update. The method currently skips non-win trades for multiplier updates, but `StopDistanceStore` should receive all closed trades (wins and losses). Refactor `_update_multipliers()` to iterate all trades and branch per store:

   ```python
   def _update_multipliers(self, trades: list[dict]) -> None:
       required_for_multiplier = ("exit_price", "stop_price", "entry_price", "screener", "confidence_tag", "regime")
       for t in trades:
           outcome = t.get("outcome")
           if not outcome:
               continue

           # MultiplierStore: wins only, requires exit_price
           if outcome == "win" and self._multiplier_store is not None:
               if not any(t.get(f) is None for f in required_for_multiplier):
                   risk = t["entry_price"] - t["stop_price"]
                   if risk > 0:
                       achieved_rr = (t["exit_price"] - t["entry_price"]) / risk
                       bucket_key = f"{t['screener']}+{t['confidence_tag']}+{t['regime']}"
                       self._multiplier_store.update(bucket_key, achieved_rr)

           # TimeOfDayTracker: all closed trades with entry_time
           if self._time_of_day_tracker and t.get("entry_time"):
               try:
                   from datetime import datetime
                   from zoneinfo import ZoneInfo
                   entry_dt = datetime.fromisoformat(t["entry_time"])
                   hour_et = entry_dt.astimezone(ZoneInfo("America/New_York")).hour
                   self._time_of_day_tracker.record(hour_et, outcome)
               except Exception:
                   pass

           # StopDistanceStore: all closed trades with required price fields
           if self._stop_distance_store and t.get("stop_price") and t.get("entry_price") and t.get("screener"):
               try:
                   stop_pct = abs((t["entry_price"] - t["stop_price"]) / t["entry_price"]) * 100
                   bucket_key = f"{t['screener']}+{t.get('confidence_tag', 'CLEAR')}+{t.get('regime', 'unknown')}"
                   self._stop_distance_store.record(bucket_key, stop_pct, outcome)
               except Exception:
                   pass
   ```

### Changes to `main.py`

Add instantiation of the three new classes after the existing `multiplier_store = MultiplierStore()` line:

```python
from learning.time_of_day_tracker import TimeOfDayTracker
from learning.stop_distance_store import StopDistanceStore
from learning.experiment_tracker import ExperimentTracker

time_of_day_tracker = TimeOfDayTracker()
stop_distance_store = StopDistanceStore()
experiment_tracker = ExperimentTracker(is_paper=ALPACA_PAPER)
```

Pass to `PatternExtractor`:

```python
pattern_extractor = PatternExtractor(
    alpaca_client=alpaca,
    rule_store=rule_store,
    cache_dir=CACHE_DIR,
    multiplier_store=multiplier_store,
    time_of_day_tracker=time_of_day_tracker,
    stop_distance_store=stop_distance_store,
    experiment_tracker=experiment_tracker,
)
```

### TDD Steps

- [ ] **5.1 — Write failing tests** — add to `tests/test_pattern_extractor.py` (or create if it doesn't exist):

  ```python
  import sys, json, tempfile
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
  from unittest.mock import MagicMock, patch

  def _make_closed_trade(outcome: str = "win") -> dict:
      return {
          "symbol": "AAPL",
          "order_id": "abc123",
          "entry_time": "2026-03-22T14:30:00+00:00",
          "entry_price": 100.0,
          "stop_price": 97.0,
          "exit_price": 106.0,
          "confidence_tag": "CLEAR",
          "screener": "vcp",
          "regime": "bull",
          "outcome": outcome,
      }

  def _make_extractor(tmp: Path, time_of_day_tracker=None, stop_distance_store=None):
      from learning.pattern_extractor import PatternExtractor
      from learning.rule_store import RuleStore
      alpaca = MagicMock()
      alpaca.is_configured = False
      rule_store = RuleStore(rules_file=tmp / "rules.json")
      return PatternExtractor(
          alpaca_client=alpaca,
          rule_store=rule_store,
          cache_dir=tmp,
          time_of_day_tracker=time_of_day_tracker,
          stop_distance_store=stop_distance_store,
      )

  def test_time_of_day_tracker_called_for_closed_trade():
      with tempfile.TemporaryDirectory() as d:
          tracker = MagicMock()
          extractor = _make_extractor(Path(d), time_of_day_tracker=tracker)
          trade = _make_closed_trade("win")
          extractor._update_multipliers([trade])
          tracker.record.assert_called_once()
          call_args = tracker.record.call_args[0]
          # First arg is hour (ET), second is outcome
          assert call_args[1] == "win"

  def test_stop_distance_store_called_for_all_closed_trades():
      with tempfile.TemporaryDirectory() as d:
          store = MagicMock()
          extractor = _make_extractor(Path(d), stop_distance_store=store)
          trades = [_make_closed_trade("win"), _make_closed_trade("loss")]
          extractor._update_multipliers(trades)
          assert store.record.call_count == 2

  def test_neither_store_called_when_stores_are_none():
      with tempfile.TemporaryDirectory() as d:
          # No stores injected — should not raise
          extractor = _make_extractor(Path(d))
          trade = _make_closed_trade("win")
          # Should complete without error
          extractor._update_multipliers([trade])
  ```

  Run `uv run pytest tests/test_pattern_extractor.py -v -k "time_of_day or stop_distance or stores_are_none"` — all 3 should fail.

- [ ] **5.2 — Implement** the `__init__` and `_update_multipliers` changes in `learning/pattern_extractor.py` as described above.

- [ ] **5.3 — Update `main.py`** with the three new class instantiations and updated `PatternExtractor` call.

- [ ] **5.4 — Verify** `uv run pytest tests/test_pattern_extractor.py -v -k "time_of_day or stop_distance or stores_are_none"` passes (3/3).

---

## Task 6: /stats Page

**Depends on:** Tasks 1, 2, 3 (new stores must exist), Task 5 (wired into main.py)

**New files:** `templates/stats.html`
**Modify:** `main.py` (add `/stats` route), `tests/test_routes.py` (add route test)

### Route

Add to `main.py` after the `/` route:

```python
@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    ctx = {
        "request": request,
        "multiplier_stats": multiplier_store._load_learned(),
        "time_of_day": time_of_day_tracker.get_stats(),
        "experiments": experiment_tracker.get_stats(),
        "pdt_slots": pdt_tracker.slots_remaining(date.today()) if "pdt_tracker" in dir() else 3,
    }
    return templates.TemplateResponse("stats.html", ctx)
```

### Template

**New file:** `templates/stats.html`

Dark theme matching the existing dashboard style. Extends `base.html`. Sections:

1. **Page header** — "Learning Stats" title, "Last updated: [now]"
2. **Overall stats** — total trades (sum across all buckets), estimated win rate, avg R
3. **Multiplier store by bucket** — table with columns: Bucket | Samples | p75 R:R | Last Updated
4. **Time-of-day heatmap** — table with columns: Hour (ET) | Wins | Losses | Win Rate | Adjustment
5. **Active experiments** — table with columns: Variation | Trades | Win Rate | vs Control | Promotable?
6. **PDT slots remaining** — simple badge showing slots left

The template receives `multiplier_stats` (dict from `MultiplierStore._load_learned()`), `time_of_day` (dict from `TimeOfDayTracker.get_stats()`), `experiments` (dict from `ExperimentTracker.get_stats()`), and `pdt_slots` (int).

**Style notes:**
- Use `{% extends "base.html" %}` and `{% block content %}`
- Use `<div class="bottom-panel">` style cards for each section (matches existing CSS)
- Use `<table>` with inline dark styles consistent with `detail/` templates
- Color-code the Adjustment column: NORMAL = grey, HIGH_CONVICTION = yellow, BLOCKED = red

### TDD Steps

- [ ] **6.1 — Write failing test** in `tests/test_routes.py` (add to existing file or create):

  ```python
  import sys
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

  def test_stats_route_returns_200(tmp_path, monkeypatch):
      """GET /stats returns 200."""
      import json
      from fastapi.testclient import TestClient

      # Patch CACHE_DIR to tmp_path so no real files needed
      monkeypatch.setenv("ALPACA_API_KEY", "")
      monkeypatch.setenv("ALPACA_SECRET_KEY", "")

      # Import app after env patch
      import importlib
      import main as m
      importlib.reload(m)

      client = TestClient(m.app)
      response = client.get("/stats")
      assert response.status_code == 200
  ```

  **Note:** If the existing `tests/test_routes.py` uses a shared `client` fixture that already handles app setup, follow the same pattern. The key assertion is `response.status_code == 200`.

  Run `uv run pytest tests/test_routes.py -v -k "stats"` — should fail (route not yet defined).

- [ ] **6.2 — Add `/stats` route** to `main.py` as described above.

- [ ] **6.3 — Create `templates/stats.html`** with the following structure:

  ```html
  {% extends "base.html" %}
  {% block content %}
  <div style="padding: 16px;">
    <h2 style="color:#e2e8f0; margin-bottom:16px;">Learning Stats</h2>

    <!-- Multiplier Store -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Take-Profit Multipliers (by Bucket)</div>
      <table style="width:100%; border-collapse:collapse; font-size:12px; color:#cbd5e1;">
        <thead>
          <tr style="color:#94a3b8; border-bottom:1px solid #334155;">
            <th style="padding:6px; text-align:left;">Bucket</th>
            <th style="padding:6px; text-align:right;">Samples</th>
            <th style="padding:6px; text-align:right;">p75 R:R</th>
            <th style="padding:6px; text-align:right;">Last Updated</th>
          </tr>
        </thead>
        <tbody>
          {% for key, bucket in multiplier_stats.items() %}
          <tr style="border-bottom:1px solid #1e293b;">
            <td style="padding:6px;">{{ key }}</td>
            <td style="padding:6px; text-align:right;">{{ bucket.sample_count }}</td>
            <td style="padding:6px; text-align:right;">{{ bucket.p75 }}</td>
            <td style="padding:6px; text-align:right;">{{ bucket.last_updated }}</td>
          </tr>
          {% else %}
          <tr><td colspan="4" style="padding:6px; color:#64748b;">No learned data yet.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Time-of-Day -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Win Rate by Hour (ET)</div>
      <table style="width:100%; border-collapse:collapse; font-size:12px; color:#cbd5e1;">
        <thead>
          <tr style="color:#94a3b8; border-bottom:1px solid #334155;">
            <th style="padding:6px; text-align:left;">Hour</th>
            <th style="padding:6px; text-align:right;">Wins</th>
            <th style="padding:6px; text-align:right;">Losses</th>
            <th style="padding:6px; text-align:right;">Win Rate</th>
            <th style="padding:6px; text-align:right;">Adjustment</th>
          </tr>
        </thead>
        <tbody>
          {% for hour, s in time_of_day.items() | sort %}
          {% set n = s.wins + s.losses %}
          {% set win_rate = (s.wins / n * 100) | round(1) if n > 0 else 0 %}
          <tr style="border-bottom:1px solid #1e293b;">
            <td style="padding:6px;">{{ hour }}:00</td>
            <td style="padding:6px; text-align:right; color:#4ade80;">{{ s.wins }}</td>
            <td style="padding:6px; text-align:right; color:#f87171;">{{ s.losses }}</td>
            <td style="padding:6px; text-align:right;">{{ win_rate }}%</td>
            <td style="padding:6px; text-align:right;
              {% if n >= 10 and s.wins / n < 0.30 %}color:#f87171;
              {% elif n >= 10 and s.wins / n < 0.40 %}color:#fbbf24;
              {% else %}color:#94a3b8;{% endif %}">
              {% if n < 10 %}NORMAL (insufficient data)
              {% elif s.wins / n < 0.30 %}BLOCKED
              {% elif s.wins / n < 0.40 %}HIGH_CONVICTION required
              {% else %}NORMAL{% endif %}
            </td>
          </tr>
          {% else %}
          <tr><td colspan="5" style="padding:6px; color:#64748b;">No time-of-day data yet.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Experiments -->
    <div class="bottom-panel" style="margin-bottom:16px;">
      <div class="panel-title">Active Experiments (paper only)</div>
      {% set exps = experiments.get("experiments", {}) %}
      {% set control = experiments.get("control", {"wins": 0, "losses": 0}) %}
      {% set ctrl_n = control.wins + control.losses %}
      {% set ctrl_wr = (control.wins / ctrl_n * 100) | round(1) if ctrl_n > 0 else 0 %}
      <p style="font-size:11px; color:#94a3b8; margin-bottom:8px;">
        Control: {{ ctrl_wr }}% win rate (n={{ ctrl_n }})
      </p>
      <table style="width:100%; border-collapse:collapse; font-size:12px; color:#cbd5e1;">
        <thead>
          <tr style="color:#94a3b8; border-bottom:1px solid #334155;">
            <th style="padding:6px; text-align:left;">Variation</th>
            <th style="padding:6px; text-align:right;">Trades</th>
            <th style="padding:6px; text-align:right;">Win Rate</th>
            <th style="padding:6px; text-align:right;">vs Control</th>
            <th style="padding:6px; text-align:right;">Promotable?</th>
          </tr>
        </thead>
        <tbody>
          {% for var_key, exp in exps.items() %}
          {% set n = exp.wins + exp.losses %}
          {% set wr = (exp.wins / n * 100) | round(1) if n > 0 else 0 %}
          {% set vs_ctrl = (wr - ctrl_wr) | round(1) %}
          <tr style="border-bottom:1px solid #1e293b;">
            <td style="padding:6px; font-size:11px;">{{ var_key }}</td>
            <td style="padding:6px; text-align:right;">{{ n }}</td>
            <td style="padding:6px; text-align:right;">{{ wr }}%</td>
            <td style="padding:6px; text-align:right;
              {% if vs_ctrl >= 5 %}color:#4ade80;{% elif vs_ctrl <= -5 %}color:#f87171;{% else %}color:#94a3b8;{% endif %}">
              {{ "+" if vs_ctrl >= 0 else "" }}{{ vs_ctrl }}%
            </td>
            <td style="padding:6px; text-align:right;
              {% if n >= 10 and vs_ctrl >= 5 %}color:#4ade80;{% else %}color:#64748b;{% endif %}">
              {% if n >= 10 and vs_ctrl >= 5 %}YES{% else %}No{% endif %}
            </td>
          </tr>
          {% else %}
          <tr><td colspan="5" style="padding:6px; color:#64748b;">No experiments recorded yet.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- PDT Status -->
    <div class="bottom-panel">
      <div class="panel-title">PDT Status</div>
      <p style="font-size:13px; color:#cbd5e1;">
        Day trades remaining this week:
        <strong style="color:{% if pdt_slots >= 2 %}#4ade80{% elif pdt_slots == 1 %}#fbbf24{% else %}#f87171{% endif %};">
          {{ pdt_slots }}
        </strong>
      </p>
    </div>

  </div>
  {% endblock %}
  ```

- [ ] **6.4 — Verify** `uv run pytest tests/test_routes.py -v -k "stats"` passes (1/1).

---

## Integration Verification

After all tasks complete:

- [ ] **Full test suite passes:** `uv run pytest tests/ -v` — zero failures.
- [ ] **App starts cleanly:** `uv run uvicorn main:app --port 8000` — no import errors.
- [ ] **`/stats` page loads** in browser — all 5 sections visible.
- [ ] **Learning files created** in `learning/` directory after first `PatternExtractor.extract()` run:
  - `learning/time_of_day_stats.json`
  - `learning/stop_distance_stats.json`
  - `learning/experiments.json`
- [ ] **Regime confidence** applies in `_calc_qty()` — verify by writing a test cache with score=10 and confirming order qty is reduced by 75%.

---

## Key Implementation Notes

### Constructor Injection Pattern (follow MultiplierStore)

All new classes accept a `Path` argument in `__init__` defaulting to a sibling file in `learning/`. This keeps production defaults simple while making tests fully isolated (each test gets a `tempfile.TemporaryDirectory()`).

### Defensive Loading

All `_load()` methods must return a sensible default on any file error. Copy the pattern from `MultiplierStore._load_learned()`:

```python
def _load(self) -> dict:
    if not self._file.exists():
        return {}
    try:
        return json.loads(self._file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
```

### Never Raises

All public `get_*` methods must catch all exceptions and return a safe default. Follows `MultiplierStore.get()` which always returns `2.0` on error.

### sys.path Insert Pattern

All test files must follow the pattern from `tests/test_multiplier_store.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

### ExperimentTracker is Paper-Only

The `is_paper` flag must be read from `config.py`'s `ALPACA_PAPER` at `main.py` startup and injected into `ExperimentTracker`. This prevents any accidental experiment firing during live trading.

### PatternExtractor is Non-Breaking

The three new optional stores default to `None` in `PatternExtractor.__init__`. Existing code and tests that construct `PatternExtractor` without these arguments continue to work unchanged.
