"""Provider domain models.

Pydantic models for the provider discovery, refresh, and test endpoints
(Plan 04.5-06b).  Also hosts ``SessionCreateError`` — the structured probe
failure envelope surfaced via ``HTTPException.detail`` on
``POST /api/chat/session`` when the chosen provider/model fails its
pre-flight probe.

All models follow the Data Model Pattern: validators enforce invariants;
no business logic or external I/O.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.llm.errors import ProbeErrorCode


class SessionCreateError(BaseModel):
    """Structured probe failure surfaced via ``HTTPException.detail``.

    Mirrors :class:`app.services.provider_probe.ProbeError` so the OpenAPI schema
    documents the F1-F4 error envelope returned by ``POST /api/chat/session``
    when the chosen provider/model fails its pre-flight probe (Plan 04).
    """

    error: ProbeErrorCode = Field(..., description="Stable error code matching the UI-SPEC F1-F4 taxonomy")
    message: str = Field(..., description="Human-readable summary for the banner heading")
    hint: str = Field(..., description="Actionable next step for the user")


class ProviderInfo(BaseModel):
    """Single provider entry in the GET /api/providers response (D-25).

    The legacy 4.2 shape carried only ``available`` + ``models``; Plan 04.5-06b
    adds ``base_url`` so the settings page can pre-fill the local-provider URL
    field. Cloud providers (OpenAI, Anthropic) leave ``base_url`` as ``None``;
    local providers (Ollama, LM Studio) populate it from ``Settings``.
    """

    available: bool = Field(..., description="True when the provider is reachable / has credentials.")
    models: list[str] = Field(
        default_factory=list, description="Model identifiers — discovered for local, curated for cloud."
    )
    base_url: str | None = Field(
        default=None,
        description="Local-provider base URL (e.g., 'http://localhost:11434'); None for cloud providers.",
    )


class ProviderRefreshEntry(BaseModel):
    """Single provider entry in the refresh response (D-06)."""

    name: str = Field(..., description="Provider name (e.g., 'ollama', 'lmstudio').")
    models: list[str] = Field(default_factory=list, description="Discovered model ids; empty when unreachable.")
    available: bool = Field(..., description="True when the last refresh attempt succeeded for this provider.")
    error: str | None = Field(
        default=None,
        description="Wire-level error code when unreachable (e.g., 'provider_unreachable').",
    )


class ProviderRefreshResponse(BaseModel):
    """Response shape for POST /api/providers/refresh (D-06)."""

    providers: list[ProviderRefreshEntry] = Field(..., description="One entry per local provider class.")


class ProviderTestRequest(BaseModel):
    """Request payload for POST /api/providers/{provider}/test (D-14).

    api_key length is bounded to 256 chars (mirrors SessionCreateRequest's
    validator) so pathological inputs cannot exhaust memory or downstream
    cloud APIs. Whitespace is stripped before length validation.
    """

    api_key: str = Field(..., min_length=1, description="Cloud provider API key to validate.")
    model: str | None = Field(
        default=None,
        description="Optional model id; required for the Anthropic test path (researcher A8).",
    )

    @field_validator("api_key")
    @classmethod
    def _strip_and_bound_api_key(cls, v: str) -> str:
        """Strip whitespace, raise on empty-after-strip, cap length at 256 chars."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("api_key must not be empty after whitespace stripping")
        if len(stripped) > 256:
            raise ValueError("api_key exceeds maximum length (256 chars)")
        return stripped


class ProviderTestResponse(BaseModel):
    """Success response for POST /api/providers/{provider}/test (D-14).

    Failure paths raise HTTPException with a ProbeError detail; this model
    is only emitted on a 200 success.
    """

    status: Literal["ok"] = Field(..., description="Always 'ok' on the success path.")
