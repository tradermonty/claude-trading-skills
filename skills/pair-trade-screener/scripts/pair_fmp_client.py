"""Load this bundle's generated client without colliding with other skills."""

import importlib.util
import sys
from pathlib import Path

_MODULE = "_pair_trade_screener_generated_fmp"
_path = Path(__file__).resolve().parent / "fmp_client.py"
_shared = sys.modules.get(_MODULE)
if _shared is None:
    _spec = importlib.util.spec_from_file_location(_MODULE, _path)
    _shared = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE] = _shared
    try:
        _spec.loader.exec_module(_shared)
    except BaseException:
        sys.modules.pop(_MODULE, None)
        raise

FMPClient = _shared.FMPClient
