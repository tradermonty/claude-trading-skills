"""Tests for load_analysis_data, generate_html defaults and main() of generate_histogram_html."""

import json
import sys

import generate_histogram_html as ghh
import pytest

DATA = {
    "analysis_date": "2026-03-04T05:06:07Z",
    "parameters": {"lookback_years": 4, "peak_window": 15, "min_depth_pct": 7.5},
    "summary": {"total_downtrends": 2},
    "downtrends": [
        {"symbol": "AAA", "sector": "Energy", "duration_days": 5, "depth_pct": -10.0},
        {"symbol": "BBB", "sector": "Utilities", "duration_days": 9, "depth_pct": -12.0},
    ],
}


def test_load_analysis_data_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps(DATA))
    assert ghh.load_analysis_data(p) == DATA


def test_generate_html_embeds_parameters():
    html = ghh.generate_html(DATA)
    assert "2026-03-04" in html
    assert '<option value="Energy">Energy</option>' in html
    assert '<option value="Utilities">Utilities</option>' in html
    assert '"symbol": "AAA"' in html


def test_generate_html_defaults_for_empty_data():
    html = ghh.generate_html({})
    # Missing analysis_date -> "Unknown"; no downtrends -> empty JSON array and no sector options.
    assert "Unknown" in html
    assert 'value="Energy"' not in html
    assert "</html>" in html


def test_find_latest_json_glob_missing_dir_falls_back_to_output_dir(tmp_path):
    (tmp_path / "downtrend_analysis_2026-01-01.json").write_text("{}")
    (tmp_path / "downtrend_analysis_2026-02-01.json").write_text("{}")
    missing = tmp_path / "nope" / "downtrend_analysis_*.json"
    found = ghh.find_latest_json(str(missing), tmp_path)
    assert found.name == "downtrend_analysis_2026-02-01.json"


class TestMain:
    def test_writes_html_from_explicit_input(self, tmp_path, monkeypatch, capsys):
        src = tmp_path / "in.json"
        src.write_text(json.dumps(DATA))
        out = tmp_path / "out"
        monkeypatch.setattr(sys, "argv", ["prog", "--input", str(src), "--output-dir", str(out)])
        ghh.main()
        files = list(out.glob("downtrend_histogram_*.html"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert '<option value="Energy">Energy</option>' in content
        assert "2026-03-04" in content
        stdout = capsys.readouterr().out
        assert f"Loading data from: {src}" in stdout
        assert "HTML visualization saved to:" in stdout

    def test_glob_input_picks_latest(self, tmp_path, monkeypatch):
        older = dict(DATA, downtrends=[DATA["downtrends"][0]])
        (tmp_path / "downtrend_analysis_2026-01-01.json").write_text(json.dumps(older))
        (tmp_path / "downtrend_analysis_2026-02-01.json").write_text(json.dumps(DATA))
        out = tmp_path / "out"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "prog",
                "--input",
                str(tmp_path / "downtrend_analysis_*.json"),
                "--output-dir",
                str(out),
            ],
        )
        ghh.main()
        content = next(out.glob("*.html")).read_text(encoding="utf-8")
        assert "Utilities" in content

    def test_no_input_exits_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            sys,
            "argv",
            ["prog", "--input", str(tmp_path / "missing.json"), "--output-dir", str(tmp_path)],
        )
        with pytest.raises(SystemExit) as exc:
            ghh.main()
        assert exc.value.code == 1
        assert "No input file found" in capsys.readouterr().err
