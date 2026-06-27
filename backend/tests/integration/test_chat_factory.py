"""Integration test: ``make_chat_service_with_mock_llm`` signature pinned.

Phase 5 / Plan 05-04 (Wave 3): per CONTEXT.md D-18 the public factory signature
is preserved across the LangChain → PydanticAI rewrite. Existing call sites
in tests/unit and tests/integration pass ``streams: list[list[Chunk]]``
positionally; widening or renaming the parameter would silently break them.
"""

import inspect

from tests.fixtures.llm import make_chat_service_with_mock_llm


def test_factory_signature_unchanged() -> None:
    """The factory accepts exactly one parameter named ``streams`` (D-18)."""
    sig = inspect.signature(make_chat_service_with_mock_llm)
    params = list(sig.parameters)
    assert params == ["streams"], f"factory signature drifted: {params}"
