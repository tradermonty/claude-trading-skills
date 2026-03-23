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

        if any([self._multiplier_store, self._time_of_day_tracker, self._stop_distance_store, self._experiment_tracker]):
            self._update_multipliers(trades)

        stats = self._compute_stats(trades)
        new_rules, updated_ids = self._generate_rules(stats)
        self._persist_rules(new_rules, updated_ids)

        return {
            "trades_analyzed": len(trades),
            "rules_updated": len(new_rules) + len(updated_ids),
        }

    def _update_multipliers(self, trades: list[dict]) -> None:
        """Update MultiplierStore for each completed trade with outcome."""
        required = ("exit_price", "stop_price", "entry_price", "screener", "confidence_tag", "regime")
        for t in trades:
            outcome = t.get("outcome")
            if outcome not in ("win", "loss"):
                continue
            if self._multiplier_store is not None:
                if any(t.get(f) is None for f in required):
                    pass
                else:
                    risk = t["entry_price"] - t["stop_price"]
                    if risk > 0:
                        achieved_rr = (t["exit_price"] - t["entry_price"]) / risk
                        bucket_key = f"{t['screener']}+{t['confidence_tag']}+{t['regime']}"
                        self._multiplier_store.update(bucket_key, achieved_rr, outcome=outcome)

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
