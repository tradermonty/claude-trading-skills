"""Own-file generated client import and explicit HTTP session ownership.

Several skills ship a different ``fmp_client.py`` under the same bare module
name, so the sibling is imported statically while ``sys.path`` and
``sys.modules`` are scoped to this bundle, then registered under a unique name.
Any other skill's ``fmp_client`` module is left untouched.
"""

import sys
from contextlib import contextmanager
from pathlib import Path

_MODULE = "_downtrend_duration_analyzer_generated_fmp"
_DIR = str(Path(__file__).resolve().parent)
_foreign = sys.modules.pop("fmp_client", None)
sys.path.insert(0, _DIR)
try:
    from fmp_client import FMPClient
finally:
    sys.path.remove(_DIR)
    _loaded = sys.modules.pop("fmp_client", None)
    if _foreign is not None:
        sys.modules["fmp_client"] = _foreign
_loaded.__name__ = _MODULE
FMPClient.__module__ = _MODULE
sys.modules[_MODULE] = _loaded


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
