"""Lazy, batch-scoped access to this standalone skill's generated transport."""

import importlib
import importlib.util
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_ACTIVE = ContextVar("postmortem_price_session", default=None)
_MODULE = "_signal_postmortem_generated_fmp"


def load_client_class():
    """Keep optional provider dependencies off help and manual-recording paths."""
    importlib.import_module("requests")  # generated module exits if this is missing
    path = Path(__file__).resolve().with_name("fmp_client.py")
    module = sys.modules.get(_MODULE)
    if module is None or Path(module.__file__).resolve() != path:
        spec = importlib.util.spec_from_file_location(_MODULE, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[_MODULE] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_MODULE, None)
            raise
    return module.FMPClient


class _PriceSession:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = None
        self.unavailable = False

    def fetch(self, ticker, start_date, end_date):
        if not self.api_key or self.unavailable:
            return None
        if self.client is None:
            try:
                self.client = load_client_class()(api_key=self.api_key)
            except (ImportError, ValueError):
                self.unavailable = True
                return None
        return self.client.fetch_postmortem_history(ticker, start_date, end_date)


@contextmanager
def price_data_session(api_key):
    """Retain rate-limit state across signals, then close and restore the scope."""
    scope = _PriceSession(api_key)
    token = _ACTIVE.set(scope)
    try:
        yield scope
    finally:
        _ACTIVE.reset(token)
        if scope.client is not None:
            scope.client.session.close()


def fetch_price_rows(ticker, start_date, end_date, api_key):
    scope = _ACTIVE.get()
    if scope is not None and scope.api_key == api_key:
        return scope.fetch(ticker, start_date, end_date)
    with price_data_session(api_key) as local:
        return local.fetch(ticker, start_date, end_date)
