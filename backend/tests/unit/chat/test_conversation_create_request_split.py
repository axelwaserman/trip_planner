"""Unit tests for the ConversationCreateRequest SRP split (REQ-p5-session-create-request-split).

Phase 6 / Plan 06-05a Task 2: split the legacy ``SessionCreateRequest`` into
three Pydantic models — :class:`ConversationTarget` (provider/model),
:class:`ProviderCredentials` (base_url/api_key with relocated SSRF + length
validators), and :class:`ConversationCreateRequest` (the nested wrapper).

These tests pin:

1. ``ConversationTarget`` accepts a minimal payload (both fields default to None).
2. ``ProviderCredentials._strip_and_bound_api_key`` carries the byte-equivalent
   behaviour of the deleted ``SessionCreateRequest`` validator (strip,
   empty-to-None, 256-char cap).
3. ``ProviderCredentials._validate_base_url`` carries the byte-equivalent SSRF
   allowlist (localhost / 127.0.0.1 / host.docker.internal; http/https only).
4. ``ConversationCreateRequest`` validates with nested ``target`` + ``credentials``.

The route-level "flat shape returns 422" assertion lives in Task 4's
integration test — this file pins direct Pydantic model validation only.
"""

import pytest
from pydantic import ValidationError

from app.chat.models import (
    ConversationCreateRequest,
    ConversationTarget,
    ProviderCredentials,
)


def test_conversation_target_accepts_minimal_payload() -> None:
    """``ConversationTarget()`` validates with no fields → both default to None."""
    target = ConversationTarget()
    assert target.provider is None
    assert target.model is None


def test_conversation_target_accepts_partial_payload() -> None:
    """Partial payloads validate — provider OR model alone is fine."""
    only_provider = ConversationTarget(provider="ollama")
    assert only_provider.provider == "ollama"
    assert only_provider.model is None

    only_model = ConversationTarget(model="qwen3:4b")
    assert only_model.provider is None
    assert only_model.model == "qwen3:4b"


def test_provider_credentials_strips_and_bounds_api_key() -> None:
    """``api_key`` is stripped, empty-after-strip becomes None, >256 chars rejects."""
    # Whitespace stripping
    creds = ProviderCredentials(api_key="  abc  ")
    assert creds.api_key == "abc"

    # Empty-after-strip → None
    creds_empty = ProviderCredentials(api_key="   ")
    assert creds_empty.api_key is None

    # Already-None stays None
    creds_none = ProviderCredentials(api_key=None)
    assert creds_none.api_key is None

    # >256 chars rejects
    oversize = "x" * 257
    with pytest.raises(ValidationError) as exc_info:
        ProviderCredentials(api_key=oversize)
    assert "256" in str(exc_info.value) or "maximum" in str(exc_info.value)


def test_provider_credentials_ssrf_allowlist() -> None:
    """``base_url`` allowlist: localhost / 127.0.0.1 / host.docker.internal; http/https only."""
    # Allowed hosts
    for url in (
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "https://host.docker.internal:1234/v1",
    ):
        creds = ProviderCredentials(base_url=url)
        assert creds.base_url == url

    # Disallowed host → ValidationError
    with pytest.raises(ValidationError) as exc_info:
        ProviderCredentials(base_url="http://example.com")
    assert "host" in str(exc_info.value)

    # Non-http/https scheme → ValidationError
    with pytest.raises(ValidationError) as exc_info:
        ProviderCredentials(base_url="ftp://localhost:21")
    assert "http" in str(exc_info.value)


def test_provider_credentials_base_url_none_passes() -> None:
    """``base_url=None`` is the documented default and passes validation."""
    creds = ProviderCredentials(base_url=None)
    assert creds.base_url is None


def test_conversation_create_request_nests_target_and_credentials() -> None:
    """The nested shape validates; legacy flat shape does not bind to fields.

    Pydantic v2 with ``extra='ignore'`` (the default) silently drops the legacy
    flat keys; the route layer enforces the nested shape via the
    ``ConversationCreateRequest`` body type so a flat shape leaves ``target``
    + ``credentials`` at their defaults — Task 4's integration test asserts
    the route returns 422 in that case.
    """
    request = ConversationCreateRequest(
        target=ConversationTarget(provider="ollama", model="qwen3"),
        credentials=ProviderCredentials(base_url="http://localhost:11434", api_key="sk-fake"),
    )
    assert request.target.provider == "ollama"
    assert request.target.model == "qwen3"
    assert request.credentials is not None
    assert request.credentials.base_url == "http://localhost:11434"
    assert request.credentials.api_key == "sk-fake"


def test_conversation_create_request_credentials_optional() -> None:
    """``credentials`` defaults to None — local providers without override use Settings."""
    request = ConversationCreateRequest(target=ConversationTarget(provider="ollama"))
    assert request.credentials is None
    assert request.target.provider == "ollama"


def test_conversation_create_request_target_default_factory() -> None:
    """``target`` uses ``default_factory=ConversationTarget`` — no fields required."""
    request = ConversationCreateRequest()
    assert isinstance(request.target, ConversationTarget)
    assert request.target.provider is None
    assert request.target.model is None
    assert request.credentials is None
