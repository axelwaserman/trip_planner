"""Concrete LLM provider implementations (Phase 4.5).

Each module in this package implements the structural ``LLMProvider`` Protocol
from :mod:`app.llm.protocol` for a specific backend:

- :mod:`app.llm.providers.ollama` — local Ollama daemon (dynamic ``/api/tags`` discovery)
- :mod:`app.llm.providers.openai` — OpenAI cloud (curated model allow-list, key-presence-only probe per D-13)
- :mod:`app.llm.providers.anthropic` — Anthropic cloud (curated model allow-list, key-presence-only probe per D-13)
- :mod:`app.llm.providers.lmstudio` — local LM Studio daemon (added by Plan 04b)

These classes implement :class:`app.llm.protocol.LLMProvider` via duck typing —
they do NOT inherit from the Protocol. The factory in :mod:`app.llm.factory`
dispatches the per-session provider literal to the matching class in Wave 3
(Plan 04.5-06).

Per D-04, cloud providers do NOT perform live model discovery in 4.5 — their
``list_models`` returns a static curated allow-list that mirrors
``Settings.get_available_providers()``.
"""
