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


def test_upload_request_accepts_empty_metadata_at_schema_level():
    # Schema is permissive; semantic validation of metadata structure lives in the router.
    req = SkillUploadRequest(
        name="foo", description="d", when_to_use="w", body="b", metadata={},
    )
    assert req.metadata == {}


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
