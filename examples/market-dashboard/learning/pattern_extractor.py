# learning/pattern_extractor.py
from __future__ import annotations

import json
from pathlib import Path

from learning.rule_store import RuleStore, MIN_SAMPLE_COUNT

LOSS_RATE_THRESHOLD = 0.60  # activate UNCERTAIN→BLOCKED rule above this stop-out rate


class PatternExtractor:
    """Weekly job: reads auto_trades.json, resolves outcomes from Alpaca, updates rule_store.

    Flow: extract() → refresh_trade_outcomes() → analyze trades with outcomes → update rules.
    Additional rule types (market top, breadth correlation) deferred to Plan 3b once
    sufficient trade history accumulates.
    """

    def __init__(self, alpaca_client, rule_store: RuleStore, cache_dir: Path):
        self._alpaca = alpaca_client
        self._rule_store = rule_store
        self._cache_dir = cache_dir

    def load_trades(self) -> list[dict]:
        trades_file = self._cache_dir / "auto_trades.json"
        if not trades_file.exists():
            return []
        try:
            return json.loads(trades_file.read_text()).get("trades", [])
        except (json.JSONDecodeError, OSError):
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
