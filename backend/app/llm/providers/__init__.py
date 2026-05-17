"""Concrete LLM provider implementations (Phase 4.5).

Each module in this subpackage defines a class implementing the
:class:`app.llm.protocol.LLMProvider` Protocol structurally (no inheritance).
The :class:`app.llm.factory.LLMProviderFactory` dispatches to these classes
per-session via ``match`` against a fixed provider name.
"""
