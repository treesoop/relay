CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    secret_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    when_to_use TEXT,
    body TEXT NOT NULL,
    metadata JSONB NOT NULL,

    description_embedding vector(1536),
    problem_embedding     vector(1536),
    solution_embedding    vector(1536),

    confidence FLOAT DEFAULT 0.5,
    used_count INT DEFAULT 0,
    good_count INT DEFAULT 0,
    bad_count  INT DEFAULT 0,
    status TEXT DEFAULT 'active',

    source_agent_id TEXT REFERENCES agents(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skills_desc_emb
  ON skills USING ivfflat (description_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_skills_problem_emb
  ON skills USING ivfflat (problem_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_skills_solution_emb
  ON skills USING ivfflat (solution_embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_skills_tools
  ON skills USING GIN ((metadata -> 'solution' -> 'tools_used'));

CREATE INDEX IF NOT EXISTS idx_skills_status_conf
  ON skills (status, confidence DESC);

CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    signal TEXT NOT NULL CHECK (signal IN ('good', 'bad', 'stale')),
    reason TEXT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_log (
    id SERIAL PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    query TEXT,
    similarity FLOAT,
    used INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
