# Relay Closed Beta Protocol

5-user dogfood for 2 weeks. Goal: figure out if the semi-automatic skill-sharing loop actually changes how people use Claude Code.

## Invite list (target)

1–5 Korean AI community devs who use Claude Code daily. Diverse domains: payments, ops, backend, frontend. Avoid: people who haven't used Claude Code in the last 7 days.

## What beta users do

1. Install: `curl ... | bash`
2. Use Claude Code normally for 2 weeks.
3. When they solve something messy, run `/relay:capture`.
4. Before starting a non-trivial task, run `/relay:search` first.
5. After using any fetched skill, run `/relay:review <id> <good|bad|stale>`.

## What we measure (daily via `scripts/metrics.py`)

- Skills captured / skills uploaded
- Searches per day / median results per search
- Reviews per day, good-vs-bad-vs-stale ratio
- Skills auto-staled
- Avg confidence of active skills

## What we ask beta users (weekly)

- Did `/relay:search` return anything you actually used?
- Did you capture a skill you might otherwise have re-debugged?
- Anything broken / confusing / slow?

## Exit criteria (after 2 weeks)

GO to v1 if:
- 3+ users captured at least 3 skills each.
- At least 5 total `good` reviews across users.
- Search hit rate (top-1 confidence > 0.5) ≥ 30% when corpus has 20+ skills.

NO-GO if:
- Users stopped capturing after week 1.
- No cross-user fetches occurred (people only captured their own, never searched anyone else's).
- Infrastructure breaks more than twice.
