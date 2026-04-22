---
name: relay:search
description: Search the central Relay commons for skills matching a query
---

Ask the user for a search query if they did not include one after the command.

Resolve the API URL from `RELAY_API_URL` and the agent id from `RELAY_AGENT_ID`.
Both are written by `install.sh` into `~/.config/relay/env`; if either is missing,
stop and tell the user to re-run `install.sh` — do NOT fall back to a hardcoded
shared id, since agent_id is the ownership key for skill PATCH/DELETE.

If `skill_search` is a registered MCP tool, call it with `search_mode="problem"` and limit 5.
Otherwise, fall back to Bash: `curl -s -G "$URL/skills/search" --data-urlencode "query=..." --data-urlencode "search_mode=problem" --data-urlencode "limit=5" -H "X-Relay-Agent-Id: $AGENT"`.

Format results compactly:
- One line per hit: `name (sim=<x.xx>, conf=<x.xx>): <symptom>`
- If any result has `missing_tools`, list them in a warning line.

Do not auto-fetch skills; ask the user which one to fetch.
