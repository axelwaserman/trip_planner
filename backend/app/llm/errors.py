"""Wire-level error taxonomy for the LLM provider layer.

Relocated from :mod:`app.services.provider_probe` in Phase 4.5. The wire-level
string values of every member are **unchanged** so the frontend's
``mapProbeError`` continues to work without modification — do NOT rename the
enum values when extending this module.

CLAUDE.md cites this enum as the canonical example of the
"cross-module taxonomies use ``StrEnum``, not duplicated ``Literal[...]`` unions"
rule. The canonical pointer moves from ``app.services.provider_probe.ProbeErrorCode``
to ``app.llm.errors.ProbeErrorCode`` with this relocation.

The new ``INVALID_API_KEY = "invalid_api_key"`` member is reserved per
``04.5-RESEARCH.md`` §"Error Contract" for live cloud-key validation (failure
mode F5). Phase 4.5 does NOT yet ship a route that emits it — the value lands
here so future phases (cloud ``/test`` endpoint) extend the enum without a
wire-level renumber. Until then, the four-member enum is intentional.
"""

from enum import StrEnum

from pydantic import BaseModel


class ProbeErrorCode(StrEnum):
    """Wire-level taxonomy shared by :class:`ProbeError` and ``SessionCreateError``.

    A single source of truth for the F1-F4 codes the frontend's
    ``mapProbeError`` consumes. ``provider_unreachable`` covers any provider's
    network-level failure (currently only Ollama issues live HTTP, but the
    symbol stays generic so future cloud probes plug in without a rename).

    Per CLAUDE.md, the wire-level snake_case values are part of the contract:
    they are consumed by the frontend's ``mapProbeError`` and must NOT be
    renamed. New error codes are appended; existing codes are immutable.
    """

    PROVIDER_UNREACHABLE = "provider_unreachable"
    MODEL_NOT_INSTALLED = "model_not_installed"
    MISSING_API_KEY = "missing_api_key"
    INVALID_API_KEY = "invalid_api_key"


class ProbeError(BaseModel):
    """Structured probe failure — maps to UI-SPEC F1/F2/F3/F5."""

    error: ProbeErrorCode
    message: str
    hint: str
