"""Prompt context composer for user message, attachments, and knowledge."""

from __future__ import annotations

from agent.attachments import StoredAttachment


class PromptContextBuilder:
    """Build a bounded prompt string with optional context sections."""

    def __init__(self, user_message: str, *, max_chars: int) -> None:
        self._user_message = user_message
        self._max_chars = max_chars
        self._sections: list[str] = []

    def add_knowledge_preamble(self, preamble: str) -> None:
        if preamble.strip():
            self._sections.append(preamble.strip())

    def add_attachments(self, attachments: list[StoredAttachment]) -> None:
        if not attachments:
            return
        lines = ["[ATTACHMENTS]"]
        lines.append(
            "Uploaded files are available in the project workspace. "
            "Read these files directly when needed."
        )
        lines.append("Use only the exact relative paths listed below.")
        for attachment in attachments:
            lines.append(f"- {attachment.relative_path} ({attachment.size_bytes} bytes)")
        lines.append("Do not use WebSearch/WebFetch for attachment contents.")
        self._sections.append("\n".join(lines))

    def build(self) -> str:
        user_section = f"[USER_MESSAGE]\n{self._user_message.strip()}"
        if self._max_chars <= len(user_section):
            return user_section[: self._max_chars]

        if not self._sections:
            return user_section

        # Reserve separator before [USER_MESSAGE] section.
        remaining = self._max_chars - len(user_section) - 2
        if remaining <= 0:
            return user_section

        context_sections: list[str] = []
        suffix = "...[context truncated]"
        separator_cost = 2  # "\n\n"

        for section in self._sections:
            if remaining <= 0:
                break

            candidate = section
            if len(candidate) > remaining:
                if remaining <= len(suffix):
                    candidate = suffix[:remaining]
                else:
                    candidate = f"{candidate[: remaining - len(suffix)]}{suffix}"

            context_sections.append(candidate)
            remaining -= len(candidate) + separator_cost

        if not context_sections:
            return user_section

        return "\n\n".join([*context_sections, user_section])
