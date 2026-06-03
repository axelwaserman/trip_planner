"""OpenAI provider — wraps :class:`langchain_openai.ChatOpenAI`.

Implements :class:`app.llm.base.LLMProvider` via duck typing. Replaces the
Phase 4.2 :func:`app.services.provider_probe._probe_cloud` env-var check that
had no LangChain integration; with this module, ``"openai"`` + a real API key
yields a working chat session whose ``astream`` traffic actually reaches
``api.openai.com``.

Design notes:

- **D-13 — key presence only by default.** :meth:`validate_config` performs a
  purely local truthy check on ``self._api_key``; it never makes an outbound
  HTTP call. Rationale: a freshly pasted key on ``/settings/providers`` should
  NOT trigger an OpenAI billing event on every session create.
- **D-04 — curated cloud model list.** :meth:`list_models` returns a hardcoded
  five-element allow-list matching ``Settings.get_available_providers()``.
  Cloud providers do not perform live ``/v1/models`` discovery in Phase 4.5.
- **D-08 / D-09 — key precedence + non-logging.** The API key arrives via
  ``__init__`` from the factory (which applies the precedence rule:
  payload key > ``Settings.openai_api_key`` env-var fallback). This module
  never reads from ``os.environ`` directly and never logs ``self._api_key``;
  the value lives in process memory only and ``ChatOpenAI`` internally wraps
  it as a Pydantic ``SecretStr`` (verified in 04.5-RESEARCH.md).
- **Hint copy update vs 4.2.** The 4.2 ``_probe_cloud`` hint was
  ``"Set {env_var} on the backend and restart."``; the 4.5 wording mentions
  ``/settings/providers`` (the new UI affordance from D-19). Wire taxonomy is
  unchanged — only the human-facing string gains the UI hint.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.llm.base import LLMProvider  # noqa: F401  # imported for Wave 2 explicit subclassing
from app.llm.errors import ProbeError, ProbeErrorCode


class OpenAIProvider(LLMProvider):
    """Cloud LLM provider backed by ``langchain_openai.ChatOpenAI``.

    Phase 5 D-03: explicitly subclasses :class:`app.llm.base.LLMProvider`
    (the ABC). Constructed by :class:`app.llm.factory.LLMProviderFactory`;
    the factory injects the resolved API key (payload > env-var fallback) so
    this class never reads ``os.environ`` itself.
    """

    def __init__(self, model: str, api_key: str | None) -> None:
        """Store the model id and resolved API key in process memory.

        Args:
            model: OpenAI model identifier (e.g. ``"gpt-4o-mini"``).
            api_key: Resolved API key — ``None`` is permitted at construction
                time so :meth:`validate_config` can return a structured
                ``MISSING_API_KEY`` error rather than a SDK construction
                failure.
        """
        self._model = model
        self._api_key = api_key

    def get_provider_name(self) -> str:
        """Return the wire-level provider literal."""
        return "openai"

    async def validate_config(self) -> ProbeError | None:
        """Verify the API key is present (D-13: presence only, no HTTP).

        Returns:
            ``None`` when ``self._api_key`` is a truthy non-empty string.
            :class:`ProbeError` with ``error=MISSING_API_KEY`` when the key is
            ``None`` OR an empty/whitespace string. The truthy check covers
            both cases for ``str | None``; the
            :class:`app.models.SessionCreateRequest` validator already strips
            and normalises payload keys, but defense-in-depth here guards
            against an empty literal in a misconfigured ``.env`` file.
        """
        if not self._api_key:
            return ProbeError(
                error=ProbeErrorCode.MISSING_API_KEY,
                message="OpenAI needs an API key.",
                hint="Set OPENAI_API_KEY on the backend, or paste a key in /settings/providers.",
            )
        return None

    def bind_tools(self, tools: Sequence[BaseTool]) -> Any:
        """Construct a tool-bound runnable that streams from api.openai.com.

        Precondition: :meth:`validate_config` has already returned ``None``.
        ``ChatOpenAI`` accepts ``api_key=None`` at construction time but the
        first network call would raise — the factory orders ``validate_config``
        before ``bind_tools`` so this method is safe by contract.

        The ``api_key`` is wrapped in :class:`pydantic.SecretStr` before
        construction. ``ChatOpenAI`` types its ``api_key`` parameter as
        ``SecretStr | Callable[..., str] | None`` (mypy strict catches the
        plain-``str`` mismatch); using ``SecretStr`` explicitly aligns the
        provider type with the SDK contract while keeping the key out of
        ``repr`` / ``str`` (D-09).

        Wave 2 / Plan 05-03 replaces this method with ``build_agent`` returning
        a PydanticAI ``Agent``; the return-type annotation is ``Any`` here so
        the module imports cleanly mid-wave.
        """
        secret_key = SecretStr(self._api_key) if self._api_key is not None else None
        llm = ChatOpenAI(model=self._model, api_key=secret_key)
        # ChatOpenAI.bind_tools returns Runnable[LanguageModelInput, AIMessage];
        # the explicit ``Any`` return-type annotation here is the transitional
        # knob until Wave 2 swaps this method for ``build_agent``.
        return llm.bind_tools(list(tools))

    async def list_models(self) -> list[str]:
        """Return the curated cloud allow-list (D-04 — no live discovery).

        Mirrors ``Settings.get_available_providers()["openai"]["models"]`` so
        the ``/api/llm/providers`` route and this provider class agree on the
        offered model set. Updates land in both places together when OpenAI
        publishes a new model id.
        """
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-mini", "o3-mini"]

    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Any:
        """Wave 2 stub — Plan 05-03 replaces the body with the real PydanticAI implementation.

        Required to satisfy the :class:`app.llm.base.LLMProvider` ABC contract so
        ``OpenAIProvider`` is instantiable mid-wave. The Phase 4.5 ``bind_tools``
        path above continues to serve ``ChatService`` until Wave 3.

        Raises:
            NotImplementedError: Always, until Plan 05-03 lands the body.
        """
        raise NotImplementedError("OpenAIProvider.build_agent is implemented in Wave 2 / Plan 05-03")
