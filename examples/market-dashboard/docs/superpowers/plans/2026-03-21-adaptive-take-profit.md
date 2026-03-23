# Adaptive Take-Profit Multiplier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded 2:1 take-profit multiplier with a per-setup learned multiplier seeded from published research (Minervini, O'Neil) and updated from closed trade outcomes.

**Architecture:** A new `MultiplierStore` class manages seed priors and learned R:R per bucket key `(screener+confidence_tag+regime)`. `PatternExtractor` populates it from closed wins. Both the auto (`PivotWatchlistMonitor`) and manual (`main.py` order confirm) order paths look up the multiplier before placing a bracket order.

**Tech Stack:** Python 3.11+, FastAPI, Alpaca-py, standard library only (json, math, datetime)

**Spec:** `docs/superpowers/specs/2026-03-21-adaptive-take-profit-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `learning/multiplier_store.py` | Create | Bucket key lookup + observed R:R storage with p75 blending |
| `learning/seed_multipliers.json` | Create | Published research priors (Minervini, O'Neil) |
| `learning/learned_multipliers.json` | Auto-created at runtime | Observed R:R accumulation |
| `tests/test_multiplier_store.py` | Create | MultiplierStore unit tests |
| `learning/pattern_extractor.py` | Modify | Save exit_price; accept MultiplierStore; call update() for wins |
| `tests/test_pattern_extractor.py` | Modify | Add multiplier update + exit_price tests |
| `pivot_monitor.py` | Modify | `_fire_order`: lookup multiplier; `_log_trade`: add screener + fix regime field |
| `tests/test_pivot_monitor.py` | Modify | Add multiplier + log field tests |
| `main.py` | Modify | Instantiate MultiplierStore; order_confirm + order_preview integration; add helpers |
| `tests/test_routes.py` | Modify | Add order confirm + preview multiplier tests |
| `templates/fragments/order_preview.html` | Modify | Display multiplier; pass skill+confidence_tag to confirm |

---

## Task 1: MultiplierStore + Seed Data

**Files:**
- Create: `tests/test_multiplier_store.py`
- Create: `learning/multiplier_store.py`
- Create: `learning/seed_multipliers.json`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multiplier_store.py`:

```python
# tests/test_multiplier_store.py
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def write_seed(tmp: Path, data: dict):
    (tmp / "seed_multipliers.json").write_text(json.dumps(data))


def write_learned(tmp: Path, data: dict):
    (tmp / "learned_multipliers.json").write_text(json.dumps(data))


def make_store(tmp: Path):
    from learning.multiplier_store import MultiplierStore
    return MultiplierStore(
        learned_file=tmp / "learned_multipliers.json",
        seed_file=tmp / "seed_multipliers.json",
    )


def test_get_returns_seed_when_no_real_trades():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_seed(tmp, {"vcp+CLEAR+bull": {"multiplier": 3.0, "sample_count": 50}})
        store = make_store(tmp)
        assert store.get("vcp+CLEAR+bull") == 3.0


def test_get_returns_2_0_for_unknown_bucket_no_seed():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(Path(d))
        assert store.get("canslim+UNCERTAIN+bear") == 2.0


def test_get_returns_p75_when_5_or_more_real_trades():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # p75 of [2.0, 2.5, 3.0, 3.5, 4.0] = 3.5 (nearest rank: ceil(0.75*5)-1 = index 3)
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [2.0, 2.5, 3.0, 3.5, 4.0],
                "p75": 3.5,
                "sample_count": 5,
            }
        })
        store = make_store(tmp)
        assert store.get("vcp+CLEAR+bull") == 3.5


def test_get_returns_weighted_blend_with_3_real_trades():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # seed: 50 samples @ 3.0; real: [3.0, 3.0, 3.0] → p75=3.0
        # blend = (50*3.0 + 3*3.0) / (50+3) = 3.0
        write_seed(tmp, {"vcp+CLEAR+bull": {"multiplier": 3.0, "sample_count": 50}})
        write_learned(tmp, {
            "vcp+CLEAR+bull": {"observed_rr": [3.0, 3.0, 3.0], "p75": 3.0, "sample_count": 3}
        })
        store = make_store(tmp)
        assert abs(store.get("vcp+CLEAR+bull") - 3.0) < 0.01


def test_get_returns_2_0_when_file_unreadable():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "seed_multipliers.json").write_text("not valid json")
        store = make_store(tmp)
        assert store.get("vcp+CLEAR+bull") == 2.0


def test_update_appends_and_rewrites():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(Path(d))
        store.update("vcp+CLEAR+bull", 2.8)
        store.update("vcp+CLEAR+bull", 3.2)
        data = json.loads((Path(d) / "learned_multipliers.json").read_text())
        assert data["vcp+CLEAR+bull"]["observed_rr"] == [2.8, 3.2]
        assert data["vcp+CLEAR+bull"]["sample_count"] == 2


def test_update_discards_invalid_rr():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(Path(d))
        store.update("vcp+CLEAR+bull", 0.0)   # <= 0: discard
        store.update("vcp+CLEAR+bull", -1.0)  # <= 0: discard
        store.update("vcp+CLEAR+bull", 21.0)  # > 20: discard
        store.update("vcp+CLEAR+bull", 2.5)   # valid
        data = json.loads((Path(d) / "learned_multipliers.json").read_text())
        assert data["vcp+CLEAR+bull"]["observed_rr"] == [2.5]


def test_update_computes_correct_p75():
    with tempfile.TemporaryDirectory() as d:
        store = make_store(Path(d))
        for v in [2.0, 2.5, 3.0, 3.5, 4.0]:
            store.update("vcp+CLEAR+bull", v)
        data = json.loads((Path(d) / "learned_multipliers.json").read_text())
        assert data["vcp+CLEAR+bull"]["p75"] == 3.5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_multiplier_store.py -v
```
Expected: `ModuleNotFoundError: No module named 'learning.multiplier_store'`

- [ ] **Step 3: Create learning/seed_multipliers.json**

```json
{
  "vcp+CLEAR+bull":              { "multiplier": 3.0,  "sample_count": 50, "source": "Minervini Stage Analysis" },
  "vcp+CLEAR+choppy":            { "multiplier": 1.75, "sample_count": 50, "source": "Minervini — reduce targets in choppy" },
  "vcp+CLEAR+bear":              { "multiplier": 1.5,  "sample_count": 50, "source": "Minervini — tight targets in downtrends" },
  "vcp+CLEAR+contraction":       { "multiplier": 1.5,  "sample_count": 50, "source": "Minervini — contraction = bear-equivalent" },
  "vcp+UNCERTAIN+bull":          { "multiplier": 2.0,  "sample_count": 30, "source": "Minervini — lower confidence, conservative" },
  "vcp+UNCERTAIN+choppy":        { "multiplier": 1.5,  "sample_count": 30, "source": "Minervini — uncertain + choppy, take early" },
  "vcp+HIGH_CONVICTION+bull":    { "multiplier": 3.5,  "sample_count": 40, "source": "Minervini — institutional + positive catalyst" },
  "canslim+CLEAR+bull":          { "multiplier": 2.5,  "sample_count": 40, "source": "O'Neil CANSLIM documented win rates" },
  "canslim+CLEAR+choppy":        { "multiplier": 1.75, "sample_count": 30, "source": "O'Neil — reduced target in non-trending" },
  "canslim+UNCERTAIN+bull":      { "multiplier": 2.0,  "sample_count": 25, "source": "O'Neil CANSLIM" }
}
```

- [ ] **Step 4: Create learning/multiplier_store.py**

```python
# learning/multiplier_store.py
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

LEARNING_DIR = Path(__file__).resolve().parent
DEFAULT_LEARNED_FILE = LEARNING_DIR / "learned_multipliers.json"
DEFAULT_SEED_FILE = LEARNING_DIR / "seed_multipliers.json"

MIN_SAMPLE_COUNT = 5
_MAX_VALID_RR = 20.0


def _p75(values: list[float]) -> float:
    """75th percentile using nearest-rank method. Spec test: [2,2.5,3,3.5,4] → 3.5."""
    s = sorted(values)
    idx = math.ceil(0.75 * len(s)) - 1
    return round(s[max(0, idx)], 3)


class MultiplierStore:
    """Reads/writes learned take-profit multipliers per bucket key.

    Bucket key format: "{screener}+{confidence_tag}+{regime}"

    Fallback chain:
      1. learned p75 (≥5 real trades)
      2. weighted blend of seed prior + observed p75 (1–4 real trades)
      3. seed prior (0 real trades, bucket in seed)
      4. 2.0 hardcoded default (unknown bucket)
    """

    def __init__(
        self,
        learned_file: Path = DEFAULT_LEARNED_FILE,
        seed_file: Path = DEFAULT_SEED_FILE,
    ):
        self._learned_file = learned_file
        self._seed_file = seed_file

    def _load_learned(self) -> dict:
        if not self._learned_file.exists():
            return {}
        try:
            return json.loads(self._learned_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_seed(self) -> dict:
        if not self._seed_file.exists():
            return {}
        try:
            return json.loads(self._seed_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def get(self, bucket_key: str) -> float:
        """Return the multiplier to use for a bracket order. Never raises."""
        try:
            learned_all = self._load_learned()
            seed_all = self._load_seed()
            bucket = learned_all.get(bucket_key, {})
            seed = seed_all.get(bucket_key)
            observed = bucket.get("observed_rr", [])
            n_real = len(observed)

            if n_real >= MIN_SAMPLE_COUNT:
                return bucket["p75"]
            elif n_real > 0:
                observed_p75 = _p75(observed)
                if seed is None:
                    return observed_p75
                seed_weight = seed["sample_count"]
                return (seed_weight * seed["multiplier"] + n_real * observed_p75) / (
                    seed_weight + n_real
                )
            else:
                return seed["multiplier"] if seed is not None else 2.0
        except Exception:
            return 2.0

    def update(self, bucket_key: str, achieved_rr: float) -> None:
        """Append a real trade's achieved R:R and recompute p75. Discards bad values."""
        if achieved_rr <= 0 or achieved_rr > _MAX_VALID_RR:
            return
        data = self._load_learned()
        bucket = data.get(bucket_key, {"observed_rr": []})
        bucket["observed_rr"].append(achieved_rr)
        n = len(bucket["observed_rr"])
        bucket["p75"] = _p75(bucket["observed_rr"])
        bucket["sample_count"] = n
        bucket["last_updated"] = date.today().isoformat()
        data[bucket_key] = bucket
        self._learned_file.parent.mkdir(parents=True, exist_ok=True)
        self._learned_file.write_text(json.dumps(data, indent=2))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_multiplier_store.py -v
```
Expected: all 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add learning/multiplier_store.py learning/seed_multipliers.json tests/test_multiplier_store.py
git commit -m "feat: add MultiplierStore with seed priors and p75 blending logic"
```

---

## Task 2: PatternExtractor — save exit_price and update MultiplierStore

**Files:**
- Modify: `learning/pattern_extractor.py`
- Modify: `tests/test_pattern_extractor.py`

- [ ] **Step 1: Write the failing tests**

Add these functions to the bottom of `tests/test_pattern_extractor.py`:

```python
# ── New helpers and tests ──

def make_extractor_with_mstore(tmp_path: Path, alpaca=None):
    if alpaca is None:
        alpaca = MagicMock()
        alpaca.is_configured = False
    from learning.multiplier_store import MultiplierStore
    rule_store = RuleStore(tmp_path / "learned_rules.json")
    mstore = MultiplierStore(
        learned_file=tmp_path / "learned_multipliers.json",
        seed_file=tmp_path / "seed_multipliers.json",
    )
    extractor = PatternExtractor(
        alpaca_client=alpaca,
        rule_store=rule_store,
        cache_dir=tmp_path,
        multiplier_store=mstore,
    )
    return extractor, mstore


def test_refresh_saves_exit_price_to_trade_entry():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "outcome": None,
            "order_id": "ord1", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        tp_leg = MagicMock()
        tp_leg.side = "sell"; tp_leg.status = "filled"; tp_leg.filled_avg_price = 163.0
        order = MagicMock(); order.legs = [tp_leg]
        alpaca.trading_client.get_order_by_id.return_value = order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        extractor.refresh_trade_outcomes()
        trades = json.loads((Path(d) / "auto_trades.json").read_text())["trades"]
        assert trades[0]["exit_price"] == 163.0


def test_extract_updates_multiplier_store_for_winning_trade():
    with tempfile.TemporaryDirectory() as d:
        # entry=100, stop=97, exit=109 → risk=3, achieved_rr = (109-100)/3 = 3.0
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "regime": "bull", "outcome": "win",
            "entry_price": 100.0, "stop_price": 97.0, "exit_price": 109.0,
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()
        data = json.loads((Path(d) / "learned_multipliers.json").read_text())
        assert "vcp+CLEAR+bull" in data
        assert data["vcp+CLEAR+bull"]["observed_rr"] == [3.0]


def test_extract_does_not_update_multiplier_for_losing_trade():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "regime": "bull", "outcome": "loss",
            "entry_price": 100.0, "stop_price": 97.0, "exit_price": 96.0,
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()
        assert not (Path(d) / "learned_multipliers.json").exists()


def test_extract_skips_trade_missing_stop_price():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "regime": "bull", "outcome": "win",
            "entry_price": 100.0, "exit_price": 109.0,
            # stop_price missing — must skip without error
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()  # must not raise
        assert not (Path(d) / "learned_multipliers.json").exists()


def test_extract_skips_trade_missing_regime():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "outcome": "win",
            "entry_price": 100.0, "stop_price": 97.0, "exit_price": 109.0,
            # regime missing — must skip without error
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()  # must not raise
        assert not (Path(d) / "learned_multipliers.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pattern_extractor.py::test_refresh_saves_exit_price_to_trade_entry tests/test_pattern_extractor.py::test_extract_updates_multiplier_store_for_winning_trade tests/test_pattern_extractor.py::test_extract_does_not_update_multiplier_for_losing_trade tests/test_pattern_extractor.py::test_extract_skips_trade_missing_stop_price tests/test_pattern_extractor.py::test_extract_skips_trade_missing_regime -v
```
Expected: all 5 FAIL

- [ ] **Step 3: Replace learning/pattern_extractor.py**

```python
# learning/pattern_extractor.py
from __future__ import annotations

import json
from pathlib import Path

from learning.rule_store import RuleStore, MIN_SAMPLE_COUNT

LOSS_RATE_THRESHOLD = 0.60


class PatternExtractor:
    """Weekly job: reads auto_trades.json, resolves outcomes from Alpaca,
    updates multiplier_store (for R:R learning) and rule_store (for entry filtering).
    """

    def __init__(self, alpaca_client, rule_store: RuleStore, cache_dir: Path, multiplier_store=None):
        self._alpaca = alpaca_client
        self._rule_store = rule_store
        self._cache_dir = cache_dir
        self._multiplier_store = multiplier_store

    def load_trades(self) -> list[dict]:
        trades_file = self._cache_dir / "auto_trades.json"
        if not trades_file.exists():
            return []
        try:
            return json.loads(trades_file.read_text()).get("trades", [])
        except (json.JSONDecodeError, OSError):
            return []

    def extract(self) -> dict:
        """Refresh outcomes, update multipliers, update entry filter rules."""
        self.refresh_trade_outcomes()

        all_trades = self.load_trades()
        trades = [t for t in all_trades if t.get("outcome") is not None]

        if not trades:
            return {"trades_analyzed": 0, "rules_updated": 0}

        if self._multiplier_store is not None:
            self._update_multipliers(trades)

        stats = self._compute_stats(trades)
        new_rules, updated_ids = self._generate_rules(stats)
        self._persist_rules(new_rules, updated_ids)

        return {
            "trades_analyzed": len(trades),
            "rules_updated": len(new_rules) + len(updated_ids),
        }

    def _update_multipliers(self, trades: list[dict]) -> None:
        """Update MultiplierStore for each winning trade with all required fields."""
        required = ("exit_price", "stop_price", "entry_price", "screener", "confidence_tag", "regime")
        for t in trades:
            if t.get("outcome") != "win":
                continue
            if any(t.get(f) is None for f in required):
                continue
            risk = t["entry_price"] - t["stop_price"]
            if risk <= 0:
                continue
            achieved_rr = (t["exit_price"] - t["entry_price"]) / risk
            bucket_key = f"{t['screener']}+{t['confidence_tag']}+{t['regime']}"
            self._multiplier_store.update(bucket_key, achieved_rr)

    def refresh_trade_outcomes(self) -> int:
        """Query Alpaca closed bracket order legs to populate outcome and exit_price fields."""
        trades_file = self._cache_dir / "auto_trades.json"
        if not trades_file.exists():
            return 0
        try:
            data = json.loads(trades_file.read_text())
        except (json.JSONDecodeError, OSError):
            return 0

        open_trades = [
            t for t in data.get("trades", [])
            if t.get("outcome") is None and t.get("order_id")
        ]
        if not open_trades or not self._alpaca.is_configured:
            return 0

        updated = 0
        for trade in open_trades:
            result = self._get_order_outcome(trade["order_id"], trade.get("entry_price", 0))
            if result is not None:
                outcome, exit_price = result
                trade["outcome"] = outcome
                trade["exit_price"] = exit_price
                updated += 1

        if updated:
            trades_file.write_text(json.dumps(data, indent=2))

        return updated

    def _get_order_outcome(self, order_id: str, entry_price: float) -> tuple[str, float] | None:
        """Returns (outcome, exit_price) or None if order still open."""
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
                    outcome = "win" if exit_price > entry_price else "loss"
                    return (outcome, exit_price)
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
            elif t.get("outcome") == "loss":
                stats[tag]["losses"] += 1
        return stats

    def _generate_rules(self, stats: dict) -> tuple[list[dict], set[str]]:
        new_rules = []
        update_ids: set[str] = set()
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

- [ ] **Step 4: Run all pattern_extractor tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pattern_extractor.py -v
```
Expected: all tests PASS (original + 5 new)

- [ ] **Step 5: Commit**

```bash
git add learning/pattern_extractor.py tests/test_pattern_extractor.py
git commit -m "feat: PatternExtractor saves exit_price and updates MultiplierStore for winning trades"
```

---

## Task 3: PivotWatchlistMonitor — multiplier lookup + log field fixes

**Files:**
- Modify: `pivot_monitor.py`
- Modify: `tests/test_pivot_monitor.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_pivot_monitor.py`:

```python
# ── New tests: multiplier lookup + log field fixes ──

def make_monitor_with_store(tmp_path: Path):
    from learning.multiplier_store import MultiplierStore
    alpaca = MagicMock()
    alpaca.is_configured = True
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
    }
    mstore = MultiplierStore(
        learned_file=tmp_path / "learned_multipliers.json",
        seed_file=tmp_path / "seed_multipliers.json",
    )
    monitor = PivotWatchlistMonitor(
        alpaca_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
        multiplier_store=mstore,
    )
    return monitor, alpaca


def test_fire_order_passes_explicit_take_profit_price():
    """_fire_order must pass take_profit_price explicitly, not rely on 2:1 default."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor, alpaca = make_monitor_with_store(tmp)
        alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        alpaca.get_positions.return_value = []
        alpaca.get_last_price.return_value = 100.0
        alpaca.place_bracket_order.return_value = {
            "id": "ord1", "symbol": "AAPL", "qty": 10.0, "limit_price": 100.0, "status": "new"
        }
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        monitor._fire_order({"symbol": "AAPL", "pivot_price": 99.0}, "CLEAR")

        call_kwargs = alpaca.place_bracket_order.call_args
        assert call_kwargs is not None
        assert "take_profit_price" in call_kwargs.kwargs
        assert call_kwargs.kwargs["take_profit_price"] is not None
        assert call_kwargs.kwargs["take_profit_price"] > 100.0


def test_log_trade_stores_screener_field():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor, alpaca = make_monitor_with_store(tmp)
        alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        monitor._log_trade(
            {"symbol": "AAPL", "pivot_price": 99.0}, "ord1", 100.0, 97.0, 10, "CLEAR"
        )
        trades = json.loads((tmp / "auto_trades.json").read_text())["trades"]
        assert trades[0]["screener"] == "vcp"


def test_log_trade_stores_regime_as_string():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "macro-regime-detector.json").write_text(json.dumps({
            "regime": {"current_regime": "bull", "score": 75}
        }))
        monitor, alpaca = make_monitor_with_store(tmp)
        alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        monitor._log_trade(
            {"symbol": "AAPL", "pivot_price": 99.0}, "ord1", 100.0, 97.0, 10, "CLEAR"
        )
        trades = json.loads((tmp / "auto_trades.json").read_text())["trades"]
        assert trades[0]["regime"] == "bull"
        assert isinstance(trades[0]["regime"], str)
        assert "macro_regime" not in trades[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py::test_fire_order_passes_explicit_take_profit_price tests/test_pivot_monitor.py::test_log_trade_stores_screener_field tests/test_pivot_monitor.py::test_log_trade_stores_regime_as_string -v
```
Expected: all 3 FAIL

- [ ] **Step 3: Update pivot_monitor.py**

**3a.** Add `multiplier_store=None` parameter to `__init__` (after `rule_store=None`):
```python
def __init__(
    self,
    alpaca_client: AlpacaClient,
    settings_manager: SettingsManager,
    cache_dir: Path,
    rule_store=None,
    multiplier_store=None,
    _search_fn: Optional[Callable[[str], list[str]]] = None,
    _data_stream=None,
):
    ...
    self._multiplier_store = multiplier_store
```

**3b.** Add `_get_current_regime()` method (add after `_guard_rails_allow`):
```python
def _get_current_regime(self) -> str:
    """Extract current_regime string from macro-regime-detector cache."""
    try:
        data = json.loads((self._cache_dir / "macro-regime-detector.json").read_text())
        regime_data = data.get("regime", {})
        if isinstance(regime_data, dict):
            return regime_data.get("current_regime", "unknown")
        return str(regime_data).lower() if regime_data else "unknown"
    except Exception:
        return "unknown"
```

**3c.** Replace the body of `_fire_order()`:
```python
def _fire_order(self, candidate: dict, tag: str) -> None:
    """Fetch live price, look up learned multiplier, place bracket order, log trade."""
    symbol = candidate["symbol"]
    try:
        entry_price = self._alpaca.get_last_price(symbol)
        stop_price = round(entry_price * 0.97, 2)
        qty = self._calc_qty(entry_price, stop_price, high_conviction=(tag == "HIGH_CONVICTION"))
        if qty <= 0:
            print(f"[pivot_monitor] {symbol}: qty=0, skipping", file=sys.stderr)
            return

        regime = self._get_current_regime()
        multiplier = 2.0
        if self._multiplier_store is not None:
            bucket_key = f"vcp+{tag}+{regime}"
            multiplier = self._multiplier_store.get(bucket_key)
        take_profit_price = round(entry_price + (entry_price - stop_price) * multiplier, 2)

        result = self._alpaca.place_bracket_order(
            symbol=symbol, qty=qty, limit_price=entry_price, stop_price=stop_price,
            take_profit_price=take_profit_price,
        )
        print(
            f"[pivot_monitor] ORDER: {symbol} {qty}sh @ {entry_price} "
            f"tp={take_profit_price} ({multiplier:.1f}x) | {result}",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"[pivot_monitor] {symbol} order error: {e}", file=sys.stderr)
        return
    try:
        self._log_trade(candidate, result["id"], entry_price, stop_price, qty, tag)
    except Exception as e:
        print(f"[pivot_monitor] {symbol} log error (order placed): {e}", file=sys.stderr)
```

**3d.** In `_log_trade()`, remove the `macro_regime` local variable and replace the `"macro_regime": macro_regime` entry:

Remove this line (near line 270):
```python
macro_regime = self._read_cache_field("macro-regime-detector.json", "regime")
```

In the `trades["trades"].append({...})` block, replace:
```python
"macro_regime": macro_regime,
```
With:
```python
"regime": self._get_current_regime(),
"screener": "vcp",
```

- [ ] **Step 4: Run all pivot_monitor tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_pivot_monitor.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add pivot_monitor.py tests/test_pivot_monitor.py
git commit -m "feat: pivot_monitor uses learned multiplier; stores screener and regime string in trade log"
```

---

## Task 4: main.py — manual order flow integration

**Files:**
- Modify: `main.py`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_routes.py`:

```python
def test_order_confirm_in_advisory_mode_returns_403():
    client = make_client()
    r = client.post("/api/order/confirm", json={
        "symbol": "AAPL", "qty": 10, "limit_price": 155.0, "stop_price": 150.0,
        "skill": "vcp", "confidence_tag": "CLEAR",
    })
    assert r.status_code == 403


def test_order_confirm_passes_take_profit_price_to_alpaca(monkeypatch):
    """order_confirm must pass an explicit take_profit_price, not rely on 2:1 default."""
    from main import alpaca
    from config import SETTINGS_FILE
    import json

    captured = {}

    def fake_place(symbol, qty, limit_price, stop_price, take_profit_price=None):
        captured["take_profit_price"] = take_profit_price
        return {"id": "ord1", "symbol": symbol, "qty": qty, "limit_price": limit_price, "status": "new"}

    monkeypatch.setattr(alpaca, "is_configured", True)
    monkeypatch.setattr(alpaca, "place_bracket_order", fake_place)
    SETTINGS_FILE.write_text(json.dumps({"mode": "auto", "environment": "paper"}))

    client = make_client()
    r = client.post("/api/order/confirm", json={
        "symbol": "AAPL", "qty": 10, "limit_price": 155.0, "stop_price": 150.0,
        "skill": "vcp", "confidence_tag": "CLEAR",
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert captured.get("take_profit_price") is not None
    assert captured["take_profit_price"] > 155.0


def test_order_confirm_missing_regime_cache_does_not_error(monkeypatch, tmp_path):
    """Missing macro-regime cache must not block order placement."""
    from main import alpaca
    from config import SETTINGS_FILE, CACHE_DIR
    import json, shutil

    monkeypatch.setattr(alpaca, "is_configured", True)
    monkeypatch.setattr(
        alpaca, "place_bracket_order",
        lambda symbol, qty, limit_price, stop_price, take_profit_price=None: {
            "id": "ord2", "symbol": symbol, "qty": qty,
            "limit_price": limit_price, "status": "new",
        }
    )
    SETTINGS_FILE.write_text(json.dumps({"mode": "auto", "environment": "paper"}))

    regime_file = CACHE_DIR / "macro-regime-detector.json"
    backup = tmp_path / "macro-regime-detector.json.bak"
    existed = regime_file.exists()
    if existed:
        shutil.copy(regime_file, backup)
        regime_file.unlink()
    try:
        client = make_client()
        r = client.post("/api/order/confirm", json={
            "symbol": "AAPL", "qty": 5, "limit_price": 100.0, "stop_price": 97.0,
            "skill": "vcp", "confidence_tag": "CLEAR",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        if existed:
            shutil.copy(backup, regime_file)


def test_order_preview_includes_multiplier_in_response(monkeypatch):
    """order_preview HTML must contain the take-profit multiplier."""
    from main import alpaca
    from config import SETTINGS_FILE
    import json

    monkeypatch.setattr(alpaca, "is_configured", True)
    monkeypatch.setattr(alpaca, "get_last_price", lambda sym: 155.0)
    monkeypatch.setattr(alpaca, "get_account", lambda: {"portfolio_value": 100_000.0})
    SETTINGS_FILE.write_text(json.dumps({"mode": "auto", "environment": "paper"}))

    client = make_client()
    r = client.post("/api/order/preview", data={
        "symbol": "AAPL", "entry_price": "155.0", "stop_price": "150.0", "skill": "vcp",
    })
    assert r.status_code == 200
    assert "×" in r.text or "x R" in r.text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd examples/market-dashboard
uv run pytest tests/test_routes.py::test_order_confirm_in_advisory_mode_returns_403 tests/test_routes.py::test_order_confirm_passes_take_profit_price_to_alpaca tests/test_routes.py::test_order_confirm_missing_regime_cache_does_not_error tests/test_routes.py::test_order_preview_includes_multiplier_in_response -v
```
Expected: failures due to missing `skill` field in `OrderConfirmRequest` and missing multiplier logic

- [ ] **Step 3: Update main.py**

**3a.** Add import (after existing learning imports):
```python
from learning.multiplier_store import MultiplierStore
```

**3b.** Instantiate `multiplier_store` (add after `rule_store = RuleStore()`):
```python
multiplier_store = MultiplierStore()  # uses learning/seed_multipliers.json + learning/learned_multipliers.json
```

**3c.** Add `multiplier_store=multiplier_store` to `pivot_monitor` constructor call:
```python
pivot_monitor = PivotWatchlistMonitor(
    alpaca_client=alpaca,
    settings_manager=settings_manager,
    cache_dir=CACHE_DIR,
    rule_store=rule_store,
    multiplier_store=multiplier_store,
)
```

**3d.** Add `multiplier_store=multiplier_store` to `pattern_extractor` constructor call:
```python
pattern_extractor = PatternExtractor(
    alpaca_client=alpaca,
    rule_store=rule_store,
    cache_dir=CACHE_DIR,
    multiplier_store=multiplier_store,
)
```

**3e.** Add helper functions (insert before the route definitions, after `_market_state()`):
```python
def _read_regime(cache_dir: Path) -> str:
    """Extract current_regime string from macro-regime-detector cache."""
    try:
        data = json.loads((cache_dir / "macro-regime-detector.json").read_text())
        regime_data = data.get("regime", {})
        if isinstance(regime_data, dict):
            return regime_data.get("current_regime", "unknown")
        return str(regime_data).lower() if regime_data else "unknown"
    except Exception:
        return "unknown"


def _log_manual_trade(body: "OrderConfirmRequest", order_id: str, regime: str) -> None:
    """Append manual order to auto_trades.json so PatternExtractor can learn from it."""
    trades_file = CACHE_DIR / "auto_trades.json"
    try:
        data = json.loads(trades_file.read_text()) if trades_file.exists() else {"trades": []}
    except (json.JSONDecodeError, OSError):
        data = {"trades": []}
    from datetime import timezone
    data["trades"].append({
        "symbol": body.symbol,
        "order_id": order_id,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "entry_price": body.limit_price,
        "stop_price": body.stop_price,
        "qty": body.qty,
        "confidence_tag": body.confidence_tag,
        "screener": body.skill,
        "regime": regime,
        "outcome": None,
    })
    try:
        trades_file.write_text(json.dumps(data, indent=2))
    except OSError:
        pass
```

**3f.** Replace `OrderConfirmRequest`:
```python
class OrderConfirmRequest(BaseModel):
    symbol: str
    qty: int
    limit_price: float
    stop_price: float
    skill: str = "unknown"
    confidence_tag: str = "CLEAR"
```

**3g.** Replace the body of `order_confirm()`:
```python
@app.post("/api/order/confirm")
async def order_confirm(body: OrderConfirmRequest):
    settings = settings_manager.load()
    if settings.get("mode") == "advisory":
        raise HTTPException(status_code=403, detail="Execute not available in Advisory mode")
    if not alpaca.is_configured:
        return JSONResponse({"ok": False, "error": "Alpaca not configured — set API keys in .env"})

    regime = _read_regime(CACHE_DIR)
    bucket_key = f"{body.skill}+{body.confidence_tag}+{regime}"
    mult = multiplier_store.get(bucket_key)
    take_profit_price = round(body.limit_price + (body.limit_price - body.stop_price) * mult, 2)

    try:
        result = alpaca.place_bracket_order(
            symbol=body.symbol,
            qty=body.qty,
            limit_price=body.limit_price,
            stop_price=body.stop_price,
            take_profit_price=take_profit_price,
        )
        _log_manual_trade(body, result["id"], regime)
        return JSONResponse({"ok": True, "order_id": result["id"], "status": result["status"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
```

**3h.** Update `order_preview()` — add multiplier computation after `effective_stop` line, then update `ctx`:

Add after `effective_stop = ...`:
```python
    regime = _read_regime(CACHE_DIR)
    bucket_key = f"{skill}+CLEAR+{regime}"
    mult = multiplier_store.get(bucket_key)
    learned_bucket = multiplier_store._load_learned().get(bucket_key, {})
    n_real = len(learned_bucket.get("observed_rr", []))
    from learning.multiplier_store import MIN_SAMPLE_COUNT
    multiplier_source = (
        f"based on {n_real} {bucket_key} trades"
        if n_real >= MIN_SAMPLE_COUNT
        else "from published research"
    )
```

Add to `ctx` dict:
```python
        "multiplier": mult,
        "multiplier_source": multiplier_source,
```

- [ ] **Step 4: Run all route tests to verify they pass**

```bash
cd examples/market-dashboard
uv run pytest tests/test_routes.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_routes.py
git commit -m "feat: order_confirm and order_preview use learned multiplier; manual trades logged for future learning"
```

---

## Task 5: order_preview.html — display multiplier + pass skill to confirm

**Files:**
- Modify: `templates/fragments/order_preview.html`

- [ ] **Step 1: Verify the template test currently fails**

```bash
cd examples/market-dashboard
uv run pytest tests/test_routes.py::test_order_preview_includes_multiplier_in_response -v
```
Expected: FAIL (template doesn't render multiplier yet)

- [ ] **Step 2: Update templates/fragments/order_preview.html**

**2a.** Add take-profit info row — insert after the entry/stop/risk row (after the closing `</div>` of the first flex row, before the mode selector div):

```html
  <!-- Take-profit multiplier (learned from trade history) -->
  <div style="margin-bottom:10px; padding:5px 8px; background:#162032; border-radius:4px; font-size:11px;">
    <span style="color:#8b949e;">Take-profit:</span>
    <span style="color:#4ade80; font-weight:bold;">{{ "%.1f"|format(multiplier) }}× R</span>
    <span style="color:#8b949e; margin-left:6px;">— {{ multiplier_source }}</span>
  </div>
```

**2b.** Add JS variables for `skill` and `confidence_tag` — insert after `var DEFAULT_RISK = ...`:

```javascript
  var SKILL = "{{ skill }}";
  var CONFIDENCE_TAG = "CLEAR";
```

**2c.** Update `opConfirm` fetch body to include `skill` and `confidence_tag`. Replace:

```javascript
      body: JSON.stringify({symbol: sym, qty: shares, limit_price: entry, stop_price: stop})
```

With:

```javascript
      body: JSON.stringify({symbol: sym, qty: shares, limit_price: entry, stop_price: stop, skill: SKILL, confidence_tag: CONFIDENCE_TAG})
```

- [ ] **Step 3: Run the template test to verify it passes**

```bash
cd examples/market-dashboard
uv run pytest tests/test_routes.py::test_order_preview_includes_multiplier_in_response -v
```
Expected: PASS

- [ ] **Step 4: Run the full test suite**

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add templates/fragments/order_preview.html
git commit -m "feat: order_preview shows take-profit multiplier and passes skill to confirm form"
```

---

## Done

At this point:
- Auto mode (PivotWatchlistMonitor) uses a bucket-keyed multiplier for every bracket order
- Manual mode (order_confirm) uses the same multiplier, and logs the trade for future learning
- PatternExtractor resolves closed wins and feeds achieved R:R back into MultiplierStore weekly
- The dashboard shows each order's multiplier and whether it came from research or real trades
- Paper trading accumulates data that gradually replaces the published research priors
