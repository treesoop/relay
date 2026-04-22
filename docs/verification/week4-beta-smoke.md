# Week 4 — beta onboarding smoke test

One section per invited user. Fill in as they come online.

## Template

```
### <user handle>
- Date: YYYY-MM-DD
- OS: macOS / Linux
- Install result: ok / failed (what failed)
- First /relay:capture: ok / failed
- First /relay:search: ok / failed
- First hour observations: <free text>
- Follow-up needed: yes / no
```

## Users

(none yet)

## Week 4 Task 4 — local install sweep

Date: 2026-04-22
Host: macOS arm64, Python 3.14.4

- `install.sh` in a clean `/tmp` directory with `RELAY_REPO_URL` pointing at the local repo: **PASS**
  - Python 3.11+ detector picked `python3.14`.
  - Clone + venv + `pip install -e ".[dev]"` + symlink `relay-mcp` all completed without errors.
  - `claude plugin install relay@relay-local` detected the existing install and skipped.
- `imports ok`: `python -c "import local_mcp; import central_api"` succeeded from the scratch venv.
- `pytest tests/test_types.py tests/test_fs.py tests/test_drift.py -q`: 23 passed in 0.30s.
- Full suite on the project venv: **93 passed, 1 skipped** (Week 1–3 baseline preserved).
- Cloud health: `https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com/health` → `{"status":"ok"}`.
- `metrics.py` against RDS: 7 active skills, 2 reviews in last 24h, avg confidence 0.571.
- `make help` lists all 9 targets; `help` / `install` / `test` / `up` / `down` / `reset-local` / `deploy-redeploy` / `smoke` / `metrics` all resolve.

### Bug caught during install sweep
`install.sh` initially called `python3` unconditionally and picked up the macOS system 3.9, failing the version check. Fixed by iterating candidates (`python3.14`, `python3.13`, `python3.12`, `python3.11`, then generic `python3`) and selecting the first one whose minor version is ≥ 11.

### Outstanding

- `install.sh` fallback to GitHub clone has not been exercised end-to-end yet (this run used a local path). Safe to exercise once `treesoop/relay` main branch has the latest Week 4 commits.
- `claude plugin marketplace add` on a pristine system (no prior Relay install) has not been re-tested; the current check branched to "already installed" because the local dev instance was already registered.
