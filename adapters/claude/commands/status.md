---
name: relay:status
description: Show a summary of locally stored Relay skills with drift flags
---

Call `skill_list_local`. Format the result as a short table with columns:

    name | id | location | uploaded | drift

Under the table, briefly highlight:
- Any skills with `drift_detected: true` (and suggest `/relay:upload` to re-sync).
- The count per location (mine vs downloaded vs staging).

Do not call any other MCP tool in this command.
