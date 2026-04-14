"""Helpers for safe file storage path handling."""

from __future__ import annotations

import re
from pathlib import Path

from src.config.settings import settings
from src.utils.errors import BadRequestError, NotFoundError


_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_LEGACY_UPLOADS_PREFIX = "uploads/"


def get_storage_root() -> Path:
    return Path(settings.FILE_STORAGE_PATH).resolve()


def ensure_storage_containment(candidate: Path) -> Path:
    storage_root = get_storage_root()
    resolved = candidate.resolve()

    try:
        resolved.relative_to(storage_root)
    except ValueError as exc:
        raise NotFoundError("File path escapes configured storage root") from exc

    return resolved


def resolve_stored_file_path(stored_path: str) -> Path:
    normalized = (stored_path or "").strip().replace("\\", "/")
    if normalized.startswith(_LEGACY_UPLOADS_PREFIX):
        normalized = normalized[len(_LEGACY_UPLOADS_PREFIX):]

    if not normalized:
        raise NotFoundError("Stored file path is empty")

    return ensure_storage_containment(get_storage_root() / Path(normalized))


def sanitize_uploaded_filename(filename: str) -> str:
    raw_name = (filename or "").strip().replace("\\", "/").split("/")[-1]
    if raw_name in {"", ".", ".."}:
        raise BadRequestError("Filename is invalid")

    sanitized = _SAFE_FILENAME_PATTERN.sub("_", raw_name).strip("._")
    if not sanitized:
        raise BadRequestError("Filename is invalid after sanitization")

    return sanitized[:120]
