---
name: relay:capture
description: Capture the current session as a Relay skill (Problem → Attempts → Solution)
---

You are about to call the `skill_capture` MCP tool.

Before calling:
1. Summarize the problem just solved in one sentence.
2. List every failed attempt with its failure reason. NEVER omit failures.
3. State what finally worked.
4. List the tools used: each as `{type: "mcp"|"library"|"cli", name: "..."}`.
5. Propose a kebab-case skill name.
6. Confirm with the user before writing.

Then call `skill_capture` with all required fields. Afterwards, show the user:
- The resulting `skill_md_path` and `relay_yaml_path`.
- A reminder that this is local-only; call `/relay:upload <name>` to share it.
