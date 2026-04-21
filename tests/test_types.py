from datetime import datetime, timezone
import pytest
from local_mcp.types import (
    Attempt,
    ToolUsed,
    Problem,
    Solution,
    RelayMetadata,
)


def test_attempt_failed_case():
    a = Attempt(tried="simple retry", failed_because="ignored Retry-After")
    assert a.tried == "simple retry"
    assert a.failed_because == "ignored Retry-After"
    assert a.worked is None


def test_attempt_worked_case():
    a = Attempt(worked="exponential backoff with header")
    assert a.worked == "exponential backoff with header"
    assert a.tried is None


def test_tool_used_mcp():
    t = ToolUsed(type="mcp", name="stripe")
    assert t.type == "mcp"
    assert t.name == "stripe"


def test_tool_used_invalid_type():
    with pytest.raises(ValueError):
        ToolUsed(type="unknown", name="x")


def test_problem_roundtrip():
    p = Problem(symptom="429 errors", context="checkout")
    as_dict = p.to_dict()
    assert as_dict == {"symptom": "429 errors", "context": "checkout"}
    back = Problem.from_dict(as_dict)
    assert back == p


def test_solution_with_tools():
    s = Solution(
        approach="exponential backoff",
        tools_used=[ToolUsed(type="library", name="tenacity")],
    )
    d = s.to_dict()
    assert d["approach"] == "exponential backoff"
    assert d["tools_used"] == [{"type": "library", "name": "tenacity"}]
    back = Solution.from_dict(d)
    assert back == s


def test_relay_metadata_defaults():
    m = RelayMetadata(
        id="sk_abc",
        source_agent_id="pseudo",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
    )
    assert m.version == 1
    assert m.confidence == 0.5
    assert m.used_count == 0
    assert m.trigger == "manual"
    assert m.status == "active"
    assert m.uploaded is False
    assert m.uploaded_hash is None
    assert m.problem is None


def test_relay_metadata_yaml_roundtrip():
    m = RelayMetadata(
        id="sk_abc",
        source_agent_id="pseudo",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="429", context="checkout"),
        solution=Solution(
            approach="backoff",
            tools_used=[ToolUsed(type="library", name="tenacity")],
        ),
        attempts=[
            Attempt(tried="sleep", failed_because="burst"),
            Attempt(worked="backoff"),
        ],
        context={"languages": ["python"]},
    )
    y = m.to_yaml()
    assert isinstance(y, str)
    back = RelayMetadata.from_yaml(y)
    assert back == m
