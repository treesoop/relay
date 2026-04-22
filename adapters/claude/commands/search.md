---
name: relay:search
description: Search the central Relay commons for skills matching a query
---

Argument: a natural-language description of the problem. If the user did not
include one, ask for it. ALWAYS try this before guessing a non-trivial solution.

## Steps

1. Run the shared bootstrap from the `relay` SKILL.md if `~/.config/relay/env` is missing.

2. Call the API:

   ```bash
   source "${XDG_CONFIG_HOME:-$HOME/.config}/relay/env"
   curl -sG "$RELAY_API_URL/skills/search" \
     --data-urlencode "query=<QUERY>" \
     --data-urlencode "search_mode=problem" \
     --data-urlencode "limit=5" \
     -H "X-Relay-Agent-Id: $RELAY_AGENT_ID" | jq
   ```

3. Present results compactly, one line per hit:

   `<name>  sim=<x.xx>  conf=<x.xx>  —  <problem.symptom>`

   If any result has `missing_tools`, warn on a separate line: the caller
   does not have the required MCP tool installed.

4. The response body already contains the full skill body inline — read it
   in-context to answer the user's question. Do NOT call `/relay:fetch`
   unless the user wants the skill to auto-activate in future sessions.

5. Ask the user which hit (if any) to fetch.
