"""Make the skill's scripts/ importable and keep tests offline/fast."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Neutralize the FMP rate-limit sleep so tests run instantly."""

    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)
