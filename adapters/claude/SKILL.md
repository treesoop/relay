---
name: relay
description: Capture, search, upload, fetch, and review problem-solving skills across the Relay commons. Use whenever the user starts a non-trivial task (search first before guessing), after recovering from errors through trial and error (capture the lesson), when deploying anything to AWS/GCP/infra, debugging slow builds, working with Docker/CUDA/ML deps, or after applying a fetched skill (review so others learn from your experience). Make sure to invoke whenever a user mentions a specific error message, a platform name (AWS App Runner, Stripe, etc.), or says "save this / remember this / how did I do this last time".
when_to_use: Start of any non-trivial task — SEARCH FIRST. Solved something messy — CAPTURE. Used a fetched skill — REVIEW.
---

# Relay Agent Behavior

You have five MCP tools for the shared skill commons:

| Tool | When |
|---|---|
| `skill_search` | **ALWAYS try first** when starting a non-trivial task. Search by `problem` mode with a natural-language description. The response contains full skill bodies inline — read them in-context, no filesystem write needed. |
| `skill_fetch` | Only when you commit to USE a skill across future sessions. Fetches it to `~/.claude/skills/downloaded/<name>/` + a flat `~/.claude/skills/<name>` symlink so Claude Code auto-activates it next session. |
| `skill_capture` | After recovering from non-trivial errors OR when the user says save this / remember this. Local-only until uploaded. |
| `skill_upload` | When the user confirms they want a captured skill shared with the commons. Masks PII, rewrites the local body with the masked version. |
| `skill_review` | After USING a fetched skill. One honest signal per use — `good`, `bad`, or `stale`. |

## When to search

Before starting a difficult task, ask: "have I seen this before?" Call `skill_search`
with a natural-language description of the symptom. The response already contains
the top-N skill bodies — read them inline. Only call `skill_fetch` if you want the
skill available automatically in future sessions.

## When to capture

After you solve something through trial and error:
1. Enumerate the attempts and their failure reasons. Never omit a failed attempt.
2. Propose a kebab-case name.
3. Confirm with the user before calling `skill_capture`.
4. Ask whether they want to share it via `skill_upload`.

## How to call `skill_capture`

Collect these from the conversation BEFORE calling:
- **name**: kebab-case, e.g. `stripe-rate-limit-handler`.
- **description**: THIS IS THE PRIMARY TRIGGER. Write it pushy and keyword-rich. See below.
- **when_to_use**: a sentence describing when this applies.
- **problem_symptom / problem_context**: what was observed.
- **solution_approach**: one sentence describing what worked.
- **attempts**: list of `{tried, failed_because}` for each failure, plus one `{worked}` entry at the end.
- **tools_used**: list of `{type: "mcp" | "library" | "cli", name}`.
- **languages / libraries / domain**: free-form lists.
- **body_sections**: a mapping from heading to markdown text. Always include at minimum `Problem`, `What I tried`, `What worked`, `Tools used`, `When NOT to use this`.

### Writing the `description` field

The description is how Claude Code decides whether to auto-activate this skill
later. Write it like an advertisement for the skill — what it does AND every
naive phrasing a future user might type when they hit this problem.

Bad: "AWS App Runner fails in ap-northeast-2."

Good: "AWS App Runner deployment guide — App Runner is NOT available in Seoul
(ap-northeast-2). Use this skill whenever the user mentions deploying to AWS App
Runner, especially with Seoul/ap-northeast-2, or hits 'Could not connect to
apprunner.ap-northeast-2' errors. Contains the Tokyo (ap-northeast-1) + cross-region
ECR workaround. 한국에서 App Runner 배포할 때 반드시 참고."

Patterns that help:
- Name the symptom keywords a frustrated user would type (error messages, service names).
- Include a "Make sure to use this skill whenever…" clause with 3+ trigger phrases.
- If the problem is specific to a language/region/platform, say so explicitly.
- If the problem is bilingual (e.g. Korean devs), include Korean trigger sentences.

Never omit failed attempts in the body. The failure log is the most valuable part of a skill.
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
