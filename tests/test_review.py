import httpx
import pytest

from local_mcp.tools.review import ReviewInput, review_skill


@pytest.fixture
def fake_api(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/skills/sk_abc/reviews" and request.method == "POST":
            return httpx.Response(201, json={
                "id": 1,
                "skill_id": "sk_abc",
                "agent_id": "me",
                "signal": "good",
                "reason": None,
                "note": None,
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("local_mcp.tools.review._build_transport", lambda: transport)


@pytest.mark.asyncio
async def test_review_good_succeeds(fake_api):
    result = await review_skill(ReviewInput(
        skill_id="sk_abc", api_url="http://test", agent_id="me", signal="good",
    ))
    assert result.review_id == 1
    assert result.skill_id == "sk_abc"


@pytest.mark.asyncio
async def test_review_with_reason_and_note(fake_api):
    result = await review_skill(ReviewInput(
        skill_id="sk_abc", api_url="http://test", agent_id="me",
        signal="good", reason="worked as described", note="saved 20 min",
    ))
    assert result.skill_id == "sk_abc"


@pytest.mark.asyncio
async def test_review_missing_skill_raises(fake_api):
    with pytest.raises(httpx.HTTPStatusError):
        await review_skill(ReviewInput(
            skill_id="sk_nope", api_url="http://test", agent_id="me", signal="good",
        ))
