"""Configuration management for the application."""

import logging

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

    # Auth / JWT
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    auth_users: str = "admin:admin"

    # Default LLM Provider
    default_provider: str = "ollama"
    default_model: str = "qwen3:4b"

    # Ollama Configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"  # Fallback if not specified

    # OpenAI Configuration (optional)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Anthropic Configuration (optional)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Provider probe (RESEARCH.md Pitfall 3, Assumption A2). 1.5 s caps the worst
    # case for a misconfigured Ollama daemon; localhost hits are typically 50–200 ms.
    provider_probe_timeout_seconds: float = 1.5

    def model_post_init(self, __context: object) -> None:
        """Emit a warning when the JWT secret is still the insecure default."""
        if self.jwt_secret == _DEFAULT_JWT_SECRET:
            logger.warning(
                "JWT_SECRET is set to the default value '%s'. "
                "Set the JWT_SECRET environment variable to a strong random secret "
                "before running in production.",
                _DEFAULT_JWT_SECRET,
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
