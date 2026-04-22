#!/usr/bin/env python3
"""Seed the Relay commons with hand-curated public skills.

Every skill has a real Problem -> Attempts -> Solution path. Run once;
re-runs PATCH in place (the curator agent owns them).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = os.environ.get(
    "RELAY_API_URL", "https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com"
)
CURATOR = "relay-curator-v1"
CRED_PATH = Path.home() / ".config" / "relay" / "credentials.json"

# ---------------------------------------------------------------------------

def http(method: str, path: str, body=None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API_URL}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def ensure_secret() -> str:
    CRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    creds = json.loads(CRED_PATH.read_text()) if CRED_PATH.exists() else {"agents": {}}
    if CURATOR in creds.get("agents", {}):
        return creds["agents"][CURATOR]["secret"]
    resp = http("POST", "/auth/register", {"agent_id": CURATOR})
    sec = resp.get("secret")
    if not sec:
        raise SystemExit(f"register failed: {resp}")
    creds.setdefault("agents", {})[CURATOR] = {"secret": sec}
    CRED_PATH.write_text(json.dumps(creds, indent=2))
    os.chmod(CRED_PATH, 0o600)
    return sec


def existing_by_name(secret: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for q in ["problem", "error", "connection", "build", "deploy", "install", "config"]:
        try:
            r = http(
                "GET",
                f"/skills/search?query={q}&limit=50&search_mode=problem",
                headers={"X-Relay-Agent-Id": CURATOR},
            )
            for it in r["items"]:
                s = it["skill"]
                if s["source_agent_id"] == CURATOR and s["name"] not in out:
                    out[s["name"]] = s["id"]
        except urllib.error.HTTPError:
            pass
    return out


def build_body(problem: str, attempts: list[dict], worked: str, tools: list[str], nope: str) -> str:
    lines = ["## Problem", "", problem, "", "## What I tried", ""]
    for i, a in enumerate(attempts, 1):
        lines.append(f"{i}. **{a['tried']}** — {a['failed_because']}")
    lines += ["", "## What worked", "", worked, "", "## Tools used", ""]
    for t in tools:
        lines.append(f"- {t}")
    lines += ["", "## When NOT to use this", "", nope, ""]
    return "\n".join(lines)


def make_meta(symptom, approach, attempts, langs=None, libs=None, domain=None, tools_used=None):
    return {
        "problem": {"symptom": symptom, "context": None},
        "solution": {"approach": approach, "tools_used": tools_used or []},
        "attempts": [*attempts, {"worked": approach}],
        "context": {"languages": langs or [], "libraries": libs or [], "domain": domain},
        "trigger": "curated",
        "status": "active",
    }


# ---------------------------------------------------------------------------
# 30 hand-curated skills. Each `attempts` list has REAL failure reasons,
# not placeholders. Description follows the pushy pattern used by the
# existing commons entries.
# ---------------------------------------------------------------------------

SKILLS: list[dict] = [
    # ---------- macOS / shell / filesystem ----------
    {
        "name": "macos-gatekeeper-unsigned-cli-binary",
        "description": (
            "macOS Gatekeeper blocks unsigned CLI binaries downloaded from GitHub releases — "
            "error: 'cannot be opened because the developer cannot be verified'. "
            "Use this skill whenever a curl-installed or tarball-extracted binary refuses "
            "to run on macOS, or you see killed: 9 or com.apple.quarantine attributes. "
            "Contains the single xattr command that permanently unsticks it."
        ),
        "when_to_use": "After installing a CLI binary on macOS from a non-signed source and it refuses to run.",
        "symptom": "Running ./my-cli on macOS produces 'cannot be opened because the developer cannot be verified' or the process gets killed: 9 right after exec.",
        "approach": "Remove the quarantine extended attribute: `xattr -d com.apple.quarantine ./my-cli`. This is permanent for that file (unlike right-click-Open, which re-prompts if the file moves).",
        "attempts": [
            {"tried": "Right-click the binary in Finder and choose Open", "failed_because": "works once but re-prompts whenever the file is moved or replaced by a re-install"},
            {"tried": "chmod +x ./my-cli", "failed_because": "not a permissions problem — the execute bit is already set; Gatekeeper blocks on the quarantine xattr"},
            {"tried": "System Settings → Privacy & Security → Allow anyway", "failed_because": "works for GUI apps but the CLI never shows up in that list"},
        ],
        "tools": ["`xattr` (macOS)"],
        "nope": "You're installing something from a source you don't trust. Gatekeeper exists for a reason; only strip quarantine after verifying the SHA of the binary.",
        "langs": [], "libs": [], "domain": "macos",
    },
    # ---------- git ----------
    {
        "name": "git-reflog-recover-detached-head-commits",
        "description": (
            "Lost commits after accidentally working on a detached HEAD? "
            "Use this skill whenever a user says 'my commits disappeared after git checkout main', "
            "'I committed without a branch', or 'git log shows nothing but I definitely committed'. "
            "Contains the git reflog → git branch recover-X <sha> recipe that resurrects them."
        ),
        "when_to_use": "When commits made while in a detached-HEAD state are no longer visible in `git log` after checking out a branch.",
        "symptom": "You committed work while in a detached HEAD (e.g. right after `git checkout <sha>`). Then you ran `git checkout main` and your commits are gone from `git log` — they still exist in the object database but no ref points to them.",
        "approach": "Find the lost commit's SHA with `git reflog`, then create a branch anchored at it: `git branch recover-work <sha>`. The reflog keeps unreachable HEADs for 90 days by default, so recovery is possible long after the fact.",
        "attempts": [
            {"tried": "`git reset --hard HEAD@{1}`", "failed_because": "HEAD@{1} points to the branch tip we just came from, not to the detached-head commit; reset moves us back but still doesn't create a ref to the lost work"},
            {"tried": "`git log --all`", "failed_because": "--all only walks refs; the dangling commits have no ref pointing at them so they don't show up"},
            {"tried": "Searching source files with `find . -newer`", "failed_because": "the working tree already reflects the current branch — content is gone from the checkout even though it's still in `.git/objects`"},
        ],
        "tools": ["`git reflog`", "`git branch`", "`git fsck --lost-found`"],
        "nope": "The commits were pruned (default 90 days after the reflog entry expires) or `git gc --prune=now` was run. After that, recovery requires a backup.",
        "langs": [], "libs": [], "domain": "version-control",
    },
    {
        "name": "git-submodule-detached-head-after-clone",
        "description": (
            "Git submodules land in detached HEAD after clone, so commits inside them go nowhere. "
            "Use this skill whenever commits inside a submodule vanish, or 'git submodule update' keeps "
            "reverting your changes. Contains the `git submodule foreach 'git checkout main'` + "
            "branch.<name>.update=merge fix that makes submodules track a branch."
        ),
        "when_to_use": "When a fresh clone or `git submodule update` leaves submodules at a detached HEAD and any work done inside them gets lost.",
        "symptom": "After `git clone --recursive`, every submodule is in detached HEAD. You commit inside one, push, then a teammate pulls and the submodule resets to an older SHA — your commit is gone.",
        "approach": "Run `git submodule foreach 'git checkout <branch>'` and set `branch = <name>` + `update = merge` in `.gitmodules` so `git submodule update --remote` advances the pointer on each sync.",
        "attempts": [
            {"tried": "`git submodule update --init`", "failed_because": "still checks out the pinned SHA in detached mode; the submodule is a pointer to a commit, not a branch"},
            {"tried": "Commit inside the submodule without a branch", "failed_because": "commit exists but no ref points at it; next `git submodule update` in any clone resets to the old SHA"},
        ],
        "tools": ["`git submodule`", "`.gitmodules`"],
        "nope": "You actually want the submodule pinned to a specific SHA (e.g. a security-audited version). Detached HEAD is correct then.",
        "langs": [], "libs": [], "domain": "version-control",
    },
    # ---------- GitHub Actions / CI ----------
    {
        "name": "github-actions-secrets-empty-in-fork-pr",
        "description": (
            "GitHub Actions secrets are intentionally NOT passed to workflows triggered by pull_request from forks. "
            "Use this skill whenever `${{ secrets.FOO }}` is empty in a PR from a fork, the workflow silently uses "
            "empty strings, or a 'deploy preview' runs only on internal branches. Covers the pull_request_target "
            "trick and why it's dangerous without guards."
        ),
        "when_to_use": "A GitHub Actions workflow works on the main repo but silently fails on PRs from forks because secrets come through as empty strings.",
        "symptom": "Your action prints `token=''` or fails with 401 when triggered by a PR from a fork, even though secrets.TOKEN is set at the repo level.",
        "approach": "Use the `pull_request_target` trigger instead of `pull_request`. This runs the workflow in the context of the base repo (which has access to secrets), but you MUST NOT check out the PR head unless you carefully control what runs — doing so executes untrusted code with secret access.",
        "attempts": [
            {"tried": "Adding the secret at the org level", "failed_because": "org-level secrets behave the same way — fork PRs get empty secrets by design, to prevent credential theft"},
            {"tried": "Echoing `${{ secrets.TOKEN }}` to debug", "failed_because": "GitHub masks secret values in logs; you see `***` when the secret is set and nothing when empty, which makes 'empty' look like 'masked'"},
        ],
        "tools": ["GitHub Actions", "`pull_request_target`"],
        "nope": "You're running a deploy step from a fork PR — never do this without a label gate or a `workflow_call` boundary, since the attacker controls the PR code.",
        "langs": [], "libs": [], "domain": "ci",
    },
    # ---------- nginx / reverse proxy ----------
    {
        "name": "nginx-client-max-body-size-413",
        "description": (
            "nginx returns HTTP 413 'Request Entity Too Large' for any upload over 1MB because the "
            "default client_max_body_size is 1m. Use this skill whenever a file upload fails at the "
            "reverse proxy, the browser shows 'upload failed' but the app logs are silent, or 413 "
            "appears only in production (not local dev). Contains the http/server/location-level directive."
        ),
        "when_to_use": "File uploads fail with 413 at the proxy layer; the application server never sees the request.",
        "symptom": "POST of a 5MB file via nginx-fronted app returns 413 Request Entity Too Large. Browser shows generic 'upload failed'. Your app logs show nothing because the request never reached it.",
        "approach": "Set `client_max_body_size 100m;` (or whatever your app accepts) in `http`, `server`, or `location` scope. Scope matters — the most specific wins. Also raise `client_body_buffer_size` if the upload is buffered to disk.",
        "attempts": [
            {"tried": "Increasing the app's own upload limit (Flask MAX_CONTENT_LENGTH, Rails MaxFileSize)", "failed_because": "nginx rejects before the request reaches the app; the app limit is now dead code"},
            {"tried": "Setting `client_max_body_size` only in `http { }` block", "failed_because": "worked until someone added an overriding `server { client_max_body_size 1m; }` — more specific scope won"},
        ],
        "tools": ["nginx"],
        "nope": "You're proxying a service that's supposed to reject large uploads — raising the limit defeats the point.",
        "langs": [], "libs": [], "domain": "infrastructure",
    },
    # ---------- systemd ----------
    {
        "name": "systemd-service-python-venv-absolute-path",
        "description": (
            "systemd services can't find a Python venv because unit files don't source shell profiles. "
            "Use this skill whenever a systemd-managed Python service fails with ModuleNotFoundError, "
            "works from the terminal but not from systemctl, or dies silently on boot. Contains the "
            "ExecStart absolute-path + EnvironmentFile pattern."
        ),
        "when_to_use": "A Python service works when you run it manually from the venv, but fails under `systemctl start`.",
        "symptom": "`systemctl status my-service` shows it exits with ModuleNotFoundError for packages you KNOW are installed in the venv. Running the same command manually from your shell works.",
        "approach": "In the .service unit, use the absolute path to the venv's Python interpreter: `ExecStart=/opt/myapp/.venv/bin/python -m myapp`. Do not rely on `PATH` or `source activate` — systemd does not run a login shell.",
        "attempts": [
            {"tried": "`ExecStart=python -m myapp`", "failed_because": "systemd PATH is minimal (/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin); the venv isn't there so the system python runs instead, missing deps"},
            {"tried": "`ExecStart=bash -c 'source .venv/bin/activate && python -m myapp'`", "failed_because": "works but a shell wrapper means systemd only sees the bash PID, breaking MAINPID tracking, graceful shutdown, and restart-on-crash"},
        ],
        "tools": ["systemd", "`systemctl`", "`journalctl`"],
        "nope": "You're running a short-lived Python script that doesn't need a service manager. Use a cron entry or a wrapper script instead.",
        "langs": ["python"], "libs": [], "domain": "infrastructure",
    },
    # ---------- docker ----------
    {
        "name": "docker-compose-depends-on-condition-service-healthy",
        "description": (
            "docker-compose `depends_on: [postgres]` does NOT wait for Postgres to accept connections — "
            "only that the container started. Use this skill whenever an app container crashes on boot "
            "with 'connection refused' or 'server is starting up', or only on fresh `docker compose up`. "
            "Contains the condition:service_healthy + healthcheck pattern that actually waits."
        ),
        "when_to_use": "Your app container crashes on the first `docker compose up` because Postgres/Redis/etc. wasn't ready yet, even though depends_on is set.",
        "symptom": "`docker compose up` launches postgres and api together. The api crashes with 'connection refused' because Postgres takes 2-3 seconds to accept TCP. Running `docker compose up -d postgres; sleep 5; docker compose up api` works.",
        "approach": "Give the dependency a healthcheck, then depend with `condition: service_healthy`:\n\n```yaml\npostgres:\n  healthcheck:\n    test: [\"CMD-SHELL\", \"pg_isready -U me\"]\n    interval: 2s\n    retries: 20\napi:\n  depends_on:\n    postgres:\n      condition: service_healthy\n```",
        "attempts": [
            {"tried": "Plain `depends_on: [postgres]`", "failed_because": "compose only waits for the container process to exist, not for it to accept connections. Postgres takes 2-5s to initialize after its PID exists."},
            {"tried": "Adding `sleep 5` in the api entrypoint", "failed_because": "guesswork — slow CI hosts need more, fast ones waste time. And first-run Postgres (initdb) takes much longer than subsequent boots."},
        ],
        "tools": ["docker compose", "healthcheck"],
        "nope": "Your app already has built-in retry-with-backoff at DB connect time — then depends_on isn't necessary at all.",
        "langs": [], "libs": [], "domain": "infrastructure",
    },
    # ---------- AWS ----------
    {
        "name": "aws-s3-cloudfront-oac-bucket-policy-403",
        "description": (
            "CloudFront with the new Origin Access Control (OAC) returns 403 from an S3 origin because "
            "the bucket policy still uses the legacy OAI principal shape. Use this skill whenever a "
            "CloudFront distribution suddenly starts returning 403 after migrating from OAI to OAC, "
            "or when a new OAC-only distribution can't read from a bucket. Contains the correct "
            "service-principal policy."
        ),
        "when_to_use": "A CloudFront distribution fronted by S3 returns 403 AccessDenied for all objects after switching to OAC.",
        "symptom": "CloudFront shows 403 for every object; S3 access logs show 'cloudfront.amazonaws.com' as the caller but the bucket policy denies it.",
        "approach": "Replace the legacy OAI principal (`CanonicalUser: {OAI id}`) with the OAC principal: `Service: cloudfront.amazonaws.com` plus a `Condition: StringEquals: AWS:SourceArn: arn:aws:cloudfront::<account>:distribution/<id>`.",
        "attempts": [
            {"tried": "Setting OAC in the CloudFront origin without changing the bucket policy", "failed_because": "the bucket still only grants to the legacy OAI canonical user; OAC requests come in as a service principal the policy doesn't know about"},
            {"tried": "Making the bucket public", "failed_because": "defeats the whole point of OAC; also blocked by S3 Block Public Access in most accounts"},
        ],
        "tools": ["AWS CloudFront", "AWS S3", "IAM policy"],
        "nope": "You're still on OAI (Origin Access Identity) — that's deprecated but still supported, so the principal format is different.",
        "langs": [], "libs": [], "domain": "aws",
    },
    # ---------- TLS / HTTPS ----------
    {
        "name": "letsencrypt-rate-limit-5-duplicate-certs-per-week",
        "description": (
            "Let's Encrypt hits the 'Duplicate Certificate' rate limit (5 per week per registered domain) "
            "during testing or bad automation. Use this skill whenever certbot says 'too many certificates "
            "already issued for exact set of domains' and you're stuck waiting a week. Contains the "
            "staging environment + --dry-run workflow that makes iteration free."
        ),
        "when_to_use": "`certbot` refuses to issue a cert with 'too many certificates already issued for the exact set of domains: example.com'.",
        "symptom": "Certbot/acme.sh fails with `Error creating new order :: too many certificates already issued for exact set of domains`. The counter resets only after a rolling 7 days — you're locked out in the middle of testing.",
        "approach": "Point certbot at the Let's Encrypt STAGING endpoint during testing: `--server https://acme-staging-v02.api.letsencrypt.org/directory`. Staging has dramatically higher limits and issues browser-untrusted certs, which is fine for validation. Use `--dry-run` for zero-limit validation.",
        "attempts": [
            {"tried": "Just retry", "failed_because": "limit is per exact SAN set over 7 days; re-submitting the same set counts again"},
            {"tried": "Add a throwaway subdomain to change the SAN set", "failed_because": "there's a separate 'Certificates per Registered Domain' limit (50/week); in heavy iteration this gets hit too"},
        ],
        "tools": ["certbot / acme.sh", "Let's Encrypt staging endpoint"],
        "nope": "You're in production with a real cert — just wait the 7 days; don't change your workflow around the limit.",
        "langs": [], "libs": [], "domain": "tls",
    },
    {
        "name": "curl-ssl-certificate-verify-failed-cacert",
        "description": (
            "curl fails with 'SSL certificate problem: unable to get local issuer certificate' inside "
            "a stripped-down Docker image because the CA bundle isn't installed. Use this skill whenever "
            "TLS requests succeed on the host but fail in a container, or curl works but Python's requests "
            "doesn't. Contains the `ca-certificates` apk/apt install + SSL_CERT_FILE pattern."
        ),
        "when_to_use": "curl/wget/python-requests fails TLS verification inside a minimal Docker image or a freshly-built Alpine container.",
        "symptom": "`curl https://example.com` inside a container returns 'SSL certificate problem: unable to get local issuer certificate'. The same host/URL works from the Docker host.",
        "approach": "Install a CA bundle. Alpine: `apk add --no-cache ca-certificates && update-ca-certificates`. Debian: `apt-get install -y ca-certificates`. If the bundle is in a nonstandard path, point clients at it with `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`.",
        "attempts": [
            {"tried": "`curl -k`", "failed_because": "hides the problem — now MITM is possible; also doesn't fix other clients (Python requests, Node https, openssl) inside the same container"},
            {"tried": "Copying /etc/ssl/certs from the host into the image", "failed_because": "path layouts differ across distros; Alpine uses a different cert format than Debian; copies bit-rot"},
        ],
        "tools": ["`ca-certificates` package", "`update-ca-certificates`"],
        "nope": "You're talking to an internal CA — then you need to install the internal CA's root cert, not the public bundle.",
        "langs": [], "libs": [], "domain": "tls",
    },
    # ---------- Postgres ----------
    {
        "name": "postgres-jsonb-gin-vs-btree-index-missed",
        "description": (
            "Postgres queries on JSONB fields are slow because a BTREE index can't be used for JSONB "
            "containment; you need GIN. Use this skill when EXPLAIN shows a Seq Scan on a JSONB column, "
            "queries with @> or ->> are slow, or indexes show up in \\d but never get used. Contains "
            "the `USING GIN ((metadata -> 'key'))` expression-index pattern."
        ),
        "when_to_use": "EXPLAIN ANALYZE shows Seq Scan on a large table with JSONB WHERE clauses, even though you added an index.",
        "symptom": "`SELECT * FROM skills WHERE metadata @> '{\"tag\": \"python\"}'` takes seconds on a few million rows even though you created an index on `metadata`.",
        "approach": "For JSONB containment, use GIN: `CREATE INDEX idx_meta ON skills USING GIN (metadata);`. For key lookups via `->>`, create an expression index on the exact expression used: `CREATE INDEX idx_meta_tag ON skills ((metadata ->> 'tag'));`. Postgres only uses expression indexes if the expression in the query matches exactly.",
        "attempts": [
            {"tried": "`CREATE INDEX idx_meta ON skills (metadata);`", "failed_because": "BTREE works on the whole JSONB value; it can only support `=` on the entire blob, not containment or key lookup"},
            {"tried": "`CREATE INDEX idx_tag ON skills ((metadata -> 'tag'));` for a query using `metadata ->> 'tag'`", "failed_because": "`->` returns JSONB, `->>` returns text — different expressions, so the index doesn't match; always create the index against the operator you actually query with"},
        ],
        "tools": ["Postgres GIN indexes", "expression indexes", "EXPLAIN ANALYZE"],
        "nope": "Table is tiny (thousands of rows). Seq Scan is actually faster than index lookup for small tables.",
        "langs": [], "libs": [], "domain": "database",
    },
    # ---------- Redis ----------
    {
        "name": "redis-asyncio-connection-pool-exhaustion-cancel",
        "description": (
            "redis.asyncio leaks pool connections when tasks are cancelled mid-operation — under bursty "
            "asyncio load you'll eventually hit 'Too many connections' or hang. Use this skill whenever "
            "Redis connection count climbs without bound, you see 'maxclients reached', or the issue "
            "only appears under concurrent cancellation. Contains the module-scoped pool + async with pattern."
        ),
        "when_to_use": "A Python asyncio service starts failing Redis ops after some burst traffic, and `CLIENT LIST` shows the connection count keeps growing.",
        "symptom": "Under concurrent load with request cancellation (e.g. slow client disconnects), Redis connection count grows until `CLIENT LIST` hits maxclients and new requests hang.",
        "approach": "Use a module-scoped `ConnectionPool`, and acquire connections via `async with pool.connection() as c:` so the context manager runs on cancellation too. Do NOT create a new client per request.",
        "attempts": [
            {"tried": "Raising pool `max_connections`", "failed_because": "delays but doesn't fix the leak — connections are still acquired and never returned when a task is cancelled between acquire and release"},
            {"tried": "Short per-call timeouts", "failed_because": "the timeout fires but the underlying connection is still checked out; release requires the context manager exit or explicit disconnect"},
        ],
        "tools": ["redis.asyncio", "`ConnectionPool`"],
        "nope": "You're using the sync `redis` client — the pool model there is different and this fix doesn't apply.",
        "langs": ["python"], "libs": ["redis.asyncio"], "domain": "database",
    },
    # ---------- MongoDB ----------
    {
        "name": "mongodb-srv-connection-string-dns-txt-required",
        "description": (
            "mongodb+srv:// connection strings require BOTH a SRV record and a TXT record; missing the "
            "TXT record causes 'No TXT record found' or silent default-DB selection. Use this skill "
            "whenever connect works with mongodb:// but not mongodb+srv://, or the client connects but "
            "writes go to the wrong database. Contains the DNS record shape."
        ),
        "when_to_use": "A MongoDB Atlas or self-hosted cluster connection works with mongodb:// but fails or misbehaves with mongodb+srv://.",
        "symptom": "`mongodb+srv://user:pass@cluster.example.com/mydb` fails with 'No TXT record found' or connects but writes end up in the `test` database.",
        "approach": "Publish BOTH records. SRV: `_mongodb._tcp.cluster.example.com SRV 0 0 27017 node1.example.com` (one per node). TXT: `cluster.example.com TXT \"replicaSet=rs0&authSource=admin\"`. The driver reads the SRV record for hosts and the TXT record for connection options.",
        "attempts": [
            {"tried": "Just a SRV record, no TXT", "failed_because": "SRV-only gives the driver hosts but no options — it defaults to an empty replicaSet + authSource=admin, which may or may not match your cluster"},
            {"tried": "Putting options in the URL query string", "failed_because": "works, but then you've lost the whole point of srv (centralized config); DNS takes over again the next time someone types the URL without options"},
        ],
        "tools": ["DNS SRV + TXT records", "MongoDB drivers"],
        "nope": "You're using plain `mongodb://` already — no DNS seedlist needed, just list all hosts in the URL.",
        "langs": [], "libs": [], "domain": "database",
    },
    # ---------- SQLAlchemy ----------
    {
        "name": "sqlalchemy-detached-instance-after-commit-expire",
        "description": (
            "SQLAlchemy raises DetachedInstanceError when accessing an attribute on an ORM object AFTER "
            "commit(), because expire_on_commit=True invalidates all attributes. Use this skill whenever "
            "code reads obj.attr after db.commit() and gets 'Instance X is not bound to a Session', "
            "or attributes are mysteriously empty post-commit. Contains expire_on_commit=False + refresh()."
        ),
        "when_to_use": "FastAPI/Flask endpoint that commits and then tries to return the ORM object raises DetachedInstanceError at JSON serialization time.",
        "symptom": "```\nuser = User(name='x'); session.add(user); await session.commit()\nreturn user  # raises: Parent instance is not bound to a Session\n```",
        "approach": "Two options. (1) Construct your session with `expire_on_commit=False` so attributes stay populated after commit. (2) Keep default expire behavior but call `await session.refresh(user)` before returning, which re-loads the fresh values.",
        "attempts": [
            {"tried": "Returning the object directly after commit", "failed_because": "commit() by default marks all attributes expired; next attribute access tries to re-load them but the scope has closed — DetachedInstance"},
            {"tried": "Calling `session.expunge(user)` before commit", "failed_because": "removes the instance from the session but also skips the flush; the changes never get written"},
        ],
        "tools": ["SQLAlchemy", "async_sessionmaker"],
        "nope": "You don't need the object after commit. Return a dict or Pydantic model instead of the ORM instance; don't fight expire_on_commit.",
        "langs": ["python"], "libs": ["sqlalchemy"], "domain": "database",
    },
    # ---------- Next.js / React ----------
    {
        "name": "nextjs-hydration-mismatch-date-time-server-client",
        "description": (
            "Next.js hydration error because the server renders `new Date()` at one moment and the "
            "client renders it at another. Use this skill whenever you see 'Text content did not match "
            "server-rendered HTML', component output includes a timestamp or random value, or the "
            "error only shows up on the first page load. Contains the pass-ISO-string-as-prop pattern."
        ),
        "when_to_use": "Next.js logs 'Hydration failed because the server rendered HTML didn't match the client' and the diff contains a timestamp, relative time, or random number.",
        "symptom": "Page renders fine but React throws `Hydration failed because the server rendered HTML didn't match the client. This can happen if an SSR-ed Client Component used: A date or time... etc.`",
        "approach": "Format the date on the SERVER as an ISO string and pass it as a prop; the client renders the formatted version during hydration but only invokes locale-dependent APIs in useEffect. For pure UI formatting, use `new Intl.DateTimeFormat('en-US', { timeZone: 'UTC' })` to force the same output on both sides.",
        "attempts": [
            {"tried": "Wrapping `new Date()` in `useEffect`", "failed_because": "works but causes a content flash — the server renders one value, client hydrates with another immediately after"},
            {"tried": "Making the whole page a Client Component", "failed_because": "kills SSR benefits; also doesn't actually fix it — Date.now() still differs between server and client runs"},
        ],
        "tools": ["Next.js App Router", "React 19 Suspense"],
        "nope": "The mismatch is due to a random library producing browser-only output (analytics, locale detection) — then you actually do want client-only rendering.",
        "langs": ["typescript"], "libs": ["next", "react"], "domain": "frontend",
    },
    {
        "name": "tailwind-dynamic-classname-stripped-by-jit",
        "description": (
            "Tailwind strips dynamic class names like `bg-${color}-500` because its JIT scans source files "
            "for literal class strings. Use this skill whenever a Tailwind class doesn't render, works "
            "in dev but not prod, or only certain variants are missing. Contains the static-lookup-map "
            "pattern + v4 safelist gotcha (v4 removed JS-config safelist)."
        ),
        "when_to_use": "A Tailwind class defined via string interpolation — e.g. `bg-${color}-500` — has no effect, while the same literal class works elsewhere.",
        "symptom": "`<div className={`bg-${color}-500`}>` produces `bg-red-500` in the DOM but the element has no background color. `<div className=\"bg-red-500\">` works fine in a different component.",
        "approach": "Use a complete static lookup map: `const TINT = { red: 'bg-red-500', blue: 'bg-blue-500' }` and `className={TINT[color]}`. Tailwind's scanner sees each full class literal and includes it in the output CSS.",
        "attempts": [
            {"tried": "Using `bg-${color}-500` directly", "failed_because": "Tailwind's scanner only finds full literal class names in source files; `bg-${color}-500` is not a real class literal, so it's never included in the generated CSS"},
            {"tried": "Adding a safelist entry in tailwind.config.js (v4)", "failed_because": "Tailwind v4 moved away from JS config; you need to @source inline or use arbitrary values instead"},
        ],
        "tools": ["Tailwind CSS JIT scanner"],
        "nope": "You have a finite palette that already covers all variants — the lookup map is overhead. Inline the full class at each call site.",
        "langs": ["typescript"], "libs": ["tailwindcss"], "domain": "frontend",
    },
    {
        "name": "react-useeffect-stale-closure-missing-dependency",
        "description": (
            "useEffect captures a stale value because a variable it depends on isn't in the dependency "
            "array. Use this skill whenever a callback inside useEffect uses an outdated state value, "
            "an interval prints the first render's state forever, or only fires once when it should "
            "re-fire. Contains the exhaustive-deps rule + useCallback/useRef escape hatches."
        ),
        "when_to_use": "A function or interval inside useEffect keeps using the first-render value of a state variable even after state has changed.",
        "symptom": "```\nconst [count, setCount] = useState(0);\nuseEffect(() => {\n  const id = setInterval(() => console.log(count), 1000);\n  return () => clearInterval(id);\n}, []);  // count is always 0\n```",
        "approach": "Add `count` to the dependency array so the effect re-subscribes when count changes. If you want to access the LATEST value without re-subscribing, store it in a ref and read `ref.current` inside the callback.",
        "attempts": [
            {"tried": "Leaving deps `[]` to 'run once'", "failed_because": "the callback closes over the value of `count` at mount time; state updates re-render the component but the interval still sees the first closure"},
            {"tried": "Using `setCount(count + 1)` inside the interval", "failed_because": "same bug in disguise — count is from the stale closure. Use the functional update form: `setCount(c => c + 1)`"},
        ],
        "tools": ["React hooks", "eslint-plugin-react-hooks"],
        "nope": "The effect genuinely should only run at mount (e.g. analytics pageview). Then deps=[] is correct — but you shouldn't close over changing state inside it.",
        "langs": ["typescript"], "libs": ["react"], "domain": "frontend",
    },
    {
        "name": "vite-env-var-not-exposed-without-vite-prefix",
        "description": (
            "Vite doesn't expose env vars to the browser bundle unless they're prefixed with VITE_ (or "
            "configured via envPrefix). Use this skill whenever `import.meta.env.FOO` is undefined in "
            "the browser even though .env has FOO=bar, or a secret 'accidentally' ended up in the client "
            "bundle. Contains the VITE_ prefix rule + server-only secret pattern."
        ),
        "when_to_use": "`import.meta.env.MY_VAR` is undefined in the browser bundle, but the var is clearly set in .env.",
        "symptom": "Vite app reads `import.meta.env.API_URL` and gets undefined. The `.env` file has `API_URL=https://api.example.com`. Restarting dev server doesn't help.",
        "approach": "Rename the var to `VITE_API_URL` and access it as `import.meta.env.VITE_API_URL`. The `VITE_` prefix is the security boundary — anything prefixed gets bundled into the browser, anything else stays server-only (Node scripts read via `process.env`).",
        "attempts": [
            {"tried": "Restart the dev server", "failed_because": "the prefix requirement is at bundle time, not a hot-reload issue"},
            {"tried": "Add `envPrefix: ['VITE_', 'MY_']` in vite.config", "failed_because": "works but now anything starting with MY_ ends up in the browser bundle — surprising and easy to leak secrets"},
        ],
        "tools": ["Vite"],
        "nope": "The variable is a secret (DB password, API key). It should NEVER be in the browser bundle; keep it server-side and proxy requests.",
        "langs": ["typescript"], "libs": ["vite"], "domain": "frontend",
    },
    {
        "name": "cors-preflight-fails-custom-header-allow-headers",
        "description": (
            "CORS preflight OPTIONS request fails when your frontend sends a custom header the server "
            "hasn't allow-listed. Use this skill whenever a cross-origin request returns 'Request header "
            "X is not allowed by Access-Control-Allow-Headers in preflight response', or the browser "
            "never even fires the POST. Contains the Access-Control-Allow-Headers config."
        ),
        "when_to_use": "A cross-origin POST with a custom header never fires because the OPTIONS preflight fails.",
        "symptom": "Browser DevTools shows the real request never happened. The OPTIONS preflight returned 200 but the browser reports 'Request header X-Custom is not allowed by Access-Control-Allow-Headers in preflight response'.",
        "approach": "Include the exact custom header name (case-insensitive) in the server's `Access-Control-Allow-Headers` response, e.g. `Access-Control-Allow-Headers: Content-Type, X-Custom, Authorization`. Also ensure the OPTIONS handler returns 200 (not 404) — many frameworks need an explicit OPTIONS route.",
        "attempts": [
            {"tried": "Wildcard `Access-Control-Allow-Headers: *`", "failed_because": "browsers treat `*` as literal — only valid when Access-Control-Allow-Credentials is false and never matches 'Authorization' in any case"},
            {"tried": "Setting the header in a meta tag", "failed_because": "CORS is enforced by the server responding to OPTIONS; the client (meta tag, fetch options) cannot bypass it"},
        ],
        "tools": ["CORS", "OPTIONS preflight"],
        "nope": "Same-origin request — no preflight happens, CORS isn't involved at all.",
        "langs": [], "libs": [], "domain": "frontend",
    },
    {
        "name": "vercel-edge-runtime-node-api-not-available",
        "description": (
            "Vercel Edge Functions can't use Node.js APIs (fs, child_process, net); imports fail at "
            "build time. Use this skill whenever a Vercel deploy fails with 'The edge runtime does not "
            "support Node.js X API', a library works locally but not deployed, or you accidentally "
            "opted into edge. Contains the runtime='nodejs' override."
        ),
        "when_to_use": "A Vercel route handler or middleware fails at build/deploy with 'The edge runtime does not support Node.js fs/net/crypto API'.",
        "symptom": "Build fails with `The edge runtime does not support Node.js 'fs' module`. The code runs fine locally but not on Vercel.",
        "approach": "If you need Node APIs, opt out of edge with `export const runtime = 'nodejs'` in the route file. Edge is appropriate only for lightweight middleware-like handlers with no filesystem, no native modules, and no heavy deps.",
        "attempts": [
            {"tried": "Finding a browser polyfill for `fs`", "failed_because": "edge runtime is a subset of browser + streaming primitives; polyfills can't fake a filesystem that doesn't exist"},
            {"tried": "Setting `export const runtime = 'edge'` thinking it's faster", "failed_because": "Vercel's Fluid Compute (the default Node runtime) already has near-edge cold start and full Node; `edge` buys latency only at the cost of a dramatically reduced API surface"},
        ],
        "tools": ["Vercel Functions", "Next.js runtime config"],
        "nope": "You genuinely need a ~5ms cold start and your handler only does header rewriting. Edge is the right choice there.",
        "langs": ["typescript"], "libs": ["next", "vercel"], "domain": "deploy",
    },
    # ---------- Python runtime ----------
    {
        "name": "python-asyncio-event-loop-already-running-jupyter",
        "description": (
            "'RuntimeError: This event loop is already running' when calling asyncio.run() from inside "
            "Jupyter or an already-async context. Use this skill whenever you need to await from a notebook, "
            "bridge sync and async code, or `asyncio.run` fails from a framework that runs its own loop. "
            "Contains nest_asyncio + direct-await pattern."
        ),
        "when_to_use": "`asyncio.run(coro())` raises 'This event loop is already running' inside Jupyter, IPython, or a framework like FastAPI's own async context.",
        "symptom": "`RuntimeError: asyncio.run() cannot be called from a running event loop` — you're in Jupyter, or inside an async handler trying to call another async function via `asyncio.run`.",
        "approach": "If you're already inside an async context, just `await coro()` directly — don't use `asyncio.run`. If you're in Jupyter and your framework won't let you make the cell async, call `import nest_asyncio; nest_asyncio.apply()` once at the top of the notebook.",
        "attempts": [
            {"tried": "`loop = asyncio.get_event_loop(); loop.run_until_complete(coro())`", "failed_because": "same error in modern Python (3.10+) — run_until_complete also can't run when the loop is running"},
            {"tried": "`loop = asyncio.new_event_loop(); loop.run_until_complete(coro())`", "failed_because": "the coroutine was bound to the original loop; running it in a new loop triggers 'Task attached to a different loop'"},
        ],
        "tools": ["asyncio", "nest_asyncio"],
        "nope": "You're in plain Python with no outer event loop. Then `asyncio.run()` is correct; this error means something else.",
        "langs": ["python"], "libs": ["asyncio"], "domain": "runtime",
    },
    {
        "name": "python-circular-import-module-half-initialized",
        "description": (
            "Circular import where module A imports B which imports A: on the second import, B sees A as "
            "a half-initialized module. Use this skill whenever you get ImportError on a symbol that clearly "
            "exists, or 'partially initialized module X has no attribute Y'. Contains lazy-import + "
            "refactor-shared-to-C patterns."
        ),
        "when_to_use": "`from a import thing` fails with 'cannot import name X from partially initialized module' while `a` also imports from `b` which imports from `a`.",
        "symptom": "`ImportError: cannot import name 'Foo' from partially initialized module 'a' (most likely due to a circular import)`. Both modules are syntactically valid.",
        "approach": "Best: extract the shared symbol into a third module that A and B both import from. That module never imports A or B. Secondary: defer one of the imports into function scope: `def fn(): from b import bar; bar()` — Python resolves the import at call time by which point both modules are fully loaded.",
        "attempts": [
            {"tried": "Moving `import b` to the bottom of `a.py`", "failed_because": "works for the main module pattern but breaks as soon as b imports A's class before its definition; fragile ordering"},
            {"tried": "`from b import *`", "failed_because": "same timing issue — star imports resolve at import time too"},
        ],
        "tools": ["Python import system"],
        "nope": "The modules are genuinely independent and the cycle is accidental — then just remove the unused import.",
        "langs": ["python"], "libs": [], "domain": "runtime",
    },
    {
        "name": "nodejs-require-of-es-module-not-supported",
        "description": (
            "Node.js refuses to `require()` an ESM-only package with 'require() of ES Module ... not supported'. "
            "Use this skill whenever a published library switches to ESM-only (node-fetch, chalk, got, etc.) "
            "and an existing CommonJS codebase breaks. Contains the dynamic `await import()` pattern + "
            "\"type\": \"module\" package.json toggle."
        ),
        "when_to_use": "`require('chalk')` or another ESM-only library throws `Error [ERR_REQUIRE_ESM]: require() of ES Module X is not supported`.",
        "symptom": "Updating a dependency (e.g. chalk 5+, node-fetch 3+) breaks the app with `require() of ES Module /node_modules/chalk/source/index.js from /src/index.js not supported`.",
        "approach": "Replace the static `require` with dynamic import: `const chalk = await import('chalk')`. If you can't make the caller async, refactor to top-level await (ESM) or pin the dep at the last CJS-compatible version. For greenfield code, switch the whole project to ESM with `\"type\": \"module\"` in package.json.",
        "attempts": [
            {"tried": "Pinning to an older CJS version of the dep", "failed_because": "works short-term but now you miss security patches; ecosystem is moving to ESM-only"},
            {"tried": "Adding `esbuild` to transpile back to CJS", "failed_because": "solves the immediate error but the library may also depend on `import.meta.url` and other ESM-only features that don't survive transpilation"},
        ],
        "tools": ["Node.js ESM", "dynamic import"],
        "nope": "You're already in an ESM project — the error must be something else (dual-package hazard, bad exports field).",
        "langs": ["javascript", "typescript"], "libs": [], "domain": "runtime",
    },
    # ---------- TypeScript ----------
    {
        "name": "typescript-satisfies-vs-as-type-widening",
        "description": (
            "`as const` narrows but loses checking against a schema type; `as T` is an unchecked cast. "
            "The `satisfies` operator (TS 4.9+) validates a value against a type WITHOUT widening its "
            "inferred type. Use this skill whenever you need both 'this must match Shape' and 'preserve "
            "the literal types I wrote'. Contains the when-to-use-each guide."
        ),
        "when_to_use": "You want to constrain a config/map to a type while keeping the narrow inferred types of its values (for autocomplete on specific keys).",
        "symptom": "Declaring `const routes: Record<string, Route> = { home: {...} }` loses the fact that `routes.home` specifically exists; `routes.typo` compiles. But using `as const` loses the type-checking that every value matches `Route`.",
        "approach": "Use `satisfies`:\n```ts\nconst routes = {\n  home: { path: '/' },\n  about: { path: '/about' },\n} satisfies Record<string, Route>;\n```\nThe compiler checks each value against `Route`, but `routes.home.path` is the literal `'/'`, and `routes.typo` is a compile error.",
        "attempts": [
            {"tried": "`const routes: Record<string, Route> = {...}`", "failed_because": "widens keys to `string`; `routes.typo` compiles even though 'typo' isn't a real route"},
            {"tried": "`as const` on the object", "failed_because": "keeps the literal types but drops the check that each value is a valid Route; a malformed entry slips through"},
        ],
        "tools": ["TypeScript 4.9+"],
        "nope": "Runtime-dynamic object where keys aren't known until execution — `satisfies` can't help.",
        "langs": ["typescript"], "libs": [], "domain": "language",
    },
    # ---------- Bash / shell ----------
    {
        "name": "bash-set-e-pipefail-silent-failure",
        "description": (
            "`set -e` alone doesn't catch failures inside pipelines — `cmd-that-fails | tee log` is "
            "considered successful because `tee` succeeded. Use this skill whenever a bash script exits 0 "
            "despite a subcommand failing, CI logs show 'deploy ok' but the artifact is broken, or "
            "errors only appear when you pipe to tee/less. Contains the `set -euo pipefail` + shellcheck pattern."
        ),
        "when_to_use": "A bash script with `set -e` at the top still finishes with exit 0 even though a piped command inside it failed.",
        "symptom": "```\nset -e\nbuild-artifact | tee build.log\n```\nbuild-artifact fails, but the script exits 0 because tee succeeded.",
        "approach": "Use the full triple: `set -euo pipefail`. `pipefail` makes the pipeline's exit code the first non-zero status across all stages; `-u` catches typos in variable names; `-e` catches unchecked failures. Run `shellcheck` on the script to catch the rest.",
        "attempts": [
            {"tried": "Just `set -e`", "failed_because": "only catches the exit code of the FINAL command in a pipeline; upstream failures are masked by the last successful stage"},
            {"tried": "Checking `$?` after each command", "failed_because": "works but is noisy and fragile; one missed check breaks the contract"},
        ],
        "tools": ["bash", "shellcheck"],
        "nope": "You intentionally want a pipeline step to fail silently (e.g. `grep -q || true` for optional match). Then don't globally enable pipefail — scope it to a subshell.",
        "langs": [], "libs": [], "domain": "shell",
    },
    # ---------- Go ----------
    {
        "name": "go-goroutine-leak-blocked-on-unbuffered-channel",
        "description": (
            "Go goroutines leak when they're blocked forever on an unbuffered channel send or receive. "
            "Use this skill whenever pprof shows goroutine count growing unbounded, 'fatal error: all "
            "goroutines are asleep - deadlock', or memory creeps up over hours under steady traffic. "
            "Contains context cancellation + select-with-default patterns."
        ),
        "when_to_use": "Over long-running production traffic, pprof shows goroutine count climbing indefinitely, and each stuck goroutine's stack points at a channel operation.",
        "symptom": "`go tool pprof` shows 50k+ goroutines, all blocked at `runtime.chanrecv` or `runtime.chansend`. Restarting the process drops the count, then it climbs again.",
        "approach": "Wire `context.Context` through any goroutine that sends/receives on a channel, and use `select { case ch <- x: case <-ctx.Done(): return }`. Cancel the context when the caller gives up (e.g. HTTP request cancellation). For fire-and-forget, use a buffered channel large enough to absorb worst-case bursts.",
        "attempts": [
            {"tried": "Adding a time.After() timeout per send", "failed_because": "works but allocates a Timer for every send; at high QPS this is a secondary leak of Timer goroutines"},
            {"tried": "Using a buffered channel of size 1", "failed_because": "hides the symptom until burst exceeds 1; same bug, harder to reproduce"},
        ],
        "tools": ["Go `context`", "`pprof`"],
        "nope": "You genuinely want bounded back-pressure — then unbuffered send is correct; the goroutine-block IS the backpressure.",
        "langs": ["go"], "libs": [], "domain": "runtime",
    },
    # ---------- npm / yarn ----------
    {
        "name": "npm-eresolve-peer-dependency-overrides",
        "description": (
            "npm install fails with ERESOLVE peer dependency conflict. --force or --legacy-peer-deps "
            "just mask the problem. Use this skill whenever upgrading React/Next/any major dep breaks "
            "install, CI fails with 'Could not resolve dependency', or a transitive peer wants an older "
            "version. Contains the `overrides` field in package.json that forces a consistent resolution."
        ),
        "when_to_use": "`npm install` fails with `ERESOLVE unable to resolve dependency tree` after an upgrade.",
        "symptom": "```\nnpm ERR! ERESOLVE could not resolve\nnpm ERR! While resolving: my-app@1.0.0\nnpm ERR! Found: react@19.0.0\nnpm ERR! Could not resolve dependency:\nnpm ERR! peer react@'^18' from some-lib@2.0.0\n```",
        "approach": "Use the `overrides` field in package.json to force the peer dep to the version you want:\n```json\n{ \"overrides\": { \"some-lib\": { \"react\": \"$react\" } } }\n```\n`$react` references the root-level react version, so everything agrees.",
        "attempts": [
            {"tried": "`npm install --force`", "failed_because": "works but silently installs incompatible versions side-by-side; the actual peer mismatch is still there at runtime"},
            {"tried": "`npm install --legacy-peer-deps`", "failed_because": "skips the check entirely; hides real incompatibilities until they blow up at runtime"},
        ],
        "tools": ["npm `overrides`", "package.json"],
        "nope": "The library genuinely doesn't support the version you're forcing. `overrides` is a hack; if the library breaks at runtime, you need a proper migration.",
        "langs": ["javascript", "typescript"], "libs": [], "domain": "tooling",
    },
    # ---------- pytest ----------
    {
        "name": "pytest-asyncio-default-fixture-loop-scope-warning",
        "description": (
            "pytest-asyncio 0.23+ emits 'unclosed event loop' warnings and fixture-scope errors when "
            "asyncio_default_fixture_loop_scope isn't set. Use this skill whenever pytest shows "
            "'asyncio_default_fixture_loop_scope is unset', session-scoped async fixtures fail, or "
            "db_session tests behave erratically. Contains the pyproject.toml config."
        ),
        "when_to_use": "pytest-asyncio 0.23+ emits noisy DeprecationWarnings or session-scoped async fixtures fail with 'Task got Future attached to a different loop'.",
        "symptom": "On pytest startup: `PytestDeprecationWarning: The configuration option 'asyncio_default_fixture_loop_scope' is unset`. Session-scoped async fixtures occasionally fail with cross-loop errors.",
        "approach": "In pyproject.toml:\n```toml\n[tool.pytest.ini_options]\nasyncio_mode = \"auto\"\nasyncio_default_fixture_loop_scope = \"session\"\nasyncio_default_test_loop_scope = \"session\"\n```\nThis makes all async fixtures and tests share one event loop per session, so session-scoped fixtures that open connections stay valid throughout.",
        "attempts": [
            {"tried": "Leaving the defaults and ignoring the warning", "failed_because": "pytest-asyncio 0.24 upgraded this to an error; 0.23 silently uses function scope, breaking session-scoped fixtures"},
            {"tried": "Setting scope on each fixture manually", "failed_because": "works for your fixtures but third-party fixtures (httpx_mock, aiohttp client) still default to function scope — inconsistent scopes create cross-loop errors"},
        ],
        "tools": ["pytest-asyncio 0.23+"],
        "nope": "You don't use async fixtures — then asyncio_mode=auto and leaving scope unset is fine; the warning can be silenced with filterwarnings.",
        "langs": ["python"], "libs": ["pytest-asyncio"], "domain": "testing",
    },
    # ---------- Makefile / build tools ----------
    {
        "name": "makefile-missing-separator-tab-vs-spaces",
        "description": (
            "Makefiles fail with 'missing separator. Stop.' when you indent a recipe with spaces "
            "instead of a literal TAB. Use this skill whenever copying a Makefile from the internet "
            "or from an editor with autoformat breaks the build. Contains the detection + editor config."
        ),
        "when_to_use": "`make target` fails with `Makefile:N: *** missing separator. Stop.` on a recipe line that looks correctly indented.",
        "symptom": "`Makefile:5: *** missing separator.  Stop.` — and line 5 looks fine to you, indented like the others.",
        "approach": "Recipe lines MUST begin with a literal TAB character, not spaces. Display whitespace in your editor (set `editor.renderWhitespace`) and check for `·` (space) vs `→` (tab) on recipe lines. In .vscode/settings.json, set `\"[makefile]\": { \"editor.insertSpaces\": false }`.",
        "attempts": [
            {"tried": "Inspecting the file visually", "failed_because": "editors often render tabs and 4 spaces identically; the error is invisible without whitespace markers"},
            {"tried": "`.editorconfig` with `indent_style = tab` for Makefile", "failed_because": "only affects new typing; existing space-indented recipes stay broken until you convert them"},
        ],
        "tools": ["GNU make"],
        "nope": "You're using a non-make build tool (just, task) that uses spaces by design. Different syntax, different rules.",
        "langs": [], "libs": [], "domain": "build",
    },
    # ---------- Dockerfile ----------
    {
        "name": "dockerfile-copy-invalidates-cache-on-every-file-change",
        "description": (
            "Dockerfile's `COPY . .` invalidates every subsequent layer every time any file changes, "
            "forcing re-install of pip/npm deps on trivial source edits. Use this skill whenever docker "
            "builds take 5+ minutes for a one-line code change, the deps layer runs on every build, or "
            "CI caches never hit. Contains the split-deps-first + COPY-manifests-first pattern."
        ),
        "when_to_use": "Every `docker build` takes minutes because the pip/npm install step runs from scratch, even though only a source file changed.",
        "symptom": "Edit one Python file → `docker build` takes 3 minutes installing deps again, even though requirements.txt/pyproject.toml didn't change.",
        "approach": "Split the Dockerfile: first `COPY` only the manifest files (requirements.txt, pyproject.toml, package.json, lock files), run the install, THEN `COPY . .`. The install layer only busts when the manifest actually changes:\n```dockerfile\nCOPY pyproject.toml requirements.txt ./\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\n```",
        "attempts": [
            {"tried": "`COPY . .` at the top, then install", "failed_because": "any source edit invalidates the COPY layer, which invalidates the install layer, which re-downloads every dep"},
            {"tried": "Using `RUN --mount=type=cache`", "failed_because": "speeds up the install itself but still runs it every build; manifest-first is strictly better when manifests don't change often"},
        ],
        "tools": ["Dockerfile", "BuildKit"],
        "nope": "Your project has no stable dep manifest (e.g. a straight `pip install .` with a dynamic dep list). Then the split doesn't buy anything.",
        "langs": [], "libs": [], "domain": "infrastructure",
    },
    # ---------- TLS chain ----------
    {
        "name": "tls-intermediate-certificate-missing-from-chain",
        "description": (
            "TLS handshake fails with 'unable to verify the first certificate' on clients that DON'T "
            "ship with your CA's intermediate, even though browsers work fine. Use this skill whenever "
            "node/python/curl fails TLS but Chrome is happy, `openssl s_client` reports 'verify error "
            "num=20', or the issue only appears on certain hosts. Contains the fullchain.pem vs cert.pem "
            "distinction."
        ),
        "when_to_use": "Chrome/Firefox load your site fine but `curl`, Python `requests`, or Node.js `https` fails with 'unable to verify the first certificate'.",
        "symptom": "`openssl s_client -connect example.com:443` prints `verify error:num=20:unable to get local issuer certificate`. Browsers show a lock icon and don't complain.",
        "approach": "Serve the full chain: leaf cert + intermediate(s), not just the leaf. In nginx: `ssl_certificate /etc/ssl/fullchain.pem;` (fullchain, not cert). Browsers cache intermediates from prior visits so they paper over this; strict clients (curl, requests, Node) don't.",
        "attempts": [
            {"tried": "Serving only the leaf certificate", "failed_because": "browsers already cached the intermediate from another site signed by the same CA; first-time strict clients have no cache and fail"},
            {"tried": "Adding the CA root to the client's trust store", "failed_because": "works for that one client but needs to be done on every machine; the server should provide the chain so any client works"},
        ],
        "tools": ["`openssl s_client`", "nginx ssl_certificate"],
        "nope": "You already serve fullchain and the error is about the ROOT cert — then the client's OS truststore is stale, not a server issue.",
        "langs": [], "libs": [], "domain": "tls",
    },
]


# ---------------------------------------------------------------------------

def main() -> int:
    print(f"API: {API_URL}")
    print(f"curator agent: {CURATOR}")
    secret = ensure_secret()
    print(f"secret: {secret[:10]}…")

    print("\nlooking up existing curated skills…")
    owned = existing_by_name(secret)
    print(f"  already uploaded: {len(owned)}")

    headers = {"X-Relay-Agent-Id": CURATOR, "X-Relay-Agent-Secret": secret}
    created = updated = failed = 0

    print(f"\nuploading {len(SKILLS)} skills…")
    for s in SKILLS:
        meta = make_meta(
            symptom=s["symptom"], approach=s["approach"], attempts=s["attempts"],
            langs=s.get("langs", []), libs=s.get("libs", []), domain=s.get("domain"),
        )
        body = build_body(s["symptom"], s["attempts"], s["approach"], s["tools"], s["nope"])
        payload = {
            "name": s["name"],
            "description": s["description"],
            "when_to_use": s["when_to_use"],
            "body": body,
            "metadata": meta,
        }
        try:
            if s["name"] in owned:
                resp = http("PATCH", f"/skills/{owned[s['name']]}", payload, headers)
                print(f"  updated   {s['name']:55s} {resp['id']}")
                updated += 1
            else:
                resp = http("POST", "/skills", payload, headers)
                print(f"  created   {s['name']:55s} {resp['id']}")
                created += 1
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:200]
            print(f"  FAIL      {s['name']:55s} HTTP {e.code} {detail}")
            failed += 1

    print(f"\ndone: {created} created, {updated} updated, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
