"""Provider domain models.

Pydantic models for the provider discovery and refresh endpoints
(Plan 04.5-06b). Also hosts ``SessionCreateError`` — the structured probe
failure envelope surfaced via ``HTTPException.detail`` on
``POST /api/chat/conversation`` when the chosen provider/model fails its
pre-flight probe.

Phase 6 / Plan 06-05a (REQ-p5-provider-info-split) splits the legacy
``ProviderInfo`` class into :class:`LocalProviderInfo` and
:class:`CloudProviderInfo` behind a :data:`ProviderInfoResponse` discriminated
union. Local providers (ollama, lmstudio) carry a required ``base_url``;
cloud providers (openai, anthropic) carry an ``api_key_configured: bool`` and
NEVER expose the api_key itself on the wire (D-09 lock from Phase 5).

All models follow the Data Model Pattern: validators enforce invariants;
no business logic or external I/O.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.llm.errors import ProbeErrorCode


class SessionCreateError(BaseModel):
    """Structured probe failure surfaced via ``HTTPException.detail``.

    Mirrors :class:`app.services.provider_probe.ProbeError` so the OpenAPI schema
    documents the F1-F4 error envelope returned by ``POST /api/chat/conversation``
    when the chosen provider/model fails its pre-flight probe (Plan 04).

    Note: the class name retains its ``Session`` prefix because the underlying
    ``ProbeErrorCode`` taxonomy is wire-level snake_case and is exempt from the
    Phase 6 / Plan 06-05a rename per CLAUDE.md "wire-level snake_case values
    are part of the contract".
    """

    error: ProbeErrorCode = Field(..., description="Stable error code matching the UI-SPEC F1-F4 taxonomy")
    message: str = Field(..., description="Human-readable summary for the banner heading")
    hint: str = Field(..., description="Actionable next step for the user")


class LocalProviderInfo(BaseModel):
    """Local-provider response shape (ollama, lmstudio) — base_url is always present.

    Field order: ``type`` is declared FIRST as the discriminator (Pydantic
    convention for tagged unions); ``base_url`` is required (``Field(...)``)
    so the local-provider response always carries the daemon's URL — the
    settings page uses it to pre-fill the URL field on first paint.
    """

    type: Literal["local"] = "local"
    available: bool
    models: list[str] = Field(default_factory=list)
    base_url: str = Field(..., description="Local-provider base URL — must be present.")


class CloudProviderInfo(BaseModel):
    """Cloud-provider response shape (openai, anthropic).

    ``api_key_configured`` is the only credential signal on the wire; the
    api_key itself never crosses the network (D-09 lock from Phase 5). The
    Phase 6 / Plan 06-05a split removes any ambiguity — there is NO
    ``api_key`` field on this class, period.
    """

    type: Literal["cloud"] = "cloud"
    available: bool
    models: list[str] = Field(default_factory=list)
    api_key_configured: bool = Field(
        ..., description="True iff Settings has a non-empty api_key for this provider."
    )


# Discriminated alias used by the route layer's ``-> dict[str, ProviderInfoResponse]``
# return type. Pydantic's ``discriminator="type"`` selects between the two
# concrete subclasses based on the wire-level ``type`` field — both serialise
# with their own field set, so cloud responses contain no ``base_url`` and
# local responses contain no ``api_key_configured`` (D-09 lock).
ProviderInfoResponse = Annotated[LocalProviderInfo | CloudProviderInfo, Field(discriminator="type")]


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
