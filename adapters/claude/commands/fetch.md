---
name: relay:fetch
description: Fetch a skill from the central Relay commons into local storage
---

Expected argument: `<skill_id>` (a result from `/relay:search`). Optional second arg: `staging` (default `downloaded`).

If no argument, run `/relay:search` first to let the user pick.

Resolve `api_url` + `agent_id` from env (see `/relay:search`).

Before calling `skill_fetch`:
- Confirm mode: `downloaded` (Claude Code auto-activates) vs `staging` (preview only, not auto-loaded).

Call `skill_fetch` and show the user:
- Destination path.
- A reminder to call `/relay:review <id> <good|bad|stale>` after they use it.
