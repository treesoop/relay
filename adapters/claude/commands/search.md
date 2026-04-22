---
name: relay:search
description: Search the central Relay commons for skills matching a query
---

Ask the user for a search query if they did not include one after the command.

Resolve the API URL from:
- Environment variable `RELAY_API_URL`, if set.
- Otherwise the URL printed in the Relay README's "Live URL" section.

Agent id: use `RELAY_AGENT_ID` if set, else `local-dev`.

If `skill_search` is a registered MCP tool, call it with `search_mode="problem"` and limit 5.
Otherwise, fall back to Bash: `curl -s -G "$URL/skills/search" --data-urlencode "query=..." --data-urlencode "search_mode=problem" --data-urlencode "limit=5" -H "X-Relay-Agent-Id: $AGENT"`.

Format results compactly:
- One line per hit: `name (sim=<x.xx>, conf=<x.xx>): <symptom>`
- If any result has `missing_tools`, list them in a warning line.

Do not auto-fetch skills; ask the user which one to fetch.
