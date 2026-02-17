"""Theme configuration loader with YAML support and inline fallback.

Loads cross-sector theme definitions from:
1. User-specified YAML file (--themes-config)
2. Bundled themes.yaml (same directory as this module)
3. Inline DEFAULT_THEMES_CONFIG (fallback when YAML is unavailable)

Error handling:
- Explicit yaml_path: fail-fast on any error (FileNotFoundError, yaml.YAMLError)
- No yaml_path: bundled YAML -> inline fallback (safe degradation)
"""

import copy
import os
import sys
from typing import Dict, Optional, Tuple


def load_themes_config(
    yaml_path: Optional[str] = None,
) -> Tuple[Dict, Dict[str, int]]:
    """Load themes config and ETF catalog.

    Args:
        yaml_path: Path to custom themes YAML. If None, tries bundled then inline.

    Returns:
        (themes_config, etf_catalog) where themes_config has etf_count stripped.

    Raises:
        FileNotFoundError: If explicit yaml_path doesn't exist.
        yaml.YAMLError: If explicit yaml_path contains invalid YAML.
        ValueError: If config fails validation.
    """
    if yaml_path is not None:
        # Explicit path -> fail-fast
        raw = _load_yaml(yaml_path)
        _validate_config(raw)
        catalog = _extract_etf_catalog(raw)
        config = _strip_etf_count(raw)
        return config, catalog

    # No path specified -> try bundled YAML, then inline fallback
    try:
        bundled = _get_bundled_yaml_path()
        raw = _load_yaml(bundled)
        _validate_config(raw)
        catalog = _extract_etf_catalog(raw)
        config = _strip_etf_count(raw)
        return config, catalog
    except Exception:
        print("WARNING: YAML load failed, using inline config", file=sys.stderr)
        from default_theme_config import DEFAULT_THEMES_CONFIG, ETF_CATALOG
        return copy.deepcopy(DEFAULT_THEMES_CONFIG), dict(ETF_CATALOG)


def _load_yaml(path: str) -> Dict:
    """Load and parse a YAML file.

    Raises:
        FileNotFoundError: If file doesn't exist.
        RuntimeError: If PyYAML is not installed.
        yaml.YAMLError: If YAML is malformed.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"YAML config not found: {path}")

    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            "PyYAML is required but not installed. "
            "Install with: pip install pyyaml>=6.0"
        )

    with open(path) as f:
        return yaml.safe_load(f)


def _validate_config(config: Dict) -> None:
    """Validate required keys in themes config.

    Raises:
        ValueError: If required keys are missing.
    """
    if not isinstance(config, dict):
        raise ValueError("Config must be a dict")

    if "cross_sector" not in config:
        raise ValueError("Config missing required key: cross_sector")

    for i, theme in enumerate(config["cross_sector"]):
        if "theme_name" not in theme:
            raise ValueError(
                f"Theme at index {i} missing required key: theme_name"
            )
        if "matching_keywords" not in theme:
            raise ValueError(
                f"Theme '{theme.get('theme_name', i)}' missing required key: "
                f"matching_keywords"
            )


def _extract_etf_catalog(config: Dict) -> Dict[str, int]:
    """Extract ETF counts from config into a catalog dict.

    Each theme may have an `etf_count` field. Missing etf_count defaults to 0.

    Returns:
        {theme_name: etf_count}
    """
    catalog = {}
    for theme in config.get("cross_sector", []):
        name = theme.get("theme_name", "")
        catalog[name] = theme.get("etf_count", 0)
    return catalog


def _strip_etf_count(config: Dict) -> Dict:
    """Return a copy of config with etf_count removed from each theme.

    The etf_count is only used for ETF catalog extraction and should not
    be passed to classify_themes().
    """
    result = copy.deepcopy(config)
    for theme in result.get("cross_sector", []):
        theme.pop("etf_count", None)
    return result


def _get_bundled_yaml_path() -> str:
    """Return the absolute path to the bundled themes.yaml."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes.yaml")
