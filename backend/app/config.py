"""Configuration management for the application."""

import logging
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEFAULT_JWT_SECRET = "changeme"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # Auth / JWT.
    # Phase 6 / Plan 06-04 (D-07) deleted the env-backed user-list field
    # and its module constant; ``PostgresUserRepository`` is the sole impl
    # and dev/test bootstrap is via ``just db-seed`` (Plan 06-06).
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # CORS — comma-separated origins for CORSMiddleware. Override via CORS_ALLOWED_ORIGINS env var.
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_allowed_origins")
    @classmethod
    def _block_cors_wildcard_with_credentials(cls, v: list[str]) -> list[str]:
        if "*" in v:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not contain '*' when allow_credentials=True. "
                "List explicit origins instead (e.g. ['https://app.example.com'])."
            )
        return v

    # Default LLM Provider
    default_provider: str = "ollama"
    default_model: str = "qwen3:4b"

    # Ollama Configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"  # Fallback if not specified

    # LM Studio Configuration (D-28)
    # OpenAI-compatible local server. Default port 1234 with /v1 prefix; no API key in v1 (D-17).
    lmstudio_base_url: str = "http://localhost:1234/v1"

    # OpenAI Configuration (optional)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Anthropic Configuration (optional)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Duffel Configuration (Phase 7 — D-01).
    # ``duffel_api_token`` defaults to ``None`` so a fresh checkout boots
    # without a Duffel account (Pitfall 6); the lifespan auto-fallback in
    # Plan 07-03 swaps in ``MockFlightAPIClient`` when the token is absent.
    # ``SecretStr`` keeps the raw token out of ``repr()``/debug dumps as a
    # first-line defence; the ``ApiKeyScrubber`` regex (Pitfall 7) is the
    # second-line defence at the log-formatter boundary. ``duffel_env``'s
    # ``"mock"`` literal forces the mock client even when a token is present
    # (useful for tests that need real creds in env but a deterministic client).
    duffel_api_token: SecretStr | None = None
    duffel_env: Literal["test", "live", "mock"] = "test"

    # Database (Phase 6 — D-01, D-11). database_url drives create_async_engine
    # in app/db/session.py; pool knobs are tunables on Settings per CLAUDE.md
    # ("Tunable thresholds live on Settings, not as module-level constants").
    # seed_allow_non_local guards scripts/seed.py against non-localhost targets
    # (Plan 06-06 will enforce; the field lands here so its env override is wired now).
    database_url: str = "postgresql+psycopg://trip_planner:trip_planner@localhost:5432/trip_planner"
    db_pool_size: int = 5
    db_pool_overflow: int = 10
    seed_allow_non_local: bool = False

    # MessageStore guardrail (Plan 06-03 / 06-RESEARCH.md Pitfall 5).
    # Phase 6 has no image/file-input LLM in scope; serialized ModelMessage
    # payloads stay text-shaped and well under 1 MB. The cap defends against
    # accidental BinaryContent/FilePart bloat slipping past the LLM boundary
    # and turning a single row into a multi-MB JSONB blob (RESEARCH Pattern 3
    # caveat). PostgresMessageStore.append rejects any ``to_jsonable_python``
    # output exceeding this byte length before issuing the INSERT.
    message_max_payload_bytes: int = 1_000_000

    # Provider probe (RESEARCH.md Pitfall 3, Assumption A2). 1.5 s caps the worst
    # case for a misconfigured Ollama daemon; localhost hits are typically 50–200 ms.
    provider_probe_timeout_seconds: float = 1.5

    # Provider model discovery cache (D-05 + D-06). TTL gates how aggressively the
    # /api/providers/refresh button re-hits local daemons; 60s balances "user
    # pulled a new model and forgot to click Refresh" UX against thrashing localhost.
    provider_models_cache_ttl_seconds: int = 60

    # PydanticAI dispatch knob: model identifiers matching one of these prefixes
    # are routed through ``OpenAIResponsesModel`` (which exposes the o-series
    # reasoning surface) instead of the default ``OpenAIChatModel`` — D-14,
    # RESEARCH OQ-03. Wave 2 (Plan 05-03) wires this into ``OpenAIProvider``.
    # Override via ``OPENAI_O_SERIES_MODEL_PREFIXES`` (comma-separated) if
    # OpenAI adds a new o-series family.
    openai_o_series_model_prefixes: tuple[str, ...] = ("o1", "o3")

    def model_post_init(self, __context: object) -> None:
        """Emit warnings when insecure defaults are still in use."""
        if self.jwt_secret == _DEFAULT_JWT_SECRET:
            logger.warning(
                "JWT_SECRET is set to the default value '%s'. "
                "Set the JWT_SECRET environment variable to a strong random secret "
                "before running in production.",
                _DEFAULT_JWT_SECRET,
            )
        if self.cors_allowed_origins == ["http://localhost:5173"]:
            logger.warning(
                "CORS_ALLOWED_ORIGINS is set to the development default (['http://localhost:5173']). "
                "Set CORS_ALLOWED_ORIGINS to your production origin(s) before deploying.",
            )

    def get_available_providers(self) -> dict[str, dict[str, list[str] | bool]]:
        """Get available providers with their models and credential status.

        Returns:
            Dict mapping provider names to their config:
            {
                "ollama": {
                    "available": True,
                    "models": ["qwen3:4b", "qwen3:8b", ...]
                },
                "openai": {
                    "available": bool(self.openai_api_key),
                    "models": ["gpt-4o", "gpt-4o-mini", ...]
                },
                ...
            }
        """
        return {
            "ollama": {
                "available": True,  # Always available (local)
                "models": [
                    "qwen3:4b",
                    "qwen3:8b",
                    "mistral:7b",
                    "deepseek-r1:8b",
                ],
            },
            "lmstudio": {
                # Local OpenAI-compatible daemon. Model existence is owned by
                # LMStudioProvider.validate_config (route layer skips the
                # whitelist check for local providers per
                # _resolve_allowed_cloud_models). The empty curated list keeps
                # the route validator's defense-in-depth check satisfied
                # without forcing a frozen model set.
                "available": True,
                "models": [],
            },
            "openai": {
                "available": bool(self.openai_api_key),
                "models": [
                    "gpt-4o",
                    "gpt-4o-mini",
                    "gpt-4-turbo",
                    "o1-mini",
                    "o3-mini",
                ],
            },
            "anthropic": {
                "available": bool(self.anthropic_api_key),
                "models": [
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                    "claude-3-opus-20240229",
                ],
            },
        }


settings = Settings()
