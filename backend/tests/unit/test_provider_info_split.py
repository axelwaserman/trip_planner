"""Unit tests for the ProviderInfo discriminated-union split (REQ-p5-provider-info-split).

Phase 6 / Plan 06-05a Task 3: replace the legacy ``ProviderInfo`` class with
:class:`LocalProviderInfo` (type=local, required base_url) +
:class:`CloudProviderInfo` (type=cloud, api_key_configured: bool) behind a
:data:`ProviderInfoResponse` discriminated alias.

These tests pin:

1. ``LocalProviderInfo`` round-trips with type=local + required base_url.
2. ``LocalProviderInfo.base_url`` is required (omitting it raises).
3. ``CloudProviderInfo.api_key_configured`` is the only credential signal —
   the api_key itself never crosses the wire (D-09 lock from Phase 5).
4. ``ProviderInfoResponse`` discriminates on ``type``: local payloads
   resolve to ``LocalProviderInfo``, cloud payloads to ``CloudProviderInfo``.
5. Unknown ``type`` values raise ``ValidationError``.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.providers.models import (
    CloudProviderInfo,
    LocalProviderInfo,
    ProviderInfoResponse,
)


def test_local_provider_info_validates_with_base_url() -> None:
    """``LocalProviderInfo`` round-trips via ``model_dump_json()`` containing type=local."""
    info = LocalProviderInfo(available=True, models=["qwen3:4b"], base_url="http://localhost:11434")
    payload = info.model_dump_json()
    assert '"type":"local"' in payload
    assert '"base_url":"http://localhost:11434"' in payload
    assert '"available":true' in payload


def test_local_provider_info_requires_base_url() -> None:
    """Omitting ``base_url`` raises — local providers always carry the daemon URL."""
    with pytest.raises(ValidationError) as exc_info:
        LocalProviderInfo(available=True, models=[])  # type: ignore[call-arg]
    assert "base_url" in str(exc_info.value)


def test_local_provider_info_default_models_empty_list() -> None:
    """``models`` defaults to an empty list when the daemon has none yet."""
    info = LocalProviderInfo(available=False, base_url="http://localhost:11434")
    assert info.models == []
    assert info.available is False


def test_cloud_provider_info_carries_api_key_configured_boolean() -> None:
    """``CloudProviderInfo`` round-trips with ``api_key_configured: bool``; no api_key field."""
    info = CloudProviderInfo(available=True, models=["gpt-4"], api_key_configured=True)
    payload = info.model_dump_json()
    assert '"type":"cloud"' in payload
    assert '"api_key_configured":true' in payload
    # The api_key itself MUST NOT be a field on the model (D-09 lock).
    assert "api_key" not in CloudProviderInfo.model_fields or "api_key_configured" in CloudProviderInfo.model_fields
    # Stronger assertion: there is no bare ``api_key`` field — only ``api_key_configured``.
    field_names = set(CloudProviderInfo.model_fields.keys())
    assert "api_key" not in field_names
    assert "api_key_configured" in field_names


def test_cloud_provider_info_requires_api_key_configured() -> None:
    """``api_key_configured`` is required — every cloud entry must declare credential state."""
    with pytest.raises(ValidationError) as exc_info:
        CloudProviderInfo(available=True, models=["gpt-4"])  # type: ignore[call-arg]
    assert "api_key_configured" in str(exc_info.value)


def test_provider_info_response_discriminates_by_type() -> None:
    """Discriminated union: local payloads → LocalProviderInfo, cloud payloads → CloudProviderInfo."""
    adapter: TypeAdapter[ProviderInfoResponse] = TypeAdapter(ProviderInfoResponse)

    local = adapter.validate_python(
        {"type": "local", "available": True, "models": [], "base_url": "http://x"},
    )
    assert isinstance(local, LocalProviderInfo)
    assert local.base_url == "http://x"

    cloud = adapter.validate_python(
        {"type": "cloud", "available": True, "models": [], "api_key_configured": False},
    )
    assert isinstance(cloud, CloudProviderInfo)
    assert cloud.api_key_configured is False


def test_provider_info_response_rejects_unknown_type() -> None:
    """Unknown ``type`` discriminator value raises ``ValidationError``."""
    adapter: TypeAdapter[ProviderInfoResponse] = TypeAdapter(ProviderInfoResponse)
    with pytest.raises(ValidationError) as exc_info:
        adapter.validate_python({"type": "weird", "available": True, "models": []})
    # Pydantic surfaces the discriminator failure in the error message.
    assert "weird" in str(exc_info.value) or "discriminator" in str(exc_info.value).lower()


def test_local_provider_info_response_serializes_without_cloud_fields() -> None:
    """A local-typed ``ProviderInfoResponse`` payload contains no ``api_key_configured``."""
    info = LocalProviderInfo(available=True, models=[], base_url="http://localhost")
    dumped = info.model_dump()
    assert "api_key_configured" not in dumped
    assert "base_url" in dumped


def test_cloud_provider_info_response_serializes_without_local_fields() -> None:
    """A cloud-typed ``ProviderInfoResponse`` payload contains no ``base_url``."""
    info = CloudProviderInfo(available=True, models=[], api_key_configured=False)
    dumped = info.model_dump()
    assert "base_url" not in dumped
    # D-09 lock — bare api_key never lands on the wire.
    assert "api_key" not in dumped
    assert "api_key_configured" in dumped
