"""Per-provider LLM implementations satisfying :class:`app.llm.protocol.LLMProvider`.

Concrete providers (Wave 2):

- :class:`app.llm.providers.openai.OpenAIProvider` — cloud, key-presence only
  validate_config (D-13).
- :class:`app.llm.providers.ollama.OllamaProvider` — local, live ``/api/tags``
  probe (sibling plan).
- :class:`app.llm.providers.anthropic.AnthropicProvider` — cloud, key-presence
  only validate_config (sibling plan).

These classes implement :class:`app.llm.protocol.LLMProvider` via duck typing —
they do NOT inherit from the Protocol. The factory in :mod:`app.llm.factory`
dispatches the per-session provider literal to the matching class in Wave 3.
"""
