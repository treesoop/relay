# Relay Week 2C — Swap OpenAI for Local BGE-small Embedder

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the OpenAI `text-embedding-3-small` (1536-dim) default with a locally-hosted `BAAI/bge-small-en-v1.5` (384-dim) via sentence-transformers. The OpenAI embedder stays as an opt-in alternative behind a `RELAY_EMBEDDING_PROVIDER=openai` flag. Migration-safe: since skill bodies + metadata are preserved verbatim in Postgres, any future dimension change is a "re-embed from stored source" operation, never a data-loss event.

**Architecture:** Introduce an `embedding_provider` config knob reading `local` (default) or `openai`. Add a `LocalEmbedder` class that wraps `sentence_transformers.SentenceTransformer` in an async thread-pool shim so it satisfies the existing `EmbeddingClient` Protocol. Rewrite the DB schema from `vector(1536)` to `vector(384)` (dev DB is greenfield, so `docker compose down -v` is the acceptable reset path for MVP). Server container pre-downloads the model at build time so cold starts don't stall on a 130MB network fetch. No local MCP client changes — all embedding logic remains server-side.

**Tech Stack:**
- `sentence-transformers>=3.0` (with `torch` CPU-only wheel via `--extra-index-url https://download.pytorch.org/whl/cpu`)
- `BAAI/bge-small-en-v1.5` — 384 dims, MTEB avg 62.17, ~130MB
- All existing Week 2 components: FastAPI, SQLAlchemy, pgvector, asyncpg

---

## File Structure

```
relay/
├── pyproject.toml                            # MODIFY: sentence-transformers, torch CPU index
├── .env.example                              # MODIFY: provider/dim/model defaults
│
├── central_api/
│   ├── config.py                             # MODIFY: embedding_provider/dim; openai_api_key optional
│   ├── embedding.py                          # MODIFY: add LocalEmbedder + build_embedder factory
│   ├── sql/
│   │   └── 001_init.sql                      # MODIFY: vector(1536) → vector(384)
│   ├── models.py                             # MODIFY: Vector(1536) → Vector(384)
│   ├── main.py                               # MODIFY: create_app uses build_embedder() when None
│   ├── Dockerfile                            # MODIFY: pre-download model during build
│   └── tests/
│       ├── test_config.py                    # MODIFY: new provider/dim fields
│       ├── test_embedding.py                 # MODIFY: stub default 384 + LocalEmbedder smoke
│       └── (unchanged otherwise)
│
├── tests/
│   └── test_e2e_upload_fetch.py              # MODIFY: drop OpenAI-key requirement
│
├── docker-compose.yml                        # UNCHANGED (api service pulls env, schema mount still correct)
│
└── README.md                                 # MODIFY: document default-local + migration recipe
```

**What does NOT change:**
- Local MCP tools (`upload.py`, `fetch.py`, `capture.py`, `list_local.py`) — they're HTTP clients that don't know embedding exists.
- Domain types, fs/drift modules, plugin adapter.
- PII masking, ranking, auth, schemas, ORM structure (only Vector dim changes).
- Claude Code plugin — MCP interface unchanged.

---

## Task 0: Dependencies + Settings rework

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add sentence-transformers to deps**

Edit `pyproject.toml` `dependencies` list. Add **after** the existing `openai` line:

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
    # Week 2C — local embeddings
    "sentence-transformers>=3.0",
]
```

- [ ] **Step 2: Install (CPU torch wheel)**

On macOS/Linux, sentence-transformers pulls in `torch` which is ~700MB. Force the CPU wheel to avoid CUDA weight:

```bash
cd /Users/dion/potenlab/our_project/relay
source .venv/bin/activate
pip install --extra-index-url https://download.pytorch.org/whl/cpu -e ".[dev]"
python -c "import sentence_transformers; print('ok', sentence_transformers.__version__)"
```

Expected: `ok 3.x.x`

- [ ] **Step 3: Rewrite `.env.example`**

Replace the file contents with:

```
# Central API — embedding provider
# "local" (default) uses sentence-transformers with BAAI/bge-small-en-v1.5 (384 dims).
# "openai" requires RELAY_OPENAI_API_KEY and uses text-embedding-3-small (1536 dims) —
#   requires a DB schema with vector(1536) (not the default vector(384)).
RELAY_EMBEDDING_PROVIDER=local
RELAY_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RELAY_EMBEDDING_DIM=384

# Central API — infra
RELAY_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay
RELAY_API_HOST=0.0.0.0
RELAY_API_PORT=8080

# Only required if RELAY_EMBEDDING_PROVIDER=openai
RELAY_OPENAI_API_KEY=

# Local MCP client
RELAY_API_URL=http://localhost:8080
RELAY_AGENT_ID=local-dev
```

- [ ] **Step 4: Smoke-test imports**

```bash
python -c "from sentence_transformers import SentenceTransformer; print('ok')"
python -c "import torch; print(torch.__version__, 'cuda:', torch.cuda.is_available())"
```

Expected: `ok`, then `2.x.x cuda: False`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example
git commit -m "chore(week2c): add sentence-transformers + update env template for local embeddings"
```

---

## Task 1: DB schema migration (1536 → 384)

**Files:**
- Modify: `central_api/sql/001_init.sql`

- [ ] **Step 1: Update init SQL**

Change every `vector(1536)` to `vector(384)`. The rest of the file stays identical.

After edit, the three embedding columns should read:

```sql
    description_embedding vector(384),
    problem_embedding     vector(384),
    solution_embedding    vector(384),
```

- [ ] **Step 2: Wipe and re-initialize the dev DB**

The `001_init.sql` bind mount only runs on a fresh data directory. We must destroy the volume:

```bash
cd /Users/dion/potenlab/our_project/relay
docker compose down -v
docker compose up -d postgres
# Wait for healthy
until [ "$(docker compose ps --format json postgres | python3 -c 'import sys,json; d=json.loads(sys.stdin.read()); print(d.get("Health",""))')" = "healthy" ]; do sleep 1; done
```

- [ ] **Step 3: Verify the new schema**

```bash
docker compose exec -T postgres psql -U relay -d relay -c "\d skills" | grep embedding
```

Expected:
```
 description_embedding | vector(384)                 |
 problem_embedding     | vector(384)                 |
 solution_embedding    | vector(384)                 |
```

- [ ] **Step 4: Commit**

```bash
git add central_api/sql/001_init.sql
git commit -m "feat(api): switch embedding vector dimension from 1536 to 384 (BGE-small)"
```

---

## Task 2: ORM dimension update

**Files:**
- Modify: `central_api/models.py`

- [ ] **Step 1: Change Vector(1536) → Vector(384)**

In `central_api/models.py`, the `Skill` class has three embedding columns. Change each `Vector(1536)` to `Vector(384)`:

```python
    description_embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    problem_embedding:     Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    solution_embedding:    Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
```

- [ ] **Step 2: Run the ORM tests**

```bash
source .venv/bin/activate
pytest central_api/tests/test_models.py -v
```

Expected: 2 passed. (The tests insert skills without embeddings, so dimension doesn't matter at this level.)

- [ ] **Step 3: Commit**

```bash
git add central_api/models.py
git commit -m "feat(api): update ORM Vector(1536) → Vector(384) to match new schema"
```

---

## Task 3: Config changes — provider/dim/model

**Files:**
- Modify: `central_api/config.py`
- Modify: `central_api/tests/test_config.py`

- [ ] **Step 1: Update `central_api/config.py`**

Replace the `Settings` class with:

```python
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


EmbeddingProvider = Literal["local", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RELAY_", env_file=".env", extra="ignore")

    database_url: str

    # Embedding provider selection. "local" is the default and uses sentence-transformers.
    # "openai" is opt-in and requires openai_api_key + DB schema with vector(1536).
    embedding_provider: EmbeddingProvider = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # Only required when embedding_provider == "openai".
    openai_api_key: str | None = None

    api_host: str = "0.0.0.0"
    api_port: int = 8080


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 2: Update `central_api/tests/test_config.py`**

Replace the existing two tests with:

```python
import pytest

from central_api.config import Settings


def test_settings_loads_defaults(monkeypatch):
    # Clear all optional envs so defaults kick in.
    for key in ("RELAY_EMBEDDING_PROVIDER", "RELAY_EMBEDDING_MODEL",
                "RELAY_EMBEDDING_DIM", "RELAY_OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.embedding_provider == "local"
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.embedding_dim == 384
    assert s.openai_api_key is None
    assert s.api_host == "0.0.0.0"
    assert s.api_port == 8080


def test_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("RELAY_DATABASE_URL", raising=False)
    with pytest.raises(Exception):
        Settings()


def test_settings_openai_provider_allows_key(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk-test")

    s = Settings()
    assert s.embedding_provider == "openai"
    assert s.openai_api_key == "sk-test"


def test_settings_invalid_provider_rejected(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "bogus")
    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 3: Run config tests**

```bash
pytest central_api/tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add central_api/config.py central_api/tests/test_config.py
git commit -m "feat(api): add embedding_provider config (local default, openai opt-in)"
```

---

## Task 4: LocalEmbedder + build_embedder factory

**Files:**
- Modify: `central_api/embedding.py`
- Modify: `central_api/tests/test_embedding.py`

- [ ] **Step 1: Write failing tests**

Edit `central_api/tests/test_embedding.py`. Replace the file contents with:

```python
import pytest

from central_api.config import Settings
from central_api.embedding import (
    EmbeddingClient,
    LocalEmbedder,
    OpenAIEmbedder,
    StubEmbedder,
    build_embedder,
    build_embedding_targets,
)


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
    assert "retry loop" in targets["solution"]


@pytest.mark.asyncio
async def test_stub_embedder_default_dim_is_384():
    stub = StubEmbedder()
    v = await stub.embed("x")
    assert len(v) == 384


@pytest.mark.asyncio
async def test_stub_embedder_custom_dim():
    stub = StubEmbedder(dim=1536)
    v = await stub.embed("x")
    assert len(v) == 1536


@pytest.mark.asyncio
async def test_stub_embedder_deterministic():
    stub = StubEmbedder()
    v1 = await stub.embed("same")
    v2 = await stub.embed("same")
    v3 = await stub.embed("different")
    assert v1 == v2
    assert v1 != v3


@pytest.mark.asyncio
async def test_stub_embedder_batch():
    stub = StubEmbedder()
    vectors = await stub.embed_many(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)


@pytest.mark.asyncio
async def test_local_embedder_smoke():
    """Actual end-to-end with sentence-transformers. Slow (downloads model on first run).

    If the test machine has no disk/network for the model, this will raise.
    We accept the slowness — it's the only integration check for the real embedder.
    """
    emb = LocalEmbedder(model_name="BAAI/bge-small-en-v1.5")
    v = await emb.embed("hello world")
    assert len(v) == 384
    assert all(isinstance(x, float) for x in v)

    batch = await emb.embed_many(["alpha", "beta"])
    assert len(batch) == 2
    assert all(len(x) == 384 for x in batch)


def test_build_embedder_local_by_default(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    for key in ("RELAY_EMBEDDING_PROVIDER", "RELAY_OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    emb = build_embedder(settings)
    assert isinstance(emb, LocalEmbedder)


def test_build_embedder_openai_when_configured(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk-test")
    settings = Settings()
    emb = build_embedder(settings)
    assert isinstance(emb, OpenAIEmbedder)


def test_build_embedder_openai_without_key_raises(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("RELAY_OPENAI_API_KEY", raising=False)
    settings = Settings()
    with pytest.raises(ValueError, match="openai_api_key"):
        build_embedder(settings)
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest central_api/tests/test_embedding.py -v
```

Expected: import errors for `LocalEmbedder` and `build_embedder`.

- [ ] **Step 3: Implement `central_api/embedding.py`**

Replace the file contents with:

```python
from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Protocol

from openai import AsyncOpenAI

from central_api.config import Settings, get_settings


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


class LocalEmbedder:
    """sentence-transformers in an async thread-pool shim.

    Model is loaded once on first instantiation. Callers should reuse the instance
    (LocalEmbedder() at app start, reused per request).
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    async def embed(self, text: str) -> list[float]:
        vec = await asyncio.to_thread(
            self._model.encode, text, normalize_embeddings=True
        )
        return vec.tolist()

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = await asyncio.to_thread(
            self._model.encode, texts, normalize_embeddings=True, batch_size=32
        )
        return [v.tolist() for v in vecs]


class StubEmbedder:
    """Deterministic fake embedder for tests. sha256(text) hashed down to floats."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
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


def build_embedder(settings: Settings | None = None) -> EmbeddingClient:
    """Return an EmbeddingClient based on settings.

    - provider=local (default): LocalEmbedder with settings.embedding_model
    - provider=openai: OpenAIEmbedder — requires openai_api_key
    """
    s = settings or get_settings()
    if s.embedding_provider == "openai":
        if not s.openai_api_key:
            raise ValueError(
                "embedding_provider=openai requires openai_api_key (set RELAY_OPENAI_API_KEY)"
            )
        return OpenAIEmbedder()
    return LocalEmbedder(model_name=s.embedding_model)
```

- [ ] **Step 4: Run tests**

```bash
pytest central_api/tests/test_embedding.py -v
```

Expected: 9 passed. The `test_local_embedder_smoke` will take 10-30 seconds the first time (downloads the model to `~/.cache/huggingface/hub/`).

- [ ] **Step 5: Commit**

```bash
git add central_api/embedding.py central_api/tests/test_embedding.py
git commit -m "feat(api): add LocalEmbedder (sentence-transformers) + build_embedder factory"
```

---

## Task 5: Wire build_embedder in main.py

**Files:**
- Modify: `central_api/main.py`

- [ ] **Step 1: Update `create_app`**

Replace `central_api/main.py` with:

```python
from __future__ import annotations

from fastapi import FastAPI

from central_api.embedding import EmbeddingClient, build_embedder
from central_api.routers.auth_router import router as auth_router
from central_api.routers.skills import router as skills_router


def create_app(*, embedder: EmbeddingClient | None = None) -> FastAPI:
    app = FastAPI(title="Relay Central API", version="0.1.0")

    app.state.embedder = embedder or build_embedder()

    app.include_router(auth_router)
    app.include_router(skills_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

Only change: `OpenAIEmbedder()` → `build_embedder()`. Tests still inject `StubEmbedder` explicitly.

- [ ] **Step 2: Run API tests**

```bash
pytest central_api/tests/test_api_skills.py central_api/tests/test_api_search.py -v
```

Expected: 7 passed (4 skills + 3 search). These use `StubEmbedder()` explicitly so no LocalEmbedder load happens.

- [ ] **Step 3: Commit**

```bash
git add central_api/main.py
git commit -m "feat(api): wire build_embedder() as default in create_app"
```

---

## Task 6: Dockerfile — pre-download model at build

**Files:**
- Modify: `central_api/Dockerfile`

- [ ] **Step 1: Update Dockerfile**

Replace `central_api/Dockerfile` with:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install CPU torch first so sentence-transformers dep resolution uses the CPU wheel.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch

COPY pyproject.toml ./
COPY README.md ./
COPY central_api ./central_api
COPY local_mcp ./local_mcp

RUN pip install --no-cache-dir -e ".[dev]"

# Pre-download the embedding model so cold starts don't stall on a 130MB fetch.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

EXPOSE 8080
CMD ["uvicorn", "--factory", "central_api.main:create_app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Rebuild and verify**

```bash
docker compose build api
docker compose up -d
sleep 5
curl -s http://localhost:8080/health
```

Expected: `{"status":"ok"}`. The image will be ~1.5GB (torch CPU + transformers + model). Build takes ~3-5 minutes the first time; subsequent builds cache the pip + model download layers.

- [ ] **Step 3: Commit**

```bash
git add central_api/Dockerfile
git commit -m "feat(api): pre-download BGE-small model in Docker image build"
```

---

## Task 7: E2E test — drop OpenAI key requirement

**Files:**
- Modify: `tests/test_e2e_upload_fetch.py`

- [ ] **Step 1: Update the docstring/comments**

The actual skip guard (`RELAY_RUN_E2E != "1"`) already works without OpenAI — the api container now uses LocalEmbedder by default. No logic changes are needed, but update the `reason` string in the `pytestmark.skipif` to reflect the new state:

In `tests/test_e2e_upload_fetch.py`, find:

```python
pytestmark = pytest.mark.skipif(
    os.environ.get("RELAY_RUN_E2E") != "1",
    reason="opt-in: set RELAY_RUN_E2E=1 to run (requires docker compose up)",
)
```

Change to:

```python
pytestmark = pytest.mark.skipif(
    os.environ.get("RELAY_RUN_E2E") != "1",
    reason="opt-in: set RELAY_RUN_E2E=1 to run (requires `docker compose up -d`)",
)
```

(This is a clarification edit — the underlying behavior is unchanged.)

- [ ] **Step 2: Actually run the E2E**

With the new stack, no OpenAI key is needed:

```bash
docker compose up -d
sleep 5
curl -s http://localhost:8080/health  # expect {"status":"ok"}
RELAY_RUN_E2E=1 pytest tests/test_e2e_upload_fetch.py -v
```

Expected: **1 passed**. The LocalEmbedder embedding inside the container takes ~100-500ms for the 3-vector batch, so total test runtime is typically 2-4 seconds.

If the test fails with a connection refused or embedder error, check `docker compose logs api | tail -40` for clues.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_upload_fetch.py
git commit -m "test(e2e): remove OpenAI key requirement (local embedder is now default)"
```

---

## Task 8: README update — document default + migration

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Privacy and embeddings" section after "Design principles"**

Add this section verbatim to `README.md` just after the "Design principles" block (look for the `## Development` heading — insert before it):

```markdown
## Privacy and embeddings

Relay runs a **local embedding model** (`BAAI/bge-small-en-v1.5`, 384 dims, MTEB avg 62.17) by default. Your skill bodies never leave the Relay server, and no OpenAI API key is required.

To opt in to OpenAI's embeddings (for possibly higher quality at some scale), set:

    RELAY_EMBEDDING_PROVIDER=openai
    RELAY_OPENAI_API_KEY=sk-...

This also requires the DB schema to use `vector(1536)` instead of `vector(384)`. See the migration recipe below.

### Changing embedding dimensions later

Skill bodies and metadata are the source of truth; embeddings are a derived cache. To migrate to a different model/dimension:

1. **For dev / small corpora:** edit `central_api/sql/001_init.sql` and `central_api/models.py`, then `docker compose down -v && docker compose up -d postgres`. Re-upload skills (only ever tens or hundreds).
2. **For production / existing corpora:**
   - Add new columns (`description_embedding_v2 vector(N)`, etc.) via migration.
   - Backfill by iterating every skill and calling the new embedder on its stored body + metadata.
   - Switch search/upload code to the `_v2` columns.
   - Drop the old columns and indexes once traffic is fully cut over.

Because `body` (TEXT) and `metadata` (JSONB) are always preserved, embedding migration is a pure recomputation — no data can be lost.
```

- [ ] **Step 2: Update the "How it works" ASCII diagram**

In the `## How it works` section, change:

```
  Central API (FastAPI on AWS App Runner)
  Postgres + pgvector on RDS
  OpenAI text-embedding-3-small
```

to:

```
  Central API (FastAPI on AWS App Runner)
  Postgres + pgvector on RDS
  Local embeddings — BGE-small-en-v1.5 (384 dims, sentence-transformers)
  OpenAI text-embedding-3-small — opt-in via env var
```

- [ ] **Step 3: Update the `## Current status — Week 1 shipped` section**

Nothing to change here (Week 1 work is still accurate). But add a new block **below** it:

```markdown
## Week 2 shipped — central API + local embeddings

- FastAPI server with Postgres + pgvector (384-dim).
- Local BGE-small-en-v1.5 embeddings via sentence-transformers — no API keys required.
- `POST /skills`, `GET /skills/{id}`, `GET /skills/search` with hybrid ranking (similarity + confidence + context match).
- `skill_upload` + `skill_fetch` MCP tools, end-to-end tested through docker-compose.
- PII masking of bodies and attempts before storage.
- OpenAI embeddings available behind a single env var flip.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document local embedding default + migration recipe + Week 2 status"
```

---

## Task 9: Full suite + cleanup verification

**Files:** none created; this is verification only.

- [ ] **Step 1: Run the full suite without E2E**

```bash
source .venv/bin/activate
pytest -v
```

Expected: `N passed, 1 skipped` where N ≥ 76 (the Week 2 suite plus any new tests from Tasks 3 and 4 above — specifically new config tests and new embedding tests). Precisely: Week 2 had 76 passed + 1 skipped; Plan 2C added 2 config tests (3 → 5 → net +2) and 5 embedding tests (3 → 9 → net +5, of which 1 is a slow real-model test). So expect about **83 passed, 1 skipped** total.

If the full count differs, investigate.

- [ ] **Step 2: Run the E2E with real embedding**

```bash
RELAY_RUN_E2E=1 pytest tests/test_e2e_upload_fetch.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Measure image size (informational)**

```bash
docker images relay-api --format '{{.Size}}'
```

Expected: ~1.2-1.8 GB. Document the actual number in your report.

- [ ] **Step 4: Final commit (if any cleanup needed)**

No expected code changes in Task 9. If the full suite reveals a dangling test failure that wasn't caught in earlier tasks (e.g. a 1536-dim assertion somewhere), fix it here with a focused commit:

```bash
# Only if something is broken; otherwise skip.
git add <specific files>
git commit -m "chore(week2c): fix <specific issue>"
```

---

## Exit Criteria for Plan 2C

1. `pytest` (no env vars) shows roughly 83 passed + 1 skipped — both Week 1 and Week 2 coverage intact.
2. `RELAY_RUN_E2E=1 pytest tests/test_e2e_upload_fetch.py -v` passes without any OpenAI credentials.
3. `docker compose up -d` starts postgres + api; `curl http://localhost:8080/health` returns `{"status":"ok"}`.
4. `docker compose exec -T postgres psql -U relay -d relay -c "\d skills"` shows all three embedding columns as `vector(384)`.
5. Setting `RELAY_EMBEDDING_PROVIDER=openai` + `RELAY_OPENAI_API_KEY=sk-...` and restarting api **would** fall back to OpenAI cleanly (not verified in this plan but explicitly supported — follows from `build_embedder` logic).
6. Commits are per-task (9-ish commits on branch `week2`).

---

## Self-review — performed

- **Spec coverage.** Every task in the plan touches exactly the files listed in its File Structure. OpenAI path is preserved as an opt-in; default is `local`. Plan 2B (AWS deploy) is unaffected — it only ships whatever is in the container, which now includes BGE-small.
- **Placeholder scan.** No TBD / similar-to / "add error handling" — every step has full code or exact commands.
- **Type consistency.** `EmbeddingClient` Protocol unchanged; `LocalEmbedder`, `OpenAIEmbedder`, `StubEmbedder` all satisfy it. `build_embedder(settings)` returns `EmbeddingClient`. `Settings.embedding_provider: Literal["local", "openai"]` matches `EmbeddingProvider` alias. `StubEmbedder(dim=384)` default is consistent with `Settings.embedding_dim=384`. Tests that previously used 1536 dim explicitly (in test_embedding.py Week 2) have been rewritten to use the new default 384, with a separate `test_stub_embedder_custom_dim` to pin the parameter-override behavior.
- **Scope discipline.** No new MCP tools, no new routes, no new domain types. Just: swap embedder implementation, shrink vector dim, update config + docs.

---

## What this plan does NOT do (intentionally)

- **Does not add a migration script for non-empty DBs.** Dev DB is small; SPEC migration recipe is documented in README for production use.
- **Does not add GPU support.** `--extra-index-url .../cpu` forces CPU torch. GPU support can be added in a separate plan for production inference workloads.
- **Does not re-run Week 1 plugin install.** The Claude Code plugin is unchanged; no re-install needed.
- **Does not measure embedding quality.** We accept BGE-small-en-v1.5's MTEB-reported quality as sufficient for MVP. Benchmark against our real skill corpus is a Week 3+ concern.
