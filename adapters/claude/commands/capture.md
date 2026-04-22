---
name: relay:capture
description: Capture the current session as a Relay skill (Problem → Attempts → Solution)
---

You are about to call the `skill_capture` MCP tool.

Before calling, collect:

1. **One-sentence problem** that was just solved.
2. **Every failed attempt** with its failure reason. NEVER omit failures.
3. **What finally worked.**
4. **Tools used:** each as `{type: "mcp"|"library"|"cli", name: "..."}`.
5. **Kebab-case name** (propose it; confirm with user).
6. **Triggering description** — this decides whether the skill auto-activates later.

## How to write the `description` (critical)

The description is the primary trigger. Claude Code matches it against future
user prompts to decide whether to load this skill. Write it keyword-rich and
"pushy" — like an advertisement — not as a terse fact.

Bad: `"AWS App Runner not available in Seoul"`

Good: `"AWS App Runner deployment guide for Korean developers — App Runner is
NOT available in ap-northeast-2 (Seoul). Use this skill whenever the user
mentions deploying to AWS App Runner, especially with Seoul/ap-northeast-2
region, or hits 'Could not connect to apprunner.ap-northeast-2' errors.
Contains the Tokyo (ap-northeast-1) + cross-region ECR workaround.
서울 리전 App Runner 배포 계획 시 반드시 참고."`

Checklist for the description:
- Names the **symptom keywords** a future user would naturally type.
- Includes a **"Use this skill whenever…" clause** listing 3+ trigger phrases.
- Mentions **language/platform/region** if that scopes the problem.
- Includes **a Korean trigger sentence** if the user is Korean — description
  matching is stronger with native-language cues.
- Under 500 chars total (Claude Code truncates description+when_to_use at 1536 combined).

Confirm the description with the user before calling `skill_capture`.

## After capture

Show the user:
- The resulting `skill_md_path` and `relay_yaml_path`.
- The `~/.claude/skills/<name>` auto-activation symlink that was created.
- A reminder that the skill is local-only; call `/relay:upload <name>` to share it.
