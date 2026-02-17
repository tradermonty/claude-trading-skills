"""Tests for config_loader module.

Covers YAML loading, validation, ETF catalog extraction, and fallback behavior.
"""

import os
import tempfile

import pytest

from config_loader import (
    load_themes_config,
    _load_yaml,
    _validate_config,
    _extract_etf_catalog,
    _strip_etf_count,
    _get_bundled_yaml_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmpdir, content):
    path = os.path.join(tmpdir, "themes.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


VALID_YAML = """\
cross_sector_min_matches: 2
vertical_min_industries: 3
cross_sector:
  - theme_name: "Test Theme"
    matching_keywords:
      - Semiconductors
      - Software - Application
    proxy_etfs: [SMH, SOXX]
    static_stocks: [NVDA, AMD]
    etf_count: 4
"""

VALID_YAML_NO_ETF_COUNT = """\
cross_sector_min_matches: 2
vertical_min_industries: 3
cross_sector:
  - theme_name: "No ETF Count"
    matching_keywords:
      - Gold
    proxy_etfs: [GDX]
    static_stocks: [NEM]
"""


# ---------------------------------------------------------------------------
# TestLoadYaml
# ---------------------------------------------------------------------------

class TestLoadYaml:

    def test_loads_valid_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_yaml(tmpdir, VALID_YAML)
            config = _load_yaml(path)
            assert config["cross_sector_min_matches"] == 2
            assert len(config["cross_sector"]) == 1

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            _load_yaml("/nonexistent/path/themes.yaml")

    def test_invalid_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_yaml(tmpdir, "cross_sector: [{{invalid")
            with pytest.raises(Exception):
                _load_yaml(path)


# ---------------------------------------------------------------------------
# TestValidateConfig
# ---------------------------------------------------------------------------

class TestValidateConfig:

    def test_valid_config_passes(self):
        config = {
            "cross_sector_min_matches": 2,
            "vertical_min_industries": 3,
            "cross_sector": [
                {
                    "theme_name": "Test",
                    "matching_keywords": ["A"],
                    "proxy_etfs": [],
                    "static_stocks": [],
                },
            ],
        }
        _validate_config(config)  # should not raise

    def test_missing_cross_sector_raises(self):
        config = {"cross_sector_min_matches": 2}
        with pytest.raises(ValueError, match="cross_sector"):
            _validate_config(config)

    def test_missing_theme_name_raises(self):
        config = {
            "cross_sector": [
                {"matching_keywords": ["A"]},
            ],
        }
        with pytest.raises(ValueError, match="theme_name"):
            _validate_config(config)

    def test_missing_matching_keywords_raises(self):
        config = {
            "cross_sector": [
                {"theme_name": "Test"},
            ],
        }
        with pytest.raises(ValueError, match="matching_keywords"):
            _validate_config(config)


# ---------------------------------------------------------------------------
# TestExtractEtfCatalog
# ---------------------------------------------------------------------------

class TestExtractEtfCatalog:

    def test_extracts_etf_counts(self):
        config = {
            "cross_sector": [
                {"theme_name": "A", "etf_count": 5},
                {"theme_name": "B", "etf_count": 3},
            ],
        }
        catalog = _extract_etf_catalog(config)
        assert catalog == {"A": 5, "B": 3}

    def test_missing_etf_count_defaults_to_zero(self):
        config = {
            "cross_sector": [
                {"theme_name": "A"},
            ],
        }
        catalog = _extract_etf_catalog(config)
        assert catalog == {"A": 0}

    def test_empty_config_returns_empty(self):
        config = {"cross_sector": []}
        catalog = _extract_etf_catalog(config)
        assert catalog == {}


# ---------------------------------------------------------------------------
# TestStripEtfCount
# ---------------------------------------------------------------------------

class TestStripEtfCount:

    def test_removes_etf_count_from_themes(self):
        config = {
            "cross_sector": [
                {"theme_name": "A", "etf_count": 5, "matching_keywords": ["X"]},
            ],
        }
        stripped = _strip_etf_count(config)
        assert "etf_count" not in stripped["cross_sector"][0]
        assert stripped["cross_sector"][0]["theme_name"] == "A"

    def test_preserves_other_keys(self):
        config = {
            "cross_sector_min_matches": 2,
            "vertical_min_industries": 3,
            "cross_sector": [
                {"theme_name": "A", "etf_count": 5, "matching_keywords": ["X"]},
            ],
        }
        stripped = _strip_etf_count(config)
        assert stripped["cross_sector_min_matches"] == 2
        assert stripped["vertical_min_industries"] == 3


# ---------------------------------------------------------------------------
# TestLoadThemesConfig (integration)
# ---------------------------------------------------------------------------

class TestLoadThemesConfig:

    def test_bundled_yaml_loads_successfully(self):
        """Default (no path) loads the bundled themes.yaml."""
        config, catalog = load_themes_config()
        assert "cross_sector" in config
        assert len(config["cross_sector"]) == 15
        assert "AI & Semiconductors" in catalog
        assert catalog["AI & Semiconductors"] == 8

    def test_custom_yaml_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_yaml(tmpdir, VALID_YAML)
            config, catalog = load_themes_config(yaml_path=path)
            assert len(config["cross_sector"]) == 1
            assert config["cross_sector"][0]["theme_name"] == "Test Theme"
            assert catalog == {"Test Theme": 4}

    def test_explicit_path_missing_raises_error(self):
        """Explicit path that doesn't exist -> fail-fast (not fallback)."""
        with pytest.raises(FileNotFoundError):
            load_themes_config(yaml_path="/nonexistent/themes.yaml")

    def test_explicit_path_invalid_yaml_raises_error(self):
        """Explicit path with invalid YAML -> fail-fast."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_yaml(tmpdir, "cross_sector: [{{invalid")
            with pytest.raises(Exception):
                load_themes_config(yaml_path=path)

    def test_bundled_yaml_fallback_to_inline(self, monkeypatch):
        """When bundled YAML is broken, falls back to inline config."""
        def fake_get_path():
            return "/nonexistent/bundled/themes.yaml"
        monkeypatch.setattr("config_loader._get_bundled_yaml_path", fake_get_path)
        config, catalog = load_themes_config()
        # Should fall back to DEFAULT_THEMES_CONFIG from default_theme_config.py
        assert "cross_sector" in config
        assert len(config["cross_sector"]) == 15

    def test_config_has_no_etf_count_after_loading(self):
        """etf_count should be stripped from the returned config."""
        config, catalog = load_themes_config()
        for theme in config["cross_sector"]:
            assert "etf_count" not in theme

    def test_get_bundled_yaml_path_exists(self):
        path = _get_bundled_yaml_path()
        assert os.path.exists(path)
        assert path.endswith("themes.yaml")
