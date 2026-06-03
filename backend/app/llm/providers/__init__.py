"""Concrete LLM provider implementations (Phase 5 D-01..D-03).

Each module in this package implements the ``LLMProvider`` ABC from
:mod:`app.llm.base` for a specific backend:

- :mod:`app.llm.providers.ollama` — local Ollama daemon (dynamic ``/api/tags`` discovery)
- :mod:`app.llm.providers.openai` — OpenAI cloud (curated model allow-list, key-presence-only probe per D-13)
- :mod:`app.llm.providers.anthropic` — Anthropic cloud (curated model allow-list, key-presence-only probe per D-13)
- :mod:`app.llm.providers.lmstudio` — local LM Studio daemon

Phase 5 retires the Phase 4.5 second-tier "bound" Protocol entirely — PydanticAI's
``Agent`` IS the bound thing returned by ``build_agent``. Wave 2 / Plan 05-03
makes each concrete class explicitly subclass :class:`app.llm.base.LLMProvider`
and implement ``build_agent`` in place of ``bind_tools``.

Per D-04, cloud providers do NOT perform live model discovery — their
``list_models`` returns a static curated allow-list that mirrors
``Settings.get_available_providers()``.
"""
