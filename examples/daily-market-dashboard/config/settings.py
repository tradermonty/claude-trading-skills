"""Application settings for Daily Market Dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv


def _load_dotenv_if_enabled() -> None:
    flag = os.getenv("PYTHON_DOTENV_DISABLED", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return
    load_dotenv()


_load_dotenv_if_enabled()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG_PATH = PROJECT_ROOT / ".mcp.json"

APP_TITLE = "Daily Market Dashboard"
APP_ICON = "\U0001f4ca"

PermissionMode = Literal["default", "acceptEdits", "plan", "bypassPermissions"]
SettingSource = Literal["user", "project", "local"]
UiLocale = Literal["en", "ja"]
LogFormat = Literal["text", "json"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _parse_permission_mode(raw: str) -> PermissionMode:
    if raw in {"default", "acceptEdits", "plan", "bypassPermissions"}:
        return cast(PermissionMode, raw)
    return "default"


def _parse_setting_sources(raw: str) -> list[SettingSource]:
    parsed: list[SettingSource] = []
    for source in raw.split(","):
        normalized = source.strip()
        if normalized in {"user", "project", "local"}:
            parsed.append(cast(SettingSource, normalized))
    return parsed or ["project", "local"]


def _parse_ui_locale(raw: str) -> UiLocale:
    if raw in {"en", "ja"}:
        return cast(UiLocale, raw)
    return "en"


def _parse_log_format(raw: str) -> LogFormat:
    if raw in {"text", "json"}:
        return cast(LogFormat, raw)
    return "text"


def _parse_log_level(raw: str) -> LogLevel:
    if raw in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return cast(LogLevel, raw)
    return "INFO"


def _parse_bool(raw: str, *, default: bool = False) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_positive_int(raw: str, *, default: int, minimum: int = 1) -> int:
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return value if value >= minimum else default


def _parse_extensions(raw: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    parsed: list[str] = []
    for token in raw.split(","):
        ext = token.strip().lower().lstrip(".")
        if ext and ext not in parsed:
            parsed.append(ext)
    if not parsed:
        return default
    return tuple(parsed)


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
DEFAULT_PERMISSION_MODE: PermissionMode = _parse_permission_mode(
    os.getenv("CLAUDE_PERMISSION_MODE", "default").strip()
)
DEFAULT_MAX_RETRIES = int(os.getenv("CLAUDE_MAX_RETRIES", "2"))
DEFAULT_RETRY_BACKOFF_SECONDS = float(os.getenv("CLAUDE_RETRY_BACKOFF_SECONDS", "0.5"))
LEGACY_AUTH_MODE = os.getenv("CLAUDE_AUTH_MODE", "").strip().lower()

SETTING_SOURCES = _parse_setting_sources(os.getenv("CLAUDE_SETTING_SOURCES", "project,local"))
UI_LOCALE: UiLocale = _parse_ui_locale(os.getenv("APP_LOCALE", "en").strip().lower())
APP_LOG_FORMAT: LogFormat = _parse_log_format(os.getenv("APP_LOG_FORMAT", "text").strip().lower())
APP_LOG_LEVEL: LogLevel = _parse_log_level(os.getenv("APP_LOG_LEVEL", "INFO").strip().upper())
SDK_SANDBOX_ENABLED = _parse_bool(os.getenv("CLAUDE_SDK_SANDBOX_ENABLED", "0"), default=False)

ATTACHMENTS_ENABLED = _parse_bool(os.getenv("ATTACHMENTS_ENABLED", "1"), default=True)
ATTACHMENTS_MAX_FILE_MB = _parse_positive_int(
    os.getenv("ATTACHMENTS_MAX_FILE_MB", "5"),
    default=5,
)
ATTACHMENTS_MAX_FILE_BYTES = ATTACHMENTS_MAX_FILE_MB * 1024 * 1024
ATTACHMENTS_STORAGE_DIR = os.getenv("ATTACHMENTS_STORAGE_DIR", "uploads").strip() or "uploads"
ATTACHMENTS_ALLOWED_EXTENSIONS = _parse_extensions(
    os.getenv("ATTACHMENTS_ALLOWED_EXT", "txt,md,csv,json"),
    default=("txt", "md", "csv", "json"),
)

KNOWLEDGE_ENABLED = _parse_bool(os.getenv("KNOWLEDGE_ENABLED", "1"), default=True)
KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "knowledge").strip() or "knowledge"
KNOWLEDGE_MAX_HITS = _parse_positive_int(
    os.getenv("KNOWLEDGE_MAX_HITS", "8"),
    default=8,
)

CONTEXT_MAX_CHARS = _parse_positive_int(
    os.getenv("CONTEXT_MAX_CHARS", "12000"),
    default=12000,
    minimum=1000,
)
REQUESTS_PER_MINUTE_LIMIT = _parse_positive_int(
    os.getenv("REQUESTS_PER_MINUTE_LIMIT", "20"),
    default=20,
)


def validate_runtime_environment() -> list[str]:
    """Return user-facing configuration errors that block chat requests."""
    return []


def get_auth_compliance_warnings() -> list[str]:
    """Return warnings when legacy/unsupported auth settings are present."""
    return []


def get_auth_description() -> str:
    """Return a human-readable description of the active auth method."""
    if ANTHROPIC_API_KEY:
        return "API Key"
    return "Subscription"
