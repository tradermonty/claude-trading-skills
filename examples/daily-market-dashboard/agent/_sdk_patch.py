"""Monkey-patch for claude-agent-sdk to handle unknown message types gracefully.

The SDK's parse_message() raises MessageParseError on any message type it
doesn't recognise (e.g. ``rate_limit_event`` added by the Anthropic API after
the SDK was released).  This module wraps the original function so that
unknown types are logged and returned as a lightweight SystemMessage instead
of crashing the stream.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED = False


def apply_sdk_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return

    try:
        from claude_agent_sdk._errors import MessageParseError
        from claude_agent_sdk._internal import client as _internal_client
        from claude_agent_sdk._internal import message_parser as _mp
        from claude_agent_sdk.types import SystemMessage

        _original_parse = _mp.parse_message

        def _safe_parse_message(data: dict[str, Any]) -> Any:
            try:
                return _original_parse(data)
            except MessageParseError:
                msg_type = data.get("type", "<missing>")
                logger.debug("Ignoring unrecognised SDK message type: %s", msg_type)
                return SystemMessage(subtype=msg_type, data=data)

        _mp.parse_message = _safe_parse_message
        _internal_client.parse_message = _safe_parse_message

        _PATCHED = True
        logger.debug("SDK message parser patched successfully")
    except Exception:
        logger.warning("Failed to patch SDK message parser", exc_info=True)
