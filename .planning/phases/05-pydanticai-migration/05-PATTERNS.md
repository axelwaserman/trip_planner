---
phase: 5
slug: pydanticai-migration
created: 2026-06-03
---

# Phase 5 — Pattern Map

> Existing-codebase analogs for every file the planner will touch in Phase 5
> (PydanticAI migration). Excerpts are tight by design — they convey shape, not
> implementation. The planner uses these to keep the rewrite faithful to the
> repo's conventions (ABC over Protocol, frozen dataclasses for DTOs,
> StrEnum for cross-module taxonomies, tunables on `Settings`, `pyreqwest`
> deferred to Phase 7 — `httpx` survives in `validate_config` / `list_models`).

---

## Index

| Target file | Role | Analog | Match | Delta summary |
|---|---|---|---|---|
| `backend/app/llm/base.py` (renamed from `protocol.py`) | LLMProvider ABC | `backend/app/auth/repository.py:35-55` (`UserRepository(ABC)`) | exact (ABC + same scope: per-app interface with FastAPI DI swap) | `Protocol` → `ABC`; `bind_tools→BoundProvider` → `build_agent→Agent[Deps,str]`; `BoundProvider` retires |
| `backend/app/llm/factory.py` | factory + DTO | itself (Phase 4.5; in-place edit) | exact | Return type annotation `LLMProvider` (ABC, not Protocol); `match` body unchanged otherwise |
| `backend/app/llm/providers/ollama.py` | concrete provider (local) | itself (in-place rewrite) | exact (same role, new SDK) | `bind_tools(tools)→BoundProvider` → `build_agent(tools, deps_type)→Agent[Any,str]`; drop `ChatOllama`/`reasoning=`/`_model_supports_reasoning`; `OpenAIChatModel + OllamaProvider` instead |
| `backend/app/llm/providers/openai.py` | concrete provider (cloud) | itself (in-place rewrite) | exact | Drop `ChatOpenAI`/`SecretStr`; add `OpenAIChatModel`/`OpenAIResponsesModel` dispatch (D-14); `_O_SERIES_PREFIXES` lives on `Settings` |
| `backend/app/llm/providers/anthropic.py` | concrete provider (cloud) | itself (in-place rewrite) | exact | Drop `ChatAnthropic`/`SecretStr`; add `AnthropicModel + AnthropicProvider`; preserve `assert self._api_key is not None` defense-in-depth (Pitfall 4) |
| `backend/app/llm/providers/lmstudio.py` | concrete provider (local) | itself (in-place rewrite) | exact | Drop `ChatOpenAI`/`SecretStr("lm-studio")` sentinel; `OpenAIChatModel + OpenAIProvider(base_url=...)` (PydanticAI auto-fills placeholder) |
| `backend/app/chat/deps.py` | `ChatDeps` frozen dataclass | `backend/app/llm/factory.py:35-58` (`SessionLLMConfig`) | role-match (frozen DTO pattern) | New file; same `@dataclass(frozen=True)` shape; carries `flight_client` + `session_id` + `user_id` |
| `backend/app/chat/store.py` | `ConversationStore(ABC)` + `InMemoryConversationStore` | `backend/app/auth/repository.py:35-93` (`UserRepository`/`EnvUserRepository`) | exact (ABC + first impl, same Phase-N→Phase-N+1 swap pattern) | New file; methods are async; storage is `dict[str, list[ModelMessage]]` |
| `backend/app/chat/models.py` | StreamEvent ABC + 5 subclasses + DTOs | itself (in-place edit) | exact | Replace `Annotated[..., Field(discriminator="type")]` alias with `class StreamEvent(BaseModel, ABC)`; the 5 concrete event classes explicitly subclass it |
| `backend/app/chat/service.py` | rewritten ChatService | itself (full rewrite, kept for diff context) | exact | LangChain → PydanticAI: `_bound_providers`→`_agents`, `_histories`→`_conversation_store`, `astream`/`additional_kwargs["reasoning_content"]` → `agent.iter()` + `ModelRequestNode.stream` / `CallToolsNode.stream`; tool DI via `RunContext[ChatDeps]` |
| `backend/app/chat/__init__.py` | package re-exports | itself (in-place edit) | exact | Add `ConversationStore`, `InMemoryConversationStore`, `ChatDeps` to `__all__` |
| `backend/app/tools/flight_search.py` | tool function | itself (in-place edit) | exact | Drop `@tool` decorator from `langchain_core.tools`; gain `ctx: RunContext[ChatDeps]` first param; replace `getattr(search_flights, "_flight_client", None)` with `ctx.deps.flight_client`; remove module-level back-door |
| `backend/app/api/main.py` | lifespan wiring | itself (in-place edit) | exact | Construct `InMemoryConversationStore`, pass to `ChatService(...)`; remove `search_flights._flight_client = flight_client` line |
| `backend/app/api/routes/routes.py` | SSE serialisation | itself (in-place edit) | exact (no logic change) | `event.model_dump_json()` continues to work — `StreamEvent` ABC subclasses keep their `Literal[...]` discriminators; route is unchanged |
| `backend/app/config.py` | `Settings` knobs | itself (in-place edit) | exact | Add `openai_o_series_model_prefixes: tuple[str, ...]`; drop `ollama_reasoning_model_prefixes` (PydanticAI handles `<think>` natively per OQ-04) |
| `backend/app/llm/__init__.py` | package re-exports | itself (in-place edit) | exact | Drop `BoundProvider` references; `LLMProvider` (ABC) re-export if needed |
| `backend/pyproject.toml` | dependency manifest | itself (in-place edit) | exact | Remove `langchain*`, `langgraph`; add `pydantic-ai>=0.8.1`; bump `pydantic>=2.12` |
| `backend/tests/fixtures/llm.py` | mock LLM fixture | itself (full rewrite) | exact | Drop `MockLLM(BaseChatModel)` / `_MockBoundProvider`; new `_MockLLMProvider(LLMProvider)` builds `Agent` with `FunctionModel(stream_function=...)`; preserve `Content`/`Thinking`/`ToolCall` chunk types and the three `MockLLMStream` scenarios |
| `backend/tests/unit/llm/test_protocol_abc.py` (renamed from `test_protocol_conformance.py`) | conformance test | `backend/tests/unit/llm/test_protocol_conformance.py:35-65` | exact (same role; renamed file) | `isinstance(p, LLMProvider)` becomes `isinstance(p, LLMProvider)` against an ABC, plus `assert not hasattr(app.llm, "BoundProvider")` |
| `backend/tests/unit/llm/test_build_agent.py` | provider→Agent unit test | `backend/tests/unit/llm/test_ollama_provider.py:107-134` (`test_model_supports_reasoning_matches_configured_prefixes`) | role-match (per-provider unit test) | Asserts `provider.build_agent(tools, deps_type)` returns `pydantic_ai.Agent` |
| `backend/tests/unit/llm/providers/test_openai_dispatch.py` | dispatch unit test | `backend/tests/unit/llm/test_factory.py:27-55` (factory dispatch test) | role-match | Asserts `o3-mini`/`o1-mini` → `OpenAIResponsesModel`; `gpt-4o-mini` → `OpenAIChatModel` |
| `backend/tests/unit/llm/providers/test_ollama_thinking.py` | qwen3 thinking surface | none (genuinely new) | none | Drives `FunctionModel`-style scenario, asserts `<think>` chunks parse into `ThinkingPart` via PydanticAI ModelProfile |
| `backend/tests/unit/chat/test_deps.py` | ChatDeps shape | `backend/tests/unit/llm/test_factory.py:27-55` (DTO construction) | role-match | Asserts `@dataclass(frozen=True)` and field shape |
| `backend/tests/unit/chat/test_conversation_store.py` | ConversationStore round-trip | `backend/tests/unit/test_user_repository.py` (UserRepository unit) | role-match | `InMemoryConversationStore` `append`/`load`/`delete`/`list_for_user` |
| `backend/tests/unit/chat/test_stream_event_abc.py` | StreamEvent ABC golden test | `backend/tests/unit/test_stream_events.py:138-159` (TypeAdapter discriminator test) | exact (same file's predecessor) | Adds `isinstance(c, StreamEvent)` ABC assertions on top of existing discriminator round-trip |
| `backend/tests/unit/chat/test_stream_event_wire_compat.py` | wire-byte compat | `backend/tests/unit/test_stream_events.py:51-73` (model_dump_json shape) | exact | Golden file: byte-equivalent `model_dump_json()` for all five subclasses |
| `backend/tests/unit/chat/test_stream_event_extraction.py` | agent.iter() event mapping | `backend/tests/unit/test_chat_stream.py:18-36` (stream events from MockLLM) | role-match | Drives `agent.iter()` with `FunctionModel`, asserts the 4 mappings (Content, Thinking, ToolCall, ToolResult) |
| `backend/tests/unit/chat/test_stream_error_event.py` | exception → ErrorEvent | `backend/tests/unit/test_chat_stream.py:38-60` (APIError → ErrorEvent) | exact | Same shape; PydanticAI substrate; `_scrub` invariant preserved |
| `backend/tests/unit/tools/test_flight_search.py` | RunContext injection | `backend/tests/unit/test_tool_json_normalization.py` (tool-level unit test) | role-match | New: drives `search_flights(ctx, ...)` with a stub `RunContext[ChatDeps]` |
| `backend/tests/unit/tools/test_flight_search_no_backdoor.py` | back-door removal regression | none (genuinely new — anti-pattern lock) | none | `assert not hasattr(search_flights, "_flight_client")`; signature first-param assertion |
| `backend/tests/unit/test_dependencies.py` | dep-manifest assertions | none (genuinely new) | none | Reads `pyproject.toml`; asserts no `langchain*`/`langgraph`; `pydantic-ai` present |
| `backend/tests/unit/test_no_langchain_imports.py` | import-scan assertion | none (genuinely new) | none | Walks `app/` AST; asserts no `langchain*` import survives |
| `backend/tests/integration/test_chat_stream.py` | three locked scenarios | `backend/tests/integration/test_chat_service_flow.py:25-83` | exact (same test file shape) | Replace `MockLLM`-based fixture with `FunctionModel`-backed; assertions unchanged (`tool_call`, `tool_result`, `content` event types) |
| `backend/tests/integration/test_chat_factory.py` | `make_chat_service_with_mock_llm` shape | `backend/tests/fixtures/llm.py:231-246` (factory itself) | role-match | Asserts factory signature unchanged after the rewrite |
| `backend/tests/integration/llm/test_{ollama,openai,anthropic}_thinking_live.py` | gated cloud acceptance | `backend/tests/integration/test_cloud_providers_real.py` | role-match | `pytest.mark.skipif(env_not_set, ...)` gating; thinking-event assertion |
| `.planning/adrs/ADR-001-langchain.md` | superseded ADR | `ARCHITECTURE.md:561-583` (current ADR-001 prose) | exact (only file embodying ADR-001 today) | Status: Accepted → Superseded; supersession note links ADR-007 |
| `.planning/adrs/ADR-007-pydantic-ai.md` | locked ADR | `ARCHITECTURE.md:585-607` (ADR-002 status-flip example) | role-match (ADR template) | Status: Proposed → Locked; rationale references RESEARCH.md OQ-01..OQ-05 + per-provider pattern |
| `ARCHITECTURE.md` | docs update | `ARCHITECTURE.md:174-251` (current LLMProvider Factory Pattern), `ARCHITECTURE.md:255-305` (StreamEvent Pattern), `ARCHITECTURE.md:783-795` (Known Tech Debt) | exact (in-place edit) | Rewrite Factory section (Protocol→ABC + `build_agent`); rewrite StreamEvent section (alias→ABC); delete "Known Tech Debt" entry; add Anti-Pattern entries closure note for `_flight_client` back-door |
| `.planning/PROJECT.md` | status table | itself (in-place edit) | exact | Mark ADR-001 Superseded; ADR-007 Locked; tick Phase 5 success criteria |

---

## Per-file mappings

### `backend/app/llm/base.py` — LLMProvider ABC

- **Role:** abstract interface for the per-session provider; consumed by `LLMProviderFactory.build()` and `ChatService.create_session`.
- **Analog (project convention):** `backend/app/auth/repository.py:35-55` (`UserRepository(ABC)` — repo's canonical ABC pattern; flagged in CLAUDE.md).
- **Excerpt — UserRepository ABC shape (the template to follow):**
  ```python
  # backend/app/auth/repository.py:35-55
  class UserRepository(ABC):
      """Abstract base class for user persistence backends.

      The auth routes depend on this ABC; concrete implementations
      (EnvUserRepository, future PostgresUserRepository) are injected via
      FastAPI's dependency override mechanism.
      """

      @abstractmethod
      def get_user(self, username: str) -> UserInDB:
          """Return UserInDB for *username*.

          Raises:
              UserNotFoundError: When *username* does not exist.
          """
          ...

      @abstractmethod
      def verify_password(self, plain: str, hashed: str) -> bool:
          """Return True if *plain* matches *hashed*."""
          ...
  ```
- **Analog being replaced:** `backend/app/llm/protocol.py:44-92` — both `BoundProvider(Protocol)` and `LLMProvider(Protocol)` retire. The ABC for Phase 5 collapses both into one (D-01).
- **Target shape (D-02 ABC surface):**
  ```python
  # backend/app/llm/base.py
  from abc import ABC, abstractmethod
  from collections.abc import Sequence
  from typing import Any
  from pydantic_ai import Agent
  from app.llm.errors import ProbeError

  class LLMProvider(ABC):
      @abstractmethod
      def get_provider_name(self) -> str: ...
      @abstractmethod
      async def validate_config(self) -> ProbeError | None: ...
      @abstractmethod
      async def list_models(self) -> list[str]: ...
      @abstractmethod
      def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]: ...
  ```
- **Delta:**
  - `Protocol` + `@runtime_checkable` → `ABC` + `@abstractmethod` decorators.
  - Concrete providers explicitly subclass `LLMProvider` (D-03), unlike Phase 4.5 duck typing.
  - `bind_tools(tools) -> BoundProvider` is replaced by `build_agent(tools, deps_type) -> Agent[Any, str]` because PydanticAI's `Agent` IS the tool-bound thing (D-01).
  - `BoundProvider` is deleted entirely — no second tier.
- **Project-rule callouts:**
  - CLAUDE.md "abstract interfaces use `ABC`, never `Protocol`" — D-03 closes the ARCHITECTURE.md "Known Tech Debt" entry (`ARCHITECTURE.md:783-795`).
  - The previous "two-tier shape" rationale (Phase 4.5 RESEARCH §"Pattern 1") was LangChain-specific (`bind_tools` returned `Runnable`, not `BaseChatModel`). Do **not** carry it forward as a `BoundProvider` ABC alongside the new one — pure rename + retype, no shim (CONTEXT.md anti-pattern: "Don't ship a `ProtocolProvider` adapter alongside the ABC").

---

### `backend/app/llm/factory.py` — `LLMProviderFactory.build()`

- **Role:** per-app factory; per-session provider construction.
- **Analog:** itself; only the return-type annotation changes.
- **Excerpt — current shape (lines 71-116) — preserved verbatim except for the import + return type:**
  ```python
  # backend/app/llm/factory.py:71-116
  def build(self, config: SessionLLMConfig) -> LLMProvider:
      match config.provider:
          case "ollama":
              return OllamaProvider(
                  model=config.model,
                  base_url=config.base_url or self._settings.ollama_base_url,
                  probe_timeout_seconds=self._settings.provider_probe_timeout_seconds,
                  reasoning_model_prefixes=self._settings.ollama_reasoning_model_prefixes,
              )
          case "openai":
              return OpenAIProvider(
                  model=config.model,
                  api_key=config.api_key or self._settings.openai_api_key,
              )
          ...
          case _:
              raise ValueError(f"Unknown provider: {config.provider}")
  ```
- **Delta:**
  - `from app.llm.protocol import LLMProvider` → `from app.llm.base import LLMProvider`.
  - `OllamaProvider(...)` constructor loses `reasoning_model_prefixes` parameter (D-12 / OQ-04 — PydanticAI handles `<think>` natively via `ModelProfile`).
  - `OpenAIProvider(...)` constructor gains an `o_series_prefixes` parameter (D-14 dispatch knob; sourced from `Settings.openai_o_series_model_prefixes`).
  - `match` branches and `ValueError` fallback unchanged.
- **Project-rule callouts:**
  - CLAUDE.md "tunable thresholds live on Settings, not as module-level constants" — the `_O_SERIES_PREFIXES` tuple is sourced from `Settings.openai_o_series_model_prefixes` and threaded through the factory's `OpenAIProvider(...)` call, mirroring how `reasoning_model_prefixes` was wired in Phase 4.5.

---

### `backend/app/llm/providers/ollama.py` — concrete provider

- **Role:** local Ollama provider; `validate_config` keeps `httpx` probe of `/api/tags`; `build_agent` constructs PydanticAI `Agent`.
- **Analog:** itself; full rewrite of `bind_tools` body.
- **Excerpt — current Phase 4.5 `bind_tools` (lines 137-161) being replaced:**
  ```python
  # backend/app/llm/providers/ollama.py:137-161
  def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider:
      llm = ChatOllama(
          model=self._model,
          base_url=self._base_url,
          reasoning=self._model_supports_reasoning(),
      )
      return llm.bind_tools(list(tools))  # type: ignore[return-value]
  ```
- **Excerpt — preserved `validate_config` + `list_models` (lines 88-135) — DO NOT TOUCH:**
  ```python
  # backend/app/llm/providers/ollama.py:88-114 (KEEP)
  async def validate_config(self) -> ProbeError | None:
      try:
          available = await self.list_models()
      except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
          return ProbeError(
              error=ProbeErrorCode.PROVIDER_UNREACHABLE,
              message=f"Can't reach Ollama at {self._base_url}.",
              hint="Run `ollama serve` and retry, or pick another provider.",
          )
      if self._model not in available:
          return ProbeError(
              error=ProbeErrorCode.MODEL_NOT_INSTALLED,
              message=f"Ollama is running but {self._model} isn't installed.",
              hint=f"Run `ollama pull {self._model}` or pick a different model.",
          )
      return None
  ```
- **Target shape — RESEARCH §Per-Provider Migration (Ollama):**
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.models.openai import OpenAIChatModel
  from pydantic_ai.providers.ollama import OllamaProvider as _PaiOllamaProvider

  class OllamaProvider(LLMProvider):  # subclass the ABC (D-03)
      def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
          model = OpenAIChatModel(
              self._model,
              provider=_PaiOllamaProvider(base_url=self._base_url),
          )
          return Agent(model, tools=list(tools), deps_type=deps_type)
  ```
- **Delta:**
  - Drop `from langchain_core.tools import BaseTool` and `from langchain_ollama import ChatOllama`.
  - Drop the Phase 4.5 docstring paragraphs about `reasoning=` gating, Pitfall 7 (reasoning protocol abstraction), and `_model_supports_reasoning` — PydanticAI's `OllamaProvider` inherits `thinking_tags=('<think>', '</think>')` from `qwen_model_profile` (RESEARCH OQ-04). The `_model_supports_reasoning` private method retires.
  - Constructor loses `reasoning_model_prefixes` parameter.
  - Subclass `LLMProvider` explicitly (`class OllamaProvider(LLMProvider):`).
- **Project-rule callouts:**
  - `httpx.AsyncClient(timeout=...)` in `list_models` stays — RESEARCH explicitly flags this as the exception to ADR-008 (`pyreqwest`), which is Phase 7 territory.

---

### `backend/app/llm/providers/openai.py` — concrete provider with o-series dispatch

- **Role:** cloud OpenAI provider; `validate_config` is presence-only (D-13 unchanged from Phase 4.5); `build_agent` dispatches on model prefix.
- **Analog:** itself; full rewrite of `bind_tools` body.
- **Excerpt — current Phase 4.5 `bind_tools` (lines 86-106) being replaced:**
  ```python
  # backend/app/llm/providers/openai.py:86-106
  def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider:
      secret_key = SecretStr(self._api_key) if self._api_key is not None else None
      llm = ChatOpenAI(model=self._model, api_key=secret_key)
      return llm.bind_tools(list(tools))  # type: ignore[return-value]
  ```
- **Target shape — RESEARCH §OpenAI Provider + OQ-03:**
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
  from pydantic_ai.providers.openai import OpenAIProvider as _PaiOpenAIProvider

  class OpenAIProvider(LLMProvider):
      def __init__(
          self,
          model: str,
          api_key: str | None,
          o_series_prefixes: tuple[str, ...] = ("o1", "o3"),  # from Settings
      ) -> None:
          self._model = model
          self._api_key = api_key
          self._o_series_prefixes = o_series_prefixes

      def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
          assert self._api_key is not None  # validate_config gated this
          provider = _PaiOpenAIProvider(api_key=self._api_key)
          if any(self._model.startswith(p) for p in self._o_series_prefixes):
              model = OpenAIResponsesModel(self._model, provider=provider)
          else:
              model = OpenAIChatModel(self._model, provider=provider)
          return Agent(model, tools=list(tools), deps_type=deps_type)
  ```
- **Delta:**
  - Drop `from langchain_openai import ChatOpenAI`, `from pydantic import SecretStr` (PydanticAI takes plain `str`).
  - Add `o_series_prefixes` constructor argument; default mirrors `Settings.openai_o_series_model_prefixes`.
  - `validate_config()` body and `list_models()` body are **unchanged**.
- **Project-rule callouts:**
  - CLAUDE.md "tunable thresholds live on Settings" — the o-series prefix tuple lives on `Settings`, not as a module constant.
  - The Phase 4.5 `assert self._api_key is not None` defense-in-depth pattern is preserved (Pitfall 4 in RESEARCH still applies to `AnthropicProvider`; for `OpenAIProvider` it's defense-in-depth even though PydanticAI tolerates `None`).

---

### `backend/app/llm/providers/anthropic.py` — concrete provider with extended thinking

- **Role:** cloud Anthropic provider; thinking surface comes "for free" via `BetaThinkingBlock`/`BetaThinkingDelta` in PydanticAI's `AnthropicStreamedResponse`.
- **Analog:** itself; full rewrite of `bind_tools` body. `validate_config` body unchanged.
- **Excerpt — current Phase 4.5 `bind_tools` (lines 101-133) being replaced — note the Pitfall 2 docstring + assert:**
  ```python
  # backend/app/llm/providers/anthropic.py:101-133
  def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider:
      # Pitfall 2: ChatAnthropic requires non-None api_key at construction;
      # validate_config gates this in the normal flow (factory ordering, Plan 06).
      assert self._api_key is not None  # bind_tools precondition (Pitfall 2)
      llm = ChatAnthropic(  # type: ignore[call-arg]
          model=self._model,
          api_key=SecretStr(self._api_key),
      )
      return llm.bind_tools(list(tools))  # type: ignore[return-value]
  ```
- **Target shape — RESEARCH §Anthropic Provider + Pitfall 4:**
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.models.anthropic import AnthropicModel
  from pydantic_ai.providers.anthropic import AnthropicProvider as _PaiAnthropicProvider

  class AnthropicProvider(LLMProvider):
      def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
          # AnthropicProvider raises UserError on api_key=None — same shape as Phase 4.5
          # ChatAnthropic ValidationError. validate_config has already gated this.
          assert self._api_key is not None
          model = AnthropicModel(
              self._model,
              provider=_PaiAnthropicProvider(api_key=self._api_key),
          )
          return Agent(model, tools=list(tools), deps_type=deps_type)
  ```
- **Delta:**
  - Drop `from langchain_anthropic import ChatAnthropic`, `from pydantic import SecretStr`.
  - Update the docstring paragraph "Pitfall 2 — ChatAnthropic requires a non-None api_key" to "Pitfall 4 — `AnthropicProvider(api_key=None)` raises `pydantic_ai.UserError`" (RESEARCH Pitfall 4). The behaviour is the same; the SDK changed.
  - `validate_config()` and `list_models()` and `_CURATED_ANTHROPIC_MODELS` are unchanged.
- **Project-rule callouts:** none beyond what's already enforced.

---

### `backend/app/llm/providers/lmstudio.py` — local OpenAI-compat provider

- **Role:** local LM Studio provider; `validate_config` keeps `httpx` probe of `/v1/models`; `build_agent` constructs PydanticAI `Agent` against an OpenAI-compatible endpoint.
- **Analog:** itself; full rewrite of `bind_tools` body.
- **Excerpt — current Phase 4.5 `bind_tools` (lines 144-171) being replaced — note the sentinel:**
  ```python
  # backend/app/llm/providers/lmstudio.py:144-171
  def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider:
      llm = ChatOpenAI(
          model=self._model,
          base_url=self._base_url,
          api_key=SecretStr("lm-studio"),  # sentinel; D-17, RESEARCH.md Pitfall 3
      )
      return llm.bind_tools(list(tools))  # type: ignore[return-value]
  ```
- **Target shape — RESEARCH §LM Studio Provider:**
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.models.openai import OpenAIChatModel
  from pydantic_ai.providers.openai import OpenAIProvider as _PaiOpenAIProvider

  class LMStudioProvider(LLMProvider):
      def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
          model = OpenAIChatModel(
              self._model,
              # api_key defaults to "api-key-not-set" placeholder when base_url is set;
              # the "lm-studio" sentinel from Phase 4.5 D-17 is no longer needed.
              provider=_PaiOpenAIProvider(base_url=self._base_url),
          )
          return Agent(model, tools=list(tools), deps_type=deps_type)
  ```
- **Delta:**
  - Drop `from langchain_openai import ChatOpenAI`, `from pydantic import SecretStr`.
  - **Drop the `"lm-studio"` sentinel literal** — RESEARCH confirms PydanticAI's `OpenAIProvider(base_url=..., api_key=None)` auto-fills `"api-key-not-set"` when `OPENAI_API_KEY` is unset and `base_url` is provided. Update the docstring (lines 19-23) to reflect the simplification.
  - `list_models()` (`GET {base_url}/models`) and `validate_config()` bodies unchanged — they continue using `httpx` per the `validate_config` exception called out in RESEARCH.
- **Project-rule callouts:** none.

---

### `backend/app/chat/deps.py` — `ChatDeps` frozen dataclass (NEW)

- **Role:** per-turn dependency container threaded through PydanticAI `RunContext`.
- **Analog:** `backend/app/llm/factory.py:35-58` (`SessionLLMConfig`) — repo's canonical `@dataclass(frozen=True)` DTO pattern.
- **Excerpt — analog (`SessionLLMConfig`):**
  ```python
  # backend/app/llm/factory.py:35-58
  @dataclass(frozen=True)
  class SessionLLMConfig:
      """Per-session LLM configuration, from request payload + Settings fallbacks.
      ...
      """
      provider: str
      model: str
      base_url: str | None
      api_key: str | None
  ```
- **Target shape — D-05 + RESEARCH §ChatDeps:**
  ```python
  # backend/app/chat/deps.py
  from dataclasses import dataclass
  from app.tools.flight_client import FlightAPIClient

  @dataclass(frozen=True)
  class ChatDeps:
      """Per-turn dependency container for PydanticAI RunContext injection."""
      flight_client: FlightAPIClient
      session_id: str
      user_id: str
  ```
- **Delta:** New file. Same `@dataclass(frozen=True)` shape as `SessionLLMConfig`.
- **Project-rule callouts:**
  - `~/.claude/rules/python/coding-style.md` "Prefer immutable data structures: `@dataclass(frozen=True)`" — followed.
  - D-05 widens the deps to include `session_id` + `user_id` (not just `flight_client`) so Phase 8 structured logging can correlate without a Deps-shape churn.

---

### `backend/app/chat/store.py` — `ConversationStore(ABC)` + `InMemoryConversationStore` (NEW)

- **Role:** abstraction for chat history persistence; Phase 6 swaps `InMemoryConversationStore` → `PostgresConversationStore` via DI.
- **Analog:** `backend/app/auth/repository.py:35-93` (`UserRepository(ABC)` + `EnvUserRepository(UserRepository)`) — the repo's canonical "ABC + first-impl + Phase-N+1 swap via lifespan" pattern.
- **Excerpt — analog (full ABC + concrete impl shape):**
  ```python
  # backend/app/auth/repository.py:35-93 (template)
  class UserRepository(ABC):
      @abstractmethod
      def get_user(self, username: str) -> UserInDB: ...
      @abstractmethod
      def verify_password(self, plain: str, hashed: str) -> bool: ...

  class EnvUserRepository(UserRepository):
      def __init__(self) -> None:
          self._users: dict[str, UserInDB] = _load_users_from_env()

      def get_user(self, username: str) -> UserInDB:
          user = self._users.get(username)
          if user is None:
              raise UserNotFoundError(username)
          return user
      ...
  ```
- **Target shape — D-08 + D-11 + RESEARCH §ConversationStore ABC:**
  ```python
  # backend/app/chat/store.py
  from abc import ABC, abstractmethod
  from pydantic_ai.messages import ModelMessage
  from app.chat.models import ChatSessionInfo

  class ConversationStore(ABC):
      @abstractmethod
      async def append(self, session_id: str, messages: list[ModelMessage]) -> None: ...
      @abstractmethod
      async def load(self, session_id: str) -> list[ModelMessage]: ...
      @abstractmethod
      async def delete(self, session_id: str) -> None: ...
      @abstractmethod
      async def list_for_user(self, user_id: str) -> list[ChatSessionInfo]: ...

  class InMemoryConversationStore(ConversationStore):
      def __init__(self) -> None:
          self._store: dict[str, list[ModelMessage]] = {}

      async def append(self, session_id: str, messages: list[ModelMessage]) -> None:
          existing = self._store.get(session_id, [])
          self._store[session_id] = existing + messages  # immutable concat (coding-style)

      async def load(self, session_id: str) -> list[ModelMessage]:
          return list(self._store.get(session_id, []))

      async def delete(self, session_id: str) -> None:
          self._store.pop(session_id, None)
      ...
  ```
- **Delta:** New file. Methods are `async def` (CLAUDE.md "all I/O must be `async def`") because Phase 6's Postgres impl is naturally async; Phase 5's in-memory impl is async-but-uncontended.
- **Project-rule callouts:**
  - CLAUDE.md "Abstract interfaces use `ABC`, never `Protocol`" — followed.
  - `~/.claude/rules/common/coding-style.md` immutability — `existing + messages` returns a new list rather than `existing.append(...)`.
  - `cleanup_expired_sessions` becomes `async def` because it now `await store.delete(...)`s (RESEARCH Assumption A1; `app/api/main.py:76` and any test callers must be updated accordingly).

---

### `backend/app/chat/models.py` — `StreamEvent(BaseModel, ABC)` refactor

- **Role:** the wire-level event hierarchy serialised via `model_dump_json()` to SSE; Phase 5 promotes the `Annotated[..., Field(discriminator="type")]` alias to a real ABC base class.
- **Analog:** itself; in-place edit. `ARCHITECTURE.md:255-305` documents the current pattern that Phase 5 supersedes.
- **Excerpt — current alias + concrete classes (lines 42-102):**
  ```python
  # backend/app/chat/models.py:42-102
  class ContentEvent(BaseModel):
      type: Literal["content"] = "content"
      chunk: str = ""
      session_id: str

  class ThinkingEvent(BaseModel):
      type: Literal["thinking"] = "thinking"
      ...

  # DO NOT instantiate StreamEvent directly; it is a Field-discriminated union alias
  # used only for type annotations and TypeAdapter validation.
  StreamEvent = Annotated[
      ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent,
      Field(discriminator="type"),
  ]
  ```
- **Target shape — D-15 + RESEARCH OQ-01:**
  ```python
  # backend/app/chat/models.py (rewrite)
  from abc import ABC
  from pydantic import BaseModel

  class StreamEvent(BaseModel, ABC):
      """Base class for all SSE stream events (Phase 5 — replaces the Phase 4.7 alias)."""
      type: str
      session_id: str

  class ContentEvent(StreamEvent):
      type: Literal["content"] = "content"
      chunk: str = ""

  class ThinkingEvent(StreamEvent):
      type: Literal["thinking"] = "thinking"
      chunk: str = ""

  class ToolCallEvent(StreamEvent):
      type: Literal["tool_call"] = "tool_call"
      tool_name: str
      tool_args: dict[str, Any]

  class ToolResultEvent(StreamEvent):
      type: Literal["tool_result"] = "tool_result"
      tool_name: str
      tool_result: str
      elapsed_ms: int

  class ErrorEvent(StreamEvent):
      type: Literal["error"] = "error"
      error_code: ErrorCode
      message: str
      retryable: bool
      tool_name: str | None = None
      raw_detail: str | None = None
  ```
- **Delta:**
  - The `Annotated[..., Field(discriminator="type")]` alias is **deleted**.
  - `StreamEvent` becomes a real class — no `@abstractmethod` (RESEARCH OQ-01: "Use ABC purely as a mixin for `isinstance` checks").
  - `session_id` is hoisted into the base class (RESEARCH §StreamEvent ABC Refactor) — the five subclasses no longer redeclare it.
  - **Wire format unchanged.** `model_dump_json()` output is byte-equivalent (RESEARCH OQ-01 verified).
  - DTOs below the alias (`SessionCreateRequest`, `ChatSessionInfo`, `RetryRequest`, etc.) are **untouched**.
- **Project-rule callouts:**
  - CLAUDE.md "abstract interfaces use `ABC`, never `Protocol`" — followed.
  - The `Field(discriminator="type")` alias remains valid as a type annotation in code that constructs `TypeAdapter(StreamEvent)`. Per RESEARCH OQ-01 the ABC base + discriminator combination "works cleanly in Pydantic v2" — verified in live execution. The `test_stream_event_union_alias_*` tests in `tests/unit/test_stream_events.py` continue to pass with the same payload shape.

---

### `backend/app/chat/service.py` — full ChatService rewrite

- **Role:** the rewrite that anchors Phase 5. Loads history via `ConversationStore`, builds `Agent` via `provider.build_agent(...)`, runs `agent.iter()` and maps PydanticAI events to `StreamEvent` subclasses.
- **Analog:** itself (in-place rewrite). The current Phase 4.5/4.7 file is the diff base.
- **Excerpt — current chat_stream loop (lines 247-409) being replaced wholesale — note the LangChain-specific surface:**
  ```python
  # backend/app/chat/service.py:247-300 (excerpt — illustrates surface being retired)
  history = self.get_session_history(session_id)
  bound = self._bound_providers[session_id]
  history_messages: list[BaseMessage] = list(history.messages)
  messages: list[BaseMessage] = [*history_messages, HumanMessage(content=message)]

  if persist_user_message:
      history.add_user_message(message)

  accumulated_chunk: AIMessageChunk | None = None
  async for chunk in bound.astream(messages):
      if not isinstance(chunk, AIMessageChunk):
          continue
      if chunk.additional_kwargs:
          reasoning = chunk.additional_kwargs.get("reasoning_content")
          if reasoning:
              yield ThinkingEvent(chunk=reasoning, session_id=session_id)
      ...
      accumulated_chunk = chunk if accumulated_chunk is None else (accumulated_chunk + chunk)

  if accumulated_chunk is not None and accumulated_chunk.tool_calls:
      ...
      for tool_call in accumulated_chunk.tool_calls:
          yield ToolCallEvent(...)
          tool_result = await search_flights.ainvoke(tool_call["args"])
          yield ToolResultEvent(...)
  ```
- **Excerpt — current `__init__` + `create_session` (lines 67-114) for the `_agents` and `ConversationStore` retrofit:**
  ```python
  # backend/app/chat/service.py:67-114
  def __init__(self, flight_client: FlightAPIClient, factory: LLMProviderFactory) -> None:
      self._factory = factory
      self._histories: dict[str, InMemoryChatMessageHistory] = {}
      self._metadata: dict[str, dict[str, Any]] = {}
      self._bound_providers: dict[str, BoundProvider] = {}
      self._last_activity: dict[str, float] = {}

      # Wire the tool's client dependency here so callers don't need to know internals
      search_flights._flight_client = flight_client  # type: ignore[attr-defined]

  async def create_session(self, config, user_id) -> tuple[str, ProbeError | None]:
      provider = self._factory.build(config)
      probe_error = await provider.validate_config()
      if probe_error is not None:
          return "", probe_error
      bound = provider.bind_tools([search_flights])
      session_id = str(uuid.uuid4())
      self._histories[session_id] = InMemoryChatMessageHistory()
      self._bound_providers[session_id] = bound
      self._metadata[session_id] = {...}
      ...
  ```
- **Target shape — RESEARCH §3 streaming + §Agent + RunContext + Tool Registration:**
  ```python
  # backend/app/chat/service.py (Phase 5 rewrite)
  def __init__(
      self,
      flight_client: FlightAPIClient,
      factory: LLMProviderFactory,
      conversation_store: ConversationStore,
  ) -> None:
      self._flight_client = flight_client
      self._factory = factory
      self._conversation_store = conversation_store
      self._agents: dict[str, Agent[ChatDeps, str]] = {}
      self._metadata: dict[str, dict[str, Any]] = {}
      self._last_activity: dict[str, float] = {}
      # NOTE: search_flights._flight_client = flight_client is REMOVED.

  async def create_session(self, config, user_id) -> tuple[str, ProbeError | None]:
      provider = self._factory.build(config)
      probe_error = await provider.validate_config()
      if probe_error is not None:
          return "", probe_error
      agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
      session_id = str(uuid.uuid4())
      self._agents[session_id] = agent
      self._metadata[session_id] = {...}  # unchanged
      ...

  async def chat_stream(self, message, session_id, *, persist_user_message=True):
      history = await self._conversation_store.load(session_id)
      deps = ChatDeps(
          flight_client=self._flight_client,
          session_id=session_id,
          user_id=self._metadata[session_id]["user_id"],
      )
      agent = self._agents[session_id]
      async with agent.iter(message, message_history=history, deps=deps) as agent_run:
          async for node in agent_run:
              if isinstance(node, ModelRequestNode):
                  async with node.stream(agent_run.ctx) as model_stream:
                      async for event in model_stream:
                          match event:
                              case PartStartEvent(part=ThinkingPart(content=c)) if c:
                                  yield ThinkingEvent(chunk=c, session_id=session_id)
                              case PartDeltaEvent(delta=ThinkingPartDelta(content_delta=d)) if d:
                                  yield ThinkingEvent(chunk=d, session_id=session_id)
                              case PartStartEvent(part=TextPart(content=c)) if c:
                                  yield ContentEvent(chunk=c, session_id=session_id)
                              case PartDeltaEvent(delta=TextPartDelta(content_delta=d)) if d:
                                  yield ContentEvent(chunk=d, session_id=session_id)
              elif isinstance(node, CallToolsNode):
                  async with node.stream(agent_run.ctx) as tool_stream:
                      async for ev in tool_stream:
                          # ToolCallPart.args may be str or dict (RESEARCH Pitfall 3)
                          ...
      if agent_run.result is not None:
          await self._conversation_store.append(
              session_id, agent_run.result.new_messages()
          )
  ```
- **Delta — preserved invariants (DO NOT regress):**
  - `_metadata` and `_last_activity` dicts (D-09).
  - `_metadata[session_id]["last_tool_invocation"]` write-back inside the tool-call branch (Phase 4.7 retry endpoint depends on this).
  - `ErrorEvent` emission with `_scrub(str(exc))` for `raw_detail` (Phase 4.7 contract; RESEARCH §3 stream error mapping).
  - `cleanup_expired_sessions` becomes `async def` (Assumption A1).
- **Delta — retired:**
  - `_histories: dict[str, InMemoryChatMessageHistory]` — replaced by `self._conversation_store`.
  - `_bound_providers: dict[str, BoundProvider]` — replaced by `_agents: dict[str, Agent[ChatDeps, str]]` (D-10).
  - `from langchain_core.chat_history import InMemoryChatMessageHistory`, `from langchain_core.messages import ...` — removed.
  - `search_flights._flight_client = flight_client` line in `__init__` — **DELETED** (D-06; closes ARCHITECTURE.md "Monkey-Patched Tool Dependency" anti-pattern). CONTEXT.md anti-pattern: "Don't keep `search_flights._flight_client` 'just in case'."
- **Project-rule callouts:**
  - CLAUDE.md "all I/O must be `async def`" — `chat_stream` was already `async def`; `cleanup_expired_sessions` flips to `async def` (Assumption A1).
  - Anti-pattern: "Don't mock at the `Agent` level when you could mock at the `Model` level" — drives the test-fixture rewrite (see `tests/fixtures/llm.py` below).

---

### `backend/app/chat/__init__.py` — package re-exports

- **Role:** package barrel; consumed by `from app.chat import ChatService, ConversationStore, ...`.
- **Analog:** itself; in-place edit.
- **Excerpt — current shape (full file, 28 lines):**
  ```python
  # backend/app/chat/__init__.py
  from app.chat.models import (
      ContentEvent, ErrorCode, ErrorEvent, StreamEvent,
      ThinkingEvent, ToolCallEvent, ToolResultEvent,
  )
  from app.chat.service import ChatService

  __all__ = [
      "ChatService", "ContentEvent", "ErrorCode", "ErrorEvent",
      "StreamEvent", "ThinkingEvent", "ToolCallEvent", "ToolResultEvent",
  ]
  ```
- **Delta:** Add `ChatDeps` (from `app.chat.deps`) and `ConversationStore`, `InMemoryConversationStore` (from `app.chat.store`) to the imports + `__all__`.
- **Project-rule callouts:** none.

---

### `backend/app/tools/flight_search.py` — `search_flights` with `RunContext[ChatDeps]`

- **Role:** the agent's only tool; signature changes; body largely preserved.
- **Analog:** itself (in-place edit).
- **Excerpt — current decorator + signature + back-door (lines 277-342):**
  ```python
  # backend/app/tools/flight_search.py:277-342
  @tool
  async def search_flights(
      origin: str,
      destination: str,
      departure_date: str,
      passengers: int = 1,
      sort_by: str = "price",
      max_price: float | None = None,
      max_duration: int | None = None,
      max_stops: int | None = None,
      limit: int = 5,
  ) -> str:
      """Search for flights between two airports.
      ...
      """
      # Get the flight client from the tool's context
      # NOTE: This will be injected when the tool is bound to the ChatService
      client: FlightAPIClient | None = getattr(search_flights, "_flight_client", None)

      if client is None:
          return "Error: Flight search service not initialized. Please contact support."
      ...
  ```
- **Target shape — D-06 + RESEARCH §search_flights:**
  ```python
  from pydantic_ai import RunContext
  from app.chat.deps import ChatDeps

  async def search_flights(
      ctx: RunContext[ChatDeps],
      origin: str,
      destination: str,
      departure_date: str,
      passengers: int = 1,
      sort_by: str = "price",
      max_price: float | None = None,
      max_duration: int | None = None,
      max_stops: int | None = None,
      limit: int = 5,
  ) -> str:
      """Search for flights between two airports. ..."""  # docstring preserved verbatim
      client = ctx.deps.flight_client  # replaces getattr back-door
      ...  # rest of body preserved
  ```
- **Delta:**
  - Drop `from langchain_core.tools import tool`; drop the `@tool` decorator above the function.
  - Add `ctx: RunContext[ChatDeps]` as the first positional parameter (PydanticAI auto-detects context tools by signature).
  - Replace `client: FlightAPIClient | None = getattr(search_flights, "_flight_client", None)` with `client = ctx.deps.flight_client` — the client is now non-`None` by type (no more "Flight search service not initialized" defense; the `if client is None:` branch can be deleted).
  - The rest of the body (validation, `client.search(...)`, `_to_flight_search_result`) is unchanged.
- **Project-rule callouts:**
  - **Anti-pattern lock (CONTEXT.md):** "Don't keep `search_flights._flight_client` 'just in case'" — the attribute back-door must be deleted, not coexist with `RunContext`. Closes the ARCHITECTURE.md "Monkey-Patched Tool Dependency" entry.
  - The Phase 4.7 / 4.8 input validators inside `search_flights` (date parsing, IATA length checks) are preserved verbatim.

---

### `backend/app/api/main.py` — lifespan wiring

- **Role:** startup wiring; constructs all singletons.
- **Analog:** itself (in-place edit).
- **Excerpt — current lifespan (lines 23-77) — note lines 47-59 specifically:**
  ```python
  # backend/app/api/main.py:47-59
  flight_client = MockFlightAPIClient(seed=42)
  llm_factory = LLMProviderFactory(settings)

  # Inject flight_client into search_flights tool
  search_flights._flight_client = flight_client  # type: ignore[attr-defined]

  # Initialize chat service with the factory (D-03 — no singleton bound LLM).
  chat_service = ChatService(
      flight_client=flight_client,
      factory=llm_factory,
  )
  ```
- **Target shape — RESEARCH §Recommended File Layout + Integration Points:**
  ```python
  flight_client = MockFlightAPIClient(seed=42)
  llm_factory = LLMProviderFactory(settings)
  conversation_store = InMemoryConversationStore()

  # NOTE: search_flights._flight_client = flight_client is DELETED — D-06 closes the back-door.
  # Tool DI is via RunContext[ChatDeps] threaded by ChatService.chat_stream.

  chat_service = ChatService(
      flight_client=flight_client,
      factory=llm_factory,
      conversation_store=conversation_store,
  )
  ```
- **Delta:** Construct `InMemoryConversationStore`, pass to `ChatService(...)`. Delete `search_flights._flight_client = ...` line. Delete `from app.tools.flight_search import search_flights` if no other lifespan code uses it.
- **Project-rule callouts:**
  - "Lifespan-managed singletons via `app.state`" pattern (`ARCHITECTURE.md:138-170`) — followed.
  - The `cleanup_expired_sessions` call at shutdown (line 76) becomes `await chat_service.cleanup_expired_sessions(...)` because the method is now async (Assumption A1).

---

### `backend/app/api/routes/routes.py` — SSE serialisation

- **Role:** SSE stream serialisation; consumes `event.model_dump_json()`.
- **Analog:** itself (in-place edit, but trivial).
- **Excerpt — current event_generator (lines 95-138):**
  ```python
  # backend/app/api/routes/routes.py:95-103
  async def event_generator() -> AsyncGenerator[str]:
      try:
          async for event in chat_service.chat_stream(
              session_id=request.session_id,
              message=request.message,
          ):
              yield f"data: {event.model_dump_json()}\n\n"
      ...
  ```
- **Delta:** **No code change**. `StreamEvent` ABC subclasses (Phase 5 D-15) remain Pydantic models with `Literal[...]` discriminators; `model_dump_json()` output is byte-equivalent (RESEARCH OQ-01 verified). The route file is included only because its imports may need a small adjustment if `from app.chat.models import ErrorEvent` etc. anchor changes — verify and leave.
- **Project-rule callouts:** none.

---

### `backend/app/config.py` — `Settings`

- **Role:** environment-driven knobs.
- **Analog:** itself (in-place edit).
- **Excerpt — current Ollama reasoning prefix knob (lines 72-83):**
  ```python
  # backend/app/config.py:72-83
  ollama_reasoning_model_prefixes: tuple[str, ...] = (
      "qwen3",
      "deepseek-r1",
  )
  ```
- **Target shape — D-14 + CLAUDE.md "tunables on Settings":**
  ```python
  # NEW: o-series dispatch knob for OpenAIProvider (D-14)
  openai_o_series_model_prefixes: tuple[str, ...] = ("o1", "o3")

  # REMOVED: ollama_reasoning_model_prefixes (PydanticAI handles <think> natively
  # via OllamaProvider's qwen_model_profile + ModelProfile.thinking_tags — RESEARCH OQ-04)
  ```
- **Delta:**
  - **Add** `openai_o_series_model_prefixes: tuple[str, ...] = ("o1", "o3")` and the explanatory comment (mirror the Phase 4.5 `ollama_reasoning_model_prefixes` comment style).
  - **Remove** `ollama_reasoning_model_prefixes` (no longer threaded into `OllamaProvider` — D-12 / OQ-04).
- **Project-rule callouts:**
  - CLAUDE.md "tunable thresholds live on `Settings`, not as module-level constants" — `_O_SERIES_PREFIXES` does **not** become a module constant in `providers/openai.py`.

---

### `backend/app/llm/__init__.py` — package re-exports

- **Role:** package barrel.
- **Analog:** itself (in-place edit).
- **Delta:** No `BoundProvider` reference (it's deleted). Optionally add `LLMProvider` from `app.llm.base` to `__all__` if any importers reach for the package barrel.

---

### `backend/pyproject.toml` — dependency manifest

- **Role:** uv-managed Python deps.
- **Analog:** itself.
- **Excerpt — current `[project].dependencies` (lines 7-22):**
  ```toml
  # backend/pyproject.toml:7-22
  dependencies = [
      "fastapi>=0.115.0",
      "uvicorn[standard]>=0.32.0",
      "python-dotenv>=1.0.0",
      "pydantic>=2.9.0",
      "pydantic-settings>=2.6.0",
      "langchain>=0.3.0",
      "langchain-ollama>=0.2.0",
      "langgraph>=1.0.2",
      "httpx>=0.27.0", # For ollama API calls
      "pyjwt>=2.10.1",
      "pwdlib[argon2]>=0.3.0",
      "python-multipart>=0.0.21",
      "langchain-openai>=1.2.1",
      "langchain-anthropic>=1.4.3",
  ]
  ```
- **Target shape — D-20 + RESEARCH §Standard Stack:**
  ```toml
  dependencies = [
      "fastapi>=0.115.0",
      "uvicorn[standard]>=0.32.0",
      "python-dotenv>=1.0.0",
      "pydantic>=2.12",         # bumped — pydantic-ai-slim 0.8.1 requires >=2.12 (Pitfall 8)
      "pydantic-settings>=2.6.0",
      "pydantic-ai>=0.8.1",      # NEW
      "httpx>=0.27.0",            # kept — used by validate_config / list_models (Phase 7 swaps to pyreqwest for travel APIs)
      "pyjwt>=2.10.1",
      "pwdlib[argon2]>=0.3.0",
      "python-multipart>=0.0.21",
  ]
  ```
- **Delta:**
  - **Remove:** `langchain`, `langchain-ollama`, `langchain-openai`, `langchain-anthropic`, **and `langgraph`** (Pitfall 9 — still in manifest despite PR #1 claiming otherwise).
  - **Add:** `pydantic-ai>=0.8.1`.
  - **Bump:** `pydantic>=2.9.0` → `pydantic>=2.12` (Pitfall 8).
  - `uv lock` is regenerated to reflect the swap.
- **Project-rule callouts:**
  - CLAUDE.md "use `uv` exclusively" — installation via `uv add pydantic-ai` and `uv remove langchain langchain-core langchain-ollama langchain-openai langchain-anthropic langgraph`.

---

## Test-file mappings

### `backend/tests/fixtures/llm.py` — full mock-LLM rewrite

- **Role:** the offline fixture for `make_chat_service_with_mock_llm(...)`. Today it wraps `MockLLM(BaseChatModel)`; Phase 5 wraps `FunctionModel(stream_function=...)`.
- **Analog:** itself (full rewrite). RESEARCH §MockLLMStream Strategy specifies the new shape.
- **Excerpt — current `_MockLLMProvider` + `_MockBoundProvider` (lines 186-246) being replaced — note the duck-typed Protocol surface:**
  ```python
  # backend/tests/fixtures/llm.py:186-246
  class _MockBoundProvider:
      def __init__(self, llm: MockLLM) -> None:
          self._llm = llm

      def astream(self, input, **kwargs) -> AsyncIterator[AIMessageChunk]:
          return self._llm.astream(input, **kwargs)
      async def ainvoke(self, input, **kwargs) -> AIMessage:
          return await self._llm.ainvoke(input, **kwargs)

  class _MockLLMProvider:
      def __init__(self, llm: MockLLM) -> None:
          self._llm = llm
      def get_provider_name(self) -> str: return "ollama"
      async def validate_config(self) -> ProbeError | None: return None
      def bind_tools(self, tools) -> BoundProvider:
          return _MockBoundProvider(self._llm)
      async def list_models(self) -> list[str]: return []

  def make_chat_service_with_mock_llm(streams):
      flight_client = MockFlightAPIClient(seed=42)
      provider = _MockLLMProvider(MockLLM(streams=streams))
      factory = MagicMock(spec=LLMProviderFactory)
      factory.build = MagicMock(return_value=provider)
      return ChatService(flight_client=flight_client, factory=factory)
  ```
- **Excerpt — preserved chunk types + scenarios (lines 44-176) — DO NOT TOUCH:**
  ```python
  # backend/tests/fixtures/llm.py:44-67 (KEEP)
  @dataclass(frozen=True, slots=True)
  class Content: text: str
  @dataclass(frozen=True, slots=True)
  class Thinking: text: str
  @dataclass(frozen=True, slots=True)
  class ToolCall:
      name: str
      args: dict[str, Any]
      id: str = "call_test"
  Chunk = Content | Thinking | ToolCall

  # MockLLMStream classmethods (greeting / single_tool_call / multi_turn) — KEEP
  ```
- **Target shape — D-17, D-18 + RESEARCH §MockLLMStream Strategy:**
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.models.function import FunctionModel, DeltaToolCall, DeltaThinkingPart
  from app.llm.base import LLMProvider

  def _make_stream_function(streams: list[list[Chunk]]):
      streams_iter = iter(streams)
      async def stream_function(messages, agent_info):
          try:
              chunks = next(streams_iter)
          except StopIteration:
              raise RuntimeError("MockLLMStream exhausted") from None
          for chunk in chunks:
              match chunk:
                  case Content(text=t):
                      yield t
                  case Thinking(text=t):
                      yield {0: DeltaThinkingPart(content=t)}
                  case ToolCall(name=n, args=a, id=i):
                      yield {0: DeltaToolCall(name=n, json_args=json.dumps(a), tool_call_id=i)}
      return stream_function

  class _MockLLMProvider(LLMProvider):  # subclass the ABC (D-03)
      def __init__(self, streams): self._streams = streams
      def get_provider_name(self) -> str: return "ollama"
      async def validate_config(self) -> ProbeError | None: return None
      async def list_models(self) -> list[str]: return []
      def build_agent(self, tools, deps_type) -> Agent[Any, str]:
          model = FunctionModel(stream_function=_make_stream_function(self._streams))
          return Agent(model, tools=list(tools), deps_type=deps_type)

  def make_chat_service_with_mock_llm(streams: list[list[Chunk]]) -> ChatService:
      flight_client = MockFlightAPIClient(seed=42)
      provider = _MockLLMProvider(streams)
      factory = MagicMock(spec=LLMProviderFactory)
      factory.build = MagicMock(return_value=provider)
      return ChatService(
          flight_client=flight_client,
          factory=factory,
          conversation_store=InMemoryConversationStore(),
      )
  ```
- **Delta:**
  - Drop `MockLLM(BaseChatModel)` class entirely; drop `langchain_core.*` and `pydantic.PrivateAttr` imports.
  - Drop `_MockBoundProvider` adapter (no second tier).
  - `_MockLLMProvider` now subclasses `LLMProvider` (the ABC); its sole "interesting" method is `build_agent` returning a real `pydantic_ai.Agent` backed by `FunctionModel`.
  - `make_chat_service_with_mock_llm` signature is **unchanged** (D-18); internals add `conversation_store=InMemoryConversationStore()`.
  - `MockLLMStream.greeting()` / `single_tool_call()` / `multi_turn()` classmethods are unchanged (D-17).
- **Project-rule callouts:**
  - **Anti-pattern (CONTEXT.md):** "Don't mock at the `Agent` level when you could mock at the `Model` level" — followed: `FunctionModel` lets the real PydanticAI `Agent` code path run in tests.
  - RESEARCH Pitfall 7 — `single_tool_call` already returns two inner lists (one per `stream_function` invocation); preserve.

---

### `backend/tests/unit/llm/test_protocol_abc.py` (rename `test_protocol_conformance.py`)

- **Role:** ABC conformance test for all four concrete providers.
- **Analog:** `backend/tests/unit/llm/test_protocol_conformance.py:35-65` (the file being renamed).
- **Excerpt — analog (current Protocol-based assertion):**
  ```python
  # backend/tests/unit/llm/test_protocol_conformance.py:35-44
  def test_ollama_provider_satisfies_llm_provider_protocol() -> None:
      provider = OllamaProvider(model="qwen3:4b", base_url="http://localhost:11434", probe_timeout_seconds=1.5)
      assert isinstance(provider, LLMProvider)
  ```
- **Target shape:**
  ```python
  from app.llm.base import LLMProvider  # ABC
  # ...
  def test_ollama_provider_subclasses_llm_provider() -> None:
      provider = OllamaProvider(model="qwen3:4b", base_url="http://localhost:11434", probe_timeout_seconds=1.5)
      assert isinstance(provider, LLMProvider)
      assert issubclass(OllamaProvider, LLMProvider)  # explicit subclass (D-03)

  def test_bound_provider_is_removed_from_module() -> None:
      """Phase 5 retires BoundProvider — not a separate Protocol or ABC."""
      import app.llm.base
      assert not hasattr(app.llm.base, "BoundProvider")
  ```
- **Delta:** Replace the `BoundProvider` "raw provider does NOT satisfy" test with an "import absent" test. Each per-provider test gains an `issubclass` check.
- **Project-rule callouts:** none.

---

### `backend/tests/unit/llm/test_build_agent.py` — provider→Agent unit test

- **Role:** asserts each concrete `provider.build_agent(tools, deps_type)` returns a `pydantic_ai.Agent`.
- **Analog:** `backend/tests/unit/llm/test_ollama_provider.py:107-134` (the existing per-provider unit test pattern; reuse the AAA test shape).
- **Excerpt — analog:**
  ```python
  # backend/tests/unit/llm/test_ollama_provider.py:107-134
  def test_model_supports_reasoning_matches_configured_prefixes() -> None:
      qwen = OllamaProvider(model="qwen3:4b", base_url="http://x", probe_timeout_seconds=1.0)
      ...
      assert qwen._model_supports_reasoning() is True
  ```
- **Target shape:**
  ```python
  from pydantic_ai import Agent
  from app.chat.deps import ChatDeps
  from app.tools.flight_search import search_flights

  def test_ollama_provider_build_agent_returns_pydantic_ai_agent() -> None:
      provider = OllamaProvider(model="qwen3:4b", base_url="http://x", probe_timeout_seconds=1.0)
      agent = provider.build_agent(tools=[search_flights], deps_type=ChatDeps)
      assert isinstance(agent, Agent)
  ```
- **Delta:** New file; one test per concrete provider.
- **Project-rule callouts:** none.

---

### `backend/tests/unit/llm/providers/test_openai_dispatch.py` — D-14 dispatch test

- **Role:** asserts `OpenAIProvider.build_agent` dispatches to `OpenAIResponsesModel` for o-series; `OpenAIChatModel` otherwise.
- **Analog:** `backend/tests/unit/llm/test_factory.py:27-55` — the factory dispatch pattern (`match` on `provider`).
- **Target shape:**
  ```python
  from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
  from app.llm.providers.openai import OpenAIProvider
  from app.chat.deps import ChatDeps

  def test_o3_mini_routes_to_openai_responses_model() -> None:
      provider = OpenAIProvider(model="o3-mini", api_key="sk-test")
      agent = provider.build_agent(tools=[], deps_type=ChatDeps)
      assert isinstance(agent.model, OpenAIResponsesModel)

  def test_gpt_4o_mini_routes_to_openai_chat_model() -> None:
      provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
      agent = provider.build_agent(tools=[], deps_type=ChatDeps)
      assert isinstance(agent.model, OpenAIChatModel)
  ```
- **Delta:** New file. Drives both branches of the D-14 dispatch.

---

### `backend/tests/unit/chat/test_conversation_store.py`

- **Role:** ABC + `InMemoryConversationStore` round-trip.
- **Analog:** `backend/tests/unit/test_user_repository.py` (the existing UserRepository unit-test shape).
- **Target shape:**
  ```python
  async def test_append_and_load_round_trip() -> None:
      store = InMemoryConversationStore()
      await store.append("s1", [<ModelMessage instances>])
      assert await store.load("s1") == [<expected>]

  async def test_delete_removes_session() -> None:
      ...

  async def test_load_returns_empty_for_unknown_session() -> None:
      ...
  ```
- **Delta:** New file.

---

### `backend/tests/unit/chat/test_stream_event_abc.py`

- **Role:** golden test for `class StreamEvent(BaseModel, ABC)`; verifies `isinstance` works and subclasses keep their discriminator.
- **Analog:** `backend/tests/unit/test_stream_events.py:138-159` (existing TypeAdapter discriminator test).
- **Excerpt — analog:**
  ```python
  # backend/tests/unit/test_stream_events.py:138-149
  def test_stream_event_union_alias_deserialises_error_event() -> None:
      payload = {"type": "error", "error_code": "tool_error", "message": "x", "retryable": True, "session_id": "s"}
      adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)
      result = adapter.validate_python(payload)
      assert isinstance(result, ErrorEvent)
  ```
- **Target shape (additive):**
  ```python
  def test_concrete_event_isinstance_streamevent_abc() -> None:
      assert isinstance(ContentEvent(chunk="hi", session_id="s"), StreamEvent)
      assert isinstance(ErrorEvent(error_code=ErrorCode.tool_error, message="x", retryable=False, session_id="s"), StreamEvent)
      # ABC base class instantiation should fail (no @abstractmethod, but ABC marker present)
  ```
- **Delta:** New file (or add tests to existing `test_stream_events.py`); preserves discriminator round-trip while adding ABC `isinstance` assertions.

---

### `backend/tests/unit/chat/test_stream_event_wire_compat.py`

- **Role:** byte-equivalent `model_dump_json()` golden vs Phase 4.7 reference.
- **Analog:** `backend/tests/unit/test_stream_events.py:51-73` (current `model_dump_json()` discriminator-string assertions).
- **Target shape:**
  ```python
  def test_content_event_wire_unchanged() -> None:
      e = ContentEvent(chunk="hi", session_id="s1")
      # Golden bytes — must match Phase 4.7 wire format byte-for-byte
      assert e.model_dump_json() == '{"type":"content","session_id":"s1","chunk":"hi"}'
      # (Note field order: PydanticAI ABC subclass inherits session_id from base;
      # confirm output ordering with a one-shot fixture in Wave 0.)
  ```
- **Delta:** New file with five fixtures (one per subclass).

---

### `backend/tests/unit/chat/test_stream_event_extraction.py`

- **Role:** drives the `agent.iter()` event loop with `FunctionModel` and asserts the four mappings.
- **Analog:** `backend/tests/unit/test_chat_stream.py:18-36` (existing greeting test against `MockLLM`).
- **Excerpt — analog:**
  ```python
  # backend/tests/unit/test_chat_stream.py:18-36
  async def test_chat_stream_emits_content_events_for_greeting() -> None:
      service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
      session_id, _ = await service.create_session(default_session_config(), user_id="testuser")
      events = [e async for e in service.chat_stream("Hello", session_id)]
      content_events = [e for e in events if e.type == "content"]
      ...
  ```
- **Target shape:** same fixture-driven pattern; assertions add `tool_call`, `tool_result`, and `thinking` mapping (when a `Thinking` chunk is in the scenario).
- **Delta:** New file (or add tests to `test_chat_stream.py`); semantics unchanged after the fixture rewrite.

---

### `backend/tests/unit/chat/test_stream_error_event.py`

- **Role:** asserts exception in stream surfaces as `ErrorEvent` with `_scrub` applied.
- **Analog:** `backend/tests/unit/test_chat_stream.py:38-60` (existing APIError → ErrorEvent test).
- **Delta:** Same shape; trigger an exception inside `stream_function` (the `FunctionModel` substrate); assert the resulting `ErrorEvent.raw_detail` is scrubbed.

---

### `backend/tests/unit/tools/test_flight_search.py` — RunContext injection

- **Role:** unit test for the rewritten `search_flights(ctx, ...)` signature.
- **Analog:** `backend/tests/unit/test_tool_json_normalization.py` (existing tool-level unit test).
- **Target shape:**
  ```python
  from pydantic_ai.tools import RunContext
  from app.chat.deps import ChatDeps

  async def test_search_flights_reads_client_from_runcontext() -> None:
      flight_client = MockFlightAPIClient(seed=42)
      ctx = RunContext(deps=ChatDeps(flight_client=flight_client, session_id="s", user_id="u"), ...)
      result = await search_flights(ctx, origin="LAX", destination="JFK", departure_date="2026-06-15")
      parsed = FlightSearchResult.model_validate_json(result)
      assert parsed.status == "ok"
  ```
- **Delta:** New file. Uses the real `RunContext` constructor (RESEARCH §Tool registration confirms the shape).

---

### `backend/tests/unit/tools/test_flight_search_no_backdoor.py` — anti-pattern lock

- **Role:** regression test that the `_flight_client` attribute back-door cannot be reintroduced.
- **Analog:** none — genuinely new file; this is a project-history regression guard.
- **Target shape:**
  ```python
  from app.tools.flight_search import search_flights

  def test_search_flights_has_no_flight_client_attribute() -> None:
      """The Phase 4.x `_flight_client` back-door is closed (D-06)."""
      assert not hasattr(search_flights, "_flight_client")

  def test_search_flights_first_param_is_runcontext() -> None:
      import inspect
      sig = inspect.signature(search_flights)
      first_param = next(iter(sig.parameters.values()))
      assert first_param.name == "ctx"
  ```
- **Delta:** New file. Anti-pattern lock.

---

### `backend/tests/unit/test_dependencies.py` — pyproject manifest assertion

- **Role:** asserts `langchain*`/`langgraph` are gone, `pydantic-ai` is present.
- **Analog:** none — genuinely new file.
- **Target shape:**
  ```python
  import tomllib
  from pathlib import Path

  def test_no_langchain_dependencies() -> None:
      manifest = tomllib.loads(Path("pyproject.toml").read_text())
      deps = manifest["project"]["dependencies"]
      for d in deps:
          name = d.split(">=")[0].split("==")[0].strip()
          assert not name.startswith("langchain")
          assert name != "langgraph"

  def test_pydantic_ai_present() -> None:
      manifest = tomllib.loads(Path("pyproject.toml").read_text())
      deps = manifest["project"]["dependencies"]
      assert any(d.startswith("pydantic-ai") for d in deps)
  ```
- **Delta:** New file.

---

### `backend/tests/unit/test_no_langchain_imports.py` — import-scan assertion

- **Role:** AST-walk of `app/` asserting no `langchain*` import remains.
- **Analog:** none — genuinely new file.
- **Target shape:**
  ```python
  import ast
  from pathlib import Path

  def test_no_langchain_imports_in_app_tree() -> None:
      bad: list[tuple[Path, str]] = []
      for py in Path("app").rglob("*.py"):
          tree = ast.parse(py.read_text())
          for node in ast.walk(tree):
              if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("langchain"):
                  bad.append((py, node.module))
              elif isinstance(node, ast.Import):
                  for alias in node.names:
                      if alias.name.startswith("langchain"):
                          bad.append((py, alias.name))
      assert not bad, f"Lingering langchain imports: {bad}"
  ```
- **Delta:** New file.

---

### `backend/tests/integration/test_chat_stream.py` — three locked scenarios

- **Role:** the three `MockLLMStream` scenarios (`greeting`, `single_tool_call`, `multi_turn`) exercised through `make_chat_service_with_mock_llm` after the fixture rewrite.
- **Analog:** `backend/tests/integration/test_chat_service_flow.py:25-83` (current integration shape).
- **Excerpt — analog (the test that becomes Phase 5's `test_single_tool_call`):**
  ```python
  # backend/tests/integration/test_chat_service_flow.py:25-58
  async def test_chat_stream_emits_tool_events_for_flight_query() -> None:
      service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
      session_id, _ = await service.create_session(default_session_config(), user_id="testuser")
      events = [e async for e in service.chat_stream("Find flights LAX to JFK", session_id)]
      types = [e.type for e in events]
      assert "tool_call" in types
      assert "tool_result" in types
      assert "content" in types
      ...
  ```
- **Target shape:** identical — only the fixture's internals change.
- **Delta:**
  - History assertions that read `history.messages` (LangChain shape) are rewritten to read from the `ConversationStore` (`await store.load(session_id)` returns `list[ModelMessage]`).
  - Specifically lines 47-51 (`isinstance(m, HumanMessage)`, `isinstance(m, ToolMessage)`, `len([m for m in msgs if isinstance(m, AIMessage)]) == 2`) must be replaced with PydanticAI message-kind checks (`ModelRequest`/`ModelResponse` parts).
- **Project-rule callouts:** none.

---

### `backend/tests/integration/llm/test_{ollama,openai,anthropic}_thinking_live.py` — gated cloud acceptance

- **Role:** D-13 per-provider acceptance tests for thinking surface.
- **Analog:** `backend/tests/integration/test_cloud_providers_real.py` — the existing gated-cloud-key skipif pattern.
- **Target shape:**
  ```python
  import os
  import pytest

  @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
  async def test_openai_o_series_emits_thinking_events() -> None:
      provider = OpenAIProvider(model="o3-mini", api_key=os.environ["OPENAI_API_KEY"])
      ...
  ```
- **Delta:** New skeletons. Same gating pattern as Phase 4.5.

---

## ADR / docs files

### `.planning/adrs/ADR-001-langchain.md`

- **Role:** ADR-001 status flip Locked/Accepted → Superseded.
- **Analog:** `ARCHITECTURE.md:561-583` (current ADR-001 prose lives in ARCHITECTURE.md, not a standalone file). The file may not exist yet; if so, create it from the ARCHITECTURE.md prose plus a "Superseded by ADR-007" note.
- **Excerpt — current ADR-001 prose to lift:**
  ```markdown
  ### ADR-001: LangChain 1.0 with bind_tools() Pattern
  **Date**: 2025-11-10
  **Status**: Accepted
  **Context**: Need agent framework for tool calling with LLMs.
  **Decision**: Use LangChain 1.0 `bind_tools()` pattern instead of older `create_agent()` approach.
  ...
  ```
- **Target shape:** Header `Status: Superseded` plus a "Superseded by ADR-007 (PydanticAI). See `.planning/phases/05-pydanticai-migration/05-CONTEXT.md` D-21 for the transition rationale." note.
- **Delta:** Status flip + supersession note. The original prose is preserved verbatim for archeology.

### `.planning/adrs/ADR-007-pydantic-ai.md`

- **Role:** ADR-007 status flip Proposed → Locked.
- **Analog:** `ARCHITECTURE.md:585-607` (ADR-002's status-flip footer is a similar editorial pattern).
- **Target shape:** the locked ADR cites RESEARCH OQ-01..OQ-05 verifications and lists the per-provider migration rules verbatim.

### `ARCHITECTURE.md`

- **Role:** rewrite three sections to match Phase 5.
- **Analog:** itself.
- **Sections to update:**
  - Lines 174-251 (LLMProvider Factory Pattern) — `Protocol` → `ABC`, single tier, `build_agent` instead of `bind_tools`, drop `BoundProvider`.
  - Lines 255-305 (Discriminated StreamEvent Union Pattern) — alias → ABC; rule "Do not instantiate StreamEvent directly" is *removed* (it's now a real class, just one without abstract methods that would prevent direct usage).
  - Lines 405-456 ("LangChain 1.0 Integration") — replace with "PydanticAI Integration"; bind_tools / `astream` example → `agent.iter()` + per-node streaming.
  - Lines 561-583 (ADR-001) — add Status: Superseded line.
  - Lines 783-795 ("Known Tech Debt: app/llm/protocol.py uses typing.Protocol") — **delete entire section**.
  - Add: "Anti-Pattern Closures (Phase 5)" subsection listing both closures: `_flight_client` back-door + Protocol-vs-ABC.
- **Delta:** Editorial only; no code in ARCHITECTURE.md.
- **Project-rule callouts:** none.

### `.planning/PROJECT.md`

- **Role:** project-level status board; ADR transitions land in the Key Decisions table.
- **Delta:** mark ADR-001 Superseded; ADR-007 Locked; tick Phase 5 success criteria.

---

## New-file inventory (no analog)

| File | Why no analog |
|---|---|
| `backend/app/chat/deps.py` (`ChatDeps`) | First PydanticAI-native DTO. Closest neighbour is `SessionLLMConfig` (factory.py) — same `@dataclass(frozen=True)` style. |
| `backend/app/chat/store.py` (`ConversationStore` ABC + `InMemoryConversationStore`) | First Phase 5–native abstraction. Closest neighbour is `UserRepository(ABC)` + `EnvUserRepository` in `app/auth/repository.py` — same ABC + first-impl + Phase-N+1-swap-via-DI pattern. |
| `backend/tests/unit/llm/providers/test_ollama_thinking.py` | No prior Ollama thinking-surface unit test exists — Phase 4.5 only had `_model_supports_reasoning` prefix gating. The closest neighbour is `test_ollama_provider.py` (style, AAA, fixture). |
| `backend/tests/unit/tools/test_flight_search_no_backdoor.py` | Anti-pattern lock; no analog by design. Style mirrors any unit test in `tests/unit/`. |
| `backend/tests/unit/test_dependencies.py` | First `pyproject.toml` content assertion in the repo. |
| `backend/tests/unit/test_no_langchain_imports.py` | First import-scan assertion in the repo. |

---

## Project-rule callouts (cross-cutting)

These rules apply to every plan; the planner should reference them at each implementation site that touches them:

1. **ABC, not Protocol** (CLAUDE.md, `/dignified-python` skill, D-03). Every new abstract type Phase 5 introduces (`LLMProvider`, `ConversationStore`, `StreamEvent`) is an `abc.ABC` subclass. Concrete implementations declare the parent explicitly. Anti-pattern: shipping a `ProtocolProvider` adapter alongside the new ABC.
2. **`StrEnum` for cross-module taxonomies** (CLAUDE.md). `ErrorCode` (Phase 4.7) and `ProbeErrorCode` (Phase 4.5) remain `StrEnum`s — Phase 5 does not change them. The `type: Literal[...]` discriminator on each `StreamEvent` subclass stays a `Literal`, not a `StrEnum`, because the discriminator must be a literal type for Pydantic's discriminator machinery.
3. **Tunables on `Settings`, not module constants** (CLAUDE.md). `_O_SERIES_PREFIXES` lives on `Settings.openai_o_series_model_prefixes`; `provider_probe_timeout_seconds` continues to flow from `Settings` into provider constructors.
4. **All I/O is `async def`** (CLAUDE.md). `ConversationStore` methods are async; `cleanup_expired_sessions` flips to async (Assumption A1).
5. **Outbound HTTP uses `pyreqwest`** (ADR-008). **Exception:** `httpx` survives in `validate_config` / `list_models` per RESEARCH §Standard Stack note; the pyreqwest swap lands in Phase 7 with the real Amadeus client.
6. **No `_flight_client` back-door** (D-06, CONTEXT.md anti-pattern). The attribute must be deleted, not coexist with `RunContext`.
7. **No `BoundProvider` shim** (CONTEXT.md anti-pattern). Pure rename + retype on `LLMProvider`; no two-tier carry-over.
8. **Mock at the Model layer, not the Agent layer** (CONTEXT.md anti-pattern). `FunctionModel(stream_function=...)` inside `_MockLLMProvider.build_agent()`, not a fake `_MockAgent`.
9. **SSE wire format is unchanged** (CONTEXT.md anti-pattern). `StreamEvent` ABC keeps the byte-for-byte `model_dump_json()` output verified in RESEARCH OQ-01; frontend stays untouched.

---

## Metadata

- **Files classified:** 38 (24 source/config + 14 tests/docs/ADRs).
- **Existing analogs found:** 33 (`exact` + `role-match`); **no analog:** 6 genuinely new files.
- **Pattern map version:** 1.0 (Phase 5 / PydanticAI migration).
- **Generated:** 2026-06-03.
