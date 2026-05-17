"""Minimal API-key scrubber for stdlib logging — D-10.

Phase 8's structlog migration replaces this filter with a processor; do NOT
extend this module beyond the regex patterns. The patterns are contract
(per CLAUDE.md), not tunable thresholds, so they live as a module-level
constant rather than on Settings.

The filter sits between LogRecord creation and handler-formatter dispatch:
``record.msg`` is rewritten in place (when it is a ``str``); ``record.args``
is rebuilt as a fresh tuple/dict with each string entry scrubbed; non-string
entries pass through unchanged. ``filter()`` always returns ``True`` — we
redact, we never drop. Zero project-internal imports so this module can
install FIRST in the FastAPI lifespan.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

# Order matters: ``sk-ant-`` MUST match before bare ``sk-``, else the OpenAI
# regex would cannibalize Anthropic keys. Patterns are part of the contract
# (per CLAUDE.md) — module-level constant, not a tunable threshold.
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "sk-ant-[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-[REDACTED]"),
    (re.compile(r'("[A-Za-z0-9_]*api_key"\s*:\s*)"[^"]+"'), r'\1"[REDACTED]"'),
)

_UVICORN_LOGGER_NAMES: tuple[str, ...] = ("uvicorn.access", "uvicorn.error")


def _scrub(text: str) -> str:
    """Return ``text`` with each :data:`SECRET_PATTERNS` pair applied in order."""
    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _scrub_args(args: Any) -> Any:
    """Return a new args object with string entries scrubbed."""
    if isinstance(args, tuple | list):
        return tuple(_scrub(item) if isinstance(item, str) else item for item in args)
    if isinstance(args, Mapping):
        return {key: (_scrub(value) if isinstance(value, str) else value) for key, value in args.items()}
    return args


class ApiKeyScrubber(logging.Filter):
    """Redact API-key-shaped substrings from a :class:`logging.LogRecord`.

    Mutates ``record.msg`` and ``record.args`` BEFORE the handler formats
    the record. Always returns ``True`` — never drops a record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args is not None:
            record.args = _scrub_args(record.args)
        return True


def install_log_scrubber() -> ApiKeyScrubber:
    """Attach a fresh :class:`ApiKeyScrubber` to root + uvicorn loggers.

    Idempotent at the per-handler / per-logger level. Returns the scrubber
    so the caller can pass it to :func:`uninstall_log_scrubber`.
    """
    scrubber = ApiKeyScrubber()
    for handler in logging.getLogger().handlers:
        if scrubber not in handler.filters:
            handler.addFilter(scrubber)
    for name in _UVICORN_LOGGER_NAMES:
        uvicorn_logger = logging.getLogger(name)
        if scrubber not in uvicorn_logger.filters:
            uvicorn_logger.addFilter(scrubber)
    return scrubber


def uninstall_log_scrubber(scrubber: ApiKeyScrubber) -> None:
    """Best-effort removal of ``scrubber`` from root + uvicorn loggers."""
    for handler in logging.getLogger().handlers:
        try:
            handler.removeFilter(scrubber)
        except ValueError:
            pass
    for name in _UVICORN_LOGGER_NAMES:
        try:
            logging.getLogger(name).removeFilter(scrubber)
        except ValueError:
            pass
