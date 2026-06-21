"""LLM provider factory — builds a per-session provider from session-scoped config.

Two pieces in this module:

- :class:`SessionLLMConfig`: a frozen :func:`~dataclasses.dataclass` carrying
  the per-session DTO (provider, model, base_url, api_key) — D-24. Frozen
  per ``~/.claude/rules/python/coding-style.md`` *"Prefer immutable data
  structures: ``@dataclass(frozen=True)``"*.
- :class:`LLMProviderFactory`: a per-app singleton constructed once in
  ``api/main.py::lifespan``. Its :meth:`build` method dispatches on
  ``config.provider`` to a concrete provider class.

Per RESEARCH.md §"Pattern 2: Factory Builds from Session-Scoped Config",
``build`` resolves the D-08 key precedence (payload value wins over
``Settings.{provider}_api_key`` env var) and the analogous ``base_url``
fallback for local providers.

Plan 06 fills in the ``match`` body in ``build`` with the three concrete
provider classes (``OllamaProvider``, ``OpenAIProvider``, ``AnthropicProvider``).
Plan 04b extends the match block with a fourth ``"lmstudio"`` case backed by
:class:`app.llm.providers.lmstudio.LMStudioProvider` — closing CONTEXT.md
decisions D-15, D-16, D-17, D-18, D-28.
"""

from dataclasses import dataclass

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.lmstudio import LMStudioProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider


@dataclass(frozen=True)
class SessionLLMConfig:
    """Per-session LLM configuration, from request payload + Settings fallbacks.

    Four fields per D-24 — the canonical session-create payload shape:

    - ``provider``: wire-level provider name (``"ollama"`` / ``"openai"`` /
      ``"anthropic"`` / etc.).
    - ``model``: per-provider model identifier (e.g. ``"qwen3:4b"``,
      ``"gpt-4o-mini"``, ``"claude-3-5-sonnet-20241022"``).
    - ``base_url``: optional override for local providers; ``None`` falls back
      to ``Settings.ollama_base_url`` / ``Settings.lmstudio_base_url``.
    - ``api_key``: optional cloud-provider key from the request payload;
      ``None`` falls back to ``Settings.{provider}_api_key`` (env var).

    Per D-09 the ``api_key`` lives only inside the in-memory ``SessionLLMConfig``
    instance — never logged in clear, never persisted.
    """

    provider: str
    model: str
    base_url: str | None
    api_key: str | None


class LLMProviderFactory:
    """Per-app factory; builds session-scoped providers.

    Instantiated once in ``api/main.py::lifespan`` and stashed on
    ``app.state.llm_factory``. :meth:`build` is called per session-create
    (D-08 precedence resolution lives there).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build(self, config: SessionLLMConfig) -> LLMProvider:
        """Build the per-session provider; dispatch on ``config.provider``.

        Resolves D-08 precedence inline: when the payload supplies a value for
        ``api_key`` or ``base_url`` it wins; otherwise the corresponding
        ``Settings`` field is used as fallback.

        Args:
            config: Session-scoped configuration DTO.

        Returns:
            A concrete provider instance structurally satisfying
            :class:`app.llm.base.LLMProvider`.

        Raises:
            ValueError: When ``config.provider`` is not one of the three
                supported provider names. ``routes.py`` 400s on unknown names
                before reaching the factory in normal flow; this branch is the
                defense-in-depth backstop (T-04.5-06-01).
        """
        match config.provider:
            case "ollama":
                return OllamaProvider(
                    model=config.model,
                    base_url=config.base_url or self._settings.ollama_base_url,
                    probe_timeout_seconds=self._settings.provider_probe_timeout_seconds,
                )
            case "openai":
                # H5: openai_api_key is SecretStr | None — call get_secret_value()
                # to unwrap to str before passing to the provider.
                settings_key = (
                    self._settings.openai_api_key.get_secret_value()
                    if self._settings.openai_api_key is not None
                    else None
                )
                return OpenAIProvider(
                    model=config.model,
                    api_key=config.api_key or settings_key,
                    o_series_prefixes=self._settings.openai_o_series_model_prefixes,
                )
            case "anthropic":
                # H5: anthropic_api_key is SecretStr | None — unwrap to str.
                settings_key = (
                    self._settings.anthropic_api_key.get_secret_value()
                    if self._settings.anthropic_api_key is not None
                    else None
                )
                return AnthropicProvider(
                    model=config.model,
                    api_key=config.api_key or settings_key,
                )
            case "lmstudio":
                return LMStudioProvider(
                    model=config.model,
                    base_url=config.base_url or self._settings.lmstudio_base_url,
                    probe_timeout_seconds=self._settings.provider_probe_timeout_seconds,
                )
            case _:
                raise ValueError(f"Unknown provider: {config.provider}")

    async def refresh_local_models(self) -> dict[str, list[str] | None]:
        """Re-discover all local providers in parallel (D-06).

        Per D-06, ``POST /api/providers/refresh`` re-runs ``OllamaProvider.list_models``
        and ``LMStudioProvider.list_models`` against the configured base URLs.
        Cloud providers are no-ops here; their curated lists live elsewhere.

        Returns a dict mapping each local provider name to its discovered models,
        or ``None`` when the daemon was unreachable. Per RESEARCH.md Pitfall 6,
        ``asyncio.gather(..., return_exceptions=True)`` ensures one slow daemon
        does not block the other.
        """
        import asyncio

        # Build local provider instances. ``model=""`` is intentional —
        # ``list_models`` does not consult ``self._model``. The probe_timeout
        # from Settings caps each call.
        ollama = OllamaProvider(
            model="",
            base_url=self._settings.ollama_base_url,
            probe_timeout_seconds=self._settings.provider_probe_timeout_seconds,
        )
        lmstudio = LMStudioProvider(
            model="",
            base_url=self._settings.lmstudio_base_url,
            probe_timeout_seconds=self._settings.provider_probe_timeout_seconds,
        )
        local_providers: list[tuple[str, OllamaProvider | LMStudioProvider]] = [
            ("ollama", ollama),
            ("lmstudio", lmstudio),
        ]

        results = await asyncio.gather(
            *(p.list_models() for _, p in local_providers),
            return_exceptions=True,
        )

        cache: dict[str, list[str] | None] = {}
        for (name, _), result in zip(local_providers, results, strict=True):
            if isinstance(result, BaseException):
                cache[name] = None
            else:
                cache[name] = list(result)
        return cache
