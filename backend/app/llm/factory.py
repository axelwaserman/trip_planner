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

Phase 4.5 Plan 02 ships the **skeleton only** — ``build`` raises
``NotImplementedError``. Plans 03/04/04b/05 land the four concrete providers
(``OllamaProvider``, ``LMStudioProvider``, ``OpenAIProvider``,
``AnthropicProvider``) in Wave 2. Plan 06 fills in the ``match`` body in
``build`` once the four ``app.llm.providers.*`` modules exist. The signature
is locked NOW so per-provider tests in Wave 2 can write assertions against
this exact shape.
"""

from dataclasses import dataclass

from app.config import Settings
from app.llm.protocol import LLMProvider


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
        """Build the per-session provider; signature locked in Plan 02, body in Plan 06.

        Plan 06 will dispatch on ``config.provider`` via ``match`` against a
        fixed ``Literal`` set, returning the matching ``OllamaProvider`` /
        ``LMStudioProvider`` / ``OpenAIProvider`` / ``AnthropicProvider``
        instance (RESEARCH.md §"Pattern 2"). The signature is locked here so
        per-provider tests in Wave 2 (Plans 03/04/04b/05) can write assertions
        against this exact shape without re-importing.
        """
        raise NotImplementedError(
            "Plan 06 wires concrete providers; this is the Plan 02 skeleton."
        )
