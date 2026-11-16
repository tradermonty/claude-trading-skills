"""Missing PyYAML handling: explicit config exits 2, bundled config degrades (#497)."""

import sys

import config_loader
import pytest
import theme_detector


def test_explicit_themes_config_without_pyyaml_exits_2(monkeypatch, capsys, tmp_path):
    cfg = tmp_path / "themes.yaml"
    cfg.write_text("cross_sector: []\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)  # `import yaml` raises ImportError
    rc = theme_detector.main(["--themes-config", str(cfg), "--output-dir", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR: PyYAML library not found" in captured.err
    assert "pip install -r" in captured.err
    assert "requirements.txt" in captured.err
    assert "ERROR" not in captured.out


def test_explicit_path_load_raises_missing_dependency(monkeypatch, tmp_path):
    cfg = tmp_path / "themes.yaml"
    cfg.write_text("cross_sector: []\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(config_loader.MissingDependencyError, match="requirements.txt"):
        config_loader.load_themes_config(str(cfg))


def test_bundled_config_without_pyyaml_degrades_with_stderr_hint(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yaml", None)
    config, catalog = config_loader.load_themes_config()
    captured = capsys.readouterr()
    assert config["cross_sector"]
    assert catalog
    assert "WARNING: YAML load failed" in captured.err
    assert "requirements.txt" in captured.err
    assert captured.out == ""
