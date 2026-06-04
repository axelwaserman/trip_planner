"""Wave 0 RED stub: stream-time exception → ErrorEvent with ``_scrub`` invariant.

Per CONTEXT.md (Phase 4.7 contract preserved into Phase 5) and PATTERNS.md
``chat/service.py § Delta — preserved invariants``, when the underlying
``stream_function`` raises, ``ChatService.chat_stream`` must:

1. Catch the exception (do NOT let it propagate to the SSE generator).
2. Emit a final ``ErrorEvent`` whose ``raw_detail`` is the scrubbed exception
   string (``app.llm.log_scrubbing._scrub`` applied at the construction site).
3. Set ``error_code = ErrorCode.stream_error`` (per the existing taxonomy in
   ``app/chat/models.py``).

The Phase 4.7 ``test_chat_stream_scrubs_api_key_from_raw_detail`` analog tests
the same invariant for tool errors; this file extends the contract to the
PydanticAI ``stream_function`` substrate.

This file collects via ``pytest.importorskip`` until the Wave 1 fixture rewrite
introduces ``_MockLLMProvider(LLMProvider)`` with a ``stream_function``-injected
exception path.
"""

import pytest

fixtures_llm = pytest.importorskip("tests.fixtures.llm")
make_chat_service_with_mock_llm = fixtures_llm.make_chat_service_with_mock_llm
default_session_config = fixtures_llm.default_session_config

from app.chat.models import ErrorEvent  # noqa: E402  # imported for type narrowing


async def test_chat_stream_emits_error_event_on_exception() -> None:
    """Exception in stream_function → ErrorEvent with scrubbed raw_detail.

    Today (Wave 0) the fixture's ``_MockLLMProvider`` does not accept a
    ``stream_function`` callable; the Wave 1 rewrite adds the ``streams``
    list-of-lists shape AND the per-chunk failure injection used here.

    The "sk-secret" string is the canary: ``app.llm.log_scrubbing._scrub``
    must rewrite it to ``sk-[REDACTED]`` so the exception text never reaches
    the SSE wire intact.
    """
    secret = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA"

    # Wave 1 fixture API: a ``streams`` argument that is a callable raising
    # an exception, signalling "fail the stream_function". The exact shape
    # is defined by Wave 1's fixtures rewrite; this test pins the contract.
    def boom() -> None:
        raise RuntimeError(f"upstream failure with key {secret}")

    service = make_chat_service_with_mock_llm(boom)  # type: ignore[arg-type]
    conversation_id, _ = await service.create_session(default_session_config(), user_id="u")

    events = [e async for e in service.chat_stream("hi", conversation_id)]
    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) == 1, "exactly one ErrorEvent expected"
    err = error_events[0]
    assert isinstance(err, ErrorEvent)
    assert err.raw_detail is not None
    # _scrub from app.llm.log_scrubbing rewrites sk-* keys to sk-[REDACTED].
    assert secret not in err.raw_detail
    assert "sk-[REDACTED]" in err.raw_detail
