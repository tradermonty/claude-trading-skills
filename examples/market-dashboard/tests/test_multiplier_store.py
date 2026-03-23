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


# ── Kelly multiplier tests ────────────────────────────────────────────────────

def test_kelly_returns_1_when_insufficient_samples():
    """< 10 samples → no adjustment, return 1.0."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [2.0, 2.5, 3.0],
                "wins": 2, "losses": 1,
                "p75": 3.0, "sample_count": 3,
            }
        })
        store = make_store(tmp)
        assert store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0) == 1.0


def test_kelly_high_win_rate_returns_multiplier_above_1():
    """High win rate + good R:R → multiplier > 1.0."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # 8 wins, 2 losses, avg_rr ~3.0 → kelly > base_risk_pct/100 → mult > 1
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [3.0] * 10,
                "wins": 8, "losses": 2,
                "p75": 3.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0)
        assert result > 1.0


def test_kelly_low_win_rate_returns_multiplier_below_1():
    """Low win rate → multiplier < 1.0 (reduce size)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # 2 wins, 8 losses → kelly fraction small → mult < 1
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [2.0] * 10,
                "wins": 2, "losses": 8,
                "p75": 2.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0)
        assert result < 1.0


def test_kelly_multiplier_capped_at_max():
    """Multiplier never exceeds max_multiplier."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Perfect win rate, very high R:R → would normally produce huge multiplier
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [10.0] * 10,
                "wins": 10, "losses": 0,
                "p75": 10.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0, max_multiplier=2.0)
        assert result <= 2.0


def test_kelly_multiplier_floor_prevents_zero_size():
    """Multiplier never drops below 0.1 — always some position taken."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # 0 wins, 10 losses → kelly fraction would be 0 or negative
        write_learned(tmp, {
            "vcp+CLEAR+bull": {
                "observed_rr": [1.0] * 10,
                "wins": 0, "losses": 10,
                "p75": 1.0, "sample_count": 10,
            }
        })
        store = make_store(tmp)
        result = store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0)
        assert result >= 0.1


def test_kelly_returns_1_on_corrupt_data():
    """Corrupt JSON in learned file → graceful fallback to 1.0."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "learned_multipliers.json").write_text("not valid json {{{")
        store = make_store(tmp)
        assert store.get_kelly_multiplier("vcp+CLEAR+bull", base_risk_pct=1.0) == 1.0


def test_update_loss_with_negative_rr_still_increments_counter():
    """Losses with negative RR (common in practice) must still increment the loss counter."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        store = make_store(tmp)
        # Simulate a typical loss: exit below entry gives negative RR
        store.update("vcp+CLEAR+bull", -0.5, outcome="loss")
        data = json.loads((tmp / "learned_multipliers.json").read_text())
        bucket = data["vcp+CLEAR+bull"]
        assert bucket["losses"] == 1
        assert bucket.get("wins", 0) == 0
        assert bucket.get("observed_rr", []) == []  # no RR appended for losses
