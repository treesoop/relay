---
name: relay
description: Capture, search, upload, fetch, and review problem-solving skills across the Relay commons. Use when starting a non-trivial task (search first!), after recovering from errors (capture), or after using someone else's skill (review).
when_to_use: Starting a difficult task — search first. Solved something messy — capture. Used a fetched skill — review.
---

# Relay Agent Behavior

You have five MCP tools for the shared skill commons:

| Tool | When |
|---|---|
| `skill_search` | **ALWAYS try first** when starting a non-trivial task. Search by `problem` mode with a natural-language description of your situation. |
| `skill_fetch` | After picking a search result. Use `mode=staging` for previews, `mode=downloaded` once you're committing to try it. |
| `skill_capture` | After recovering from non-trivial errors OR when the user says save this / remember this. Local-only until uploaded. |
| `skill_upload` | When the user confirms they want a captured skill shared with the commons. Masks PII, rewrites the local body with the masked version. |
| `skill_review` | After USING a fetched skill. One honest signal per use — `good`, `bad`, or `stale`. |

## When to search

Before starting a difficult task, ask: "have I seen this before?" Call `skill_search`
with a natural-language description of the symptom. If similarity > 0.7 and
confidence > 0.5 on the top hit, read it before you start.

## When to capture

After you solve something through trial and error:
1. Enumerate the attempts and their failure reasons. Never omit a failed attempt.
2. Propose a kebab-case name.
3. Confirm with the user before calling `skill_capture`.
4. Ask whether they want to share it via `skill_upload`.

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

Never omit failed attempts. The failure log is the most valuable part of a skill.
Never write "this works" as solution body. Always narrate: "I tried X, failed because Y, then Z worked because …"

## When to review

Always call `skill_review` after you used a fetched skill. One review per use.

- `signal="good"`: skill applied cleanly and the approach worked.
- `signal="bad"`: skill was technically valid but didn't apply (wrong context, outdated library, unclear). Supply `reason` when you can.
- `signal="stale"`: skill references something that no longer exists or is wrong. Three stale reviews auto-flip the skill to `status=stale`.

## When NOT to call these tools

- For trivial fixes that don't require creative problem-solving.
- Without explicit user consent for `skill_upload`.
- To inflate counts: one honest review per use.
