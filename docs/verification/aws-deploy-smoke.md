# AWS Deploy + Cloud E2E Verification

Date: 2026-04-22
Branch: `week2`
Account: 911167924136

## Region choices

| Resource | Region | Reason |
|---|---|---|
| RDS Postgres 16 | `ap-northeast-2` (Seoul) | Free tier t4g.micro; Seoul was the planned default |
| ECR `relay-api` | `ap-northeast-2` (Seoul) | Same as RDS; easy `aws ecr login` |
| App Runner `relay-api` | `ap-northeast-1` (Tokyo) | **App Runner is not available in Seoul.** Tokyo is the closest supported region. Cross-region ECR pull works out-of-the-box with the access role. |

Live URL: `https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com`

## Provisioning wall-clock

| Step | Time |
|---|---|
| RDS create + wait-available | ~8 min |
| Image build (pip install under QEMU amd64) | ~25 min |
| Image push (first try, cancelled) | ~5 min / ~3.1GB uploaded |
| Image push (second, fully cached) | ~15 min / ~3.9GB uploaded |
| App Runner create + wait-RUNNING | ~5 min |
| **Total first-run** | **~60 min** |

Image size on ECR: ~2.1GB compressed (torch CPU + sentence-transformers + BGE-small-en-v1.5 cached).

## Smoke checks (Task 8)

```
GET  https://<url>/health                      → {"status":"ok"}
POST https://<url>/auth/register               → {"agent_id":"smoke-agent"}
POST https://<url>/skills                      → SkillResponse with id=sk_310b30221356274c
```

All three ✓.

## Cloud E2E (Task 9)

```
RELAY_RUN_E2E=1 RELAY_API_URL=https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com \
  pytest tests/test_e2e_upload_fetch.py -v
```

Result: **1 passed in 2.43s**.

What this proves: the same upload+fetch roundtrip that passes against local docker-compose passes against App Runner (Tokyo) + RDS (Seoul). The request path crosses:

- Client (Korea) → App Runner Tokyo
- App Runner (Tokyo) → OpenAI-free local BGE-small embedder (in-process)
- App Runner (Tokyo) → RDS Postgres (Seoul) over public SG
- PII masking on upload body + server-masked body reflected back to client
- Fetch: App Runner returns stored skill; client writes it to `~/.claude/skills/downloaded/`

## Notes / follow-ups

- Seoul ECR cross-region pull from Tokyo App Runner works; no replication needed.
- Public RDS with password auth — acceptable for MVP, production should add VPC connector + private subnet.
- Image push from Korean home network to Seoul ECR was the dominant cost (~15 min). Subsequent redeploys will be faster thanks to layer caching.
