"""Issue #759: requested equity price checks must fail closed before saving."""

import json

import pytest
import thesis_store as store


def setup_report(tmp_path, parameters):
    state = tmp_path / "state"
    tid = store.register(
        state,
        {
            "ticker": "AAPL",
            "thesis_type": "dividend_income",
            "thesis_statement": "Expected price verification",
            "origin": {"skill": "test", "output_file": "test.json"},
        },
    )
    report = tmp_path / "position.json"
    report.write_text(
        json.dumps(
            {
                "mode": "shares",
                "parameters": parameters,
                "final_recommended_shares": 10,
                "final_position_value": 1500,
                "final_risk_dollars": 100,
                "final_risk_pct": 0.01,
            }
        ),
        encoding="utf-8",
    )
    return state, tid, str(report)


def snapshot(state):
    return {p.name: p.read_bytes() for p in state.iterdir()}


@pytest.mark.parametrize("field", ["entry", "stop"])
@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), float("-inf"), True, False, "150", 10**400]
)
def test_invalid_expected_prices_preserve_state(tmp_path, field, bad):
    # Bool/string expectations could otherwise compare equal to a report price.
    price = 1 if isinstance(bad, bool) else 150
    state, tid, report = setup_report(tmp_path, {f"{field}_price": price})
    before = snapshot(state)
    with pytest.raises(ValueError, match=f"expected_{field} must be a finite number"):
        store.attach_position(state, tid, report, **{f"expected_{field}": bad})
    assert snapshot(state) == before


@pytest.mark.parametrize("field", ["entry", "stop"])
@pytest.mark.parametrize(
    "bad", [None, "bad", True, False, {}, [], float("nan"), float("inf"), float("-inf"), 10**400]
)
def test_invalid_report_prices_preserve_state(tmp_path, field, bad):
    # Omit the other price so the initial-stop pair validator cannot mask this guard.
    state, tid, report = setup_report(tmp_path, {f"{field}_price": bad})
    before = snapshot(state)
    with pytest.raises(ValueError, match=f"report {field} is invalid or missing"):
        store.attach_position(state, tid, report, **{f"expected_{field}": 150})
    assert snapshot(state) == before


@pytest.mark.parametrize("field", ["entry", "stop"])
def test_missing_report_price_rejected_before_loading_state(tmp_path, field):
    state, tid, report = setup_report(tmp_path, {})
    before = snapshot(state)
    with pytest.raises(ValueError, match=f"report {field} is invalid or missing"):
        store.attach_position(state, tid, report, **{f"expected_{field}": 150})
    assert snapshot(state) == before
    absent = tmp_path / "absent"
    with pytest.raises(ValueError, match=f"report {field} is invalid or missing"):
        store.attach_position(absent, "missing", report, **{f"expected_{field}": 150})
    assert not absent.exists()


@pytest.mark.parametrize("field", ["entry", "stop"])
@pytest.mark.parametrize("price", [150, 0, -10])
@pytest.mark.parametrize("delta", [0, 0.005])
def test_finite_expected_prices_preserve_equity_compatibility(tmp_path, field, price, delta):
    state, tid, report = setup_report(tmp_path, {f"{field}_price": price})
    thesis = store.attach_position(state, tid, report, **{f"expected_{field}": price + delta})
    assert thesis["position"]["shares"] == 10
    assert store.get(state, tid)["position"] == thesis["position"]


@pytest.mark.parametrize("field", ["entry", "stop"])
@pytest.mark.parametrize("price,expected", [(150, 150.02), (2**53 + 1, 2**53)])
def test_mismatches_preserve_state_and_integer_precision(tmp_path, field, price, expected):
    state, tid, report = setup_report(tmp_path, {f"{field}_price": price})
    before = snapshot(state)
    with pytest.raises(ValueError, match=f"{field.title()} price mismatch"):
        store.attach_position(state, tid, report, **{f"expected_{field}": expected})
    assert snapshot(state) == before


def test_omitted_expectations_keep_legacy_missing_prices(tmp_path):
    state, tid, report = setup_report(tmp_path, {})
    assert store.attach_position(state, tid, report)["position"]["shares"] == 10


@pytest.mark.parametrize("field", ["entry", "stop"])
@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "true", "bad"])
def test_cli_rejects_invalid_expected_prices_before_state_access(tmp_path, capsys, field, bad):
    absent = tmp_path / "absent"
    with pytest.raises(SystemExit) as exc:
        store.main(
            [
                "--state-dir",
                str(absent),
                "attach-position",
                "missing",
                "--report",
                str(tmp_path / "missing.json"),
                f"--expected-{field}={bad}",
            ]
        )
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err
    assert not absent.exists()


@pytest.mark.parametrize("field", ["entry", "stop"])
@pytest.mark.parametrize("price", [0, -10])
def test_cli_accepts_finite_nonpositive_expected_prices(tmp_path, field, price):
    state, tid, report = setup_report(tmp_path, {f"{field}_price": price})
    assert (
        store.main(
            [
                "--state-dir",
                str(state),
                "attach-position",
                tid,
                "--report",
                report,
                f"--expected-{field}={price}",
            ]
        )
        == 0
    )
    assert store.get(state, tid)["position"]["shares"] == 10
