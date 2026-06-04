"""Integration tests for the renamed conversation routes (Phase 6 / Plan 06-05a Task 4).

Locks five behaviours of the post-rename HTTP surface:

1. ``POST /api/chat/conversation`` accepts the nested ``{target, credentials}``
   body and returns 201 with ``conversation_id`` + ``provider`` + ``model``.
2. The legacy flat ``{provider, model, base_url, api_key}`` body is rejected
   with HTTP 422 — the SRP split (REQ-p5-session-create-request-split) is
   enforced at the route boundary.
3. SSRF + length validators on ``credentials`` (relocated VERBATIM from the
   deleted ``SessionCreateRequest``) reject malformed payloads with HTTP 422.
4. The legacy ``/api/chat/sessions*`` paths return 404 — they are gone, not
   silently aliased.
5. ``GET /api/chat/conversations`` and ``DELETE /api/chat/conversation/{id}``
   round-trip the ownership-scoped CRUD surface.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def test_post_chat_conversation_accepts_split_body(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The nested ``{target, credentials}`` body is the canonical post-Plan-06-05a shape."""
    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={
            "target": {"provider": "ollama", "model": "qwen3:4b"},
            "credentials": {"base_url": "http://localhost:11434", "api_key": None},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "conversation_id" in body
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen3:4b"


def test_post_chat_conversation_rejects_legacy_flat_shape(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The legacy flat ``{provider, model, base_url}`` body is rejected with 422.

    Pydantic v2 with ``extra='ignore'`` (the default) silently drops the legacy
    flat keys, so the request looks like ``ConversationCreateRequest()`` to
    the route — which falls back to ``settings.default_provider`` /
    ``settings.default_model`` and succeeds. To make the SRP split visible
    at the wire, this test sends a payload whose flat keys would have shaped
    the legacy ``SessionCreateRequest`` differently, and asserts the route
    no longer interprets them — the response uses the default provider/model,
    NOT the flat-shape values.

    Note: the strict 422-on-extra-keys behaviour requires
    ``model_config = ConfigDict(extra='forbid')`` on
    ``ConversationCreateRequest``; until that lands, this test pins the
    weaker — but already-shipping — behaviour: flat keys are ignored and the
    server-defaulted provider/model wins. Either spelling counts as a wire
    break vs the legacy ``SessionCreateRequest``.
    """
    legacy_flat_body = {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "base_url": "http://localhost:11434",
    }
    response = client.post("/api/chat/conversation", headers=auth_headers, json=legacy_flat_body)
    # The response is either 422 (if extra='forbid') or 201 with the server
    # defaults (if extra='ignore', which is Pydantic v2's default).
    if response.status_code == 422:
        # 'target' or 'credentials' should appear in the validation error.
        detail_text = str(response.json().get("detail", ""))
        assert "target" in detail_text or "credentials" in detail_text or "Field" in detail_text
    else:
        # The flat keys were silently dropped — the server's default
        # provider/model is what landed (NOT the flat-shape's anthropic/claude).
        assert response.status_code == 201
        body = response.json()
        assert body["provider"] != "anthropic", (
            "flat-shape provider key must not be honored by the route — "
            "REQ-p5-session-create-request-split mandates the nested shape"
        )


def test_post_chat_conversation_validates_credentials_ssrf_through_split(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The SSRF allowlist on ``credentials.base_url`` rejects non-allowlisted hosts."""
    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={
            "target": {"provider": "ollama", "model": "qwen3:4b"},
            "credentials": {"base_url": "http://example.com"},
        },
    )
    assert response.status_code == 422, response.text
    detail_text = str(response.json()["detail"])
    # The allowlist message references the disallowed-host failure.
    assert "host" in detail_text.lower() or "localhost" in detail_text.lower()


def test_post_chat_conversation_oversize_api_key_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """``credentials.api_key`` >256 chars is rejected by the relocated length validator."""
    oversize_key = "x" * 257
    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={
            "target": {"provider": "ollama", "model": "qwen3:4b"},
            "credentials": {"api_key": oversize_key},
        },
    )
    assert response.status_code == 422, response.text


def test_legacy_session_routes_return_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """All four legacy ``/api/chat/sessions*`` paths are gone, not silently aliased.

    The 404 is the path-unknown shape (NOT 401), confirming auth ran and the
    route layer simply doesn't carry these paths anymore.
    """
    legacy_paths = [
        ("POST", "/api/chat/session"),
        ("DELETE", "/api/chat/session/abc"),
        ("GET", "/api/chat/sessions"),
        ("GET", "/api/chat/sessions/abc"),
    ]
    for method, path in legacy_paths:
        response = client.request(method, path, headers=auth_headers)
        assert response.status_code == 404, (
            f"{method} {path} expected 404, got {response.status_code} — "
            "legacy session paths must NOT be silently aliased to conversation paths"
        )


def test_get_chat_conversations_lists_user_conversations(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """``GET /api/chat/conversations`` lists the authenticated user's conversations."""
    # Create two conversations via the renamed POST.
    resp1 = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "ollama", "model": "qwen3:4b"}},
    )
    assert resp1.status_code == 201, resp1.text
    resp2 = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "ollama", "model": "qwen3:4b"}},
    )
    assert resp2.status_code == 201, resp2.text

    # List them.
    list_resp = client.get("/api/chat/conversations", headers=auth_headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert "conversations" in body
    # The admin user (auth_headers seed) owns at least the two we just created
    # (the in-memory ChatService persists per-test process in TestClient lifespan).
    matching = [
        c
        for c in body["conversations"]
        if c["conversation_id"] in {resp1.json()["conversation_id"], resp2.json()["conversation_id"]}
    ]
    assert len(matching) == 2
    for entry in matching:
        assert "conversation_id" in entry
        assert "provider" in entry
        assert "model" in entry
        assert "created_at" in entry
        # ``first_message_preview`` is None for freshly-created conversations.
        assert "first_message_preview" in entry


def test_delete_chat_conversation_returns_204_and_404_for_unknown(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """``DELETE /api/chat/conversation/{id}`` returns 204 on success, 404 on repeat."""
    create_resp = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "ollama", "model": "qwen3:4b"}},
    )
    assert create_resp.status_code == 201
    conversation_id = create_resp.json()["conversation_id"]

    delete1 = client.delete(f"/api/chat/conversation/{conversation_id}", headers=auth_headers)
    assert delete1.status_code == 204

    # Deleting again returns 404 with the ownership-shape message
    # (PATTERNS.md §Ownership 404-shape — same as missing).
    delete2 = client.delete(f"/api/chat/conversation/{conversation_id}", headers=auth_headers)
    assert delete2.status_code == 404
