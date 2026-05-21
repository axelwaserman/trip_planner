"""Authentication module — JWT via pyjwt, passwords via pwdlib[argon2]."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from app.auth.exceptions import UserNotFoundError
from app.auth.models import User
from app.auth.repository import _DUMMY_HASH, UserRepository
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")


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
    delta = expires_delta if expires_delta is not None else timedelta(minutes=settings.jwt_expire_minutes)
    to_encode["exp"] = datetime.now(UTC) + delta
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def get_user_repository() -> UserRepository:
    """Placeholder dependency — overridden in main.py lifespan startup.

    T-4.9.02-B: Raises RuntimeError if the lifespan override is missing,
    ensuring unauthenticated access is impossible before the override is
    registered (fail-fast rather than silently falling through).
    """
    raise RuntimeError("UserRepository not configured")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    """Decode the Bearer JWT and return the matching user.

    Args:
        token: Bearer JWT extracted by oauth2_scheme.
        repo: Injected UserRepository (resolved via dependency override).

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

    try:
        user_in_db = repo.get_user(username)
    except UserNotFoundError:
        raise credentials_exception from None
    return user_in_db


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
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> dict[str, str]:
    """Authenticate with username + password and return a signed JWT.

    Args:
        form_data: OAuth2 form with ``username`` and ``password`` fields.
        repo: Injected UserRepository (resolved via dependency override).

    Returns:
        Dict with ``access_token`` (JWT) and ``token_type`` = ``"bearer"``.

    Raises:
        HTTPException 400: Credentials are incorrect.
    """
    try:
        user = repo.get_user(form_data.username)
    except UserNotFoundError:
        # Run a dummy verify to equalise timing — prevents username enumeration.
        repo.verify_password(form_data.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        ) from None
    if not repo.verify_password(form_data.password, user.hashed_password):
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
