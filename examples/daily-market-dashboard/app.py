"""Minimal Streamlit chat UI powered by Claude Agent SDK."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import streamlit as st
from agent.async_bridge import AsyncBridge
from agent.attachments import cleanup_all_uploads, persist_attachments
from agent.client import ClaudeChatAgent
from agent.context_builder import PromptContextBuilder
from agent.knowledge import (
    build_knowledge_preamble,
    list_knowledge_markdown_files,
    resolve_knowledge_dir,
    search_knowledge_markdown,
)
from agent.sanitizer import sanitize
from config.settings import (
    APP_ICON,
    APP_LOG_FORMAT,
    APP_LOG_LEVEL,
    APP_TITLE,
    ATTACHMENTS_ALLOWED_EXTENSIONS,
    ATTACHMENTS_ENABLED,
    ATTACHMENTS_MAX_FILE_BYTES,
    ATTACHMENTS_STORAGE_DIR,
    CONTEXT_MAX_CHARS,
    KNOWLEDGE_DIR,
    KNOWLEDGE_ENABLED,
    KNOWLEDGE_MAX_HITS,
    PROJECT_ROOT,
    REQUESTS_PER_MINUTE_LIMIT,
    UI_LOCALE,
    get_auth_compliance_warnings,
    get_auth_description,
    validate_runtime_environment,
)
from streamlit.elements.widgets.chat import ChatInputValue

logger = logging.getLogger(__name__)
_LOGGING_CONFIGURED = False
_UPLOADS_CLEANED_AT_STARTUP = False


_TOOL_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "Write": "Writing file",
        "Edit": "Editing file",
        "Read": "Reading file",
        "Bash": "Running command",
        "Grep": "Searching code",
        "Glob": "Finding files",
        "LS": "Listing directory",
        "WebFetch": "Fetching web content",
        "TodoRead": "Reading task list",
        "TodoWrite": "Updating task list",
    },
    "ja": {
        "Write": "ファイル書き込み",
        "Edit": "ファイル編集",
        "Read": "ファイル読み取り",
        "Bash": "コマンド実行",
        "Grep": "コード検索",
        "Glob": "ファイル探索",
        "LS": "ディレクトリ一覧",
        "WebFetch": "Web取得",
        "TodoRead": "タスク読込",
        "TodoWrite": "タスク更新",
    },
}

_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "sidebar_title": "Project Config",
        "sidebar_project": "Project: `{project}`",
        "sidebar_auth": "Auth: `{auth}`",
        "clear_chat": "Clear chat",
        "config_issue": "Configuration issue detected.",
        "prompt_placeholder": "Type your message...",
        "thinking": "Thinking...",
        "note": "Note",
        "running_tool": "Running {label}...",
        "rate_limit_exceeded": "Rate limit exceeded ({limit}/min). Try again in about {seconds}s.",
        "chat_error": (
            "Error: chat request failed. Check authentication and network settings. "
            "Details: {details}"
        ),
        "no_response": "(No response)",
        "attachments_selected": "Attached files:",
        "attachments_error": "Attachment setup error: {details}",
        "attachment_only_prompt": "Please analyze the attached files and summarize key points.",
        "knowledge_error": "Knowledge setup error: {details}",
        "dashboard_title": "Dashboard",
        "dashboard_regenerate": "Regenerate Dashboard",
        "dashboard_running": "Running 5 skills...",
        "dashboard_success": "Dashboard updated. Reload the page to see latest data.",
        "dashboard_failed": "Failed: {details}",
        "dashboard_empty": "No dashboard yet. Click **Regenerate Dashboard** in the sidebar to generate one.",
        "dashboard_lang_label": "Language",
        "tab_chat": "Chat",
    },
    "ja": {
        "sidebar_title": "プロジェクト設定",
        "sidebar_project": "プロジェクト: `{project}`",
        "sidebar_auth": "認証: `{auth}`",
        "clear_chat": "チャットをクリア",
        "config_issue": "設定エラーを検出しました。",
        "prompt_placeholder": "メッセージを入力...",
        "thinking": "考え中...",
        "note": "注意",
        "running_tool": "{label} を実行中...",
        "rate_limit_exceeded": (
            "送信上限（1分あたり{limit}件）を超えました。約{seconds}秒後に再試行してください。"
        ),
        "chat_error": (
            "エラー: チャットリクエストに失敗しました。認証とネットワーク設定を確認してください。"
            " 詳細: {details}"
        ),
        "no_response": "(応答なし)",
        "attachments_selected": "添付ファイル:",
        "attachments_error": "添付設定エラー: {details}",
        "attachment_only_prompt": "添付ファイルを解析して、要点を要約してください。",
        "knowledge_error": "Knowledge 設定エラー: {details}",
        "dashboard_title": "ダッシュボード",
        "dashboard_regenerate": "ダッシュボード再生成",
        "dashboard_running": "5スキルを実行中...",
        "dashboard_success": "ダッシュボードを更新しました。ページをリロードすると最新データが表示されます。",
        "dashboard_failed": "失敗: {details}",
        "dashboard_empty": "ダッシュボードがまだありません。サイドバーの **ダッシュボード再生成** をクリックして生成してください。",
        "dashboard_lang_label": "言語",
        "tab_chat": "チャット",
    },
}

_CUSTOM_CSS = """
<style>
[data-testid="stChatMessage"] h1 { font-size: 1.4rem !important; }
[data-testid="stChatMessage"] h2 { font-size: 1.2rem !important; }
[data-testid="stChatMessage"] h3 { font-size: 1.05rem !important; }
[data-testid="stChatMessage"] p { margin-bottom: 0.4em !important; }
.stMainBlockContainer { padding-top: 1.5rem !important; }
[data-testid="stStatusWidget"] { display: none !important; }
</style>
"""

_IME_FIX_JS = """
<script>
(function() {
    var VERSION = 4;
    var doc = window.parent.document;
    if (doc._imeFixCleanup) doc._imeFixCleanup();
    if (doc._imeFixVersion === VERSION) return;
    doc._imeFixVersion = VERSION;

    var composing = false;
    var compositionStartedAt = 0;
    var lastComposedAt = 0;
    var JUST_COMPOSED_WINDOW_MS = 320;
    var COMPOSITION_STALE_MS = 5000;

    function nowMs() {
        return (window.performance && window.performance.now)
            ? window.performance.now() : Date.now();
    }
    function isChatInput(e) {
        return e.target && e.target.closest &&
               e.target.closest('[data-testid="stChatInput"]');
    }
    function onCompositionStart(e) {
        if (!isChatInput(e)) return;
        composing = true;
        compositionStartedAt = nowMs();
    }
    function onCompositionEnd(e) {
        if (!isChatInput(e)) return;
        var text = (typeof e.data === 'string') ? e.data : '';
        if (text.length > 0) { lastComposedAt = nowMs(); }
        composing = false;
    }
    function onFocusout(e) {
        if (!isChatInput(e)) return;
        composing = false;
    }
    function onKeydown(e) {
        if (e.key !== 'Enter' || e.shiftKey || !isChatInput(e)) return;
        var now = nowMs();
        if (composing && (now - compositionStartedAt) > COMPOSITION_STALE_MS) {
            composing = false;
        }
        var keyCode = e.keyCode || e.which || 0;
        var imeProcessKey = keyCode === 229 || e.key === 'Process';
        var recentlyComposed = (now - lastComposedAt) < JUST_COMPOSED_WINDOW_MS;
        if (imeProcessKey || composing || recentlyComposed) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            if (recentlyComposed) { lastComposedAt = 0; }
        }
    }

    doc.addEventListener('compositionstart', onCompositionStart, true);
    doc.addEventListener('compositionend', onCompositionEnd, true);
    doc.addEventListener('focusout', onFocusout, true);
    doc.addEventListener('keydown', onKeydown, true);

    doc._imeFixCleanup = function() {
        doc.removeEventListener('compositionstart', onCompositionStart, true);
        doc.removeEventListener('compositionend', onCompositionEnd, true);
        doc.removeEventListener('focusout', onFocusout, true);
        doc.removeEventListener('keydown', onKeydown, true);
        composing = false;
        lastComposedAt = 0;
        delete doc._imeFixVersion;
    };
})();
</script>
"""


class _JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter for production-friendly logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    """Configure root logger once based on environment settings."""
    global _LOGGING_CONFIGURED
    root = logging.getLogger()
    if _LOGGING_CONFIGURED:
        return

    handler = logging.StreamHandler()
    if APP_LOG_FORMAT == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, APP_LOG_LEVEL, logging.INFO))
    _LOGGING_CONFIGURED = True


def _tool_status_label(tool_name: str) -> str:
    """Convert an SDK tool name to a user-friendly label."""
    short = tool_name.split("__")[-1] if "__" in tool_name else tool_name
    localized = _TOOL_LABELS.get(UI_LOCALE, _TOOL_LABELS["en"])
    return localized.get(short, short)


def _msg(key: str, **kwargs: Any) -> str:
    """Return a localized UI message."""
    localized = _TEXTS.get(UI_LOCALE, _TEXTS["en"])
    template = localized.get(key, _TEXTS["en"].get(key, key))
    return template.format(**kwargs)


def _apply_stream_chunk(final_text_parts: list[str], chunk: dict[str, str]) -> bool:
    """Append text/error chunks to the assistant response buffer."""
    ctype = chunk.get("type")
    content = chunk.get("content", "")
    if ctype in {"text_delta", "text"} and content:
        final_text_parts.append(content)
        return True
    if ctype == "error":
        final_text_parts.append(f"\n\nError: {content}")
        return True
    return False


def _initialize_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "bridge" not in st.session_state:
        st.session_state.bridge = AsyncBridge()
    if "agent" not in st.session_state:
        st.session_state.agent = ClaudeChatAgent(project_root=PROJECT_ROOT)
    if "attachment_session_id" not in st.session_state:
        st.session_state.attachment_session_id = uuid4().hex
    if "request_timestamps" not in st.session_state:
        st.session_state.request_timestamps = []


def _cleanup_uploads_on_startup_once() -> None:
    """Clean runtime upload artifacts once per process start."""
    global _UPLOADS_CLEANED_AT_STARTUP
    if _UPLOADS_CLEANED_AT_STARTUP or not ATTACHMENTS_ENABLED:
        return

    try:
        cleanup_all_uploads(
            project_root=PROJECT_ROOT,
            storage_dir=ATTACHMENTS_STORAGE_DIR,
        )
    except (ValueError, OSError):
        logger.exception("Startup upload cleanup failed")

    _UPLOADS_CLEANED_AT_STARTUP = True


async def _stream_response(
    agent: ClaudeChatAgent,
    prompt: str,
    status_placeholder: Any,
    response_placeholder: Any,
) -> str:
    """Fetch and progressively render a single assistant response."""
    final_text_parts: list[str] = []

    async for chunk in agent.send_message_streaming(prompt):
        ctype = chunk.get("type")
        content = chunk.get("content", "")
        safe_content = sanitize(content)

        if _apply_stream_chunk(final_text_parts, {"type": ctype or "", "content": safe_content}):
            status_placeholder.empty()
            response_placeholder.markdown("".join(final_text_parts) + " \u25cc")
        elif ctype == "tool_use":
            label = _tool_status_label(safe_content)
            status_placeholder.status(_msg("running_tool", label=label), state="running")
        elif ctype == "tool_result":
            status_placeholder.status(_msg("thinking"), state="running")

    if not final_text_parts:
        final_text_parts.append(_msg("no_response"))

    status_placeholder.empty()
    return "".join(final_text_parts)


def _inject_static_assets() -> None:
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
    st.components.v1.html(_IME_FIX_JS, height=0)


def _build_prompt_context(
    prompt: str,
    uploaded_files: list[Any],
    *,
    attachment_session_id: str,
) -> tuple[str, list[str], list[str]]:
    """Build final prompt with optional knowledge and attachment context."""
    warnings: list[str] = []
    attachment_names: list[str] = []

    builder = PromptContextBuilder(
        user_message=prompt,
        max_chars=CONTEXT_MAX_CHARS,
    )

    if KNOWLEDGE_ENABLED:
        try:
            knowledge_dir = resolve_knowledge_dir(PROJECT_ROOT, KNOWLEDGE_DIR)
            knowledge_files = list_knowledge_markdown_files(knowledge_dir, PROJECT_ROOT)
            knowledge_matches = search_knowledge_markdown(
                prompt,
                knowledge_dir=knowledge_dir,
                project_root=PROJECT_ROOT,
                max_hits=KNOWLEDGE_MAX_HITS,
            )
            builder.add_knowledge_preamble(
                build_knowledge_preamble(knowledge_files, knowledge_matches)
            )
        except ValueError as exc:
            warnings.append(_msg("knowledge_error", details=exc))

    if ATTACHMENTS_ENABLED and uploaded_files:
        try:
            result = persist_attachments(
                uploaded_files,
                project_root=PROJECT_ROOT,
                storage_dir=ATTACHMENTS_STORAGE_DIR,
                session_id=attachment_session_id,
                allowed_extensions=ATTACHMENTS_ALLOWED_EXTENSIONS,
                max_file_bytes=ATTACHMENTS_MAX_FILE_BYTES,
            )
            builder.add_attachments(result.attachments)
            warnings.extend(result.warnings)
            attachment_names = [attachment.filename for attachment in result.attachments]
        except ValueError as exc:
            warnings.append(_msg("attachments_error", details=exc))

    return builder.build(), warnings, attachment_names


def _consume_rate_limit(
    now_seconds: float,
    timestamps: list[float],
    *,
    limit: int,
    window_seconds: float = 60.0,
) -> tuple[list[float], bool, int]:
    """Return updated timestamps and whether this request should be blocked."""
    recent = [ts for ts in timestamps if now_seconds - ts < window_seconds]
    if len(recent) >= limit:
        retry_after = max(1, int(window_seconds - (now_seconds - recent[0])))
        return recent, True, retry_after
    recent.append(now_seconds)
    return recent, False, 0


def _find_latest_dashboard() -> str | None:
    """Return the content of the latest dashboard markdown, or None."""
    knowledge_dir = PROJECT_ROOT / "knowledge"
    if not knowledge_dir.exists():
        return None
    files = sorted(knowledge_dir.glob("daily_dashboard_*.md"), reverse=True)
    if not files:
        return None
    try:
        return files[0].read_text(encoding="utf-8")
    except OSError:
        return None


def _resolve_project_root() -> str:
    """Resolve the parent trading-skills repository root."""
    candidate = PROJECT_ROOT.parent.parent
    if (candidate / "skills").is_dir():
        return str(candidate)
    return str(PROJECT_ROOT)


def render_app() -> None:
    """Render the Streamlit chat app."""
    _configure_logging()
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")
    _inject_static_assets()
    _initialize_session_state()
    _cleanup_uploads_on_startup_once()

    with st.sidebar:
        st.subheader(_msg("sidebar_title"))
        st.caption(_msg("sidebar_project", project=PROJECT_ROOT.name))
        st.caption(_msg("sidebar_auth", auth=get_auth_description()))
        if st.button(_msg("clear_chat"), use_container_width=True):
            try:
                cleanup_all_uploads(
                    project_root=PROJECT_ROOT,
                    storage_dir=ATTACHMENTS_STORAGE_DIR,
                )
            except (ValueError, OSError):
                logger.exception("Attachment storage cleanup failed")
            st.session_state.messages = []
            st.session_state.attachment_session_id = uuid4().hex
            st.session_state.request_timestamps = []
            st.rerun()

        st.divider()
        st.subheader(_msg("dashboard_title"))
        dashboard_lang = st.radio(
            _msg("dashboard_lang_label"),
            options=["en", "ja"],
            format_func=lambda x: "English" if x == "en" else "日本語",
            index=0,
            horizontal=True,
        )
        if st.button(_msg("dashboard_regenerate"), use_container_width=True):
            with st.spinner(_msg("dashboard_running")):
                try:
                    result = subprocess.run(
                        [
                            "python3",
                            "generate_dashboard.py",
                            "--project-root",
                            _resolve_project_root(),
                            "--lang",
                            dashboard_lang,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        cwd=str(PROJECT_ROOT),
                    )
                except subprocess.TimeoutExpired:
                    st.error(_msg("dashboard_failed", details="Timeout after 300s"))
                    result = None
            if result is not None:
                if result.returncode == 0:
                    st.success(_msg("dashboard_success"))
                else:
                    detail = (result.stderr or result.stdout or "unknown error")[:200]
                    st.error(_msg("dashboard_failed", details=detail))

    for warning in get_auth_compliance_warnings():
        st.warning(warning)

    runtime_errors = validate_runtime_environment()
    if runtime_errors:
        st.error(_msg("config_issue"))
        for error in runtime_errors:
            st.caption(error)

    tab_dashboard, tab_chat = st.tabs(
        [
            _msg("dashboard_title"),
            _msg("tab_chat"),
        ]
    )

    with tab_dashboard:
        dashboard_content = _find_latest_dashboard()
        if dashboard_content:
            st.markdown(dashboard_content)
        else:
            st.info(_msg("dashboard_empty"))

    with tab_chat:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # chat_input must be outside tabs to stay pinned at the bottom
    submitted_input: str | ChatInputValue | None
    if ATTACHMENTS_ENABLED:
        submitted_input = st.chat_input(
            _msg("prompt_placeholder"),
            disabled=bool(runtime_errors),
            accept_file="multiple",
            file_type=list(ATTACHMENTS_ALLOWED_EXTENSIONS),
        )
    else:
        submitted_input = st.chat_input(
            _msg("prompt_placeholder"),
            disabled=bool(runtime_errors),
        )
    if submitted_input is None:
        return

    # Auto-switch to Chat tab when user submits from Dashboard tab
    st.components.v1.html(
        """<script>
        (function() {
            var tabs = window.parent.document.querySelectorAll('[data-baseweb="tab"]');
            if (tabs.length >= 2) { tabs[1].click(); }
        })();
        </script>""",
        height=0,
    )

    uploaded_files: list[Any] = []
    if isinstance(submitted_input, str):
        prompt = submitted_input
    else:
        prompt = submitted_input.text
        uploaded_files = list(submitted_input.files) if hasattr(submitted_input, "files") else []

    if not prompt and not uploaded_files:
        return
    if not prompt.strip() and uploaded_files:
        prompt = _msg("attachment_only_prompt")

    updated_timestamps, is_limited, retry_after = _consume_rate_limit(
        now_seconds=datetime.now(UTC).timestamp(),
        timestamps=st.session_state.request_timestamps,
        limit=REQUESTS_PER_MINUTE_LIMIT,
    )
    st.session_state.request_timestamps = updated_timestamps
    if is_limited:
        st.warning(
            _msg(
                "rate_limit_exceeded",
                limit=REQUESTS_PER_MINUTE_LIMIT,
                seconds=retry_after,
            )
        )
        return

    prompt_for_agent, context_warnings, attachment_names = _build_prompt_context(
        prompt,
        uploaded_files,
        attachment_session_id=st.session_state.attachment_session_id,
    )

    user_message_text = prompt
    if attachment_names:
        user_message_text = f"{prompt}\n\n{_msg('attachments_selected')}\n" + "\n".join(
            f"- {filename}" for filename in attachment_names
        )

    st.session_state.messages.append({"role": "user", "content": user_message_text})
    with tab_chat:
        with st.chat_message("user"):
            st.markdown(user_message_text)

        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            response_placeholder = st.empty()
            status_placeholder.status(_msg("thinking"), state="running")
            for warning in context_warnings:
                st.caption(f"{_msg('note')}: {warning}")

            try:
                response_text = st.session_state.bridge.run(
                    _stream_response(
                        agent=st.session_state.agent,
                        prompt=prompt_for_agent,
                        status_placeholder=status_placeholder,
                        response_placeholder=response_placeholder,
                    )
                )
            except Exception as exc:
                logger.exception("Chat request failed")
                response_text = _msg("chat_error", details=exc)
            finally:
                status_placeholder.empty()

            response_placeholder.markdown(response_text)

    st.session_state.messages.append({"role": "assistant", "content": response_text})


if __name__ == "__main__":
    render_app()
