"""Unit tests for POST /api/providers/{provider}/test (D-14).

Pattern: TestClient with monkeypatched ``httpx.AsyncClient`` (the canonical 4.2
idiom) to exercise the four paths — valid key, invalid key, network error, and
the Anthropic 429-as-valid quirk (researcher A3) — without hitting real cloud
APIs. The api_key never crosses the response or log boundary; that invariant
gets a dedicated assertion.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def _make_response(status_code: int) -> MagicMock:
    """Build a MagicMock matching httpx.Response shape with .raise_for_status semantics.

    For 4xx/5xx outside the explicit OK set (200, 401, 429), ``raise_for_status``
    raises an :class:`httpx.HTTPStatusError`, mirroring the production code path.
    """
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    if status_code >= 400 and status_code != 401 and status_code != 429:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom",
            request=MagicMock(),
            response=response,
        )
    return response


def test_test_returns_401_without_auth(client: TestClient) -> None:
    response = client.post(
        "/api/providers/openai/test",
        json={"api_key": "sk-x"},
    )
    assert response.status_code == 401


def test_openai_valid_key_returns_200(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(return_value=_make_response(200)),
    )
    response = client.post(
        "/api/providers/openai/test",
        headers=auth_headers,
        json={"api_key": "sk-valid"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_api_key_returns_400(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(return_value=_make_response(401)),
    )
    response = client.post(
        "/api/providers/openai/test",
        headers=auth_headers,
        json={"api_key": "sk-bogus"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_api_key"


def test_network_error_returns_502(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(side_effect=httpx.ConnectError("refused")),
    )
    response = client.post(
        "/api/providers/openai/test",
        headers=auth_headers,
        json={"api_key": "sk-x"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "provider_unreachable"


def test_anthropic_invalid_key_returns_400(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        AsyncMock(return_value=_make_response(401)),
    )
    response = client.post(
        "/api/providers/anthropic/test",
        headers=auth_headers,
        json={"api_key": "sk-ant-bogus", "model": "claude-3-5-sonnet-20241022"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_api_key"


def test_anthropic_rate_limit_treated_as_valid(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per researcher A3 — 429 means key is valid, just rate-limited."""
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        AsyncMock(return_value=_make_response(429)),
    )
    response = client.post(
        "/api/providers/anthropic/test",
        headers=auth_headers,
        json={"api_key": "sk-ant-x", "model": "claude-3-5-sonnet-20241022"},
    )
    assert response.status_code == 200


def test_unknown_provider_returns_400(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Local providers reject /test (use /refresh instead)."""
    response = client.post(
        "/api/providers/ollama/test",
        headers=auth_headers,
        json={"api_key": "n/a"},
    )
    assert response.status_code == 400


def test_api_key_not_in_response_or_logs(
    client: TestClient,
    auth_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-04.5-06b-01 mitigation — api_key never crosses response or log boundary."""
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(return_value=_make_response(401)),
    )
    secret_key = "sk-supersecretvaluethatshouldnotappear"
    with caplog.at_level("DEBUG"):
        response = client.post(
            "/api/providers/openai/test",
            headers=auth_headers,
            json={"api_key": secret_key},
        )
    # Assert the secret never appears in the response body.
    assert secret_key not in response.text
    # Assert the secret never appears in any log record emitted by our routes.
    for record in caplog.records:
        assert secret_key not in record.getMessage()
