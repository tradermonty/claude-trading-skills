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
        except json.JSONDecodeError:
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
        # Empty condition matches all candidates (intentional — universal rule).
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
