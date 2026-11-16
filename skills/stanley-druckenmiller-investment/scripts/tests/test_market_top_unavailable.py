"""Do not synthesize allocations from an unassessed market-top report."""

import pytest
import strategy_synthesizer as app
from report_loader import extract_signal


@pytest.mark.parametrize(
    "composite", [{"composite_score": None}, {"composite_score": 50, "data_available": False}]
)
def test_extractor_rejects_unassessed_market_top(composite):
    with pytest.raises(ValueError, match="unavailable"):
        extract_signal(
            "market_top",
            {
                "composite": composite,
                "top_risk_score": 100,
                "top_probability": 0,
                "distribution_days": 0,
            },
        )


def test_cli_refuses_allocation_without_usable_market_top(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        app,
        "load_all_reports",
        lambda *a, **kw: {
            "market_top": {"composite": {"composite_score": None, "data_available": False}}
        },
    )
    monkeypatch.setattr("sys.argv", ["strategy_synthesizer.py", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err and "unavailable" in captured.err
    assert "Traceback" not in captured.err
    assert "Equity Target:" not in captured.out
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.glob("*.md"))
