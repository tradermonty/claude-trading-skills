"""Output sanitizer for agent responses.

Applies hard code-level redaction that cannot be bypassed by prompt
injection.  Every text chunk passes through ``sanitize()`` before
reaching the Streamlit UI.
"""

from __future__ import annotations

import os
import re

_HOME = os.path.expanduser("~")

# sk-ant-... pattern (Anthropic API keys)
_RE_ANTHROPIC_KEY = re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")

# Generic long tokens/secrets: 40+ hex or base64-ish chars
_RE_LONG_TOKEN = re.compile(r"(?<![A-Za-z0-9/])[A-Za-z0-9+/\-_]{40,}(?:={0,2})(?![A-Za-z0-9/])")

# Absolute paths: /Users/..., /home/..., /tmp/..., /var/..., /private/...
_RE_ABS_PATH = re.compile(
    r"(?:/Users|/home|/tmp|/var|/private|/opt|/etc)"
    r"(?:/[^\s`\"')\]}>,:;]+)+"
)

# .claude internal paths (tool-results, projects, etc.)
_RE_CLAUDE_INTERNAL = re.compile(r"\.claude/projects/[^\s`\"')\]}>,:;]+")

# SDK internal tags (skill loading, command messages, etc.)
_RE_COMMAND_MESSAGE = re.compile(r"<command-message>.*?</command-message>", re.DOTALL)
_RE_SYSTEM_TAGS = re.compile(
    r"<(?:system-reminder|task-notification)>.*?</(?:system-reminder|task-notification)>", re.DOTALL
)


def sanitize(text: str) -> str:
    """Redact secrets, system paths, and internal tags from agent output."""
    text = _RE_COMMAND_MESSAGE.sub("", text)
    text = _RE_SYSTEM_TAGS.sub("", text)
    text = _RE_ANTHROPIC_KEY.sub("[REDACTED_API_KEY]", text)
    text = _RE_CLAUDE_INTERNAL.sub("[internal-path]", text)
    text = _RE_LONG_TOKEN.sub("[REDACTED_TOKEN]", text)
    text = _RE_ABS_PATH.sub(_redact_abs_path, text)
    return text


def _redact_abs_path(match: re.Match[str]) -> str:
    """Replace absolute path with project-relative or redacted form."""
    path = match.group(0)
    project_root = os.getcwd()
    if path.startswith(project_root + "/"):
        return path[len(project_root) + 1 :]
    if path.startswith(_HOME):
        return "~" + path[len(_HOME) :]
    return "[redacted-path]"
