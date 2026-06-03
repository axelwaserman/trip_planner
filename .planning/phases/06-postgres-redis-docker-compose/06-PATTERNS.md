# Phase 6: Postgres + Docker Compose - Pattern Map

**Mapped:** 2026-06-03
**Files analyzed:** 25 (new + modified)
**Analogs found:** 22 / 25

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/db/__init__.py` | package | n/a | `backend/app/chat/__init__.py` | role-match |
| `backend/app/db/session.py` | infrastructure (DB engine + DI) | request-response | `backend/app/api/main.py` (lifespan + `app.state`) | role-match |
| `backend/app/db/models.py` | model (SQLModel tables) | CRUD | `backend/app/chat/models.py` (Pydantic Data Model Pattern) | role-match |
| `backend/app/chat/store.py` (extend) | abstract repository (events) | event-log append/load | `backend/app/auth/repository.py::UserRepository` ABC; existing `ConversationStore` ABC | exact (split) |
| `backend/app/chat/repository.py` (new) | abstract repository (meta CRUD) | CRUD | `backend/app/auth/repository.py::UserRepository` ABC | exact |
| `backend/app/auth/repository.py` (modify) | concrete repository (Postgres) | CRUD | `backend/app/auth/repository.py::EnvUserRepository` (replace) | exact |
| `backend/app/auth/exceptions.py` (extend) | domain exception | n/a | `backend/app/auth/exceptions.py::UserNotFoundError` | exact |
| `backend/app/api/main.py` (modify) | lifespan wiring | startup-shutdown | itself (current `lifespan`) | exact |
| `backend/app/api/routes/routes.py` (modify) | controller (chat conversations) | request-response + SSE | itself (existing routes) | exact |
| `backend/app/auth/routes.py` (modify) | controller (auth/login) | request-response | itself + ABC swap is transparent | exact |
| `backend/app/chat/service.py` (modify) | service (functional + state owner) | event-driven streaming | itself + new repos | exact |
| `backend/app/chat/models.py` (extend / split) | Pydantic request/response DTOs | request-response | `backend/app/chat/models.py::SessionCreateRequest`, `app/providers/models.py::ProviderInfo` | exact |
| `backend/app/providers/models.py` (modify — `ProviderInfo` split) | Pydantic response DTOs (discriminated) | request-response | `backend/app/chat/models.py::StreamEvent` (ABC + multi-inheritance subclass split) | role-match |
| `backend/app/config.py` (modify) | config | n/a | itself (current `Settings`) | exact |
| `backend/migrations/env.py` | infrastructure (alembic) | one-shot async | RESEARCH §"Pattern 2" (no in-repo analog) | no analog |
| `backend/migrations/script.py.mako` | infrastructure (alembic template) | n/a | alembic default — copy verbatim | no analog |
| `backend/alembic.ini` | config | n/a | alembic default | no analog |
| `backend/scripts/seed.py` | one-shot script | batch upsert | `backend/app/auth/repository.py::_load_users_from_env` (pwdlib usage) + RESEARCH §"Pattern 4" | role-match |
| `backend/seed.toml.example` | config sample | n/a | n/a | no analog |
| `docker-compose.yml` (root) | infrastructure | n/a | RESEARCH §"docker-compose.yml" (D-10 verbatim) | no analog |
| `justfile` (extend) | infrastructure (DX recipes) | n/a | `justfile` (existing recipes) | exact |
| `backend/tests/integration/db/conftest.py` | test fixture | request-response | `backend/tests/integration/conftest.py` (`monkeypatch` + autouse stub) | role-match |
| `backend/tests/unit/chat/test_postgres_message_store.py` | test (unit, repo) | event-log append/load | `backend/tests/unit/test_user_repository.py` | role-match |
| `backend/tests/unit/chat/test_postgres_conversation_repo.py` | test (unit, repo) | CRUD | `backend/tests/unit/test_user_repository.py` | role-match |
| `backend/tests/integration/test_conversation_routes.py` | test (integration, route) | request-response | `backend/tests/integration/test_session.py` | role-match |
| `frontend/src/types/chat.ts` (modify) | TypeScript types (rename) | n/a | itself (current types) | exact |
| `frontend/src/hooks/useChat.ts` + others (rename) | hooks/components (rename) | n/a | themselves | exact |

---

## Pattern Assignments

### `backend/app/auth/repository.py` — `PostgresUserRepository` replaces `EnvUserRepository`

**Analog:** `backend/app/auth/repository.py::EnvUserRepository` (lines 35-93)

**ABC pattern (preserve verbatim — lines 35-55):**
```python
from abc import ABC, abstractmethod

class UserRepository(ABC):
    """Abstract base class for user persistence backends.

    The auth routes depend on this ABC; concrete implementations
    (EnvUserRepository, future PostgresUserRepository) are injected via
    FastAPI's dependency override mechanism.
    """

    @abstractmethod
    def get_user(self, username: str) -> UserInDB:
        """Return UserInDB for *username*.

        Raises:
            UserNotFoundError: When *username* does not exist.
        """
        ...

    @abstractmethod
    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True if *plain* matches *hashed*."""
        ...
```

**Phase 6 changes (Phase 6 deletes `EnvUserRepository`, adds async `PostgresUserRepository`):**
- `get_user` becomes `async def` (CLAUDE.md async-only I/O constraint).
- `verify_password` stays sync (`pwdlib` is CPU-bound, not I/O).
- Constant-time enumeration guard (`_DUMMY_HASH`, line 32) MUST be preserved — `PostgresUserRepository` reuses the same `_password_hasher` module-level singleton (line 28).

**pwdlib hashing pattern (preserve — lines 25-32, 83-85):**
```python
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Module-level hasher singleton — DO NOT change the constructor; previously
# hashed passwords would become unverifiable.
_password_hasher = PasswordHash([Argon2Hasher()])
_DUMMY_HASH: str = _password_hasher.hash("__dummy__")

def verify_password(self, plain: str, hashed: str) -> bool:
    return _password_hasher.verify(plain, hashed)
```

**Argon2 verification path stays — only swap storage backend (CONTEXT.md `code_context.Reusable Assets`).**

**Async query shape (RESEARCH Pattern 1, sessionmaker injection):**
```python
class PostgresUserRepository(UserRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_user(self, username: str) -> UserInDB:
        async with self._sessionmaker() as session:
            row = (await session.execute(
                select(User).where(User.username == username)
            )).scalar_one_or_none()
            if row is None:
                raise UserNotFoundError(username)
            return UserInDB(
                username=row.username,
                hashed_password=row.hashed_password,
                disabled=row.disabled,
            )
```

**Auth route wiring stays unchanged** — `backend/app/auth/routes.py::login` (lines 113-145) calls `repo.get_user(...)` and `repo.verify_password(...)` through the ABC; only the concrete swap on line 117 of `main.py` changes:
```python
# main.py current line 70 (Phase 5)
app.state.user_repo = EnvUserRepository()

# main.py Phase 6
app.state.user_repo = PostgresUserRepository(_async_sessionmaker)
```

The `EnvUserRepository`-specific calls (`add_user`, `remove_user`, lines 87-93) go away with the class; tests that used them migrate to seeding rows via the sessionmaker.

---

### `backend/app/chat/store.py` — extend with `MessageStore` ABC + `InMemoryMessageStore` + `PostgresMessageStore` (D-05)

**Analog:** `backend/app/chat/store.py::ConversationStore` (lines 40-114) and `InMemoryConversationStore` (lines 117-161). The current `ConversationStore` ABC is the direct ancestor (D-06 splits it).

**ABC docstring conventions (preserve — lines 40-55):**
```python
class ConversationStore(ABC):
    """Abstract conversation store keyed by ``session_id`` (D-08).

    [...]
    """

    @abstractmethod
    async def append(self, session_id: str, messages: list[ModelMessage]) -> None:
        """Append ``messages`` to the session's history.

        [Args/Returns docstring per CLAUDE.md public-API rule.]
        """
        ...
```

**Phase 6 split (D-05/D-06):**
```python
# MessageStore: events only — append, load, delete (+ the helper that replaces
# the CR-04 _store getattr peek inside ChatService — see Anti-Patterns below).
class MessageStore(ABC):
    @abstractmethod
    async def append(self, conversation_id: UUID, messages: list[ModelMessage]) -> None: ...
    @abstractmethod
    async def load(self, conversation_id: UUID) -> list[ModelMessage]: ...
    @abstractmethod
    async def delete(self, conversation_id: UUID) -> None: ...
    @abstractmethod
    async def first_user_message_preview(self, conversation_id: UUID) -> str | None: ...
```

**InMemory impl pattern (preserve immutability invariant — lines 138-142):**
```python
class InMemoryMessageStore(MessageStore):
    def __init__(self) -> None:
        self._store: dict[UUID, list[ModelMessage]] = {}

    async def append(self, conversation_id: UUID, messages: list[ModelMessage]) -> None:
        existing = self._store.get(conversation_id, [])
        # Immutable concat per ~/.claude/rules/common/coding-style.md — never `.append()` in place.
        self._store[conversation_id] = existing + messages

    async def load(self, conversation_id: UUID) -> list[ModelMessage]:
        # Defensive copy — callers cannot mutate the store's internal state.
        return list(self._store.get(conversation_id, []))

    async def delete(self, conversation_id: UUID) -> None:
        self._store.pop(conversation_id, None)
```

**Postgres impl pattern (RESEARCH Pattern 3 — JSONB round-trip via `to_jsonable_python` + `ModelMessagesTypeAdapter`):**
```python
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

class PostgresMessageStore(MessageStore):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def append(
        self, conversation_id: UUID, messages: list[ModelMessage]
    ) -> None:
        async with self._sessionmaker() as session:
            current_max = (await session.execute(
                select(func.coalesce(func.max(Message.seq), 0))
                .where(Message.conversation_id == conversation_id)
            )).scalar_one()
            for offset, msg in enumerate(messages, start=1):
                session.add(Message(
                    conversation_id=conversation_id,
                    seq=current_max + offset,
                    payload=to_jsonable_python(msg),
                ))
            await session.commit()

    async def load(self, conversation_id: UUID) -> list[ModelMessage]:
        async with self._sessionmaker() as session:
            rows = (await session.execute(
                select(Message.payload)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.seq)
            )).scalars().all()
        return ModelMessagesTypeAdapter.validate_python(list(rows))
```

---

### `backend/app/chat/repository.py` (new) — `ConversationRepository` ABC (D-06)

**Analog:** `backend/app/auth/repository.py::UserRepository` ABC (lines 35-55) and `backend/app/chat/store.py::ConversationStore::list_for_user` (lines 97-114).

**ABC contract (5 concerns from D-06 — create, rename, list_for_user, bump_last_activity, delete):**
```python
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

class ConversationRepository(ABC):
    """Abstract meta-CRUD for conversations (D-06).

    Phase 6 split: events live on MessageStore; meta lives here. Both share
    the same `app.state` singleton wiring pattern as `UserRepository`.
    """

    @abstractmethod
    async def create(self, *, user_id: str, provider: str, model: str) -> UUID: ...
    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[ChatConversationInfo]: ...
    @abstractmethod
    async def get(self, conversation_id: UUID) -> ChatConversationInfo | None: ...
    @abstractmethod
    async def bump_last_activity(self, conversation_id: UUID) -> None: ...
    @abstractmethod
    async def delete(self, conversation_id: UUID) -> None: ...
```

**Open Question (RESEARCH OQ-3):** dedicated `bump_last_activity` vs generic `update`. Recommendation: dedicated method (narrower API; matches D-06 wording).

---

### `backend/app/db/session.py` — async engine + sessionmaker + FastAPI dep

**Analog:** None inside the codebase (new infrastructure). Use RESEARCH Pattern 1 verbatim.

**RESEARCH Pattern 1 (lines 315-345 of 06-RESEARCH.md):**
```python
# app/db/session.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings

# expire_on_commit=False — Pitfall 8 in RESEARCH: True (default) breaks SSE
# streams because attribute access after commit triggers a sync refresh.
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_overflow,
    echo=settings.debug,
)

_async_sessionmaker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session per request."""
    async with _async_sessionmaker() as session:
        yield session
```

**DI wiring pattern from `backend/app/auth/routes.py::get_user_repository` (lines 52-59):**
```python
def get_user_repository() -> UserRepository:
    """Placeholder dependency — overridden in main.py lifespan startup.

    Raises RuntimeError if the lifespan override is missing, ensuring
    unauthenticated access is impossible before the override is registered
    (fail-fast rather than silently falling through).
    """
    raise RuntimeError("UserRepository not configured")
```

Phase 6 adds the same fail-fast pattern for `get_message_store()`, `get_conversation_repository()`, and `get_db_session()`.

---

### `backend/app/db/models.py` — SQLModel tables

**Analog:** `backend/app/chat/models.py` (Data Model Pattern; thin Pydantic models with validators only) and RESEARCH §"Code Examples" → "Conversation + Message + User SQLModel tables" (lines 723-792).

**Pattern (Data Model Pattern from `backend/app/auth/models.py` lines 1-26):**
```python
"""Auth domain models.

Provides the public and internal user representations [...]

These classes are intentionally thin Pydantic models (Data Model Pattern) — no
business logic beyond field declarations.  The password-hashing and JWT logic
live in ``app.auth.routes``.
"""
```

**SQLModel tables (use RESEARCH Code Examples verbatim, with the Phase 6 rename):**
```python
# app/db/models.py
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "user"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=120)
    hashed_password: str = Field(max_length=200)
    disabled: bool = Field(default=False)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )


class Conversation(SQLModel, table=True):
    __tablename__ = "conversation"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
    )
    provider: str = Field(max_length=40)
    model: str = Field(max_length=120)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )
    last_activity_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )


class Message(SQLModel, table=True):
    __tablename__ = "message"
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: UUID = Field(
        sa_column=Column(ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False, index=True),
    )
    seq: int = Field(nullable=False)
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()"),
    )


# D-02 mandatory composite unique index for replay ordering.
Index("message_conv_seq", Message.conversation_id, Message.seq, unique=True)
```

**Pitfall 1 (RESEARCH):** pin `sqlmodel>=0.0.32` — earlier versions silently lose `Annotated[..., Field(max_length=...)]` constraints under Pydantic 2.12+.

---

### `backend/app/api/main.py` — extend lifespan with DB engine + new repos

**Analog:** `backend/app/api/main.py::lifespan` (lines 22-84) — exact pattern; just additive.

**Existing lifespan startup pattern (lines 39-76):**
```python
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Startup
    log_scrubber: ApiKeyScrubber = install_log_scrubber()
    flight_client = MockFlightAPIClient(seed=42)
    llm_factory = LLMProviderFactory(settings)
    conversation_store = InMemoryConversationStore()
    chat_service = ChatService(
        flight_client=flight_client,
        factory=llm_factory,
        conversation_store=conversation_store,
    )

    app.state.chat_service = chat_service
    app.state.llm_factory = llm_factory
    app.state.user_repo = EnvUserRepository()
    app.state.provider_models_cache = {}
    app.state.provider_models_cache_timestamps = {}

    yield

    cleaned_up = await chat_service.cleanup_expired_sessions(max_age_seconds=0)
    logger.info("Cleaned up %d sessions on shutdown", cleaned_up)
    uninstall_log_scrubber(log_scrubber)
```

**Phase 6 additions (CONTEXT.md `code_context.Integration Points`):**
```python
# new — Phase 6
from app.db.session import _async_sessionmaker, engine
from app.chat.store import PostgresMessageStore
from app.chat.repository import PostgresConversationRepository
from app.auth.repository import PostgresUserRepository

# inside lifespan startup, after llm_factory:
app.state.db_engine = engine
app.state.message_store = PostgresMessageStore(_async_sessionmaker)
app.state.conversation_repo = PostgresConversationRepository(_async_sessionmaker)
app.state.user_repo = PostgresUserRepository(_async_sessionmaker)  # replaces EnvUserRepository

chat_service = ChatService(
    flight_client=flight_client,
    factory=llm_factory,
    message_store=app.state.message_store,            # was conversation_store
    conversation_repo=app.state.conversation_repo,    # new
)

# inside lifespan shutdown, before uninstall_log_scrubber:
await engine.dispose()  # release pooled connections cleanly
```

**Override registration pattern (lines 105-122 — preserve, add new):**
```python
async def get_message_store_override(request: Request) -> MessageStore:
    return request.app.state.message_store

async def get_conversation_repository_override(request: Request) -> ConversationRepository:
    return request.app.state.conversation_repo

app.dependency_overrides[chat_routes.get_message_store] = get_message_store_override
app.dependency_overrides[chat_routes.get_conversation_repository] = get_conversation_repository_override
```

---

### `backend/app/api/routes/routes.py` — rename + request-model split (`REQ-p5-conversation-rename` + `REQ-p5-session-create-request-split`)

**Analog:** `backend/app/api/routes/routes.py::create_session` (lines 288-370) and `delete_session` (lines 373-408).

**Existing controller pattern (preserve auth + ownership shape — lines 86-93, 87-93):**
```python
@router.post("/api/chat/session", status_code=status.HTTP_201_CREATED)
async def create_session(
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: SessionCreateRequest | None = None,
) -> dict[str, str]:
    [...]
    # Same 404 shape on missing-vs-not-owner so a non-owner cannot
    # probe for session existence by status code.
    metadata = chat_service._metadata.get(request.session_id)
    if metadata is None or metadata.get("user_id") != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )
```

**Phase 6 rename** (D-03):
- `POST /api/chat/session` → `POST /api/chat/conversation`
- `DELETE /api/chat/session/{id}` → `DELETE /api/chat/conversation/{id}`
- `GET /api/chat/sessions` → `GET /api/chat/conversations`
- `GET /api/chat/sessions/{id}` → `GET /api/chat/conversations/{id}`
- `request.session_id` → `request.conversation_id` (route + DTO + SSE payloads)
- `chat_service._metadata` reads stay (rename happens inside `service.py` too).

**Phase 6 request-split (REQ-p5-session-create-request-split — analog: `chat/models.py::SessionCreateRequest` lines 179-231):**

Existing monolithic shape (lines 179-231) splits into:
```python
class ConversationTarget(BaseModel):
    """What to talk to."""
    provider: str
    model: str

class ProviderCredentials(BaseModel):
    """How to reach it. Validators relocated verbatim from SessionCreateRequest."""
    base_url: str | None = None
    api_key: str | None = None

    @field_validator("api_key")
    @classmethod
    def _strip_and_bound_api_key(cls, v: str | None) -> str | None:
        # Same body as lines 207-218 of current chat/models.py — RELOCATE, do not rewrite.
        ...

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        # Same body as lines 220-231 of current chat/models.py — RELOCATE, do not rewrite.
        ...

class ConversationCreateRequest(BaseModel):
    target: ConversationTarget
    credentials: ProviderCredentials | None = None
```

**Provider-info split (REQ-p5-provider-info-split — analog: `app.providers.models::ProviderInfo` lines 31-47, plus the StreamEvent ABC + multi-inheritance pattern from `app.chat.models::StreamEvent` lines 68-117):**
```python
class LocalProviderInfo(BaseModel):
    """Local providers (ollama, lmstudio) — base_url required."""
    type: Literal["local"] = "local"
    available: bool
    models: list[str] = Field(default_factory=list)
    base_url: str  # always present for local

class CloudProviderInfo(BaseModel):
    """Cloud providers (openai, anthropic) — api_key_configured flag."""
    type: Literal["cloud"] = "cloud"
    available: bool
    models: list[str] = Field(default_factory=list)
    api_key_configured: bool

# Discriminated union — same approach as StreamEvent:
ProviderInfoResponse = Annotated[
    LocalProviderInfo | CloudProviderInfo,
    Field(discriminator="type"),
]
```

---

### `backend/app/chat/service.py` — wire new repos; remove `_store` peek

**Analog:** itself (`backend/app/chat/service.py`).

**Critical CR-04 anti-pattern fix (lines 195-211 of current `service.py`):**
```python
def _first_message_preview(self, session_id: str) -> str | None:
    [...]
    # Defensive: read from the underlying ``_store`` dict to keep this method
    # synchronous. The in-memory impl exposes ``_store`` as a dict; an
    # ``AttributeError`` here means a non-in-memory impl was injected and
    # the caller (or Phase 6) should rewrite this to ``async``.
    store_dict = getattr(self._conversation_store, "_store", None)
    if store_dict is None:
        return None
```

This `getattr(..., "_store", None)` peek silently returns `None` against `PostgresMessageStore` (no `_store` attribute). **Phase 6 MUST move this onto a method on the ABC** — see `MessageStore.first_user_message_preview` in the ABC contract above. Same fix for `get_history_for_user` (lines 213-248) which also peeks into `_store`.

---

### `backend/app/config.py` — add `database_url`, remove `auth_users`

**Analog:** `backend/app/config.py::Settings` (lines 14-99) — exact pattern.

**Existing pattern (lines 24-28):**
```python
# Auth / JWT
jwt_secret: str = _DEFAULT_JWT_SECRET
jwt_algorithm: str = "HS256"
jwt_expire_minutes: int = 60
auth_users: str = "admin:admin"   # DELETE in Phase 6 (D-07)
```

**Existing warning pattern (lines 80-98 — `model_post_init`):**
```python
def model_post_init(self, __context: object) -> None:
    """Emit warnings when insecure defaults are still in use."""
    if self.jwt_secret == _DEFAULT_JWT_SECRET:
        logger.warning(
            "JWT_SECRET is set to the default value '%s'. "
            "Set the JWT_SECRET environment variable to a strong random secret "
            "before running in production.",
            _DEFAULT_JWT_SECRET,
        )
    if self.auth_users == _DEFAULT_AUTH_USERS:   # DELETE this branch
        logger.warning(...)
```

**Phase 6 additions (RESEARCH §"Settings additions"):**
```python
# Database (Phase 6 — D-01, D-11)
database_url: str = "postgresql+psycopg://trip_planner:trip_planner@localhost:5432/trip_planner"
db_pool_size: int = 5
db_pool_overflow: int = 10

# Seed mode (dev/test only — never true in prod)
seed_allow_non_local: bool = False
```

**Cross-reference deletion (CONTEXT.md / RESEARCH.md):** `_DEFAULT_AUTH_USERS` constant (line 11) and the `auth_users` field (line 28) and the `model_post_init` branch (lines 89-93) all delete in the same PR.

---

### Provider-info wire format split (REQ-p5-provider-info-split)

**Analog:** `backend/app/chat/models.py::StreamEvent` ABC + concrete subclass multi-inheritance (lines 68-171). Same discriminator-on-Literal approach.

**Pattern excerpt from `backend/app/chat/models.py` (lines 119-171):**
```python
class StreamEvent(ABC):  # noqa: B024 - intentional marker ABC
    """Marker ABC base for all SSE stream events. [...] """
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        sub_types = list(cls.__subclasses__())
        union = reduce(operator.or_, sub_types)
        annotated = Annotated[union, Field(discriminator="type")]
        return handler.generate_schema(annotated)

class ContentEvent(BaseModel, StreamEvent):
    type: Literal["content"] = "content"
    chunk: str = ""
    session_id: str

class ThinkingEvent(BaseModel, StreamEvent):
    type: Literal["thinking"] = "thinking"
    [...]
```

**Phase 6 may use the simpler `Annotated[A | B, Field(discriminator="type")]` if no `isinstance(event, ProviderInfoResponse)` checks are needed** — `ProviderInfoResponse` is a wire-format envelope, not an inheritance hierarchy.

---

### `backend/scripts/seed.py` (new) — idempotent seed

**Analog:** `backend/app/auth/repository.py::_load_users_from_env` (lines 96-119) — pwdlib hashing pattern. RESEARCH Pattern 4 (lines 511-563) shows the full SQL upsert.

**pwdlib usage (lines 110-118):**
```python
users[username] = UserInDB(
    username=username,
    hashed_password=_password_hasher.hash(password),  # Argon2 hash at seed time
    disabled=False,
)
```

**SQL upsert (RESEARCH Pattern 4 — verbatim, with Phase 6 rename `session` → `conversation`):**
```python
import asyncio
import sys
import tomllib
from pathlib import Path

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

_HASHER = PasswordHash([Argon2Hasher()])


async def seed(toml_path: Path) -> int:
    if not toml_path.exists():
        print(f"seed file not found: {toml_path}", file=sys.stderr)
        return 1
    data = tomllib.loads(toml_path.read_text())
    users = data.get("users", [])

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        for entry in users:
            username = entry["username"]
            password = entry["password"]
            disabled = entry.get("disabled", False)
            hashed = _HASHER.hash(password)
            await conn.execute(
                text("""
                    INSERT INTO "user" (username, hashed_password, disabled)
                    VALUES (:u, :h, :d)
                    ON CONFLICT (username)
                    DO UPDATE SET hashed_password = EXCLUDED.hashed_password,
                                  disabled = EXCLUDED.disabled
                """),
                {"u": username, "h": hashed, "d": disabled},
            )
        await conn.commit()
    await engine.dispose()
    return 0


if __name__ == "__main__":
    seed_file = Path(sys.argv[1] if len(sys.argv) > 1 else "seed.toml")
    raise SystemExit(asyncio.run(seed(seed_file)))
```

---

### `backend/migrations/env.py` — async + SQLModel.metadata

**Analog:** None inside the codebase (alembic is new in Phase 6). Use RESEARCH Pattern 2 (lines 354-426 of 06-RESEARCH.md) verbatim.

**Critical (Pitfall 2, RESEARCH lines 673-677):** Import every module that defines SQLModel tables BEFORE referencing `SQLModel.metadata`, otherwise `--autogenerate` produces empty migrations.

```python
# CRITICAL — register tables on SQLModel.metadata before targeting it.
from app.db import models  # noqa: F401
```

---

### `justfile` (extend) — compose + migrate + db-seed recipes

**Analog:** existing `justfile` (lines 1-83) — exact pattern (recipe per command, `cd backend && uv run …`).

**Existing recipe pattern (lines 9-10, 16-18):**
```makefile
backend:
    cd backend && uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000

test:
    cd backend && uv run pytest
```

**Phase 6 additions (RESEARCH §"Justfile additions" + D-08 / D-10 / D-11):**
```makefile
# Compose lifecycle (D-10)
compose-up:
    docker compose up -d --wait

compose-down:
    docker compose down

compose-down-clean:
    docker compose down -v

compose-logs:
    docker compose logs -f db

db-shell:
    docker compose exec db psql -U trip_planner -d trip_planner

# Migrations (D-11)
migrate:
    cd backend && uv run alembic upgrade head

migrate-create MSG:
    cd backend && uv run alembic revision --autogenerate -m "{{MSG}}"

# Seed (D-08)
db-seed:
    cd backend && uv run python scripts/seed.py
```

---

### `docker-compose.yml` (root)

**Analog:** None. Use D-10 verbatim from CONTEXT.md (Pitfall 4 → consider 5433:5432).

---

### `backend/tests/integration/db/conftest.py` (new)

**Analog:** `backend/tests/integration/conftest.py` (lines 53-77) — autouse `monkeypatch` fixture with opt-out marker.

**Existing pattern (autouse + opt-out via marker fixture — lines 54-77):**
```python
@pytest.fixture(autouse=True)
def _stub_local_provider_probes(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Auto-stub httpx.AsyncClient.get for every integration test.

    Tests that opt out by re-monkeypatching ``httpx.AsyncClient.get`` will see
    their patch override this one (the closer-scoped patch wins). Tests that
    need the real probe (none in CI) can request the ``unmocked_httpx``
    fixture to skip this stub.
    """
    if "unmocked_httpx" in request.fixturenames:
        yield
        return
    monkeypatch.setattr(...)
    yield
```

**Phase 6 pattern (`pytest-postgresql` `postgresql_noproc` against compose db — RESEARCH §"Test DB strategy"):**
```python
import pytest
from pytest_postgresql.factories import postgresql_noproc

# Pointed at the compose db; reuses the live container.
postgresql_my_proc = postgresql_noproc(host="localhost", port=5432, user="trip_planner")

@pytest.fixture
async def db_engine(postgresql_my_proc, ...):
    """Per-test async engine with template-clone isolation."""
    [...]
```

---

### `backend/tests/unit/chat/test_postgres_message_store.py`, `test_postgres_conversation_repo.py`

**Analog:** `backend/tests/unit/test_user_repository.py` — repository unit tests against the existing pattern.

(Did not Read in detail; the test directory exists and follows path-based selection per CLAUDE.md. Planner will mirror the file's structure for the new repo unit tests.)

---

## Shared Patterns

### ABC + first-impl + DI override (cross-cutting)

**Source:** `backend/app/auth/repository.py::UserRepository` (lines 35-55) + `backend/app/auth/routes.py::get_user_repository` (lines 52-59) + `backend/app/api/main.py::get_user_repository_override` (lines 115-117) + `app.dependency_overrides` registration (line 122).

**Apply to:** `MessageStore`, `ConversationRepository`, `PostgresUserRepository`.

The four-step pattern:
1. **ABC** in domain module (`app/chat/store.py`, `app/chat/repository.py`).
2. **Placeholder dep** in route module that raises `RuntimeError("not configured")` — fail-fast.
3. **Concrete singleton** instantiated in `lifespan` startup, stashed on `app.state`.
4. **Override registration** at module load via `app.dependency_overrides[placeholder] = override`.

```python
# Step 2 (route module — fail-fast placeholder, lines 52-59 of auth/routes.py):
def get_user_repository() -> UserRepository:
    """Placeholder dependency — overridden in main.py lifespan startup.

    Raises RuntimeError if the lifespan override is missing, ensuring
    unauthenticated access is impossible before the override is registered.
    """
    raise RuntimeError("UserRepository not configured")

# Step 3 (main.py lifespan, line 70):
app.state.user_repo = EnvUserRepository()  # Phase 6: PostgresUserRepository(_async_sessionmaker)

# Step 4 (main.py module-level, lines 115-122):
async def get_user_repository_override(request: Request) -> UserRepository:
    return request.app.state.user_repo

app.dependency_overrides[auth_routes.get_user_repository] = get_user_repository_override
```

---

### StrEnum for cross-module taxonomies (CLAUDE.md canonical)

**Source:** `backend/app/llm/errors.py::ProbeErrorCode` (lines 25-41).
**Apply to:** Any new wire-level codes Phase 6 introduces (e.g., a future `ConversationStatus` enum if D-06 grows one). For Phase 6 specifically, **no new StrEnum is required** — the existing `ErrorCode` (chat/models.py line 51) and `ProbeErrorCode` cover the wire-level error surface.

```python
# backend/app/llm/errors.py (lines 20-41) — canonical example referenced by CLAUDE.md
from enum import StrEnum

class ProbeErrorCode(StrEnum):
    """Wire-level taxonomy shared by ProbeError and SessionCreateError. [...]

    Per CLAUDE.md, the wire-level snake_case values are part of the contract:
    they are consumed by the frontend's mapProbeError and must NOT be renamed.
    New error codes are appended; existing codes are immutable.
    """
    PROVIDER_UNREACHABLE = "provider_unreachable"
    MODEL_NOT_INSTALLED = "model_not_installed"
    MISSING_API_KEY = "missing_api_key"
    INVALID_API_KEY = "invalid_api_key"
```

**Rule (CLAUDE.md):** If a Phase 6 wave introduces shared string codes between two modules (e.g., conversation status strings), define once as `StrEnum`, never duplicate as `Literal[...]` unions.

---

### Async-only I/O on every store / repo method

**Source:** `backend/app/chat/store.py::ConversationStore` (line 18 of docstring + every method `async def`) + CLAUDE.md "all I/O must be async def".

```python
# Even the in-memory impl that never blocks must be async — the ABC must
# match the contract its concrete impls (Postgres) require.
async def append(self, conversation_id: UUID, messages: list[ModelMessage]) -> None: ...
```

**Apply to:** Every method on `MessageStore`, `ConversationRepository`, and `PostgresUserRepository`.

---

### Ownership 404-shape (CR-02 — horizontal privilege escalation guard)

**Source:** `backend/app/api/routes/routes.py::chat` (lines 86-93), `delete_session` (lines 396-403), `retry_tool_call` (lines 180-185), `get_chat_session_history` (lines 559-577).

```python
# Same 404 shape on missing-vs-not-owner so a non-owner cannot
# probe for session existence by status code.
metadata = chat_service._metadata.get(request.session_id)
if metadata is None or metadata.get("user_id") != current_user.username:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Session {request.session_id} not found",
    )
```

**Apply to:** Every conversation-scoped route after rename (`conversation_id`, `Conversation {id} not found`). The ownership check moves from `_metadata` peek to `ConversationRepository.get(conversation_id)` + `row.user_id == current_user.username`.

---

### Pydantic Data Model Pattern (no business logic in models)

**Source:** `backend/app/auth/models.py` (lines 1-26) + `backend/app/chat/models.py` (lines 179-231; validators only).

```python
"""These classes are intentionally thin Pydantic models (Data Model Pattern) — no
business logic beyond field declarations.  The password-hashing and JWT logic
live in ``app.auth.routes``."""
```

**Apply to:** `ConversationTarget`, `ProviderCredentials`, `ConversationCreateRequest`, `LocalProviderInfo`, `CloudProviderInfo`, `ChatConversationInfo`, `ConversationHistoryMessage`, `ConversationHistoryResponse`. All Pydantic; validators only; no SQL, no I/O.

---

### Logging-with-scrubber pattern

**Source:** `backend/app/api/routes/routes.py::event_generator` (lines 124-142, 230-243) — log full exception via `logger.exception` (the `ApiKeyScrubber` redacts on its way to the formatter), emit a static safe message to the client.

```python
except Exception:
    # CR-05: do NOT echo str(e) over the SSE wire. Log the full exception
    # server-side (the ApiKeyScrubber redacts any key-shaped substrings before
    # the formatter runs) and emit a static, generic message to the client.
    logger.exception("chat_stream failed for session %s", request.session_id)
    error_event = ErrorEvent(
        error_code=ErrorCode.stream_error,
        message="Sorry, something went wrong. Please try again.",
        retryable=False,
        ...
    )
    yield f"data: {error_event.model_dump_json()}\n\n"
```

**Apply to:** Phase 6 `PostgresMessageStore.append` unique-violation path (Pitfall 6). When `(conversation_id, seq)` insert raises `IntegrityError`, log full + emit static `ErrorEvent` (concurrency conflict — retry).

---

### Tunables on Settings, not module constants (CLAUDE.md)

**Source:** `backend/app/config.py::Settings` (lines 65-78 — probe timeout, cache TTL, model prefixes).

**Apply to:** `database_url`, `db_pool_size`, `db_pool_overflow`, `seed_allow_non_local`, future `db_statement_timeout` — all live on `Settings`, not as module-level constants in `app/db/session.py`.

```python
# CORRECT — Phase 6
class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://..."
    db_pool_size: int = 5
    db_pool_overflow: int = 10

# WRONG — would violate CLAUDE.md
# app/db/session.py
DB_POOL_SIZE = 5  # WRONG — tunable, must live on Settings
```

---

## No Analog Found

Files with no close match in the codebase (planner uses RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason | Reference |
|------|------|-----------|--------|-----------|
| `backend/migrations/env.py` | infrastructure (alembic) | one-shot async | Alembic is new in Phase 6; nothing existing | RESEARCH Pattern 2 |
| `backend/migrations/script.py.mako` | template | n/a | Alembic default template, copy verbatim | alembic upstream |
| `backend/alembic.ini` | config | n/a | Alembic default + `script_location = migrations`; `sqlalchemy.url` blank (set in env.py) | D-11 + RESEARCH §"alembic" |
| `docker-compose.yml` | infrastructure | n/a | Compose is new; CONTEXT.md D-10 ships the verbatim shape | CONTEXT.md D-10 / RESEARCH §"docker-compose.yml" |
| `backend/seed.toml.example` | sample config | n/a | TOML format for dev creds; no analog | RESEARCH Pattern 4 |

---

## Metadata

**Analog search scope:**
- `backend/app/auth/` (UserRepository ABC + EnvUserRepository — direct analog for PostgresUserRepository)
- `backend/app/chat/` (ConversationStore ABC + InMemoryConversationStore + StreamEvent ABC — analogs for MessageStore / ConversationRepository / discriminated split)
- `backend/app/api/main.py` (lifespan + `app.state` singleton wiring)
- `backend/app/api/routes/routes.py` (controller patterns — auth, ownership 404, SSE, exception handling)
- `backend/app/auth/routes.py` (placeholder dependency pattern; login flow stays unchanged through ABC swap)
- `backend/app/chat/models.py` (Pydantic SRP-split + StreamEvent ABC + multi-inherit subclass)
- `backend/app/providers/models.py` (Pydantic response DTOs; ProviderInfo split target)
- `backend/app/llm/errors.py` (StrEnum canonical example per CLAUDE.md)
- `backend/app/config.py` (Settings + `model_post_init` warning)
- `backend/tests/integration/conftest.py` (autouse fixture pattern)
- `justfile` (recipe-per-task pattern)

**Files scanned:** 13 source files, 1 test conftest, justfile, pyproject.toml.

**Pattern extraction date:** 2026-06-03

**Notes for planner:**
1. The Phase 6 split (`MessageStore` + `ConversationRepository`) maps naturally onto two existing patterns: the existing `ConversationStore` ABC (the events half) and the existing `UserRepository` ABC + DI override (the meta-CRUD half). Both are ABC-first; both wire via `app.state` singletons in `lifespan`.
2. `REQ-p5-flight-client-di` may already be closed (Phase 5 verification truth #5; RESEARCH Assumption A7) — planner verifies and either marks done or scopes residual route plumbing.
3. The `ChatService._first_message_preview` `getattr(_store)` peek (service.py lines 195-211) is a hard blocker for Phase 6 — the Postgres impl has no `_store` and silently returns `None`. ABC method `first_user_message_preview(conversation_id)` is the fix.
4. Wire-format golden file at `tests/unit/chat/test_stream_event_wire_compat.py` MUST be regenerated after the rename — this is the wire-format guard from Phase 5 that locks the SSE field order; it has to move from `session_id` to `conversation_id` cleanly.
5. CLAUDE.md skill routing notes: planner activates `/dignified-python` for backend ABC discussion, `/fastapi` for routes/Pydantic/alembic, and `/react-stack` for the frontend rename.
