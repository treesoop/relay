from __future__ import annotations

import pytest
from fastmcp import FastMCP

from local_mcp.server import build_server


async def _tools_by_name(server: FastMCP) -> dict[str, object]:
    """FastMCP 3.x exposes list_tools() -> list[Tool]; re-key by name for tests."""
    tools = await server.list_tools()
    return {t.name: t for t in tools}


@pytest.mark.asyncio
async def test_server_registers_expected_tools(skill_root):
    server = build_server()
    assert isinstance(server, FastMCP)

    tools = await _tools_by_name(server)
    names = set(tools.keys())
    assert "skill_capture" in names
    assert "skill_list_local" in names
    assert "skill_upload" in names


@pytest.mark.asyncio
async def test_capture_tool_end_to_end(skill_root):
    server = build_server()
    tools = await _tools_by_name(server)
    capture = tools["skill_capture"]

    result = await capture.run({
        "name": "foo",
        "description": "d",
        "when_to_use": "w",
        "problem_symptom": "s",
        "problem_context": None,
        "solution_approach": "a",
        "attempts": [],
        "tools_used": [],
        "languages": [],
        "libraries": [],
        "domain": None,
        "body_sections": {"Problem": "x"},
        "source_agent_id": "pseudo",
    })

    # structured_content or content depending on FastMCP version
    payload = result.structured_content or (result.content[0].text if result.content else None)
    assert payload is not None

    # Structured payload should include the skill identity + file paths
    assert isinstance(result.structured_content, dict)
    assert result.structured_content["name"] == "foo"
    assert result.structured_content["location"] == "mine"
    assert result.structured_content["id"].startswith("sk_")
    assert "skill_md_path" in result.structured_content
    assert "relay_yaml_path" in result.structured_content


@pytest.mark.asyncio
async def test_list_tool_end_to_end(skill_root):
    server = build_server()
    tools = await _tools_by_name(server)
    lst = tools["skill_list_local"]

    result = await lst.run({})
    payload = result.structured_content or (result.content[0].text if result.content else None)
    # Empty root → empty list
    assert payload is not None
