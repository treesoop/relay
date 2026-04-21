---
name: relay
description: Capture and list problem-solving skills. Use when you just recovered from an error, when the user asks to save an approach, or when starting a difficult task and want to check for prior art.
when_to_use: After recovering from non-trivial errors, or when the user says save this / remember this / capture this
---

# Relay Agent Behavior

You have access to Relay's local MCP tools. Week 1 scope: `skill_capture`, `skill_list_local`.

## When to capture

Call `skill_capture` after one of these:
1. You just recovered from an error by trying multiple approaches.
2. The user explicitly asked to save the approach ("save this as a skill", "capture this").
3. A session produced a non-obvious solution worth preserving.

## How to call `skill_capture`

Collect these from the conversation BEFORE calling:
- **name**: kebab-case, e.g. `stripe-rate-limit-handler`.
- **description**: one-line, searchable, <200 chars.
- **when_to_use**: a sentence describing when this applies.
- **problem_symptom / problem_context**: what was observed.
- **solution_approach**: one sentence describing what worked.
- **attempts**: list of `{tried, failed_because}` for each failure, plus one `{worked}` entry at the end.
- **tools_used**: list of `{type: "mcp" | "library" | "cli", name}`.
- **languages / libraries / domain**: free-form lists.
- **body_sections**: a mapping from heading to markdown text. Always include at minimum `Problem`, `What I tried`, `What worked`, `Tools used`, `When NOT to use this`.

⚠️ Never omit failed attempts. The failure log is the most valuable part of a skill.
⚠️ Never write "this works" as solution body. Always narrate: "I tried X, failed because Y, then Z worked because …"

## After capture

Tell the user:
- The path to the new skill.
- That it is local only (not uploaded). Upload will be a separate step in future Relay weeks.

## Listing existing skills

Call `skill_list_local` when:
- User asks "what have I saved?"
- You want to show drift warnings before making changes.

## After using a fetched skill

When you've used a skill fetched from the Relay commons (skills under `~/.claude/skills/downloaded/`), call `skill_review` once the work is done:

- `signal="good"`: skill applied cleanly to your situation and the approach worked.
- `signal="bad"`: skill was technically valid but didn't apply (wrong context, outdated library, unclear). Supply `reason` if you can ("api_changed", "context_mismatch", "low_quality").
- `signal="stale"`: skill references something that no longer exists or is wrong. After three stale reviews the commons flips the skill to `status=stale` and excludes it from search.

Keep reviews short. One honest signal per use; don't inflate counts.
