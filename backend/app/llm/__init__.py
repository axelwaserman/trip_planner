"""LLM provider abstraction (Phase 4.5).

Houses the structural ``LLMProvider``/``BoundProvider`` Protocols, the wire-level
error taxonomy (relocated from ``app.services.provider_probe`` in Phase 4.5),
the per-session ``SessionLLMConfig`` DTO, the per-app ``LLMProviderFactory``,
and the minimal D-10 API-key log scrubber.
"""

from app.llm.log_scrubbing import (
    ApiKeyScrubber,
    SECRET_PATTERNS,
    install_log_scrubber,
    uninstall_log_scrubber,
)

__all__ = [
    "SECRET_PATTERNS",
    "ApiKeyScrubber",
    "install_log_scrubber",
    "uninstall_log_scrubber",
]
