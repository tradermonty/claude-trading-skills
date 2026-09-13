"""Minimal Claude Agent SDK client wrapper for chat streaming."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import StreamEvent, ToolResultBlock
from config.settings import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_PERMISSION_MODE,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    MCP_CONFIG_PATH,
    SDK_SANDBOX_ENABLED,
    SETTING_SOURCES,
    PermissionMode,
)

logger = logging.getLogger(__name__)


class StreamChunk(TypedDict):
    """Normalized stream payload consumed by the Streamlit UI."""

    type: Literal["text_delta", "text", "tool_use", "tool_result", "error", "done"]
    content: NotRequired[str]


class ClaudeChatAgent:
    """Stateful chat client for Streamlit sessions."""

    def __init__(
        self,
        project_root: Path,
        model: str | None = None,
        permission_mode: PermissionMode | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        self.project_root = project_root
        self.model = model or DEFAULT_MODEL
        self.permission_mode = permission_mode or DEFAULT_PERMISSION_MODE
        retries = DEFAULT_MAX_RETRIES if max_retries is None else max_retries
        self.max_retries = max(0, retries)
        self.retry_backoff_seconds = (
            DEFAULT_RETRY_BACKOFF_SECONDS
            if retry_backoff_seconds is None
            else retry_backoff_seconds
        )
        self._client: ClaudeSDKClient | None = None
        self._connected = False

    def _build_options(self) -> ClaudeAgentOptions:
        """Build SDK options from local configuration."""
        mcp_config: dict[str, Any] | str | Path = {}
        if MCP_CONFIG_PATH.exists():
            mcp_config = MCP_CONFIG_PATH

        return ClaudeAgentOptions(
            model=self.model,
            permission_mode=self.permission_mode,
            cwd=str(self.project_root),
            setting_sources=SETTING_SOURCES,
            include_partial_messages=True,
            mcp_servers=mcp_config,
            sandbox={"enabled": SDK_SANDBOX_ENABLED},
        )

    async def connect(self) -> None:
        """Initialize and connect the underlying SDK client."""
        if self._connected and self._client is not None:
            return

        options = self._build_options()
        self._client = ClaudeSDKClient(options)
        try:
            await self._client.connect()
        except Exception:
            self._client = None
            self._connected = False
            raise

        self._connected = True

    async def disconnect(self) -> None:
        """Tear down the SDK client and reset local state."""
        if self._client and self._connected:
            try:
                await self._client.disconnect()
            except Exception:
                logger.warning("Claude SDK disconnect failed", exc_info=True)
        self._client = None
        self._connected = False

    def _require_client(self) -> ClaudeSDKClient:
        """Return a connected client or raise a clear runtime error."""
        if self._client is None or not self._connected:
            raise RuntimeError("Claude SDK client is not connected")
        return self._client

    async def _stream_once(self, user_message: str) -> AsyncIterator[StreamChunk]:
        """Execute one query/stream cycle."""
        if not self._client or not self._connected:
            await self.connect()

        client = self._require_client()
        await client.query(user_message)
        emitted_delta = False
        last_tool_error_detail = ""

        async for message in client.receive_response():
            try:
                if isinstance(message, StreamEvent):
                    event = message.event
                    event_type = event.get("type", "")
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                emitted_delta = True
                                yield {"type": "text_delta", "content": text}
                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "unknown")
                            yield {"type": "tool_use", "content": tool_name}

                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text:
                            if not emitted_delta:
                                yield {"type": "text", "content": block.text}
                        elif isinstance(block, ToolUseBlock):
                            yield {"type": "tool_use", "content": block.name}

                elif isinstance(message, UserMessage):
                    if isinstance(message.content, list):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                is_err = block.is_error or False
                                detail = _extract_tool_result_detail(block.content)
                                if is_err and detail:
                                    last_tool_error_detail = detail
                                yield {
                                    "type": "tool_result",
                                    "content": (
                                        f"error: {detail}"
                                        if is_err and detail
                                        else ("error" if is_err else "success")
                                    ),
                                }

                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        error_detail = _build_result_error_detail(
                            message=message,
                            last_tool_error_detail=last_tool_error_detail,
                        )
                        yield {"type": "error", "content": error_detail}
                    else:
                        yield {"type": "done", "content": message.session_id}

                elif isinstance(message, (SystemMessage,)):
                    subtype = getattr(message, "subtype", "?")
                    logger.debug(
                        "Ignored system message: subtype=%s",
                        subtype,
                    )

                else:
                    logger.debug("Ignored unknown message class: %s", type(message).__name__)
            except Exception as exc:
                logger.warning("Skipping unhandled message: %s", exc)

    async def send_message_streaming(self, user_message: str) -> AsyncIterator[StreamChunk]:
        """Stream a response with bounded retry on transient SDK failures."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async for chunk in self._stream_once(user_message):
                    yield chunk
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Chat stream failed on attempt %s/%s: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                await self.disconnect()

                if attempt < self.max_retries:
                    backoff = self.retry_backoff_seconds * (attempt + 1)
                    if backoff > 0:
                        await asyncio.sleep(backoff)

        error_message = f"Request failed after {self.max_retries + 1} attempt(s)."
        if last_error is not None:
            error_message = f"{error_message} {last_error}"
        yield {"type": "error", "content": error_message}


def _extract_tool_result_detail(content: str | list[dict[str, Any]] | None) -> str:
    """Extract readable error detail from a tool_result content payload."""
    if isinstance(content, str):
        return " ".join(content.split()).strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(" ".join(text.split()))
                continue
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                parts.append(" ".join(value.split()))
        return " ".join(parts).strip()
    return ""


def _build_result_error_detail(
    *,
    message: ResultMessage,
    last_tool_error_detail: str,
) -> str:
    """Compose a non-empty error detail for UI consumption."""
    parts: list[str] = []
    if isinstance(message.result, str) and message.result.strip():
        parts.append(message.result.strip())
    if hasattr(message, "subtype") and isinstance(message.subtype, str) and message.subtype:
        parts.append(f"subtype={message.subtype}")
    if last_tool_error_detail:
        parts.append(f"tool={last_tool_error_detail}")
    return " | ".join(parts) if parts else "Unknown error"
