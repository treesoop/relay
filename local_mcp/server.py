from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from local_mcp.tools.capture import CaptureInput, capture_skill
from local_mcp.tools.list_local import list_local_skills


def build_server() -> FastMCP:
    mcp = FastMCP("relay")

    @mcp.tool()
    def skill_capture(
        name: str,
        description: str,
        when_to_use: str,
        problem_symptom: str,
        problem_context: str | None,
        solution_approach: str,
        attempts: list[dict[str, Any]],
        tools_used: list[dict[str, Any]],
        languages: list[str],
        libraries: list[str],
        domain: str | None,
        body_sections: dict[str, str],
        source_agent_id: str,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        """Capture a problem-solving session into a local skill directory.

        Writes SKILL.md (Claude Code format) and .relay.yaml (Relay metadata)
        under ~/.claude/skills/mine/<name>/.
        """
        result = capture_skill(CaptureInput(
            name=name,
            description=description,
            when_to_use=when_to_use,
            problem_symptom=problem_symptom,
            problem_context=problem_context,
            solution_approach=solution_approach,
            attempts=attempts,
            tools_used=tools_used,
            languages=languages,
            libraries=libraries,
            domain=domain,
            body_sections=body_sections,
            source_agent_id=source_agent_id,
            trigger=trigger,
        ))
        return {
            "id": result.id,
            "name": result.name,
            "location": result.location,
            "skill_md_path": str(result.files.skill_md),
            "relay_yaml_path": str(result.files.relay_yaml),
        }

    @mcp.tool()
    def skill_list_local() -> list[dict[str, Any]]:
        """List every Relay-managed skill under ~/.claude/skills/."""
        return list_local_skills()

    return mcp


def main() -> None:
    server = build_server()
    server.run()  # default: stdio


if __name__ == "__main__":
    main()
