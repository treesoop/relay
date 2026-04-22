---
name: relay:upload
description: Upload a local `mine/<name>` skill to the central Relay API
---

Parse the skill name from the user's arguments. If none, list locally-uploadable
skills via `skill_list_local` (filter to `location=mine` AND `uploaded=false`) and
ask which one to upload.

Resolve `api_url` + `agent_id` from env (see /relay:search) or defaults.

Before calling `skill_upload`:
- Show a short preview: name, description, problem.symptom.
- Warn the user that PII in the body and in `attempts[].failed_because` will be
  masked server-side and that the masked body is written back locally.
- Confirm.

Then call `skill_upload` and report the returned `remote_id`.
