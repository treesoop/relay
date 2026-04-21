import re

import pytest

from local_mcp.fs import SkillLocation, read_skill
from local_mcp.tools.capture import capture_skill, CaptureInput


def test_capture_writes_both_files(skill_root):
    result = capture_skill(CaptureInput(
        name="stripe-429",
        description="Handle Stripe 429 with exponential backoff",
        when_to_use="Stripe API in high-traffic checkout",
        problem_symptom="429 under burst traffic",
        problem_context="checkout flow",
        solution_approach="exponential backoff with Retry-After",
        attempts=[
            {"tried": "simple retry", "failed_because": "ignored Retry-After"},
            {"tried": "fixed sleep", "failed_because": "still 429"},
            {"worked": "backoff with header"},
        ],
        tools_used=[
            {"type": "library", "name": "tenacity"},
        ],
        languages=["python"],
        libraries=["stripe-python>=8.0"],
        domain="payment",
        body_sections={
            "Problem": "429 under burst.",
            "What I tried": "1. Retry loop — failed\n2. Fixed sleep — failed",
            "What worked": "Exponential backoff with header.",
            "Tools used": "- tenacity",
            "When NOT to use this": "Webhook handlers.",
        },
        source_agent_id="pseudo_xyz",
    ))

    assert result.name == "stripe-429"
    assert result.location == "mine"
    assert result.files.skill_md.exists()
    assert result.files.relay_yaml.exists()

    loaded = read_skill(name="stripe-429", location=SkillLocation.MINE)
    assert loaded.frontmatter["name"] == "stripe-429"
    assert loaded.frontmatter["description"].startswith("Handle Stripe 429")
    assert "## Problem" in loaded.body
    assert "## What I tried" in loaded.body
    assert "## What worked" in loaded.body

    assert loaded.metadata.problem is not None
    assert loaded.metadata.problem.symptom == "429 under burst traffic"
    assert loaded.metadata.solution is not None
    assert loaded.metadata.solution.approach.startswith("exponential backoff")
    assert [a.tried for a in loaded.metadata.attempts[:2]] == [
        "simple retry",
        "fixed sleep",
    ]
    assert loaded.metadata.attempts[2].worked == "backoff with header"
    assert loaded.metadata.source_agent_id == "pseudo_xyz"
    assert loaded.metadata.trigger == "manual"
    assert loaded.metadata.uploaded is False


def test_capture_id_format(skill_root):
    result = capture_skill(CaptureInput(
        name="foo",
        description="d",
        when_to_use="w",
        problem_symptom="s",
        problem_context=None,
        solution_approach="a",
        attempts=[],
        tools_used=[],
        languages=[],
        libraries=[],
        domain=None,
        body_sections={"Problem": "x"},
        source_agent_id="pseudo_xyz",
    ))
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert re.match(r"^sk_[a-z0-9]{16}$", loaded.metadata.id)


def test_capture_rejects_invalid_name(skill_root):
    with pytest.raises(ValueError):
        capture_skill(CaptureInput(
            name="Invalid Name",
            description="d",
            when_to_use="w",
            problem_symptom="s",
            problem_context=None,
            solution_approach="a",
            attempts=[],
            tools_used=[],
            languages=[],
            libraries=[],
            domain=None,
            body_sections={"Problem": "x"},
            source_agent_id="pseudo_xyz",
        ))


def test_capture_with_trigger_override(skill_root):
    capture_skill(CaptureInput(
        name="foo",
        description="d",
        when_to_use="w",
        problem_symptom="s",
        problem_context=None,
        solution_approach="a",
        attempts=[],
        tools_used=[],
        languages=[],
        libraries=[],
        domain=None,
        body_sections={"Problem": "x"},
        source_agent_id="pseudo_xyz",
        trigger="error_recovery",
    ))
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert loaded.metadata.trigger == "error_recovery"
