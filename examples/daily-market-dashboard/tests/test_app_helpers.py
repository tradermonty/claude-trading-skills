"""Tests for app.py pure helper functions.

Requires streamlit to be installed. Skipped automatically if unavailable.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import streamlit  # noqa: F401

    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


@unittest.skipUnless(_HAS_STREAMLIT, "streamlit not installed")
class TestConsumeRateLimit(unittest.TestCase):
    """Test the rate limiter."""

    def _consume(self, now, timestamps, limit=5, window=60.0):
        from app import _consume_rate_limit

        return _consume_rate_limit(now, timestamps, limit=limit, window_seconds=window)

    def test_first_request_allowed(self):
        updated, blocked, _ = self._consume(100.0, [])
        assert not blocked
        assert len(updated) == 1

    def test_under_limit_allowed(self):
        timestamps = [90.0, 91.0, 92.0]
        updated, blocked, _ = self._consume(100.0, timestamps, limit=5)
        assert not blocked
        assert len(updated) == 4

    def test_at_limit_blocked(self):
        timestamps = [95.0, 96.0, 97.0, 98.0, 99.0]
        updated, blocked, retry_after = self._consume(100.0, timestamps, limit=5)
        assert blocked
        assert retry_after > 0

    def test_old_timestamps_expire(self):
        timestamps = [10.0, 11.0, 12.0]
        updated, blocked, _ = self._consume(100.0, timestamps, limit=5)
        assert not blocked
        assert len(updated) == 1


@unittest.skipUnless(_HAS_STREAMLIT, "streamlit not installed")
class TestApplyStreamChunk(unittest.TestCase):
    def _apply(self, parts, chunk):
        from app import _apply_stream_chunk

        return _apply_stream_chunk(parts, chunk)

    def test_text_delta_appended(self):
        parts = []
        result = self._apply(parts, {"type": "text_delta", "content": "hello"})
        assert result is True
        assert parts == ["hello"]

    def test_error_appended(self):
        parts = []
        result = self._apply(parts, {"type": "error", "content": "oops"})
        assert result is True
        assert "Error: oops" in parts[0]

    def test_tool_use_ignored(self):
        parts = []
        result = self._apply(parts, {"type": "tool_use", "content": "Read"})
        assert result is False
        assert parts == []

    def test_empty_content_ignored(self):
        parts = []
        result = self._apply(parts, {"type": "text_delta", "content": ""})
        assert result is False


if __name__ == "__main__":
    unittest.main()
