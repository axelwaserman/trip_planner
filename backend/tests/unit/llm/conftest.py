"""Shared fixtures for app.llm.* unit tests.

Provides ``mock_ollama_tags_response`` — a factory fixture that returns a callable
``(model_names: list[str]) -> MagicMock`` building an ``httpx.Response`` mock that
mimics the Ollama ``/api/tags`` payload shape.

The factory pattern (fixture returns a callable) lets each test customize the
``model_names`` without redefining the helper. The shape itself is verbatim from
``backend/tests/unit/test_provider_probe.py::_mock_ollama_tags_response`` (the 4.2
analog) — preserving the existing defensive ``name`` AND ``model`` field pattern
documented in RESEARCH.md §"Pitfall 4: Ollama Response Shape Variance".

The ``auth_headers`` and ``mock_flight_client`` fixtures live in the parent
``backend/tests/conftest.py`` and are auto-discovered; do NOT redefine them here.
"""

from collections.abc import Callable
from unittest.mock import MagicMock

import httpx
import pytest


@pytest.fixture
def mock_ollama_tags_response() -> Callable[[list[str]], MagicMock]:
    """Factory fixture returning a builder for Ollama /api/tags response mocks.

    Usage::

        def test_foo(mock_ollama_tags_response):
            response = mock_ollama_tags_response(["qwen3:4b", "llama3:8b"])
            # response.json() -> {"models": [{"name": "qwen3:4b", "model": "qwen3:4b"}, ...]}

    The returned MagicMock has ``status_code=200``, a no-op ``raise_for_status``,
    and ``.json()`` returning the canonical Ollama shape with both ``name`` and
    ``model`` keys populated identically (verified live against Ollama 0.23.4 in
    RESEARCH.md §"Code Examples — Ollama Discovery").
    """

    def _build(model_names: list[str]) -> MagicMock:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.return_value = {"models": [{"name": name, "model": name} for name in model_names]}
        response.raise_for_status = MagicMock()
        return response

    return _build
