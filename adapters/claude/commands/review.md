---
name: relay:review
description: Submit a good/bad/stale review for a central Relay skill
---

Expected arguments: `<skill_id> <signal>` where signal ∈ {good, bad, stale}.

If either arg is missing, ask the user. For `signal=bad`, also ask for a `reason`
(free text for MVP).

Resolve `api_url` + `agent_id` from env as in /relay:search.

Before calling `skill_review`:
- If the skill was fetched locally, read its metadata and show name + confidence.
- Confirm the signal + reason.

Call `skill_review` and report the returned `review_id`. Remind the user that
three `stale` reviews auto-flip the skill to `status=stale`.
