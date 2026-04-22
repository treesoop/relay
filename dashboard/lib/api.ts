// Server-side Relay API client. All calls go through Next.js server components,
// so the API URL never reaches the browser and we sidestep CORS entirely.

const API_URL =
  process.env.RELAY_API_URL ?? "https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com";
const AGENT_ID = process.env.RELAY_AGENT_ID ?? "dashboard-viewer";

/** Revalidation window. 60s keeps the dashboard snappy without serving stale data for long. */
const REVALIDATE = 60;

function url(path: string, params?: Record<string, string | number>): string {
  const u = new URL(path, API_URL);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      u.searchParams.set(k, String(v));
    }
  }
  return u.toString();
}

async function getJSON<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const res = await fetch(url(path, params), {
    headers: { "X-Relay-Agent-Id": AGENT_ID },
    next: { revalidate: REVALIDATE },
  });
  if (!res.ok) {
    throw new Error(`${path} → HTTP ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ---------- types (mirrors central_api/schemas.py) ----------

export interface Attempt {
  tried?: string;
  failed_because?: string;
  worked?: string;
}

export interface ToolUsed {
  type: "mcp" | "library" | "cli";
  name: string;
}

export interface SkillMetadata {
  id?: string;
  source_agent_id?: string;
  problem?: { symptom?: string; context?: string | null };
  solution?: { approach?: string; tools_used?: ToolUsed[] };
  attempts?: Attempt[];
  context?: {
    languages?: string[];
    libraries?: string[];
    domain?: string | null;
  };
  created_at?: string;
  updated_at?: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  when_to_use: string | null;
  body: string;
  metadata: SkillMetadata;
  confidence: number;
  used_count: number;
  good_count: number;
  bad_count: number;
  status: string;
  source_agent_id: string;
}

export interface SearchItem {
  skill: Skill;
  similarity: number;
  confidence: number;
  context_match: number;
  matched_on: string;
  required_tools: string[];
  missing_tools: string[];
}

export interface SearchResponse {
  items: SearchItem[];
}

// ---------- API calls ----------

export async function getSkill(id: string): Promise<Skill | null> {
  try {
    return await getJSON<Skill>(`/skills/${id}`);
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) return null;
    throw err;
  }
}

export async function search(query: string, limit = 20): Promise<SearchItem[]> {
  const data = await getJSON<SearchResponse>("/skills/search", {
    query,
    search_mode: "problem",
    limit,
  });
  return data.items;
}

/**
 * Get a broad sample of skills for the home page. The API exposes only semantic
 * search, so we run a deliberately generic query to approximate "browse all".
 * Results are de-duplicated by id.
 */
export async function listSkills(limit = 30): Promise<SearchItem[]> {
  const seen = new Set<string>();
  const out: SearchItem[] = [];
  for (const q of ["problem", "error", "deploy", "library", "build", "configure"]) {
    try {
      const items = await search(q, 20);
      for (const it of items) {
        if (!seen.has(it.skill.id)) {
          seen.add(it.skill.id);
          out.push(it);
          if (out.length >= limit) return out;
        }
      }
    } catch {
      // keep going — one bad query shouldn't kill the grid
    }
  }
  return out;
}
