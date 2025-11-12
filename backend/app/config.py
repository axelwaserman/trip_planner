"""Configuration management for the application."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # Ollama LLM
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"  # Better reasoning with tool calling support


settings = Settings()
