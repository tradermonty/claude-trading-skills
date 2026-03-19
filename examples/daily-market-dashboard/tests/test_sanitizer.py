"""Tests for agent/sanitizer.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.sanitizer import sanitize


class TestSanitize(unittest.TestCase):
    def test_redacts_anthropic_api_key(self):
        text = "Key: sk-ant-abc123def456ghi789jkl012mno345"
        result = sanitize(text)
        assert "sk-ant-" not in result
        assert "[REDACTED_API_KEY]" in result

    def test_redacts_claude_internal_paths(self):
        text = "See .claude/projects/abc123/tool-results/foo.json"
        result = sanitize(text)
        assert "tool-results" not in result
        assert "[internal-path]" in result

    def test_strips_command_message_tags(self):
        text = "Hello <command-message>skill is running…</command-message> world"
        result = sanitize(text)
        assert "<command-message>" not in result
        assert "skill is running" not in result
        assert "Hello" in result
        assert "world" in result

    def test_strips_system_reminder_tags(self):
        text = "Before <system-reminder>internal info</system-reminder> after"
        result = sanitize(text)
        assert "<system-reminder>" not in result
        assert "internal info" not in result
        assert "Before" in result
        assert "after" in result

    def test_strips_multiline_command_message(self):
        text = "Start <command-message>line1\nline2\nline3</command-message> end"
        result = sanitize(text)
        assert "<command-message>" not in result
        assert "line1" not in result

    def test_preserves_normal_text(self):
        text = "The market is up 2.5% today with strong breadth."
        assert sanitize(text) == text

    def test_preserves_short_tokens(self):
        text = "Score: 78.5, Zone: Healthy"
        assert sanitize(text) == text

    def test_redacts_absolute_home_path(self):
        text = "File at /Users/testuser/Documents/report.md"
        result = sanitize(text)
        assert "/Users/testuser" not in result

    def test_redacts_absolute_tmp_path(self):
        text = "Temp: /tmp/dashboard_abc123/output.json"
        result = sanitize(text)
        assert "/tmp/dashboard" not in result


if __name__ == "__main__":
    unittest.main()
