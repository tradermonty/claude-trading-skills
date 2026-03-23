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
