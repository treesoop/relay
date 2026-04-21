# Relay Week 2 — Central API + MCP Upload/Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI server (Central API) that stores uploaded skills in Postgres + pgvector, generates 3 embeddings per skill via OpenAI, serves semantic search with hybrid ranking, and masks PII on upload — plus add `skill_upload` and `skill_fetch` MCP tools to the local side so an agent can push a captured skill to the commons and pull someone else's skill back. Verifiable end-to-end in local docker-compose; AWS deployment is a separate Week 2B plan.

**Architecture:**
- **Central API** — async FastAPI (SQLAlchemy 2.0 + asyncpg + pgvector), 3 routers (`skills`, `reviews`-stub, `auth`). Embedding via `openai.AsyncOpenAI` (`text-embedding-3-small`, 1536 dims × 3 vectors per skill: description / problem / solution). Auth is a minimal `X-Relay-Agent-Id` header stub for MVP; real secret verification comes in Week 3.
- **Local MCP extension** — `skill_upload` reads the mine/<name>/ pair, applies PII masking, POSTs to the API, records the returned `id` + body hash as `uploaded=true` / `uploaded_hash=<sha>` back into `.relay.yaml`. `skill_fetch` resolves a skill id, writes the two files under `downloaded/` (default) or `staging/`, and records a `usage_log` "viewed" entry via the API.
- **Local verification** — docker-compose brings up Postgres 16 + pgvector; tests run against it (no mocks for DB). OpenAI client is mocked at the embedding module boundary for unit tests; one opt-in E2E test can hit the real OpenAI when `RELAY_RUN_OPENAI_E2E=1`.

**Tech Stack:**
- Python 3.11+, FastAPI, uvicorn, SQLAlchemy 2.0 async, asyncpg, pgvector (SQL + `pgvector` Python bindings)
- OpenAI Python SDK v1.12+
- Pydantic v2 for schemas
- pytest + pytest-asyncio + httpx (AsyncClient) for API tests
- Docker Compose for local Postgres (`pgvector/pgvector:pg16`)

---

## File Structure

```
relay/
├── SPEC.md                                   # existing
├── pyproject.toml                            # MODIFY: add fastapi/uvicorn/sqlalchemy/asyncpg/openai deps
├── docker-compose.yml                        # NEW: Postgres+pgvector + API services
├── .env.example                              # NEW: env var template
│
├── central_api/                              # NEW: server code
│   ├── __init__.py
│   ├── main.py                               # FastAPI app factory + app = create_app()
│   ├── config.py                             # env-var loading via pydantic-settings
│   ├── db.py                                 # async engine, session dependency
│   ├── models.py                             # SQLAlchemy ORM (Skill, Review, UsageLog, Agent)
│   ├── schemas.py                            # Pydantic request/response models
│   ├── embedding.py                          # OpenAI wrapper + EmbeddingClient protocol
│   ├── masking.py                            # PII regex masking
│   ├── ranking.py                            # similarity + confidence + context_match
│   ├── auth.py                               # X-Relay-Agent-Id header dependency
│   ├── sql/
│   │   └── 001_init.sql                      # pgvector + tables + indices
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── skills.py                         # POST /skills, GET /skills/{id}, GET /skills/search
│   │   └── auth_router.py                    # POST /auth/register (minimal)
│   ├── Dockerfile
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                       # async engine + httpx AsyncClient fixtures
│       ├── test_masking.py
│       ├── test_ranking.py
│       ├── test_embedding.py                 # mocked OpenAI
│       ├── test_api_skills.py                # POST + GET + auth behavior
│       └── test_api_search.py                # search + ranking + tool filter
│
├── local_mcp/                                # existing
│   ├── ...
│   └── tools/
│       ├── upload.py                         # NEW: skill_upload
│       └── fetch.py                          # NEW: skill_fetch
│
├── tests/                                    # existing local MCP tests
│   ├── test_upload.py                        # NEW
│   └── test_fetch.py                         # NEW
```

**Responsibilities:**
- `masking.py` / `embedding.py` / `ranking.py` are **pure modules** — no DB, no HTTP. Easy to unit test.
- `db.py` owns the async engine and `get_session()` dependency.
- `models.py` owns ORM; `schemas.py` owns wire shapes — never cross them.
- `routers/skills.py` is the **only** place that composes masking → embedding → insert.
- `local_mcp/tools/upload.py` / `fetch.py` shell out to the API via `httpx` — they do not know SQL exists.

---

## Task 0: Wire new dependencies + docker-compose scaffolding

**Files:**
- Modify: `pyproject.toml` (add Week 2 deps)
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Extend `pyproject.toml` deps**

Add these to the `dependencies` list (keep Week 1 deps):

```toml
dependencies = [
    # Week 1
    "fastmcp>=0.1.0",
    "pyyaml>=6.0",
    "python-frontmatter>=1.0.0",
    "pydantic>=2.5.0",
    # Week 2
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29.0",
    "pgvector>=0.2.5",
    "openai>=1.12.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
]
```

And dev deps:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]
```

(`httpx` moves to main deps because `skill_fetch`/`skill_upload` use it in production.)

- [ ] **Step 2: Reinstall**

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import fastapi, sqlalchemy, asyncpg, pgvector, openai, httpx; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Write `.env.example`**

```
# Central API
RELAY_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay
RELAY_OPENAI_API_KEY=
RELAY_EMBEDDING_MODEL=text-embedding-3-small
RELAY_API_HOST=0.0.0.0
RELAY_API_PORT=8080

# Local MCP client
RELAY_API_URL=http://localhost:8080
RELAY_AGENT_ID=local-dev
```

- [ ] **Step 4: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: relay
      POSTGRES_PASSWORD: relay
      POSTGRES_DB: relay
    ports:
      - "5432:5432"
    volumes:
      - relay_pgdata:/var/lib/postgresql/data
      - ./central_api/sql/001_init.sql:/docker-entrypoint-initdb.d/001_init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U relay"]
      interval: 2s
      timeout: 3s
      retries: 20

  api:
    build:
      context: .
      dockerfile: central_api/Dockerfile
    environment:
      RELAY_DATABASE_URL: postgresql+asyncpg://relay:relay@postgres:5432/relay
      RELAY_OPENAI_API_KEY: ${RELAY_OPENAI_API_KEY}
      RELAY_EMBEDDING_MODEL: text-embedding-3-small
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  relay_pgdata:
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docker-compose.yml .env.example
git commit -m "chore(week2): add central-api deps and docker-compose skeleton"
```

---

## Task 1: DB init SQL (pgvector + schema)

**Files:**
- Create: `central_api/__init__.py` (empty)
- Create: `central_api/sql/001_init.sql`

- [ ] **Step 1: Create package marker**

```bash
mkdir -p central_api/sql
touch central_api/__init__.py
```

- [ ] **Step 2: Write `001_init.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    secret_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    when_to_use TEXT,
    body TEXT NOT NULL,
    metadata JSONB NOT NULL,

    description_embedding vector(1536),
    problem_embedding     vector(1536),
    solution_embedding    vector(1536),

    confidence FLOAT DEFAULT 0.5,
    used_count INT DEFAULT 0,
    good_count INT DEFAULT 0,
    bad_count  INT DEFAULT 0,
    status TEXT DEFAULT 'active',

    source_agent_id TEXT REFERENCES agents(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skills_desc_emb
  ON skills USING ivfflat (description_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_skills_problem_emb
  ON skills USING ivfflat (problem_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_skills_solution_emb
  ON skills USING ivfflat (solution_embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_skills_tools
  ON skills USING GIN ((metadata -> 'solution' -> 'tools_used'));

CREATE INDEX IF NOT EXISTS idx_skills_status_conf
  ON skills (status, confidence DESC);

CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    signal TEXT NOT NULL CHECK (signal IN ('good', 'bad', 'stale')),
    reason TEXT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_log (
    id SERIAL PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    query TEXT,
    similarity FLOAT,
    used INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

- [ ] **Step 3: Bring up Postgres and verify**

```bash
docker compose up -d postgres
docker compose exec -T postgres pg_isready -U relay
docker compose exec -T postgres psql -U relay -d relay -c "\dt"
docker compose exec -T postgres psql -U relay -d relay -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```

Expected: tables `agents`, `skills`, `reviews`, `usage_log` listed; `vector` extension present.

- [ ] **Step 4: Commit**

```bash
git add central_api/__init__.py central_api/sql/001_init.sql
git commit -m "feat(api): initial pgvector schema — skills, reviews, usage_log, agents"
```

---

## Task 2: Config module

**Files:**
- Create: `central_api/config.py`
- Create: `central_api/tests/__init__.py` (empty)
- Create: `central_api/tests/conftest.py` (stub — extended in Task 4)
- Create: `central_api/tests/test_config.py`

- [ ] **Step 1: Write failing test**

Create `central_api/tests/__init__.py` (empty).

Create `central_api/tests/test_config.py`:

```python
import pytest

from central_api.config import Settings


def test_settings_loads_defaults(monkeypatch):
    monkeypatch.delenv("RELAY_EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk-test")

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.openai_api_key == "sk-test"
    assert s.embedding_model == "text-embedding-3-small"
    assert s.api_host == "0.0.0.0"
    assert s.api_port == 8080


def test_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("RELAY_DATABASE_URL", raising=False)
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk")
    with pytest.raises(Exception):  # pydantic-settings raises ValidationError
        Settings()
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_config.py -v
```

Expected: ImportError (`central_api.config` missing).

- [ ] **Step 3: Implement `central_api/config.py`**

```python
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RELAY_", env_file=".env", extra="ignore")

    database_url: str
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    api_host: str = "0.0.0.0"
    api_port: int = 8080


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest central_api/tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add central_api/config.py central_api/tests/__init__.py central_api/tests/test_config.py
git commit -m "feat(api): add Settings config with RELAY_ env-prefix loading"
```

---

## Task 3: PII masking module

**Files:**
- Create: `central_api/masking.py`
- Create: `central_api/tests/test_masking.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_masking.py`:

```python
from central_api.masking import mask_pii


def test_mask_openai_key():
    text = "Set OPENAI_API_KEY=sk-proj-abc123XYZdef456ghi789JKL012mno345PQR678stu901VWX"
    masked = mask_pii(text)
    assert "sk-proj-" not in masked
    assert "[REDACTED:api_key]" in masked


def test_mask_aws_access_key():
    text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE is my key"
    masked = mask_pii(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in masked
    assert "[REDACTED:aws_key]" in masked


def test_mask_github_token():
    text = "token ghp_abcdef1234567890abcdef1234567890abcd"
    masked = mask_pii(text)
    assert "ghp_" not in masked
    assert "[REDACTED:github_token]" in masked


def test_mask_email():
    text = "Contact alice@example.com for details"
    masked = mask_pii(text)
    assert "alice@example.com" not in masked
    assert "[REDACTED:email]" in masked


def test_mask_bearer_token_in_url():
    text = "curl https://api.example.com/data?token=eyJhbGciOiJIUzI1NiJ9.very-long-jwt-value-here"
    masked = mask_pii(text)
    assert "eyJhbGciOiJIUzI1NiJ9" not in masked
    assert "[REDACTED:token]" in masked


def test_preserves_non_pii():
    text = "Call stripe.Charge.create(amount=100) to charge the customer"
    masked = mask_pii(text)
    assert masked == text


def test_mask_is_idempotent():
    text = "alice@example.com and sk-proj-abc123XYZdef456ghi789JKL012mno345PQR678stu901VWX"
    once = mask_pii(text)
    twice = mask_pii(once)
    assert once == twice
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_masking.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `central_api/masking.py`**

```python
from __future__ import annotations

import re

# Order matters: more specific patterns first so generic ones don't swallow them.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"), "[REDACTED:api_key]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws_key]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "[REDACTED:github_token]"),
    (re.compile(r"(?<![A-Za-z0-9._+-])[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED:email]"),
    (re.compile(r"(?<=[?&])(?:token|access_token|api_key|apikey)=[A-Za-z0-9._\-]{16,}"), "[REDACTED:token]"),
]


def mask_pii(text: str) -> str:
    """Apply PII regex masks. Idempotent — running on already-masked text is a no-op."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest central_api/tests/test_masking.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add central_api/masking.py central_api/tests/test_masking.py
git commit -m "feat(api): add PII regex masker for api keys, emails, tokens"
```

---

## Task 4: Async DB engine + conftest (docker-compose Postgres)

**Files:**
- Create: `central_api/db.py`
- Create: `central_api/tests/conftest.py` (real content)

- [ ] **Step 1: Write conftest with async DB fixture**

Create `central_api/tests/conftest.py`:

```python
from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(
        "RELAY_TEST_DATABASE_URL",
        "postgresql+asyncpg://relay:relay@localhost:5432/relay",
    )
    return url


@pytest_asyncio.fixture(scope="session")
async def engine(database_url):
    # Fail fast if Postgres is not reachable.
    eng = create_async_engine(database_url, pool_pre_ping=True)
    async with eng.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        # Each test runs in a transaction that rolls back at the end
        # so tests don't see each other's writes.
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def _truncate_all(engine):
    """Truncate skills/reviews/usage_log/agents between tests. Runs after each test."""
    from sqlalchemy import text
    yield
    async with engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE skills, reviews, usage_log, agents RESTART IDENTITY CASCADE"
        ))
```

- [ ] **Step 2: Implement `central_api/db.py`**

```python
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from central_api.config import get_settings


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        yield session
```

- [ ] **Step 3: Smoke test the fixtures**

Create a throwaway `central_api/tests/test_db_conftest.py`:

```python
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_db_is_reachable(db_session):
    result = await db_session.execute(text("SELECT 1 AS ok"))
    row = result.one()
    assert row.ok == 1


@pytest.mark.asyncio
async def test_pgvector_extension_installed(engine):
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
        row = result.one_or_none()
        assert row is not None
```

Run (Postgres must be up via `docker compose up -d postgres`):

```bash
docker compose up -d postgres
docker compose exec -T postgres pg_isready -U relay  # should report accepting connections
pytest central_api/tests/test_db_conftest.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add central_api/db.py central_api/tests/conftest.py central_api/tests/test_db_conftest.py
git commit -m "feat(api): add async engine + pytest fixtures for dockerized Postgres"
```

---

## Task 5: SQLAlchemy ORM models

**Files:**
- Create: `central_api/models.py`
- Create: `central_api/tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_models.py`:

```python
import pytest
from sqlalchemy import select

from central_api.models import Agent, Skill


@pytest.mark.asyncio
async def test_insert_agent_and_skill(db_session):
    agent = Agent(id="pseudo_xyz")
    db_session.add(agent)
    await db_session.flush()

    skill = Skill(
        id="sk_abc",
        name="foo",
        description="desc",
        when_to_use="when",
        body="## Problem\nx\n",
        metadata_={"problem": {"symptom": "s"}, "solution": {"approach": "a", "tools_used": []}},
        confidence=0.8,
        source_agent_id="pseudo_xyz",
    )
    db_session.add(skill)
    await db_session.commit()

    result = await db_session.execute(select(Skill).where(Skill.id == "sk_abc"))
    loaded = result.scalar_one()
    assert loaded.name == "foo"
    assert loaded.metadata_["problem"]["symptom"] == "s"
    assert loaded.confidence == 0.8
    assert loaded.source_agent_id == "pseudo_xyz"


@pytest.mark.asyncio
async def test_skill_defaults(db_session):
    db_session.add(Agent(id="p"))
    skill = Skill(
        id="sk_x",
        name="x",
        description="d",
        body="b",
        metadata_={},
        source_agent_id="p",
    )
    db_session.add(skill)
    await db_session.commit()

    loaded = (await db_session.execute(select(Skill).where(Skill.id == "sk_x"))).scalar_one()
    assert loaded.confidence == 0.5
    assert loaded.used_count == 0
    assert loaded.status == "active"
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_models.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `central_api/models.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    secret_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # "metadata" is reserved on Base, so suffix with underscore and map to the real column.
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)

    description_embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    problem_embedding:     Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    solution_embedding:    Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    used_count: Mapped[int]   = mapped_column(Integer, default=0, server_default="0")
    good_count: Mapped[int]   = mapped_column(Integer, default=0, server_default="0")
    bad_count:  Mapped[int]   = mapped_column(Integer, default=0, server_default="0")
    status:     Mapped[str]   = mapped_column(String, default="active", server_default="active")

    source_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("signal IN ('good', 'bad', 'stale')", name="reviews_signal_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    signal:   Mapped[str] = mapped_column(String, nullable=False)
    reason:   Mapped[str | None] = mapped_column(String, nullable=True)
    note:     Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageLog(Base):
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    query:    Mapped[str | None]   = mapped_column(Text, nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    used:     Mapped[int]  = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest central_api/tests/test_models.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add central_api/models.py central_api/tests/test_models.py
git commit -m "feat(api): add SQLAlchemy ORM models for agent, skill, review, usage_log"
```

---

## Task 6: Pydantic schemas (wire types)

**Files:**
- Create: `central_api/schemas.py`
- Create: `central_api/tests/test_schemas.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from central_api.schemas import (
    SkillUploadRequest,
    SkillResponse,
    SearchRequest,
    SearchResultItem,
)


def test_upload_request_minimum():
    req = SkillUploadRequest(
        name="foo",
        description="d",
        when_to_use="w",
        body="b",
        metadata={"problem": {"symptom": "s"}, "solution": {"approach": "a", "tools_used": []}},
    )
    assert req.name == "foo"


def test_upload_request_rejects_missing_metadata():
    with pytest.raises(ValidationError):
        SkillUploadRequest(
            name="foo", description="d", when_to_use="w", body="b",
            metadata={},  # missing problem/solution sub-objects → still valid at schema level
        )  # will raise only if we enforce required sub-keys; otherwise this passes
    # Note: schemas permit empty metadata; routers enforce semantics. This test just proves
    # the minimum accepted shape above works.


def test_search_request_defaults():
    req = SearchRequest(query="how to handle 429")
    assert req.search_mode == "problem"
    assert req.limit == 5
    assert req.context_languages == []
    assert req.context_libraries == []
    assert req.context_available_tools == []


def test_search_mode_invalid():
    with pytest.raises(ValidationError):
        SearchRequest(query="x", search_mode="bogus")


def test_search_result_shape():
    item = SearchResultItem(
        skill=SkillResponse(
            id="sk_a", name="a", description="d", when_to_use=None,
            body="b", metadata={}, confidence=0.8, used_count=0,
            good_count=0, bad_count=0, status="active",
            source_agent_id="p",
        ),
        similarity=0.9,
        confidence=0.8,
        context_match=0.5,
        matched_on="problem",
        required_tools=["mcp:stripe"],
        missing_tools=[],
    )
    assert item.matched_on == "problem"
```

Note: the second test simply asserts the minimum shape works. We intentionally let the schema accept metadata={} — router/service layer enforces that `problem` and `solution` exist.

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_schemas.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `central_api/schemas.py`**

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SearchMode = Literal["problem", "solution", "description", "hybrid"]


class SkillUploadRequest(BaseModel):
    name: str
    description: str
    when_to_use: str | None = None
    body: str
    metadata: dict[str, Any]
    # Optional: server can default source_agent_id from the header; request override allowed for CLI tests.
    source_agent_id: str | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    when_to_use: str | None
    body: str
    metadata: dict[str, Any]
    confidence: float
    used_count: int
    good_count: int
    bad_count: int
    status: str
    source_agent_id: str


class SearchRequest(BaseModel):
    query: str
    search_mode: SearchMode = "problem"
    limit: int = Field(default=5, ge=1, le=50)
    context_languages: list[str] = Field(default_factory=list)
    context_libraries: list[str] = Field(default_factory=list)
    context_available_tools: list[str] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    skill: SkillResponse
    similarity: float
    confidence: float
    context_match: float
    matched_on: SearchMode
    required_tools: list[str]
    missing_tools: list[str]


class SearchResponse(BaseModel):
    items: list[SearchResultItem]
```

- [ ] **Step 4: Run to confirm pass**

Note: `test_upload_request_rejects_missing_metadata` is actually checking the OPPOSITE — it documents that the schema intentionally accepts `{}`. Drop the `with pytest.raises(ValidationError)` and have it pass the construction instead:

Re-edit the test:

```python
def test_upload_request_accepts_empty_metadata_at_schema_level():
    # Schema is permissive; semantic validation of metadata structure lives in the router.
    req = SkillUploadRequest(
        name="foo", description="d", when_to_use="w", body="b", metadata={},
    )
    assert req.metadata == {}
```

Replace the earlier broken test with this corrected version, then run:

```bash
pytest central_api/tests/test_schemas.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add central_api/schemas.py central_api/tests/test_schemas.py
git commit -m "feat(api): add Pydantic wire schemas for upload, search, response"
```

---

## Task 7: Embedding module (OpenAI wrapper, mock-friendly)

**Files:**
- Create: `central_api/embedding.py`
- Create: `central_api/tests/test_embedding.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_embedding.py`:

```python
import pytest

from central_api.embedding import EmbeddingClient, StubEmbedder, build_embedding_targets


def test_build_embedding_targets():
    metadata = {
        "problem": {"symptom": "429 under burst", "context": "checkout"},
        "solution": {"approach": "backoff", "tools_used": [{"type": "library", "name": "tenacity"}]},
        "attempts": [
            {"tried": "retry loop", "failed_because": "no Retry-After"},
            {"worked": "backoff"},
        ],
    }
    targets = build_embedding_targets(
        description="Handle Stripe 429 with backoff",
        metadata=metadata,
    )
    assert targets["description"].startswith("Handle Stripe 429")
    assert "429 under burst" in targets["problem"]
    assert "checkout" in targets["problem"]
    assert "backoff" in targets["solution"]
    assert "tenacity" in targets["solution"]
    # Attempts summary included in solution text
    assert "retry loop" in targets["solution"]


@pytest.mark.asyncio
async def test_stub_embedder_returns_deterministic_vectors():
    stub = StubEmbedder(dim=1536)
    v1 = await stub.embed("same text")
    v2 = await stub.embed("same text")
    v3 = await stub.embed("different")
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == 1536
    assert all(isinstance(x, float) for x in v1)


@pytest.mark.asyncio
async def test_stub_embedder_batch():
    stub = StubEmbedder(dim=1536)
    vectors = await stub.embed_many(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 1536 for v in vectors)
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_embedding.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `central_api/embedding.py`**

```python
from __future__ import annotations

import hashlib
from typing import Any, Protocol

from openai import AsyncOpenAI

from central_api.config import get_settings


def build_embedding_targets(
    *,
    description: str,
    metadata: dict[str, Any],
) -> dict[str, str]:
    """Build the three text blobs we embed per skill.

    Returns a dict with keys 'description', 'problem', 'solution'.
    """
    problem = metadata.get("problem") or {}
    solution = metadata.get("solution") or {}
    attempts = metadata.get("attempts") or []

    problem_text = " ".join(
        t for t in [problem.get("symptom"), problem.get("context")] if t
    )

    attempts_summary = "; ".join(
        (a.get("tried") or a.get("worked") or "") + (
            f" (failed: {a['failed_because']})" if a.get("failed_because") else ""
        )
        for a in attempts
    ).strip()

    tools_used = solution.get("tools_used") or []
    tool_names = ", ".join(t.get("name", "") for t in tools_used)

    solution_text = " ".join(
        t for t in [
            solution.get("approach"),
            f"tools: {tool_names}" if tool_names else "",
            f"attempts: {attempts_summary}" if attempts_summary else "",
        ] if t
    )

    return {
        "description": description,
        "problem": problem_text,
        "solution": solution_text,
    }


class EmbeddingClient(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model or settings.embedding_model

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(input=[text], model=self._model)
        return list(resp.data[0].embedding)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(input=texts, model=self._model)
        return [list(d.embedding) for d in resp.data]


class StubEmbedder:
    """Deterministic fake embedder for tests. sha256(text) hashed down to floats."""

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        # Tile the digest bytes to fill dim dimensions; normalize to [-1, 1].
        out: list[float] = []
        i = 0
        while len(out) < self._dim:
            b = seed[i % len(seed)]
            out.append((b / 255.0) * 2 - 1)
            i += 1
        return out

    async def embed(self, text: str) -> list[float]:
        return self._vector(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest central_api/tests/test_embedding.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add central_api/embedding.py central_api/tests/test_embedding.py
git commit -m "feat(api): add OpenAI embedder + deterministic stub + embedding targets builder"
```

---

## Task 8: Ranking module

**Files:**
- Create: `central_api/ranking.py`
- Create: `central_api/tests/test_ranking.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_ranking.py`:

```python
from central_api.ranking import context_match_score, combine_score


def test_context_match_full_overlap():
    score = context_match_score(
        skill_context={"languages": ["python"], "libraries": ["stripe-python>=8.0"]},
        query_languages=["python"],
        query_libraries=["stripe-python>=8.0"],
    )
    assert score == 1.0


def test_context_match_partial_overlap():
    score = context_match_score(
        skill_context={"languages": ["python"], "libraries": ["a", "b"]},
        query_languages=["python"],
        query_libraries=["a", "c"],
    )
    # languages 1/1 = 1.0; libraries 1/3 intersect-over-union; average
    assert 0 < score < 1


def test_context_match_empty_query_is_neutral():
    # With no query context, we don't penalize — every skill scores 1.0 on context.
    score = context_match_score(
        skill_context={"languages": ["python"], "libraries": ["x"]},
        query_languages=[],
        query_libraries=[],
    )
    assert score == 1.0


def test_combine_score_formula():
    score = combine_score(similarity=0.9, confidence=0.8, context_match=0.5)
    # 0.9*0.5 + 0.8*0.3 + 0.5*0.2 = 0.45 + 0.24 + 0.10 = 0.79
    assert abs(score - 0.79) < 1e-6


def test_combine_score_monotone_in_similarity():
    a = combine_score(similarity=0.5, confidence=0.5, context_match=0.5)
    b = combine_score(similarity=0.8, confidence=0.5, context_match=0.5)
    assert b > a
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_ranking.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `central_api/ranking.py`**

```python
from __future__ import annotations

from typing import Any


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def context_match_score(
    *,
    skill_context: dict[str, Any],
    query_languages: list[str],
    query_libraries: list[str],
) -> float:
    """Return a [0, 1] score for how well a skill's context matches the query's.

    With empty query-side context, returns 1.0 (we don't penalize for missing info).
    Otherwise averages the Jaccard overlap for languages and libraries.
    """
    if not query_languages and not query_libraries:
        return 1.0

    scores: list[float] = []
    if query_languages:
        scores.append(
            _jaccard(set(skill_context.get("languages") or []), set(query_languages))
        )
    if query_libraries:
        scores.append(
            _jaccard(set(skill_context.get("libraries") or []), set(query_libraries))
        )
    return sum(scores) / len(scores)


def combine_score(*, similarity: float, confidence: float, context_match: float) -> float:
    """Hybrid ranking: 0.5 similarity + 0.3 confidence + 0.2 context_match."""
    return 0.5 * similarity + 0.3 * confidence + 0.2 * context_match
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest central_api/tests/test_ranking.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add central_api/ranking.py central_api/tests/test_ranking.py
git commit -m "feat(api): add context_match scoring + hybrid combine_score"
```

---

## Task 9: Auth stub (X-Relay-Agent-Id header dependency)

**Files:**
- Create: `central_api/auth.py`
- Create: `central_api/routers/__init__.py` (empty)
- Create: `central_api/routers/auth_router.py`
- Create: `central_api/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_auth.py`:

```python
import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport

from central_api.auth import require_agent_id
from central_api.routers.auth_router import router as auth_router


def _build_app():
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(agent_id: str = Depends(require_agent_id)):
        return {"agent_id": agent_id}

    app.include_router(auth_router)
    return app


@pytest.mark.asyncio
async def test_whoami_requires_header():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/whoami")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_whoami_reads_header():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/whoami", headers={"X-Relay-Agent-Id": "pseudo_xyz"})
        assert r.status_code == 200
        assert r.json() == {"agent_id": "pseudo_xyz"}


@pytest.mark.asyncio
async def test_auth_register_creates_agent(db_session):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/auth/register", json={"agent_id": "new_pseudo"})
        assert r.status_code == 201
        assert r.json() == {"agent_id": "new_pseudo"}
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_auth.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `central_api/auth.py`**

```python
from __future__ import annotations

from fastapi import Header, HTTPException, status


async def require_agent_id(
    x_relay_agent_id: str | None = Header(default=None, alias="X-Relay-Agent-Id"),
) -> str:
    if not x_relay_agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Relay-Agent-Id header",
        )
    return x_relay_agent_id
```

- [ ] **Step 4: Implement `central_api/routers/auth_router.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.db import get_session
from central_api.models import Agent


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    agent_id: str


class RegisterResponse(BaseModel):
    agent_id: str


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    stmt = insert(Agent).values(id=body.agent_id).on_conflict_do_nothing(index_elements=["id"])
    await session.execute(stmt)
    await session.commit()
    return RegisterResponse(agent_id=body.agent_id)
```

Create `central_api/routers/__init__.py` (empty).

- [ ] **Step 5: Run to confirm pass**

```bash
pytest central_api/tests/test_auth.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add central_api/auth.py central_api/routers/__init__.py central_api/routers/auth_router.py central_api/tests/test_auth.py
git commit -m "feat(api): add X-Relay-Agent-Id auth dependency + /auth/register stub"
```

---

## Task 10: POST /skills + GET /skills/{id}

**Files:**
- Create: `central_api/routers/skills.py`
- Create: `central_api/main.py`
- Create: `central_api/tests/test_api_skills.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_api_skills.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from central_api.main import create_app
from central_api.embedding import StubEmbedder


@pytest.fixture
def app():
    return create_app(embedder=StubEmbedder())


@pytest.mark.asyncio
async def test_post_skills_masks_pii_and_stores(app, db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # register agent first
        await client.post("/auth/register", json={"agent_id": "uploader"})
        headers = {"X-Relay-Agent-Id": "uploader"}

        payload = {
            "name": "stripe-429",
            "description": "Handle Stripe 429 with backoff",
            "when_to_use": "When Stripe returns 429",
            "body": "alice@example.com debugged this; key=sk-proj-abcdefghijklmnopqrstuvwx1234567890",
            "metadata": {
                "problem": {"symptom": "429 burst", "context": "checkout"},
                "solution": {
                    "approach": "backoff",
                    "tools_used": [{"type": "library", "name": "tenacity"}],
                },
                "attempts": [
                    {"tried": "retry loop", "failed_because": "ignored Retry-After"},
                    {"worked": "backoff"},
                ],
                "context": {"languages": ["python"], "libraries": ["stripe-python"]},
            },
        }

        r = await client.post("/skills", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["id"].startswith("sk_")
        assert data["name"] == "stripe-429"
        assert "alice@example.com" not in data["body"]
        assert "[REDACTED:email]" in data["body"]
        assert "sk-proj-" not in data["body"]
        assert data["source_agent_id"] == "uploader"


@pytest.mark.asyncio
async def test_post_skills_rejects_without_header(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/skills", json={
            "name": "x", "description": "d", "when_to_use": "w",
            "body": "b", "metadata": {},
        })
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_skill_roundtrip(app, db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "u"})
        headers = {"X-Relay-Agent-Id": "u"}

        post = await client.post("/skills", json={
            "name": "foo", "description": "d", "when_to_use": "w", "body": "hi",
            "metadata": {
                "problem": {"symptom": "s"},
                "solution": {"approach": "a", "tools_used": []},
            },
        }, headers=headers)
        sid = post.json()["id"]

        r = await client.get(f"/skills/{sid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["id"] == sid
        assert r.json()["body"] == "hi"


@pytest.mark.asyncio
async def test_get_missing_skill_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "u"})
        r = await client.get("/skills/sk_does_not_exist", headers={"X-Relay-Agent-Id": "u"})
        assert r.status_code == 404
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_api_skills.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `central_api/routers/skills.py`**

```python
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.auth import require_agent_id
from central_api.db import get_session
from central_api.embedding import EmbeddingClient, build_embedding_targets
from central_api.masking import mask_pii
from central_api.models import Skill
from central_api.schemas import SkillResponse, SkillUploadRequest


router = APIRouter(prefix="/skills", tags=["skills"])


def _new_id() -> str:
    return f"sk_{secrets.token_hex(8)}"


def _to_response(s: Skill) -> SkillResponse:
    return SkillResponse(
        id=s.id, name=s.name, description=s.description, when_to_use=s.when_to_use,
        body=s.body, metadata=s.metadata_, confidence=s.confidence,
        used_count=s.used_count, good_count=s.good_count, bad_count=s.bad_count,
        status=s.status, source_agent_id=s.source_agent_id,
    )


def _mask_metadata(meta: dict) -> dict:
    """Mask PII inside nested strings of attempts[].failed_because."""
    out = dict(meta)
    attempts = [dict(a) for a in (meta.get("attempts") or [])]
    for a in attempts:
        if "failed_because" in a and isinstance(a["failed_because"], str):
            a["failed_because"] = mask_pii(a["failed_because"])
    out["attempts"] = attempts
    return out


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def upload_skill(
    body: SkillUploadRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    agent_id: Annotated[str, Depends(require_agent_id)],
) -> SkillResponse:
    embedder: EmbeddingClient = request.app.state.embedder

    masked_body = mask_pii(body.body)
    masked_meta = _mask_metadata(body.metadata)

    targets = build_embedding_targets(description=body.description, metadata=masked_meta)
    desc_vec, problem_vec, solution_vec = await embedder.embed_many(
        [targets["description"], targets["problem"], targets["solution"]]
    )

    skill = Skill(
        id=_new_id(),
        name=body.name,
        description=body.description,
        when_to_use=body.when_to_use,
        body=masked_body,
        metadata_=masked_meta,
        description_embedding=desc_vec,
        problem_embedding=problem_vec,
        solution_embedding=solution_vec,
        source_agent_id=body.source_agent_id or agent_id,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return _to_response(skill)


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[str, Depends(require_agent_id)],
) -> SkillResponse:
    s = await session.get(Skill, skill_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    return _to_response(s)
```

- [ ] **Step 4: Implement `central_api/main.py`**

```python
from __future__ import annotations

from fastapi import FastAPI

from central_api.embedding import EmbeddingClient, OpenAIEmbedder
from central_api.routers.auth_router import router as auth_router
from central_api.routers.skills import router as skills_router


def create_app(*, embedder: EmbeddingClient | None = None) -> FastAPI:
    app = FastAPI(title="Relay Central API", version="0.1.0")

    app.state.embedder = embedder or OpenAIEmbedder()

    app.include_router(auth_router)
    app.include_router(skills_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = None  # uvicorn entry: use `central_api.main:create_app` via factory
```

Configure uvicorn to use the factory:

```bash
# In docker-compose / Dockerfile:
# uvicorn --factory central_api.main:create_app --host 0.0.0.0 --port 8080
```

- [ ] **Step 5: Run to confirm pass**

```bash
pytest central_api/tests/test_api_skills.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add central_api/main.py central_api/routers/skills.py central_api/tests/test_api_skills.py
git commit -m "feat(api): POST /skills (mask+embed+insert) and GET /skills/{id}"
```

---

## Task 11: GET /skills/search

**Files:**
- Modify: `central_api/routers/skills.py` (add search endpoint)
- Create: `central_api/tests/test_api_search.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_api_search.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from central_api.main import create_app
from central_api.embedding import StubEmbedder


@pytest.fixture
def app():
    return create_app(embedder=StubEmbedder())


async def _seed(client: AsyncClient, *, name: str, symptom: str, approach: str, tools=()) -> str:
    headers = {"X-Relay-Agent-Id": "seeder"}
    r = await client.post("/skills", json={
        "name": name,
        "description": f"{name} desc",
        "when_to_use": "when",
        "body": "body",
        "metadata": {
            "problem": {"symptom": symptom},
            "solution": {"approach": approach, "tools_used": list(tools)},
            "attempts": [],
            "context": {"languages": ["python"], "libraries": []},
        },
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_search_by_problem_returns_most_similar_first(app, db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "seeder"})
        await client.post("/auth/register", json={"agent_id": "querier"})

        await _seed(client, name="a", symptom="Stripe 429 under burst",    approach="backoff")
        await _seed(client, name="b", symptom="how to center a div",        approach="flexbox")
        await _seed(client, name="c", symptom="Stripe 429 in checkout",    approach="backoff w/ header")

        headers = {"X-Relay-Agent-Id": "querier"}
        r = await client.get("/skills/search", params={
            "query": "Stripe 429 burst", "search_mode": "problem", "limit": 5,
        }, headers=headers)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 1
        # The CSS skill should NOT be the top hit
        top_names = [it["skill"]["name"] for it in items[:2]]
        assert "b" not in top_names


@pytest.mark.asyncio
async def test_search_filters_by_available_tools(app, db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "seeder"})
        await client.post("/auth/register", json={"agent_id": "q"})

        await _seed(client, name="needs-stripe", symptom="429",      approach="retry",
                    tools=[{"type": "mcp", "name": "stripe"}])
        await _seed(client, name="self-contained", symptom="429",    approach="retry", tools=[])

        # Caller has NO tools available — should only see 'self-contained'
        r = await client.get("/skills/search", params={
            "query": "429",
            "search_mode": "problem",
            "context_available_tools": [],  # empty list filter
        }, headers={"X-Relay-Agent-Id": "q"})
        items = r.json()["items"]
        names = [it["skill"]["name"] for it in items]
        assert "needs-stripe" not in names
        assert "self-contained" in names

        # Caller has mcp:stripe available — should see both
        r = await client.get("/skills/search", params=[
            ("query", "429"),
            ("search_mode", "problem"),
            ("context_available_tools", "mcp:stripe"),
        ], headers={"X-Relay-Agent-Id": "q"})
        items = r.json()["items"]
        names = [it["skill"]["name"] for it in items]
        assert "needs-stripe" in names
        assert "self-contained" in names


@pytest.mark.asyncio
async def test_search_returns_required_and_missing_tools(app, db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "seeder"})
        await client.post("/auth/register", json={"agent_id": "q"})

        await _seed(client, name="uses-stripe", symptom="x", approach="y",
                    tools=[{"type": "mcp", "name": "stripe"}])

        r = await client.get("/skills/search", params=[
            ("query", "x"),
            ("context_available_tools", "mcp:stripe"),
        ], headers={"X-Relay-Agent-Id": "q"})
        items = r.json()["items"]
        assert len(items) == 1
        it = items[0]
        assert it["required_tools"] == ["mcp:stripe"]
        assert it["missing_tools"] == []
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_api_search.py -v
```

Expected: Errors — the search endpoint doesn't exist yet.

- [ ] **Step 3: Extend `central_api/routers/skills.py` with the search endpoint**

Append to `central_api/routers/skills.py` (above the `get_skill` function so the static route is registered before the path-parameter route):

```python
from fastapi import Query

from central_api.ranking import context_match_score, combine_score
from central_api.schemas import SearchMode, SearchResponse, SearchResultItem


def _required_tools(metadata: dict) -> list[str]:
    tools_used = (metadata.get("solution") or {}).get("tools_used") or []
    return [f"{t['type']}:{t['name']}" for t in tools_used if t.get("type") == "mcp"]


_EMB_COLUMN_BY_MODE = {
    "description": Skill.description_embedding,
    "problem": Skill.problem_embedding,
    "solution": Skill.solution_embedding,
}


@router.get("/search", response_model=SearchResponse)
async def search(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[str, Depends(require_agent_id)],
    request: Request,
    query: str = Query(...),
    search_mode: SearchMode = Query("problem"),
    limit: int = Query(5, ge=1, le=50),
    context_languages: list[str] = Query(default_factory=list),
    context_libraries: list[str] = Query(default_factory=list),
    context_available_tools: list[str] = Query(default_factory=list),
) -> SearchResponse:
    embedder: EmbeddingClient = request.app.state.embedder
    query_vec = await embedder.embed(query)

    if search_mode == "hybrid":
        # Average the three embeddings; compute three distances and blend equally.
        col_d = Skill.description_embedding
        col_p = Skill.problem_embedding
        col_s = Skill.solution_embedding
        distance_expr = (
            col_d.cosine_distance(query_vec)
            + col_p.cosine_distance(query_vec)
            + col_s.cosine_distance(query_vec)
        ) / 3.0
    else:
        col = _EMB_COLUMN_BY_MODE[search_mode]
        distance_expr = col.cosine_distance(query_vec)

    stmt = (
        select(Skill, distance_expr.label("distance"))
        .where(Skill.status == "active")
        .order_by(distance_expr)
        .limit(limit * 4)  # overfetch — we filter by tools then trim to `limit`
    )
    rows = (await session.execute(stmt)).all()

    available = set(context_available_tools)
    items: list[SearchResultItem] = []
    for skill, distance in rows:
        required = _required_tools(skill.metadata_)
        missing = [t for t in required if t not in available]
        if required and missing:
            continue

        similarity = max(0.0, 1.0 - float(distance))  # cosine distance → similarity
        ctx_match = context_match_score(
            skill_context=(skill.metadata_.get("context") or {}),
            query_languages=context_languages,
            query_libraries=context_libraries,
        )

        items.append(SearchResultItem(
            skill=_to_response(skill),
            similarity=similarity,
            confidence=skill.confidence,
            context_match=ctx_match,
            matched_on=search_mode,
            required_tools=required,
            missing_tools=missing,
        ))

        if len(items) >= limit:
            break

    # Final ranking by combined score
    items.sort(
        key=lambda it: combine_score(
            similarity=it.similarity,
            confidence=it.confidence,
            context_match=it.context_match,
        ),
        reverse=True,
    )

    return SearchResponse(items=items)
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest central_api/tests/test_api_search.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Full suite**

```bash
docker compose up -d postgres
pytest central_api/tests/ -v
```

Expected: all central_api tests pass.

- [ ] **Step 6: Commit**

```bash
git add central_api/routers/skills.py central_api/tests/test_api_search.py
git commit -m "feat(api): GET /skills/search with pgvector distance + hybrid ranking + tool filter"
```

---

## Task 12: Dockerfile + api service smoke test

**Files:**
- Create: `central_api/Dockerfile`

- [ ] **Step 1: Write Dockerfile**

Create `central_api/Dockerfile`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY central_api ./central_api
COPY local_mcp ./local_mcp

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8080
CMD ["uvicorn", "--factory", "central_api.main:create_app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Build and run**

```bash
docker compose build api
docker compose up -d
sleep 3
curl -s http://localhost:8080/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: End-to-end smoke via curl**

```bash
curl -s -X POST http://localhost:8080/auth/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"dev"}'

curl -s -X POST http://localhost:8080/skills \
  -H "Content-Type: application/json" \
  -H "X-Relay-Agent-Id: dev" \
  -d '{"name":"smoke","description":"smoke test","when_to_use":"w","body":"hi","metadata":{"problem":{"symptom":"x"},"solution":{"approach":"y","tools_used":[]}}}'
```

This call will actually hit OpenAI unless `RELAY_OPENAI_API_KEY` is set to a dummy that will fail — that's acceptable for the smoke test. If you do NOT want to hit OpenAI, skip this curl and rely on the pytest suite (which uses `StubEmbedder`).

- [ ] **Step 4: Commit**

```bash
git add central_api/Dockerfile
git commit -m "feat(api): add Dockerfile for uvicorn service"
```

---

## Task 13: Local MCP `skill_upload` tool

**Files:**
- Create: `local_mcp/tools/upload.py`
- Create: `tests/test_upload.py`
- Modify: `local_mcp/server.py` (register new tool)

- [ ] **Step 1: Write failing tests**

Create `tests/test_upload.py`:

```python
import httpx
import pytest

from local_mcp.drift import body_hash
from local_mcp.fs import SkillLocation, read_skill, write_skill
from local_mcp.tools.upload import UploadInput, upload_skill
from local_mcp.types import Problem, RelayMetadata, Solution


@pytest.fixture
def fake_api(monkeypatch):
    """Mount an httpx MockTransport that pretends to be the central API."""
    received = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/register":
            return httpx.Response(201, json={"agent_id": "agent"})
        if request.url.path == "/skills" and request.method == "POST":
            received["body"] = request.read().decode()
            return httpx.Response(201, json={
                "id": "sk_remote_abc",
                "name": "foo",
                "description": "d",
                "when_to_use": "w",
                "body": "[REDACTED:email] body",
                "metadata": {},
                "confidence": 0.5,
                "used_count": 0, "good_count": 0, "bad_count": 0,
                "status": "active",
                "source_agent_id": "agent",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("local_mcp.tools.upload._build_transport", lambda: transport)
    return received


def _write_skill_on_disk(skill_root, name: str):
    meta = RelayMetadata(
        id="sk_local",
        source_agent_id="agent",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="s"),
        solution=Solution(approach="a", tools_used=[]),
    )
    write_skill(
        name=name, location=SkillLocation.MINE,
        frontmatter={"name": name, "description": "d", "when_to_use": "w"},
        body="alice@example.com body",
        metadata=meta,
    )


@pytest.mark.asyncio
async def test_upload_posts_skill_and_records_id(skill_root, fake_api):
    _write_skill_on_disk(skill_root, "foo")

    result = await upload_skill(UploadInput(
        name="foo", api_url="http://test", agent_id="agent",
    ))

    assert result.remote_id == "sk_remote_abc"

    # On disk the sidecar should be updated with uploaded=True and the hash.
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert loaded.metadata.uploaded is True
    assert loaded.metadata.uploaded_hash == body_hash(loaded.body)


@pytest.mark.asyncio
async def test_upload_errors_on_nonexistent_skill(skill_root, fake_api):
    with pytest.raises(FileNotFoundError):
        await upload_skill(UploadInput(
            name="does-not-exist", api_url="http://test", agent_id="agent",
        ))
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_upload.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `local_mcp/tools/upload.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

import httpx

from local_mcp.drift import body_hash
from local_mcp.fs import SkillLocation, read_skill, write_skill


@dataclass
class UploadInput:
    name: str
    api_url: str
    agent_id: str


@dataclass
class UploadResult:
    remote_id: str
    api_url: str


def _build_transport() -> httpx.BaseTransport | None:
    """Test hook: returns None to use the real network; overridden in tests."""
    return None


async def _ensure_agent_registered(client: httpx.AsyncClient, agent_id: str) -> None:
    resp = await client.post("/auth/register", json={"agent_id": agent_id})
    if resp.status_code not in (200, 201, 409):
        resp.raise_for_status()


async def upload_skill(inp: UploadInput) -> UploadResult:
    loaded = read_skill(name=inp.name, location=SkillLocation.MINE)

    payload = {
        "name": inp.name,
        "description": loaded.frontmatter.get("description", ""),
        "when_to_use": loaded.frontmatter.get("when_to_use"),
        "body": loaded.body,
        "metadata": loaded.metadata.to_dict(),
        "source_agent_id": inp.agent_id,
    }

    transport = _build_transport()
    async with httpx.AsyncClient(
        base_url=inp.api_url,
        headers={"X-Relay-Agent-Id": inp.agent_id},
        transport=transport,
        timeout=30.0,
    ) as client:
        await _ensure_agent_registered(client, inp.agent_id)
        resp = await client.post("/skills", json=payload)
        resp.raise_for_status()
        data = resp.json()

    # The server may have masked PII in body and/or attempts. We read back from the server
    # and rewrite local files so they mirror the commons version.
    loaded.metadata.uploaded = True
    loaded.metadata.uploaded_hash = body_hash(data["body"])
    loaded.metadata.id = data["id"]
    # Persist masked body locally too so drift doesn't fire on first read.
    write_skill(
        name=inp.name,
        location=SkillLocation.MINE,
        frontmatter=dict(loaded.frontmatter),
        body=data["body"],
        metadata=loaded.metadata,
    )

    return UploadResult(remote_id=data["id"], api_url=inp.api_url)
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest tests/test_upload.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Register the tool in FastMCP**

Modify `local_mcp/server.py` — add this tool inside `build_server()`:

```python
from local_mcp.tools.upload import UploadInput, upload_skill

...

@mcp.tool()
async def skill_upload(name: str, api_url: str, agent_id: str) -> dict[str, str]:
    """Upload a local `mine/<name>` skill to the central Relay API.

    Masks PII, re-downloads the server-masked body, updates .relay.yaml with
    uploaded=True and the body hash.
    """
    result = await upload_skill(UploadInput(name=name, api_url=api_url, agent_id=agent_id))
    return {"remote_id": result.remote_id, "api_url": result.api_url}
```

- [ ] **Step 6: Server test update**

Extend `tests/test_server.py::test_server_registers_expected_tools` to also assert `"skill_upload"` is in the registered tools.

- [ ] **Step 7: Full suite**

```bash
pytest -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add local_mcp/tools/upload.py local_mcp/server.py tests/test_upload.py tests/test_server.py
git commit -m "feat(mcp): skill_upload tool — mask, POST to central, record uploaded_hash"
```

---

## Task 14: Local MCP `skill_fetch` tool

**Files:**
- Create: `local_mcp/tools/fetch.py`
- Create: `tests/test_fetch.py`
- Modify: `local_mcp/server.py` (register)

- [ ] **Step 1: Write failing tests**

Create `tests/test_fetch.py`:

```python
import httpx
import pytest

from local_mcp.fs import SkillLocation, read_skill
from local_mcp.tools.fetch import FetchInput, fetch_skill


@pytest.fixture
def fake_api(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/skills/sk_remote_abc" and request.method == "GET":
            return httpx.Response(200, json={
                "id": "sk_remote_abc",
                "name": "stripe-429",
                "description": "Handle 429",
                "when_to_use": "in checkout",
                "body": "## Problem\n429\n",
                "metadata": {
                    "id": "sk_remote_abc",
                    "version": 1,
                    "source_agent_id": "someone",
                    "created_at": "2026-04-21T10:00:00Z",
                    "updated_at": "2026-04-21T10:00:00Z",
                    "confidence": 0.8,
                    "used_count": 10,
                    "good_count": 8,
                    "bad_count": 0,
                    "trigger": "manual",
                    "context": {"languages": ["python"], "libraries": []},
                    "attempts": [],
                    "uploaded": True,
                    "status": "active",
                    "problem": {"symptom": "429"},
                    "solution": {"approach": "backoff", "tools_used": []},
                },
                "confidence": 0.8,
                "used_count": 10, "good_count": 8, "bad_count": 0,
                "status": "active",
                "source_agent_id": "someone",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("local_mcp.tools.fetch._build_transport", lambda: transport)


@pytest.mark.asyncio
async def test_fetch_writes_to_downloaded_by_default(skill_root, fake_api):
    result = await fetch_skill(FetchInput(
        skill_id="sk_remote_abc", api_url="http://test", agent_id="me",
    ))

    assert result.location == "downloaded"
    loaded = read_skill(name="stripe-429", location=SkillLocation.DOWNLOADED)
    assert loaded.frontmatter["name"] == "stripe-429"
    assert loaded.metadata.id == "sk_remote_abc"
    assert loaded.metadata.confidence == 0.8
    assert loaded.body.strip().startswith("## Problem")


@pytest.mark.asyncio
async def test_fetch_respects_staging_mode(skill_root, fake_api):
    result = await fetch_skill(FetchInput(
        skill_id="sk_remote_abc", api_url="http://test", agent_id="me",
        mode="staging",
    ))
    assert result.location == "staging"
    loaded = read_skill(name="stripe-429", location=SkillLocation.STAGING)
    assert loaded.metadata.id == "sk_remote_abc"


@pytest.mark.asyncio
async def test_fetch_missing_id_raises(skill_root, fake_api):
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_skill(FetchInput(
            skill_id="sk_no", api_url="http://test", agent_id="me",
        ))
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_fetch.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `local_mcp/tools/fetch.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from local_mcp.fs import SkillLocation, write_skill
from local_mcp.types import RelayMetadata


FetchMode = Literal["downloaded", "staging"]


@dataclass
class FetchInput:
    skill_id: str
    api_url: str
    agent_id: str
    mode: FetchMode = "downloaded"


@dataclass
class FetchResult:
    name: str
    location: str
    skill_id: str


def _build_transport() -> httpx.BaseTransport | None:
    return None


async def fetch_skill(inp: FetchInput) -> FetchResult:
    transport = _build_transport()
    async with httpx.AsyncClient(
        base_url=inp.api_url,
        headers={"X-Relay-Agent-Id": inp.agent_id},
        transport=transport,
        timeout=30.0,
    ) as client:
        resp = await client.get(f"/skills/{inp.skill_id}")
        resp.raise_for_status()
        data = resp.json()

    name = data["name"]
    frontmatter = {
        "name": name,
        "description": data["description"],
        "when_to_use": data.get("when_to_use"),
    }
    # Strip frontmatter values that are None to keep the YAML clean.
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

    metadata = RelayMetadata.from_dict(data["metadata"])
    # Server is the source of truth on counts/confidence when fetched.
    metadata.confidence = data["confidence"]
    metadata.used_count = data["used_count"]
    metadata.good_count = data["good_count"]
    metadata.bad_count = data["bad_count"]
    metadata.status = data["status"]

    location = (
        SkillLocation.STAGING if inp.mode == "staging" else SkillLocation.DOWNLOADED
    )
    write_skill(
        name=name,
        location=location,
        frontmatter=frontmatter,
        body=data["body"],
        metadata=metadata,
    )
    return FetchResult(name=name, location=location.value, skill_id=data["id"])
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest tests/test_fetch.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Register in server**

Extend `local_mcp/server.py` inside `build_server()`:

```python
from local_mcp.tools.fetch import FetchInput, fetch_skill

...

@mcp.tool()
async def skill_fetch(
    skill_id: str,
    api_url: str,
    agent_id: str,
    mode: str = "downloaded",
) -> dict[str, str]:
    """Fetch a skill from the central API and save it under ~/.claude/skills/<mode>/<name>/."""
    result = await fetch_skill(FetchInput(
        skill_id=skill_id, api_url=api_url, agent_id=agent_id, mode=mode,  # type: ignore[arg-type]
    ))
    return {"name": result.name, "location": result.location, "skill_id": result.skill_id}
```

Update `tests/test_server.py::test_server_registers_expected_tools` to also assert `"skill_fetch"` is registered.

- [ ] **Step 6: Full suite**

```bash
pytest -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add local_mcp/tools/fetch.py local_mcp/server.py tests/test_fetch.py tests/test_server.py
git commit -m "feat(mcp): skill_fetch tool — GET /skills/{id}, write to downloaded/staging"
```

---

## Task 15: E2E integration test via docker-compose

**Files:**
- Create: `tests/test_e2e_upload_fetch.py`

- [ ] **Step 1: Write the integration test**

Create `tests/test_e2e_upload_fetch.py`:

```python
import os
import subprocess
import time

import httpx
import pytest

from local_mcp.fs import SkillLocation, read_skill, write_skill
from local_mcp.tools.fetch import FetchInput, fetch_skill
from local_mcp.tools.upload import UploadInput, upload_skill
from local_mcp.types import Problem, RelayMetadata, Solution


pytestmark = pytest.mark.skipif(
    os.environ.get("RELAY_RUN_E2E") != "1",
    reason="opt-in: set RELAY_RUN_E2E=1 to run (requires docker compose up)",
)


API_URL = os.environ.get("RELAY_API_URL", "http://localhost:8080")
AGENT_ID = "e2e-agent"


def _wait_for_api(timeout: int = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_URL}/health", timeout=1.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"API at {API_URL} did not become ready in {timeout}s")


@pytest.mark.asyncio
async def test_upload_then_fetch_roundtrip(skill_root):
    _wait_for_api()

    # Write a local skill.
    meta = RelayMetadata(
        id="sk_local",
        source_agent_id=AGENT_ID,
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="e2e test symptom"),
        solution=Solution(approach="e2e approach", tools_used=[]),
        context={"languages": ["python"], "libraries": []},
    )
    write_skill(
        name="e2e-test",
        location=SkillLocation.MINE,
        frontmatter={"name": "e2e-test", "description": "e2e", "when_to_use": "never"},
        body="body with alice@example.com for masking",
        metadata=meta,
    )

    # Upload.
    up = await upload_skill(UploadInput(
        name="e2e-test", api_url=API_URL, agent_id=AGENT_ID,
    ))
    remote_id = up.remote_id
    assert remote_id.startswith("sk_")

    # Local file should now be flagged uploaded.
    local = read_skill(name="e2e-test", location=SkillLocation.MINE)
    assert local.metadata.uploaded is True
    assert "[REDACTED:email]" in local.body

    # Fetch the same skill back into downloaded/.
    f = await fetch_skill(FetchInput(
        skill_id=remote_id, api_url=API_URL, agent_id=AGENT_ID,
    ))
    downloaded = read_skill(name=f.name, location=SkillLocation.DOWNLOADED)
    assert downloaded.metadata.id == remote_id
    assert "[REDACTED:email]" in downloaded.body
```

- [ ] **Step 2: Run end-to-end**

```bash
# In a separate terminal (or with -d), bring up the full stack:
export RELAY_OPENAI_API_KEY=...   # real key, embeddings will be called
docker compose up -d

# Run the E2E test:
RELAY_RUN_E2E=1 pytest tests/test_e2e_upload_fetch.py -v

# When done:
docker compose down
```

Expected: 1 passed (or the test skips if `RELAY_RUN_E2E` not set).

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_upload_fetch.py
git commit -m "test(e2e): upload+fetch roundtrip through docker-compose central API"
```

---

## Exit Criteria for Week 2 (Plan 2A)

1. `docker compose up -d postgres && pytest central_api/tests/ -v` — all central API tests pass.
2. `pytest tests/` — all local MCP tests pass (35 Week 1 + new upload/fetch/server additions).
3. `docker compose up -d && RELAY_RUN_E2E=1 pytest tests/test_e2e_upload_fetch.py` — E2E passes.
4. `curl http://localhost:8080/health` returns `{"status":"ok"}`.
5. Git log shows per-task commits from Task 0 through Task 15.
6. No dependency on AWS. Everything runs on localhost + docker.

Week 2B (AWS deploy) will take the working stack and ship it to App Runner + RDS in region `ap-northeast-2`.

---

## Self-review — performed

- **Spec coverage.**
  - SPEC §3.4 (Central Postgres schema) → Task 1 (SQL init) + Task 5 (ORM).
  - SPEC §4.2 `skill_upload` → Task 13.
  - SPEC §4.3 `skill_search` with `search_mode`, `available_tools` filter, hybrid ranking → Tasks 8 + 11.
  - SPEC §4.4 `skill_fetch` with `mode=staging|downloaded` → Task 14.
  - SPEC §5 endpoints `/skills`, `/skills/{id}`, `/skills/search`, `/auth/register` → Tasks 9, 10, 11.
  - SPEC §5 PII masking → Task 3.
  - SPEC §2 embedding (description/problem/solution × 1536) → Tasks 1 (schema) + 7 (builder) + 10 (insert).
  - SPEC §8 Week 2 roadmap → all of Tasks 0–15.
  - `skill_review` is SPEC §4.5 / §5 `/skills/{id}/reviews`; kept out of this plan per Week 3 scope but the DB schema (Task 1) and ORM (Task 5) include `reviews` so Week 3 has nothing new on the data side.
  - `skill_list_local` with drift post-upload: covered by Task 13 writing `uploaded_hash` back into the sidecar (existing Task 7 `check_drift` already reads it).

- **Placeholder scan.** No "TBD" / "similar to Task N" / "add appropriate error handling" remain. Every code block contains the full implementation needed for the step.

- **Type consistency.**
  - `RelayMetadata` / `Problem` / `Solution` / `Attempt` / `ToolUsed` are reused from Week 1; no redefinition.
  - `Skill.metadata_` is used consistently in ORM (Python side) because `metadata` is reserved on `DeclarativeBase`; column name on the DB is still `metadata` (via the positional `Column("metadata", ...)` arg).
  - `SearchMode` Literal ∈ {`problem`, `solution`, `description`, `hybrid`} — same set used in schemas.py, routers/skills.py, and tests.
  - `_to_response` / `_required_tools` / `_mask_metadata` / `_new_id` are all defined in `routers/skills.py` and reused within that file only.
  - `StubEmbedder.embed` / `embed_many` match the `EmbeddingClient` Protocol signatures expected by `upload_skill` endpoint in Task 10.
  - `UploadInput` / `FetchInput` dataclasses in `local_mcp/tools/*.py` match the FastMCP tool signatures registered in `server.py`.

- **Operational sequencing.**
  - Task 4 creates the DB fixtures before Task 5 (ORM) and later tasks depend on them.
  - Task 9 creates `routers/__init__.py` before Task 10 / Task 11 add routers.
  - Task 10 defines `_to_response` before Task 11 reuses it.
  - Task 13 (upload) depends on Tasks 3 (masking), 7 (embedding), 10 (POST /skills).
  - Task 15 (E2E) depends on every prior task and is gated via `RELAY_RUN_E2E=1`.
