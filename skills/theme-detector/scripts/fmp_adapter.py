"""Lazy generated theme transport. Each operation owns its HTTP session."""

import importlib.util
import sys
from pathlib import Path


def _client_class():
    name = "_theme_detector_generated_fmp"
    path = Path(__file__).resolve().with_name("fmp_client.py")
    module = sys.modules.get(name)
    if module is None or getattr(module, "__file__", None) != str(path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return module.FMPClient


def fetch_fmp(kind, symbol, api_key, params=None, *, rate_limit_sec=0.3):
    """Fetch raw evidence safely; no ambient-key fallback or legacy endpoint.

    Caller pacing spans logical operations; generated pacing applies to retries.
    All diagnostics come from the generated target's static-detail policy.
    """
    if not isinstance(api_key, str) or not api_key.strip():
        return None
    client = None
    data = None
    try:
        client = _client_class()(api_key=api_key)
        client.RATE_LIMIT_DELAY = rate_limit_sec
        data = client.fetch_theme_data(kind, symbol, params)
    except (ImportError, ValueError):
        data = None
    finally:
        if client is not None:
            try:
                client.session.close()
            except Exception:
                data = None
    return data
