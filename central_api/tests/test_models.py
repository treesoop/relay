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
