"""LLM provider abstraction (Phase 4.5 → Phase 5).

Houses the ``LLMProvider`` ABC (Phase 5 D-01..D-03 — replaces the Phase 4.5
two-tier ``LLMProvider``/second-tier Protocol pair), the wire-level error
taxonomy (relocated from ``app.services.provider_probe`` in Phase 4.5), the
per-session ``SessionLLMConfig`` DTO, the per-app ``LLMProviderFactory``, and
the minimal D-10 API-key log scrubber.
"""

from app.llm.base import LLMProvider
from app.llm.log_scrubbing import (
    SECRET_PATTERNS,
    ApiKeyScrubber,
    install_log_scrubber,
    uninstall_log_scrubber,
)

__all__ = [
    "SECRET_PATTERNS",
    "ApiKeyScrubber",
    "LLMProvider",
    "install_log_scrubber",
    "uninstall_log_scrubber",
]
