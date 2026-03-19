"""Server-side attachment persistence for prompt context."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent.path_utils import is_within


class UploadedFileLike(Protocol):
    """Minimal interface needed from Streamlit UploadedFile."""

    name: str

    def read(self) -> bytes: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...


@dataclass
class StoredAttachment:
    """Metadata for an attachment persisted on the server."""

    filename: str
    relative_path: str
    size_bytes: int


@dataclass
class AttachmentPersistResult:
    """Successful attachments and non-fatal warnings."""

    attachments: list[StoredAttachment]
    warnings: list[str]


def persist_attachments(
    uploaded_files: list[UploadedFileLike],
    *,
    project_root: Path,
    storage_dir: str,
    session_id: str,
    allowed_extensions: tuple[str, ...],
    max_file_bytes: int,
) -> AttachmentPersistResult:
    """Persist uploaded files under uploads/session and return relative paths."""
    root = project_root.resolve()
    storage_root = resolve_storage_root(project_root=root, storage_dir=storage_dir)
    session_dir = storage_root / _sanitize_session_id(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    allowed = {ext.lower().lstrip(".") for ext in allowed_extensions}
    attachments: list[StoredAttachment] = []
    warnings: list[str] = []

    for uploaded in uploaded_files:
        original_name = Path(getattr(uploaded, "name", "attachment")).name
        safe_name = _sanitize_filename(original_name)
        ext = Path(safe_name).suffix.lower().lstrip(".")
        if ext not in allowed:
            warnings.append(f"Skipped `{original_name}`: unsupported extension.")
            continue

        payload = _read_bytes(uploaded)
        size_bytes = len(payload)
        if size_bytes > max_file_bytes:
            warnings.append(f"Skipped `{original_name}`: file size exceeds configured limit.")
            continue

        destination = _next_available_path(session_dir, safe_name)
        destination.write_bytes(payload)
        rel_path = str(destination.resolve().relative_to(root))

        attachments.append(
            StoredAttachment(
                filename=original_name,
                relative_path=rel_path,
                size_bytes=size_bytes,
            )
        )

    return AttachmentPersistResult(attachments=attachments, warnings=warnings)


def cleanup_all_uploads(*, project_root: Path, storage_dir: str) -> None:
    """Delete all runtime upload artifacts under the storage directory."""
    storage_root = resolve_storage_root(project_root=project_root, storage_dir=storage_dir)
    if not storage_root.exists():
        return

    for child in storage_root.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def resolve_storage_root(*, project_root: Path, storage_dir: str) -> Path:
    """Resolve upload storage path and enforce project-root confinement."""
    root = project_root.resolve()
    candidate = Path(storage_dir)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not is_within(resolved, root):
        raise ValueError("Attachment storage directory must be inside the project root.")
    return resolved


def _read_bytes(uploaded_file: UploadedFileLike) -> bytes:
    """Read bytes and rewind so reruns can re-read the same object safely."""
    payload = uploaded_file.read()
    try:
        uploaded_file.seek(0)
    except Exception:
        # Some file-like objects may not support rewinding.
        pass
    return payload


def _sanitize_filename(name: str) -> str:
    base = Path(name).name.strip()
    if not base:
        return "attachment.bin"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return safe or "attachment.bin"


def _sanitize_session_id(session_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]", "_", session_id.strip())
    return normalized or "session"


def _next_available_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 1
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
