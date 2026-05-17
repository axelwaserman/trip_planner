"""Concrete LLM provider implementations (Phase 4.5).

Each module in this package implements the structural ``LLMProvider`` Protocol
from :mod:`app.llm.protocol` for a specific backend:

- :mod:`app.llm.providers.ollama` — local Ollama daemon (dynamic discovery)
- :mod:`app.llm.providers.lmstudio` — local LM Studio daemon (dynamic discovery)
- :mod:`app.llm.providers.openai` — OpenAI cloud (curated model list)
- :mod:`app.llm.providers.anthropic` — Anthropic cloud (curated model list)

Per D-04, cloud providers do NOT perform live model discovery in 4.5 — their
``list_models`` returns a static curated allow-list that mirrors
``Settings.get_available_providers()``.
"""
