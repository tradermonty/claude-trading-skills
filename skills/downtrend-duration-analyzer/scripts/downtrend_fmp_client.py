"""Own-file generated client loading and explicit HTTP session ownership."""

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

_MODULE = "_downtrend_duration_analyzer_generated_fmp"
_path = Path(__file__).resolve().with_name("fmp_client.py")
_shared = sys.modules.get(_MODULE)
if _shared is None or Path(_shared.__file__).resolve() != _path:
    _spec = importlib.util.spec_from_file_location(_MODULE, _path)
    _shared = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE] = _shared
    try:
        _spec.loader.exec_module(_shared)
    except BaseException:
        sys.modules.pop(_MODULE, None)
        raise

FMPClient = _shared.FMPClient


@contextmanager
def client_scope(api_key, client=None):
    """Close only clients we create; callers retain ownership of injected ones."""
    if client is not None:
        yield client
        return
    owned = FMPClient(api_key=api_key)
    try:
        yield owned
    finally:
        owned.session.close()
