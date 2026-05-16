"""Authentication module — JWT via pyjwt, passwords via pwdlib[argon2]."""

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_password_hasher = PasswordHash([Argon2Hasher()])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(BaseModel):
    """Public user representation (no sensitive fields)."""

    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    """Internal user representation including the hashed password."""

    hashed_password: str


# ---------------------------------------------------------------------------
# In-memory user store
# ---------------------------------------------------------------------------


def load_users_from_env() -> dict[str, UserInDB]:
    """Build the in-memory user store from the AUTH_USERS environment variable.

    AUTH_USERS format: ``user1:pass1,user2:pass2``

    Falls back to ``admin:admin`` when the variable is absent.

    Malformed entries (missing colon, empty username/password) are skipped
    with a warning.
    """
    raw = os.environ.get("AUTH_USERS", settings.auth_users)
    users: dict[str, UserInDB] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            logger.warning("Skipping malformed AUTH_USERS entry (no colon): %r", entry)
            continue
        username, _, password = entry.partition(":")
        username = username.strip()
        password = password.strip()
        if not username or not password:
            logger.warning("Skipping AUTH_USERS entry with empty username or password.")
            continue
        users[username] = UserInDB(
            username=username,
            hashed_password=_password_hasher.hash(password),
            disabled=False,
        )
    return users


# Module-level user store — populated once at import time.
_users_db: dict[str, UserInDB] = load_users_from_env()


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches *hashed_password*."""
    return _password_hasher.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(
    data: dict[str, object],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT containing *data* as the payload.

    Args:
        data: Claims to include in the token payload.
        expires_delta: Custom expiry; defaults to ``settings.jwt_expire_minutes``.

    Returns:
        A signed JWT string.
    """
    to_encode = dict(data)
    delta = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode["exp"] = datetime.now(UTC) + delta
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """Decode the Bearer JWT and return the matching user.

    Raises:
        HTTPException 401: Token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception from None

    user = _users_db.get(username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the authenticated user is not disabled.

    Raises:
        HTTPException 400: User account is disabled.
    """
    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> dict[str, str]:
    """Authenticate with username + password and return a signed JWT.

    Args:
        form_data: OAuth2 form with ``username`` and ``password`` fields.

    Returns:
        Dict with ``access_token`` (JWT) and ``token_type`` = ``"bearer"``.

    Raises:
        HTTPException 400: Credentials are incorrect.
    """
    user = _users_db.get(form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        )
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Return the currently authenticated user's profile.

    Mounted at ``/api/auth/me`` once main.py applies the router prefix.
    """
    return current_user
