from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(
        "RELAY_TEST_DATABASE_URL",
        "postgresql+asyncpg://relay:relay@localhost:5432/relay",
    )
    return url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(database_url):
    # Fail fast if Postgres is not reachable.
    eng = create_async_engine(database_url, pool_pre_ping=True)
    async with eng.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(engine) -> AsyncSession:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        # Each test runs in a transaction that rolls back at the end
        # so tests don't see each other's writes.
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _truncate_all(engine):
    """Truncate skills/reviews/usage_log/agents between tests. Runs after each test."""
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE skills, reviews, usage_log, agents RESTART IDENTITY CASCADE")
        )
