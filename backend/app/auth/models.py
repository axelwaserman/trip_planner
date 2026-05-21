"""Auth domain models.

Provides the public and internal user representations used by the auth router
and by any future service that needs to reason about authenticated users.

These classes are intentionally thin Pydantic models (Data Model Pattern) — no
business logic beyond field declarations.  The password-hashing and JWT logic
live in ``app.api.routes.auth``.
"""

from pydantic import BaseModel


class User(BaseModel):
    """Public user representation (no sensitive fields)."""

    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    """Internal user representation including the hashed password."""

    hashed_password: str
