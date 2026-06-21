"""Configuration management for the application."""

import logging

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEFAULT_JWT_SECRET = "changeme"
_DEFAULT_AUTH_USERS = "admin:admin"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # Auth / JWT
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    auth_users: str = "admin:admin"

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
    # H5: SecretStr prevents key material from appearing in logs, repr, and
    # pydantic model serialisation (e.g. settings.model_dump()). Call
    # .get_secret_value() only at the point where the raw string is needed
    # (factory.py before handing the key to the provider).
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"

    # Anthropic Configuration (optional)
    # H5: same SecretStr treatment as openai_api_key above.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"

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
        if self.auth_users == _DEFAULT_AUTH_USERS:
            logger.warning(
                "AUTH_USERS is set to the default 'admin:admin'. "
                "Set the AUTH_USERS environment variable before running in production.",
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
