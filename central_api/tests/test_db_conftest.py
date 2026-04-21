import pytest
from sqlalchemy import text


@pytest.mark.asyncio(loop_scope="session")
async def test_db_is_reachable(db_session):
    result = await db_session.execute(text("SELECT 1 AS ok"))
    row = result.one()
    assert row.ok == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_pgvector_extension_installed(engine):
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        )
        row = result.one_or_none()
        assert row is not None
