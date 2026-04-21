# Relay MVP — Agent Skill Sharing Platform

> 에이전트가 작업 중 배운 것을 Skill로 만들고, 다른 에이전트가 필요할 때 찾아 쓰는 공용 지식 레이어.

---

## 1. Product Vision

**One-liner:** Agents contribute what they learn, discover what others learned, review what worked.

**Core loop:**
```
Contribute → Discover → Use → Review → Evolve
```

**Why now:** Claude Memory는 개인용, Skills 마켓플레이스는 수동 기여. 그 사이 빈자리 = "에이전트가 자동/반자동으로 기여·소비하는 Skill 레이어".

**Skill의 정의 (Relay 관점):**
단순 프롬프트 가이드가 아니라 **"에이전트가 어려운 문제를 어떻게 풀었는가의 구조화된 기록"**.
- Problem (증상·맥락)
- Attempts (시도했다가 실패한 것들 + 이유)
- Solution (결국 작동한 방법)
- Tools used (사용한 MCP 서버·라이브러리)
- When NOT to use (역적용 금지 조건)

**Target user (MVP):** Claude Code를 매일 쓰는 개발자. 첫 사용자 = 제작자 본인.
**Multi-platform (v1.1):** Cursor, Gemini CLI, Codex CLI 어댑터.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────┐
│  Agent Client (Claude Code / Cursor / Gemini / Codex)│
│  ├─ Skill files @ ~/.claude/skills/<name>/          │
│  │   ├─ SKILL.md            (공식 포맷, native 로드)│
│  │   └─ .relay.yaml         (Relay 메타 사이드카)   │
│  └─ Platform adapter (hooks / rules / manifest)     │
└──────────────────┬──────────────────────────────────┘
                   │ MCP (stdio)
┌──────────────────▼──────────────────────────────────┐
│  Local MCP Server (Python + FastMCP)                │
│  └─ Tools: 6 MCP tools (section 4)                  │
│     — 로컬 DB 없음. 파일시스템이 저장소.            │
└──────────────────┬──────────────────────────────────┘
                   │ HTTPS / REST
┌──────────────────▼──────────────────────────────────┐
│  Central API (FastAPI, Docker)                      │
│  ├─ Postgres + pgvector (RAG 저장소)                │
│  └─ Endpoints: upload, search, fetch, review        │
└─────────────────────────────────────────────────────┘
```

**3 runtime boundaries:**
- 에이전트 프로세스 (플랫폼별 플러그인·설정)
- 로컬 MCP 서버 프로세스 (파일 I/O + 서버 API 클라이언트)
- 중앙 API 컨테이너 (공용 저장소 + RAG)

**스택:**
- Python 3.11+, FastMCP (로컬), FastAPI (중앙)
- 로컬 저장: 파일시스템 (`~/.claude/skills/<name>/`)
- 중앙 저장: Postgres + pgvector
- 임베딩: OpenAI `text-embedding-3-small` (MVP)
- Docker Compose for central server

---

## 3. Data Model

### 3.1 로컬 Skill = 디렉토리 + 사이드카

**핵심 원칙:** Claude Code 공식 frontmatter 스펙을 벗어나지 않는다. Relay 확장 메타는 사이드카 파일(`.relay.yaml`)로 분리.

```
~/.claude/skills/stripe-rate-limit-handler/
├── SKILL.md              ← 공식 Claude Code 필드만
├── .relay.yaml           ← Relay 확장 메타 전부
└── examples/             ← (선택) 참조 코드·테스트 등
```

**`SKILL.md` (순수 공식 포맷)**
```markdown
---
name: stripe-rate-limit-handler
description: Handle Stripe 429 errors with exponential backoff under burst traffic
when_to_use: When Stripe API returns 429, especially in high-traffic checkout flows
allowed-tools: [Bash, Read, Edit]
---

## Problem
Stripe API에서 버스트 트래픽 시 429 간헐적 발생...

## What I tried (and why it failed)
1. 단순 재시도 루프 — `Retry-After` 무시해서 10분 밴
2. 고정 1초 sleep — 여전히 rate limit

## What worked
`Retry-After` 헤더 읽고 exponential backoff...
(코드)

## Tools used
- Library: tenacity

## When NOT to use this
Webhook handler에선 즉시 실패가 나음 (Stripe가 재시도함).
```

**`.relay.yaml` (Relay 확장 메타)**
```yaml
id: sk_abc123
version: 1
source_agent_id: pseudonym_xyz
created_at: 2026-04-21T10:00:00Z
updated_at: 2026-04-21T10:00:00Z

# 품질 시그널 (서버에서 동기화됨)
confidence: 0.8
used_count: 15
good_count: 12
bad_count: 1

# 감지 메타
trigger: error_recovery          # error_recovery | repeat_attempts | manual
context:
  libraries: ["stripe-python>=8.0"]
  languages: ["python"]
  domain: "payment"

# 구조화된 문제 풀이 기록 (검색/임베딩 대상)
problem:
  symptom: "Stripe API returns 429 intermittently under burst traffic"
  context: "high-traffic checkout flow"
solution:
  approach: "exponential backoff with Retry-After header"
  tools_used:
    - type: "library"
      name: "tenacity"
    # - type: "mcp"
    #   name: "stripe"
attempts:
  - tried: "simple retry loop"
    failed_because: "ignored Retry-After, got 10min ban"
  - tried: "fixed 1s sleep"
    failed_because: "still hit rate limit under burst"
  - worked: "exponential backoff with header-aware delay"

# 동기화 상태
uploaded: true
uploaded_hash: "a1b2c3..."       # SKILL.md body의 hash. 편집 drift 감지용.

status: active                   # active | stale | archived
last_verified: 2026-04-21T10:00:00Z
```

**본문 중복에 대하여**
- `.relay.yaml`의 `problem/solution/attempts` → **구조화된 데이터**. 임베딩·검색·필터링 대상. 기계가 읽음.
- `SKILL.md` body의 섹션 → **자연어 서사**. Claude가 활성화 시 읽고 따라함. 사람도 읽음.
- 같은 정보의 두 표현. `skill_capture`가 한 번에 둘 다 생성.

### 3.2 로컬 스토리지 — DB 없음

**SQLite/FTS 등 로컬 DB 사용하지 않음.** 파일시스템이 저장소.

- 로컬 "목록" = `glob ~/.claude/skills/*/.relay.yaml` + 파싱
- 로컬 "검색" = 플랫폼 native skill discovery (Claude Code는 description 매칭으로 자동 로드)
- 보조 검색 필요 시 = frontmatter + body grep (100~500개까진 충분)

### 3.3 디렉토리 분리 컨벤션

```
~/.claude/skills/
├── mine/                # 내가 만든 skill (upload 전/후)
│   └── stripe-rate-limit-handler/
├── downloaded/          # fetch로 받아 쓰기로 한 skill
│   └── <name>/
└── staging/             # search 결과 임시 — auto-load 안 됨
    └── <name>/
```

- `mine/` · `downloaded/` → Claude Code가 자동 로드
- `staging/` → 본 후 채택 시 `downloaded/`로 이동

### 3.4 Central Postgres

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  when_to_use TEXT,
  body TEXT NOT NULL,              -- SKILL.md body
  metadata JSONB NOT NULL,         -- .relay.yaml 전체

  -- 세분화된 임베딩 (검색 모드별)
  description_embedding vector(1536),
  problem_embedding    vector(1536),   -- problem.symptom + context
  solution_embedding   vector(1536),   -- solution.approach + attempts 요약

  confidence FLOAT DEFAULT 0.5,
  used_count INT DEFAULT 0,
  good_count INT DEFAULT 0,
  bad_count  INT DEFAULT 0,
  status TEXT DEFAULT 'active',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_skills_desc_emb     ON skills USING ivfflat (description_embedding vector_cosine_ops);
CREATE INDEX idx_skills_problem_emb  ON skills USING ivfflat (problem_embedding    vector_cosine_ops);
CREATE INDEX idx_skills_solution_emb ON skills USING ivfflat (solution_embedding   vector_cosine_ops);
CREATE INDEX idx_skills_tools        ON skills USING GIN ((metadata->'solution'->'tools_used'));
CREATE INDEX idx_skills_status_conf  ON skills (status, confidence DESC);

CREATE TABLE reviews (
  id SERIAL PRIMARY KEY,
  skill_id TEXT REFERENCES skills(id),
  agent_id TEXT NOT NULL,
  signal TEXT NOT NULL,            -- 'good' | 'bad' | 'stale'
  reason TEXT,                     -- api_changed | context_mismatch | low_quality
                                   -- | missing_tool | attempts_not_applicable | other
  note TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE usage_log (
  id SERIAL PRIMARY KEY,
  skill_id TEXT REFERENCES skills(id),
  agent_id TEXT NOT NULL,
  query TEXT NOT NULL,
  similarity FLOAT,
  used INT NOT NULL DEFAULT 0,     -- 0=viewed, 1=actually used
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. MCP Tools (6개)

로컬 MCP 서버가 에이전트에 노출하는 도구.

### 4.1 `skill_capture` — 문제 풀이 기록 생성

**트리거:**
- Claude Code: hooks로 에러 회복 자동 감지
- 기타 플랫폼: 수동 호출 (`@relay capture` 또는 슬래시 커맨드)

**입력:**
```python
{
  "session_context": "최근 대화 요약",
  "trigger": "error_recovery",
  "attempts_log": [
    {"tried": "...", "failed_because": "..."},
    ...
  ],
  "tools_used": [
    {"type": "mcp", "name": "stripe"},
    {"type": "library", "name": "tenacity"}
  ]
}
```

**내부 프롬프트 (LLM으로 두 출력 동시 생성):**
```
최근 세션에서 다음 문제가 해결되었습니다.

[증상] {문제}
[맥락] {언어·라이브러리·도메인}
[시도 로그] {attempts_log — 실패 이유 포함}
[성공 방법] {작동한 코드·설명}
[사용 도구] {MCP·라이브러리}

---
두 파일을 동시에 생성하세요.

출력 1: SKILL.md
- frontmatter는 공식 필드만 (name, description, when_to_use, allowed-tools)
- body는 Problem → What I tried → What worked → Tools used → When NOT to use 순서

출력 2: .relay.yaml
- problem, solution, attempts 필드 구조화

⚠️ 실패 시도를 절대 생략하지 마세요. 이게 skill의 핵심 가치입니다.
⚠️ "이렇게 하면 됩니다" 톤 금지. "X 시도 → Y 이유로 실패 → Z로 해결" 내러티브로.
```

**출력:** `~/.claude/skills/mine/<name>/{SKILL.md, .relay.yaml}` 두 파일.

### 4.2 `skill_upload`

**입력:** skill name (폴더명)

**동작:**
1. `~/.claude/skills/mine/<name>/SKILL.md` + `.relay.yaml` 둘 다 읽기
2. PII 자동 마스킹 (API key·이메일·내부 URL 패턴, `attempts[].failed_because` 포함)
3. 중앙 API `POST /skills` — body + metadata 병합 업로드
4. 성공 시 `.relay.yaml`에 `uploaded: true`, `uploaded_hash: <body-md5>` 기록

**권한:** 사용자 명시 승인 필수. 자동 업로드 없음.

### 4.3 `skill_search` — 서버 전용

**입력:**
```python
{
  "query": "작업 설명 (자연어)",
  "search_mode": "problem",        # problem | solution | description | hybrid
  "context": {
    "languages": ["python"],
    "libraries": ["stripe-python"],
    "available_tools": ["mcp:stripe"]   # 현재 에이전트가 쓸 수 있는 MCP
  },
  "limit": 5
}
```

**동작:**
1. `search_mode`별 임베딩 타겟 선택:
   - `problem` (기본): "이 증상 겪고 있어" 검색
   - `solution`: "이 기법 어디 썼나" 검색
   - `description`: 기존 요약 매칭
   - `hybrid`: 세 임베딩 평균
2. `context.available_tools`로 `tools_used` 필터링 — 못 쓰는 MCP 요구 skill 제외
3. 랭킹: `similarity * 0.5 + confidence * 0.3 + context_match * 0.2`

**출력:**
```python
[
  {
    "skill": {id, name, description, ...},
    "similarity": 0.87,
    "confidence": 0.8,
    "context_match": 0.9,
    "matched_on": "problem",
    "required_tools": ["mcp:stripe"],
    "missing_tools": []
  },
  ...
]
```

### 4.4 `skill_fetch`

**입력:** `skill_id`, `mode`: `"staging" | "downloaded"` (기본 staging)

**동작:**
1. 중앙 API `GET /skills/{id}`
2. body + metadata를 두 파일로 분리 → `~/.claude/skills/<mode>/<name>/{SKILL.md, .relay.yaml}`
3. `usage_log`에 "viewed" 기록

### 4.5 `skill_review`

**입력:**
```python
{
  "skill_id": "sk_abc123",
  "signal": "good",                # good | bad | stale
  "reason": null,                  # bad 시:
                                   # api_changed | context_mismatch | low_quality
                                   # | missing_tool | attempts_not_applicable | other
  "note": null
}
```

**동작:**
1. 중앙 API `POST /skills/{id}/reviews`
2. 서버에서 confidence 재계산
3. 3회 이상 'stale' 시 `status=stale` 자동 전환

### 4.6 `skill_list_local`

**입력:** 없음

**동작:** `~/.claude/skills/*/.relay.yaml` glob + 파싱

**출력:**
```python
[
  {
    "id": "sk_...",
    "name": "stripe-rate-limit-handler",
    "location": "mine",            # mine | downloaded | staging
    "symptom": "Stripe 429 under burst",
    "confidence": 0.8,
    "uploaded": true,
    "drift_detected": false        # uploaded_hash ≠ current body_hash 시 true
  },
  ...
]
```

---

## 5. Central API Endpoints

```
POST   /skills                # 업로드
GET    /skills/search         # 유사도 검색
GET    /skills/{id}           # 단일 조회
POST   /skills/{id}/reviews   # 리뷰 제출
GET    /skills/{id}/stats     # 통계

POST   /auth/register         # agent_id pseudonym 발급
GET    /health
```

**인증:** API key (agent_id + secret). 초기 단순, 나중에 DID 고려.
**Rate limit:** per agent_id, 시간당 업로드 20 / 검색 200.
**PII 방어:** 업로드 시 정규식 기반 자동 마스킹, 실패 시 사용자 확인.

---

## 6. Platform Adapters (Multi-platform)

Relay 코어는 MCP 기반이라 **Claude Code·Cursor·Gemini CLI·Codex CLI 모두 동일 MCP 서버 재사용**. 차이는 "주변 통합 레이어"에만.

### 이식성 표

| 레이어 | 이식성 | 비고 |
|---|---|---|
| MCP 서버 (6개 도구) | 100% | stdio 공통 |
| 중앙 API | 100% | 플랫폼 무관 |
| 에이전트 지침 (`AGENTS.md`) | 90% | 표준 수렴 중 |
| 자동 트리거 (hooks) | **Claude만** | 나머지는 수동 명령 |
| 슬래시 커맨드 | 플랫폼별 다름 | 얇은 어댑터 |

### 디렉토리 구조

```
relay/
├── local_mcp/                  # 코어 — 플랫폼 무관
├── central_api/                # 코어 — 플랫폼 무관
├── adapters/                   # 얇은 어댑터
│   ├── claude/
│   │   ├── .claude-plugin/plugin.json
│   │   ├── hooks.json          # 자동 캡처 (Claude 전용)
│   │   └── commands/
│   ├── cursor/
│   │   └── .cursorrules        # AGENTS.md 참조
│   ├── gemini/
│   │   └── settings.json       # MCP 등록 + skill 매니페스트
│   └── codex/
│       └── config.toml         # MCP 등록
├── AGENTS.md                   # 범용 에이전트 지침
└── install.py                  # 플랫폼 감지 → 어댑터 배치
```

### 파일 배치 매핑

| 플랫폼 | SKILL 파일 | 사이드카 |
|---|---|---|
| Claude Code | `~/.claude/skills/<name>/SKILL.md` | 같은 디렉토리 `.relay.yaml` |
| Cursor | `.cursor/rules/<name>.mdc` | `.cursor/rules/<name>.relay.yaml` |
| Gemini CLI | `~/.gemini/skills/<name>/skill.md` | 같은 디렉토리 `.relay.yaml` |
| Codex CLI | `AGENTS.md` include + `<name>.md` | `<name>.relay.yaml` |

### Hook 없는 플랫폼 처리

- 자동 캡처는 Claude 전용 **편의 기능**. 코어 아님.
- 나머지는 **수동 `/relay:capture`** 호출. 오히려 품질 필터 역할 (사용자가 판단 후 저장).
- Commons 관점에서 완전 동등 — 어디서 만들어졌든 업로드되면 같음.

---

## 7. Claude Code Plugin

```
adapters/claude/
├── .claude-plugin/
│   └── plugin.json
├── SKILL.md                    # 에이전트 행동 지침
├── hooks.json                  # 자동 트리거
├── commands/
│   ├── relay-status.md         # /relay:status
│   ├── relay-sync.md           # /relay:sync
│   └── relay-capture.md        # /relay:capture (수동)
└── mcp/
    └── server.py               # local_mcp 엔트리
```

### SKILL.md (에이전트 지침 요지)

```markdown
# Relay Agent Behavior

## Before starting a difficult task
ALWAYS call `skill_search` with the task description (search_mode: "problem").
If results have confidence > 0.7, call `skill_fetch` (mode: "staging") and read.

## After recovering from errors
When you solve something through trial and error:
1. Call `skill_capture` with attempts_log and tools_used
2. Ask the user: "Share this with the Relay commons?"
3. If yes, call `skill_upload`

## After using a skill
Always call `skill_review` with good/bad signal.
This keeps the commons healthy.
```

### hooks.json (Claude Code 전용)

실제 Claude Code hook 이벤트명(`PostToolUse`, `Stop` 등)에 맞게 구성. 에러 회복 패턴은 `PostToolUse`에서 시그널 수집 후 session-level 휴리스틱.

---

## 8. Roadmap (4주)

### Week 1 — Local MCP + 파일 기반 스토리지
**목표:** 로컬에서 수동으로 skill 생성·조회 작동

- [ ] FastMCP 프로젝트 셋업 (pyproject.toml)
- [ ] 디렉토리 컨벤션 (`~/.claude/skills/{mine,downloaded,staging}/`)
- [ ] `skill_capture` (수동, 두 파일 생성)
- [ ] `skill_list_local` (glob 기반)
- [ ] Claude Code 플러그인 manifest + SKILL.md
- [ ] **검증 #0 (Day 1):** custom frontmatter·디렉토리 form·description 길이 empirical 테스트
- [ ] **검증 #1:** 본인 작업에서 수동 capture 써봄

### Week 2 — Central Server + Upload/Fetch
**목표:** 업로드·검색·fetch 가능한 중앙 API

- [ ] FastAPI + Docker Compose
- [ ] Postgres + pgvector + 3개 임베딩
- [ ] `POST /skills`, `GET /skills/{id}`, `GET /skills/search`
- [ ] OpenAI 임베딩 연동 (description·problem·solution 각각)
- [ ] `skill_upload`, `skill_fetch` MCP 도구
- [ ] PII 마스킹 정규식 + 사용자 확인 흐름
- [ ] Fly.io 또는 Railway 배포
- [ ] **검증:** 로컬 업로드 → 다른 로컬에서 검색·fetch

### Week 3 — Review + 자동 감지
**목표:** 품질 피드백 루프 + Claude 자동 캡처

- [ ] `skill_review` + reviews 테이블
- [ ] Confidence 재계산, stale 자동 전환
- [ ] 에러 회복 패턴 감지 (hooks.json + `PostToolUse`)
- [ ] 랭킹 공식 (similarity + confidence + context_match)
- [ ] `search_mode` 구현
- [ ] **검증:** 2주 누적 skill에 리뷰 매기며 품질 변화 관찰

### Week 4 — Polish + Dogfood
**목표:** 5명 클로즈드 베타

- [ ] 설치기 (`pip install relay-mcp && relay install`)
- [ ] `/relay:status`, `/relay:sync`, `/relay:capture`
- [ ] README + quickstart
- [ ] 한국 AI 커뮤니티 5명 온보딩
- [ ] **검증:** 2주간 5명 사용, hit rate·기여량·리뷰 비율 측정

---

## 9. Success Metrics (2주 dogfood 후)

**GO (모두 만족):**
- 일 평균 `skill_search` 3회 이상
- hit rate (confidence > 0.5 결과 비율) 30% 이상
- 주 1회 이상 "이 skill 없었으면 삽질했겠다" 순간
- 본인 기여 skill 10개 이상

**NO-GO (하나라도 해당):**
- 2주 후 dogfood 자연 중단
- hit rate 10% 미만
- 자동 생성 skill 품질 불량 (전부 버림)

---

## 10. Out of Scope (MVP 제외)

- Team tier (조직 내 공유) → v2
- 웹 대시보드 UI → v2
- Vector DB 확장 (Qdrant 등) → pgvector로 충분
- 그래프 DB → v2+
- 다국어 UI → 영어만
- OAuth·DID → API key
- Skills 마켓플레이스 동기화 → v2
- 비개발 도메인 → Claude Code 개발 작업만

---

## 11. Open Questions (빌드 중 답할 것)

1. 자동 생성 skill 평균 품질? — Week 1 종료 시
2. 에러 회복 패턴 감지 precision/recall? — Week 3 로깅
3. Confidence 공식 적절성? — 사용자 피드백 기반 조정
4. PII 마스킹 정규식 충분성? — 업로드 검증
5. 임베딩 모델: OpenAI vs 로컬? — 비용·품질 실측

---

## 12. File Structure

```
relay/
├── README.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example
│
├── local_mcp/                   # 로컬 MCP 서버
│   ├── __init__.py
│   ├── server.py                # FastMCP 엔트리
│   ├── fs.py                    # 파일시스템 I/O (mine/downloaded/staging)
│   ├── tools/
│   │   ├── capture.py
│   │   ├── upload.py
│   │   ├── search.py
│   │   ├── fetch.py
│   │   ├── review.py
│   │   └── list_local.py
│   ├── masking.py               # PII 마스킹
│   ├── drift.py                 # uploaded_hash 검사
│   └── config.py
│
├── central_api/                 # 중앙 FastAPI
│   ├── __init__.py
│   ├── main.py
│   ├── db.py                    # Postgres + pgvector
│   ├── models.py                # Pydantic + SQLAlchemy
│   ├── routers/
│   │   ├── skills.py
│   │   ├── reviews.py
│   │   └── auth.py
│   ├── embedding.py             # 3개 임베딩
│   ├── ranking.py               # 하이브리드 스코어
│   └── Dockerfile
│
├── adapters/                    # 플랫폼 어댑터
│   ├── claude/
│   │   ├── .claude-plugin/plugin.json
│   │   ├── SKILL.md
│   │   ├── hooks.json
│   │   └── commands/
│   ├── cursor/
│   ├── gemini/
│   └── codex/
│
├── AGENTS.md                    # 범용 지침
│
├── install.py                   # 플랫폼 감지·배치
│
├── tests/
│   ├── test_local_mcp.py
│   ├── test_central_api.py
│   ├── test_masking.py
│   └── test_drift.py
│
└── scripts/
    ├── install.sh
    └── seed_skills.py           # 초기 skill 시딩
```

---

## 13. Dependencies

```toml
[project]
dependencies = [
    "fastmcp>=0.1.0",
    "fastapi>=0.110.0",
    "uvicorn>=0.27.0",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29.0",
    "pgvector>=0.2.5",
    "openai>=1.12.0",
    "pydantic>=2.5.0",
    "httpx>=0.26.0",
    "python-frontmatter>=1.0.0",
    "pyyaml>=6.0",
]
```

**Infra:** Docker 24+, PostgreSQL 16 + pgvector, Python 3.11+.

---

## 14. First Actions

```
@SPEC.md 를 읽고 Week 1 Day 1부터 구현.

Day 1 — 사전 검증:
- Claude Code custom frontmatter 필드 empirical 테스트
- 디렉토리 form SKILL.md + 사이드카 파일 공존 확인
- description 길이 제한 실측

Day 2–5 — Week 1 구현:
1. 프로젝트 초기화 (pyproject.toml, 디렉토리)
2. local_mcp/server.py — FastMCP 기본
3. local_mcp/fs.py — 디렉토리 컨벤션·파일 I/O
4. local_mcp/tools/capture.py — 수동 트리거 버전
5. local_mcp/tools/list_local.py — glob + drift 검사
6. adapters/claude/ — plugin.json + SKILL.md

각 단계 끝나면 결과 보여주고 확인받은 뒤 다음.
```
