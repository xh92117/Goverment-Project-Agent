"""Sandbox tool limit helpers."""

from __future__ import annotations

import os

# Maximum bytes accepted in a single non-append write_file call (issue #3189).
WRITE_FILE_CONTENT_MAX_BYTES = 80 * 1024
WRITE_FILE_MAX_BYTES_ENV = "AGENT_BASE_WRITE_FILE_MAX_BYTES"
LEGACY_WRITE_FILE_MAX_BYTES_ENV = "DEERFLOW_WRITE_FILE_MAX_BYTES"


def effective_write_file_max_bytes() -> int:
    """Return the active size cap for non-append write_file calls."""
    raw = os.environ.get(WRITE_FILE_MAX_BYTES_ENV)
    if raw is None:
        raw = os.environ.get(LEGACY_WRITE_FILE_MAX_BYTES_ENV)
    if raw is None:
        return WRITE_FILE_CONTENT_MAX_BYTES
    try:
        return int(raw)
    except ValueError:
        return WRITE_FILE_CONTENT_MAX_BYTES
