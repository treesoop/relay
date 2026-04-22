---
name: relay:fetch
description: Fetch a skill from the central Relay commons and commit it to local auto-activation
---

Expected argument: `<skill_id>` (a result from `/relay:search`).

If no argument, run `/relay:search` first to let the user pick one.

**When NOT to fetch:** if the user just wants to peek at a skill's content, `/relay:search` already returns the full body inline. Only fetch when they want the skill to auto-activate in future sessions.

Resolve `api_url` + `agent_id` from env (see `/relay:search`).

Call `skill_fetch`. It writes to `~/.claude/skills/downloaded/<name>/` and creates the `~/.claude/skills/<name>` symlink so Claude Code auto-activates the skill on the next session.

After fetch, tell the user:
- Path to the fetched skill.
- Restart Claude Code to trigger auto-activation.
- Remind them to call `/relay:review <skill_id> good|bad|stale` after they use it.
