"""Persistent event-loop bridge for Streamlit + Claude SDK."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncBridge:
    """Reusable event loop that survives Streamlit reruns."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()

    def run(self, coro: Coroutine[Any, Any, T], timeout: float = 300) -> T:
        """Run a coroutine on the persistent loop with timeout protection."""
        if self._loop.is_closed():
            raise RuntimeError("AsyncBridge loop is closed")
        asyncio.set_event_loop(self._loop)
        return self._loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))

    @property
    def is_alive(self) -> bool:
        return not self._loop.is_closed()

    def shutdown(self) -> None:
        """Cancel pending tasks and close the loop."""
        if self._loop.is_closed():
            return
        try:
            if not self._loop.is_running():
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            logger.exception("AsyncBridge shutdown failed")
        finally:
            if not self._loop.is_closed() and not self._loop.is_running():
                self._loop.close()
