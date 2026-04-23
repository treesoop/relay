---
name: relay:search
description: Search the central Relay commons for skills matching a query
---

Argument: a natural-language description of the problem. If the user did not
include one, ask for it.

**Reads are anonymous.** Do NOT run the bootstrap flow (no `/auth/register`,
no env file check). Just one curl:

```bash
API="https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com"
QUERY="<user's query>"
curl -sS -G "$API/skills/search" \
  --data-urlencode "query=$QUERY" \
  --data-urlencode "search_mode=problem" \
  --data-urlencode "limit=5" \
  -H "X-Relay-Agent-Id: anonymous" \
  | jq
```

If the user has `~/.config/relay/env` already (from a previous upload),
you may source it so `X-Relay-Agent-Id` reflects their real id — but this
is optional and matters only for telemetry, not access.

## Present results

One line per hit:

`<name>  sim=<x.xx>  conf=<x.xx>  —  <problem.symptom>`

Warn if any result has `missing_tools` — caller doesn't have the required
MCP tool installed.

The response body contains each skill's full body inline. Read it in-context
to answer the user. Do NOT call `/relay:fetch` unless the user wants the
skill to auto-activate in future sessions.

Ask the user which hit (if any) to fetch.
