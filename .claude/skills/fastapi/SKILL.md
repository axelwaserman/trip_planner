---
name: fastapi
description: |
  Build production-ready Python APIs with FastAPI, Pydantic v2, SQLAlchemy 2.0 async, and uv package manager. Covers project structure, authentication, validation, database integration, and prevents 7 documented GitHub issues.

  ALWAYS USE when detecting: fastapi, FastAPI, uvicorn, pydantic, SQLAlchemy, async def, @app.get, @app.post, APIRouter, HTTPException, Depends(), BaseSettings, alembic, Python API, REST API, or API development.

  Use when: creating new FastAPI projects, implementing JWT auth, troubleshooting 422 validation errors, fixing CORS configuration, resolving async blocking issues, handling form data or file uploads, configuring background tasks, or fixing OpenAPI schema conflicts.
user-invocable: true
---

# FastAPI Skill

Production-tested patterns for FastAPI with Pydantic v2, SQLAlchemy 2.0 async, and JWT authentication.

**Latest Versions** (verified February 2026):

- FastAPI: 0.128.0
- Pydantic: 2.11.7
- SQLAlchemy: 2.0.30
- Uvicorn: 0.35.0
- PyJWT: 2.8.0
- bcrypt: 4.1.2

**Requirements**:

- Python 3.10+ (Required for `|` union type syntax; Python 3.8 support dropped in FastAPI 0.125.0)
- Pydantic v2.7.0+ (Pydantic v1 support completely removed in FastAPI 0.128.0)

---

## 7 Issues This Skill Prevents

1. **Form data loses field set metadata** ([#13399](https://github.com/fastapi/fastapi/issues/13399))
2. **BackgroundTasks silently overwritten by custom Response** ([#11215](https://github.com/fastapi/fastapi/issues/11215))
3. **Optional form fields break with TestClient** ([#12245](https://github.com/fastapi/fastapi/issues/12245))
4. **Pydantic Json type fails with Form data** ([#10997](https://github.com/fastapi/fastapi/issues/10997))
5. **Annotated ForwardRef breaks OpenAPI generation** ([#13056](https://github.com/fastapi/fastapi/issues/13056))
6. **Path parameter union types always parse as str in Pydantic v2** ([#11251](https://github.com/fastapi/fastapi/issues/11251))
7. **ValueError in field_validator returns 500 instead of 422** ([#10779](https://github.com/fastapi/fastapi/discussions/10779))

See [Known Issues Prevention](#known-issues-prevention) for detailed explanations and prevention strategies.

---

## Quick Start

### Project Setup with uv

```bash
# Create project
uv init my-api
cd my-api

# Add dependencies (using modern, maintained crypto libraries)
uv add fastapi[standard] sqlalchemy[asyncio] aiosqlite pyjwt bcrypt pydantic-settings

# Run development server
uv run fastapi dev src/main.py

```

### Minimal Working Example

```python
# src/main.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="My API")

class Item(BaseModel):
    name: str
    price: float

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/items")
async def create_item(item: Item):
    return item

```

Run: `uv run fastapi dev src/main.py`

Docs available at: `http://127.0.0.1:8000/docs`

---

## Project Structure (Domain-Based)

For maintainable projects, organize by domain not file type:

```text
my-api/
├── pyproject.toml
├── uv.lock
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app initialization
│   ├── config.py            # Global settings
│   ├── database.py          # Database connection & dependencies
│   │
│   ├── auth/                # Auth domain
│   │   ├── __init__.py
│   │   ├── router.py        # Auth endpoints
│   │   ├── schemas.py       # Pydantic models
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── service.py       # Business logic (hashing, tokens)
│   │   └── dependencies.py  # Auth dependencies (get_current_user)
│   │
│   ├── items/               # Items domain
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   └── service.py
│   │
│   └── shared/              # Shared utilities
│       ├── __init__.py
│       └── exceptions.py
└── tests/
    └── test_main.py

```

---

## Core Patterns

### Pydantic Schemas (Validation)

```python
# src/items/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum

class ItemStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

class ItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    price: float = Field(..., gt=0, description="Price must be positive")
    status: ItemStatus = ItemStatus.DRAFT

class ItemCreate(ItemBase):
    pass

class ItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    price: float | None = Field(None, gt=0)
    status: ItemStatus | None = None

class ItemResponse(ItemBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

```

**Key Points**:

* Use `Field()` for validation constraints.
* Separate Create/Update/Response schemas.
* `from_attributes=True` enables SQLAlchemy model conversion.
* Use `str | None` (Python 3.10+) not `Optional[str]`.

### SQLAlchemy Models (Database)

```python
# src/items/models.py
from sqlalchemy import String, Float, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.database import Base
from src.items.schemas import ItemStatus

class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[ItemStatus] = mapped_column(
        SQLEnum(ItemStatus), default=ItemStatus.DRAFT
    )
    # Use timezone-aware UTC dates. utcnow() is deprecated in Python 3.12+
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

```

### Database Setup & Dependencies (Async SQLAlchemy 2.0)

```python
# src/database.py
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from src.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# Modern Annotated Dependency Alias
SessionDep = Annotated[AsyncSession, Depends(get_db)]

```

### Router Pattern

```python
# src/items/router.py
from typing import Annotated
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select

from src.database import SessionDep
from src.items import schemas, models

router = APIRouter(prefix="/items", tags=["items"])

@router.get("", response_model=list[schemas.ItemResponse])
async def list_items(
    db: SessionDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    result = await db.execute(
        select(models.Item).offset(skip).limit(limit)
    )
    return result.scalars().all()

@router.get("/{item_id}", response_model=schemas.ItemResponse)
async def get_item(item_id: int, db: SessionDep):
    result = await db.execute(
        select(models.Item).where(models.Item.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@router.post("", response_model=schemas.ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(item_in: schemas.ItemCreate, db: SessionDep):
    item = models.Item(**item_in.model_dump())
    db.add(item)
    # Commit happens automatically in the dependency yield,
    # but explicit flush/commit is needed if returning the generated ID immediately
    await db.flush()
    await db.refresh(item)
    return item

```

### Service Layer Pattern

Keep business logic out of routes by using a service layer:

```python
# src/items/service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.items import models, schemas

async def get_items(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> list[models.Item]:
    """Business logic: get items with pagination."""
    result = await db.execute(
        select(models.Item).offset(skip).limit(limit)
    )
    return result.scalars().all()

async def get_item_by_id(
    db: AsyncSession,
    item_id: int
) -> models.Item | None:
    """Business logic: get item by ID."""
    result = await db.execute(
        select(models.Item).where(models.Item.id == item_id)
    )
    return result.scalar_one_or_none()

async def create_item(
    db: AsyncSession,
    item_in: schemas.ItemCreate,
    user_id: int | None = None
) -> models.Item:
    """Business logic: create item with optional owner."""
    item_data = item_in.model_dump()
    if user_id:
        item_data["user_id"] = user_id

    item = models.Item(**item_data)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item

# Update router to use service layer:
# src/items/router.py
from src.items import service

@router.get("", response_model=list[schemas.ItemResponse])
async def list_items(
    db: SessionDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    return await service.get_items(db, skip, limit)

@router.post("", response_model=schemas.ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item_endpoint(
    item_in: schemas.ItemCreate,
    db: SessionDep
):
    return await service.create_item(db, item_in)

```

### Main App with Health Checks

```python
# src/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from src.database import engine, Base, SessionDep
from src.items.router import router as items_router
from src.auth.router import router as auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables (In production, use Alembic instead!)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: cleanup if needed

app = FastAPI(title="My API", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoints
@app.get("/health", tags=["health"])
async def health_check():
    """Basic health check for Kubernetes/Docker liveness probe."""
    return {"status": "healthy"}

@app.get("/health/db", tags=["health"])
async def db_health_check(db: SessionDep):
    """Database health check for readiness probe."""
    try:
        await db.execute(select(1))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {str(e)}"
        )

# Include routers
app.include_router(auth_router)
app.include_router(items_router)

```

---

## JWT Authentication

### Auth Schemas

```python
# src/auth/schemas.py
from pydantic import BaseModel, EmailStr, ConfigDict

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

```

### Auth Service (Modern PyJWT & bcrypt)

```python
# src/auth/service.py
import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from datetime import datetime, timedelta, timezone
from src.config import settings

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except InvalidTokenError:
        return None

```

### Auth Dependencies

```python
# src/auth/dependencies.py
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from src.database import SessionDep
from src.auth import service, models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
TokenDep = Annotated[str, Depends(oauth2_scheme)]

async def get_current_user(token: TokenDep, db: SessionDep) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = service.decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(
        select(models.User).where(models.User.id == int(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user

CurrentUser = Annotated[models.User, Depends(get_current_user)]

```

### Auth Router

```python
# src/auth/router.py
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from src.database import SessionDep
from src.auth import schemas, models, service
from src.auth.dependencies import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=schemas.UserResponse)
async def register(user_in: schemas.UserCreate, db: SessionDep):
    # Check existing
    result = await db.execute(
        select(models.User).where(models.User.email == user_in.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=user_in.email,
        hashed_password=service.hash_password(user_in.password)
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.post("/login", response_model=schemas.Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: SessionDep
):
    result = await db.execute(
        select(models.User).where(models.User.email == form_data.username)
    )
    user = result.scalar_one_or_none()

    if not user or not service.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    access_token = service.create_access_token(data={"sub": str(user.id)})
    return schemas.Token(access_token=access_token)

@router.get("/me", response_model=schemas.UserResponse)
async def get_me(current_user: CurrentUser):
    return current_user

```

### Protect Routes

```python
# In any router
from src.auth.dependencies import CurrentUser
from src.database import SessionDep

@router.post("/items")
async def create_item(
    item_in: schemas.ItemCreate,
    current_user: CurrentUser,  # Requires auth! Extremely clean signature.
    db: SessionDep
):
    item = models.Item(**item_in.model_dump(), user_id=current_user.id)
    # ...

```

---

## Configuration

```python
# src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./database.db"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Modern Pydantic v2 approach
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

settings = Settings()

```

Create `.env`:

```text
DATABASE_URL=sqlite+aiosqlite:///./database.db
SECRET_KEY=your-super-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30

```

---

## Database Migrations with Alembic

For production applications, use Alembic for database migrations instead of `Base.metadata.create_all()`:

```bash
# Add Alembic to dependencies
uv add alembic

# Initialize Alembic
uv run alembic init alembic

# Edit alembic/env.py to import your models
```

```python
# alembic/env.py
from src.database import Base
from src.items.models import Item  # Import all models
from src.auth.models import User

# Set target metadata
target_metadata = Base.metadata
```

```bash
# Edit alembic.ini to use your database URL
# sqlalchemy.url = sqlite+aiosqlite:///./database.db

# Or use env var in alembic/env.py:
```

```python
# alembic/env.py
from src.config import settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
```

```bash
# Create migration
uv run alembic revision --autogenerate -m "Create items and users tables"

# Review the generated migration file in alembic/versions/

# Apply migration
uv run alembic upgrade head

# Rollback migration
uv run alembic downgrade -1
```

**Remove auto-table creation from main.py**:

```python
# src/main.py - Production version with Alembic
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Migrations handled by Alembic
    yield
    # Shutdown: cleanup if needed
```

---

## Critical Rules

### Always Do

1. **Use `Annotated` for Dependencies** - Ensures high reusability and pristine IDE autocompletion.
2. **Separate Pydantic schemas from SQLAlchemy models** - Different jobs, different files.
3. **Use async for I/O operations** - Database, HTTP calls, file access.
4. **Validate with Pydantic Field()** - Constraints, defaults, descriptions.
5. **Return proper status codes** - 201 for create, 204 for delete, etc.

### Never Do

1. **Never use blocking calls in async routes** - No `time.sleep()`, use `asyncio.sleep()`.
2. **Never put business logic in routes** - Use the service layer.
3. **Never hardcode secrets** - Use environment variables and `pydantic-settings`.
4. **Never skip validation** - Always use Pydantic schemas.
5. **Never use `*` in CORS origins for production** - Specify exact origins.

---

## Known Issues Prevention

This skill prevents **7** documented issues from official FastAPI GitHub and release notes.

### Issue #1: Form Data Loses Field Set Metadata

**Error**: `model.model_fields_set` includes default values when using `Form()`
**Source**: [GitHub Issue #13399](https://github.com/fastapi/fastapi/issues/13399)
**Why It Happens**: Form data parsing preloads default values and passes them to the validator, making it impossible to distinguish between fields explicitly set by the user and fields using defaults. This bug ONLY affects Form data, not JSON body data.

**Prevention**:

```python
# ✗ AVOID: Pydantic model with Form when you need field_set metadata
from typing import Annotated
from fastapi import Form

@app.post("/form")
async def endpoint(model: Annotated[MyModel, Form()]):
    fields = model.model_fields_set  # Unreliable! ❌

# ✓ USE: Individual form fields or JSON body instead
@app.post("/form-individual")
async def endpoint(
    field_1: Annotated[bool, Form()] = True,
    field_2: Annotated[str | None, Form()] = None
):
    # You know exactly what was provided ✓

# ✓ OR: Use JSON body when metadata matters
@app.post("/json")
async def endpoint(model: MyModel):
    fields = model.model_fields_set  # Works correctly ✓

```

### Issue #2: BackgroundTasks Silently Overwritten by Custom Response

**Error**: Background tasks added via `BackgroundTasks` dependency don't run
**Source**: [GitHub Issue #11215](https://github.com/fastapi/fastapi/issues/11215)
**Why It Happens**: When you return a custom `Response` with a `background` parameter, it overwrites all tasks added to the injected `BackgroundTasks` dependency. This is not documented and causes silent failures.

**Prevention**:

```python
# ✗ WRONG: Mixing both mechanisms
from fastapi import BackgroundTasks
from starlette.responses import Response, BackgroundTask

@app.get("/")
async def endpoint(tasks: BackgroundTasks):
    tasks.add_task(send_email)  # This will be lost! ❌
    return Response(
        content="Done",
        background=BackgroundTask(log_event)  # Only this runs
    )

# ✓ RIGHT: Use only BackgroundTasks dependency
@app.get("/")
async def endpoint(tasks: BackgroundTasks):
    tasks.add_task(send_email)
    tasks.add_task(log_event)
    return {"status": "done"}  # All tasks run ✓

```

### Issue #3: Optional Form Fields Break with TestClient (Regression)

**Error**: `422: "Input should be 'abc' or 'def'"` for optional Literal fields
**Source**: [GitHub Issue #12245](https://github.com/fastapi/fastapi/issues/12245)
**Why It Happens**: Starting in FastAPI 0.114.0, optional form fields with `Literal` types fail validation when passed `None` via TestClient.

**Prevention**:

```python
from typing import Annotated, Literal
from fastapi import Form
from fastapi.testclient import TestClient

# ✗ PROBLEMATIC: Optional Literal with Form
@app.post("/")
async def endpoint(attribute: Annotated[Literal["abc", "def"] | None, Form()] = None):
    return {"attribute": attribute}

# client.post("/", data={"attribute": None}) will return 422 ❌

# ✓ WORKAROUND: Avoid Literal types with optional form fields
@app.post("/")
async def endpoint(attribute: Annotated[str | None, Form()] = None):
    if attribute and attribute not in ["abc", "def"]:
        raise HTTPException(400, "Invalid attribute")

```

### Issue #4: Pydantic Json Type Doesn't Work with Form Data

**Error**: `"JSON object must be str, bytes or bytearray"`
**Source**: [GitHub Issue #10997](https://github.com/fastapi/fastapi/issues/10997)
**Why It Happens**: Using Pydantic's `Json` type directly with `Form()` fails. You must accept the field as `str` and parse manually.

**Prevention**:

```python
from typing import Annotated
from fastapi import Form
from pydantic import Json, BaseModel

# ✗ WRONG: Json type directly with Form
@app.post("/broken")
async def broken(json_list: Annotated[Json[list[str]], Form()]) -> list[str]:
    return json_list  # Returns 422 ❌

# ✓ RIGHT: Accept as str, parse with Pydantic
class JsonListModel(BaseModel):
    json_list: Json[list[str]]

@app.post("/working")
async def working(json_list: Annotated[str, Form()]) -> list[str]:
    model = JsonListModel(json_list=json_list)
    return model.json_list  # Works ✓

```

### Issue #5: Annotated with ForwardRef Breaks OpenAPI Generation

**Error**: Missing or incorrect OpenAPI schema for dependency types
**Source**: [GitHub Issue #13056](https://github.com/fastapi/fastapi/issues/13056)
**Why It Happens**: When using `Annotated` with `Depends()` and a forward reference (from `__future__ import annotations`), OpenAPI schema generation fails.

**Prevention**:

```python
# ✓ WORKAROUND: Define classes before they're used in dependencies
from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends

@dataclass
class Potato:
    color: str
    size: int

def get_potato() -> Potato:
    return Potato(color='red', size=10)

PotatoDep = Annotated[Potato, Depends(get_potato)]

```

### Issue #6: Pydantic v2 Path Parameter Union Type Breaking Change

**Error**: Path parameters with `int | str` always parse as `str` in Pydantic v2
**Source**: [GitHub Issue #11251](https://github.com/fastapi/fastapi/issues/11251)
**Why It Happens**: Major breaking change when migrating from Pydantic v1 to v2. Union types with `str` in path/query parameters now always parse as `str`.

**Prevention**:

```python
# ✗ PROBLEMATIC: Union with str in path parameter
@app.get("/int/{path}")
async def int_path(path: int | str):
    return str(type(path)) # Pydantic v2 returns <class 'str'> for "123" ❌

# ✓ RIGHT: Avoid union types with str in path/query parameters
@app.get("/int/{path}")
async def int_path(path: int):
    return str(type(path))  # Works correctly ✓

```

### Issue #7: ValueError in field_validator Returns 500 Instead of 422

**Error**: `500 Internal Server Error` when raising `ValueError` in custom validators
**Source**: [GitHub Discussion #10779](https://github.com/fastapi/fastapi/discussions/10779)
**Why It Happens**: When raising `ValueError` inside a Pydantic `@field_validator` with Form fields, FastAPI returns a 500 Error instead of the expected 422 validation error.

**Prevention**:

```python
from pydantic import BaseModel, field_validator, ValidationError

# ✓ RIGHT: Raise ValidationError instead of ValueError
class MyForm(BaseModel):
    value: int

    @field_validator('value')
    def validate_value(cls, v):
        if v < 0:
            raise ValidationError("Value must be positive")  # Returns 422 ✓
        return v

```

---

## Common Errors & Fixes

### 422 Unprocessable Entity

**Fix**: Add custom validation error handler to see exactly what failed:

```python
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body}
    )

```

### Database Integrity Errors

**Fix**: Handle database constraint violations gracefully:

```python
from sqlalchemy.exc import IntegrityError

@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Database constraint violation (duplicate key, foreign key, etc.)"}
    )

```

### Unhandled Exceptions

**Fix**: Catch-all handler for unexpected errors:

```python
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    # Log the error for debugging
    import logging
    logging.error(f"Unhandled error: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )

```

### Async Blocking Event Loop

**Symptoms**: Throughput plateaus far earlier than expected; requests queue indefinitely.
**Fix**: Use `def` (not `async def`) for CPU-bound routes to automatically run them in a thread pool, or use `run_in_executor`.

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor()

@app.get("/mixed")
async def mixed_task():
    # Run blocking function in thread pool so it doesn't freeze the async event loop
    result = await asyncio.get_event_loop().run_in_executor(
        executor,
        blocking_function 
    )
    return result

```

---

## Testing

### Basic Testing Setup

```python
# tests/test_main.py
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.fixture
async def client():
    # ASGITransport avoids network overhead and runs directly against the app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_create_item(client):
    response = await client.post(
        "/items",
        json={"name": "Test", "price": 9.99, "status": "draft"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test"
    assert data["price"] == 9.99
    assert "id" in data

```

### Testing Authenticated Endpoints

```python
# tests/test_auth.py
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

@pytest.fixture
async def auth_token(client):
    """Create a test user and return auth token."""
    # Register
    await client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "testpassword123"
    })

    # Login
    response = await client.post("/auth/login", data={
        "username": "test@example.com",
        "password": "testpassword123"
    })
    return response.json()["access_token"]

@pytest.mark.asyncio
async def test_protected_endpoint(client, auth_token):
    """Test accessing protected /auth/me endpoint."""
    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"

@pytest.mark.asyncio
async def test_protected_endpoint_unauthorized(client):
    """Test accessing protected endpoint without token."""
    response = await client.get("/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_create_item_with_auth(client, auth_token):
    """Test creating item as authenticated user."""
    response = await client.post(
        "/items",
        json={"name": "Authenticated Item", "price": 19.99},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 201

```

Run: `uv run pytest`

---

## Deployment

### Docker (Optimized for `uv` caching)

This `Dockerfile` is uniquely optimized to use Docker's layer caching so dependencies are only re-downloaded when `pyproject.toml` or `uv.lock` changes.

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Now copy the rest of the application
COPY . .
RUN uv sync --frozen

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

```

### Docker Compose (Production-like Setup)

For local development with a real database:

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://myuser:mypassword@db:5432/mydb
      - SECRET_KEY=${SECRET_KEY:-change-me-in-production}
      - ACCESS_TOKEN_EXPIRE_MINUTES=30
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=myuser
      - POSTGRES_PASSWORD=mypassword
      - POSTGRES_DB=mydb
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U myuser"]
      interval: 5s
      timeout: 5s
      retries: 5
    ports:
      - "5432:5432"

volumes:
  postgres_data:

```

Run with: `docker-compose up`

**Note**: Add `asyncpg` to dependencies for PostgreSQL: `uv add asyncpg`

---

**Last verified**: 2026-02-28 | **Skill version**: 2.1.0 | **Changes**: Added ALWAYS USE detection keywords, service layer pattern, Alembic migrations, comprehensive error handlers, health check endpoints, authenticated testing examples, and docker-compose setup. Listed all 7 prevented issues upfront.