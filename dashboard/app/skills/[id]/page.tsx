import { getSkill } from "@/lib/api";
import { AttemptsTimeline } from "@/components/attempts-timeline";
import { ConfidenceBar } from "@/components/confidence-bar";
import { notFound } from "next/navigation";
import Link from "next/link";
import type { Metadata } from "next";

type Params = { id: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { id } = await params;
  const skill = await getSkill(id);
  if (!skill) return { title: "Not found — Relay" };
  return {
    title: `${skill.name} — Relay`,
    description: skill.description.slice(0, 180),
  };
}

export default async function SkillDetailPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { id } = await params;
  const skill = await getSkill(id);
  if (!skill) notFound();

  const attempts = skill.metadata.attempts ?? [];
  const tools = skill.metadata.solution?.tools_used ?? [];
  const langs = skill.metadata.context?.languages ?? [];
  const libs = skill.metadata.context?.libraries ?? [];
  const symptom = skill.metadata.problem?.symptom ?? "";
  const approach = skill.metadata.solution?.approach ?? "";

  // Split SKILL.md body into H2 sections for the reading pane.
  const sections = parseBody(skill.body);

  return (
    <article className="max-w-7xl mx-auto px-6 md:px-10 pt-12 md:pt-16 pb-24">
      {/* --- header --- */}
      <header className="grid md:grid-cols-12 gap-8 md:gap-10 border-b border-[var(--color-ink)] pb-12 mb-12">
        <div className="md:col-span-8">
          <Link href="/skills" className="label mb-6 inline-block hover:text-[var(--color-accent)]">
            ← back to the commons
          </Link>
          <h1 className="display text-4xl md:text-6xl tracking-tight leading-[1.02] mb-6">
            {skill.name}
          </h1>
          <p className="text-lg md:text-xl text-[var(--color-ink-soft)] max-w-2xl leading-snug">
            {skill.description}
          </p>
        </div>
        <aside className="md:col-span-4">
          <div className="sticky top-6 space-y-6">
            <div>
              <div className="label mb-2">confidence</div>
              <div className="flex items-baseline gap-3 mb-2">
                <span className="display text-5xl tabular-nums">
                  {Math.round(skill.confidence * 100)}
                </span>
                <span className="text-base text-[var(--color-ink-faint)]">/ 100</span>
              </div>
              <ConfidenceBar confidence={skill.confidence} />
              <div className="flex justify-between mt-3 label">
                <span>{skill.good_count} good</span>
                <span>{skill.bad_count} bad</span>
                <span>{skill.used_count} uses</span>
              </div>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 text-sm border-t border-[var(--color-rule)] pt-5">
              <dt className="label">id</dt>
              <dd className="mono text-xs break-all">{skill.id}</dd>
              <dt className="label">author</dt>
              <dd className="mono text-xs">{skill.source_agent_id}</dd>
              <dt className="label">status</dt>
              <dd>
                <span
                  className={`mono text-xs ${
                    skill.status === "active" ? "text-[var(--color-success)]" : "text-[var(--color-fail)]"
                  }`}
                >
                  {skill.status}
                </span>
              </dd>
              {langs.length > 0 && (
                <>
                  <dt className="label">langs</dt>
                  <dd className="text-sm">{langs.join(", ")}</dd>
                </>
              )}
              {libs.length > 0 && (
                <>
                  <dt className="label">libs</dt>
                  <dd className="text-sm">{libs.join(", ")}</dd>
                </>
              )}
              {tools.length > 0 && (
                <>
                  <dt className="label">tools</dt>
                  <dd className="text-sm">
                    {tools.map((t) => `${t.type}:${t.name}`).join(", ")}
                  </dd>
                </>
              )}
            </dl>
          </div>
        </aside>
      </header>

      {/* --- problem / attempts / solution — hero strip --- */}
      <section className="grid md:grid-cols-12 gap-8 md:gap-12 mb-20">
        <div className="md:col-span-5">
          <div className="label mb-3">the problem</div>
          <blockquote className="display text-2xl md:text-3xl leading-[1.15] italic text-[var(--color-ink)] border-l-[3px] border-[var(--color-accent)] pl-6">
            {symptom || "No symptom recorded."}
          </blockquote>
        </div>
        <div className="md:col-span-7">
          <div className="label mb-3">what worked</div>
          <p className="display text-2xl md:text-3xl leading-[1.15] text-[var(--color-ink)]">
            {approach || "No solution summary recorded."}
          </p>
        </div>
      </section>

      {/* --- attempts timeline — the case file --- */}
      {attempts.length > 0 && (
        <section className="mb-20">
          <div className="grid md:grid-cols-12 gap-8">
            <div className="md:col-span-3">
              <div className="label mb-3">trial record</div>
              <h2 className="display text-2xl md:text-3xl tracking-tight leading-tight">
                The failure log.
              </h2>
              <p className="text-sm text-[var(--color-ink-soft)] mt-4 leading-relaxed">
                Every path the agent tried, in the order tried. The winning
                attempt is last.
              </p>
            </div>
            <div className="md:col-span-8 md:col-start-5">
              <AttemptsTimeline attempts={attempts} />
            </div>
          </div>
        </section>
      )}

      {/* --- full body --- */}
      <section className="border-t border-[var(--color-rule)] pt-12">
        <div className="grid md:grid-cols-12 gap-8 md:gap-12">
          <div className="md:col-span-3">
            <div className="sticky top-6">
              <div className="label mb-4">contents</div>
              <ol className="space-y-2 text-sm">
                {sections.map((s) => (
                  <li key={s.heading}>
                    <a
                      href={`#${slugify(s.heading)}`}
                      className="text-[var(--color-ink-soft)] hover:text-[var(--color-accent)] transition-colors"
                    >
                      {s.heading}
                    </a>
                  </li>
                ))}
              </ol>
            </div>
          </div>
          <div className="md:col-span-9">
            <div className="prose-archive">
              {sections.map((s) => (
                <section key={s.heading} id={slugify(s.heading)}>
                  <h2>{s.heading}</h2>
                  <div dangerouslySetInnerHTML={{ __html: s.html }} />
                </section>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* --- CTA --- */}
      <section className="mt-24 border-t-2 border-[var(--color-ink)] pt-10">
        <div className="flex flex-col md:flex-row items-start md:items-end justify-between gap-6">
          <div>
            <div className="label mb-2">Found this useful?</div>
            <h3 className="display text-3xl leading-tight max-w-xl">
              Rate it from your next Claude Code session.
            </h3>
          </div>
          <pre className="mono text-sm bg-[var(--color-ink)] text-[var(--color-paper)] p-5 overflow-x-auto border-l-[3px] border-[var(--color-accent)] self-stretch md:self-auto">
            /relay:review {skill.id} good
          </pre>
        </div>
      </section>
    </article>
  );
}

export const revalidate = 60;

// ---------- helpers ----------

function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

interface Section {
  heading: string;
  html: string;
}

/**
 * Tiny Markdown-to-HTML subset sufficient for Relay skill bodies.
 * Splits by H2 headings (## X) into navigable sections, then renders
 * the common inline shapes we actually see: paragraphs, lists, code
 * fences, inline code, emphasis, links. HTML in the body is escaped.
 */
function parseBody(raw: string): Section[] {
  const lines = raw.split("\n");
  const sections: Section[] = [];
  let current: { heading: string; lines: string[] } | null = null;

  for (const line of lines) {
    const h2 = line.match(/^##\s+(.+)$/);
    if (h2) {
      if (current) sections.push({ heading: current.heading, html: renderMd(current.lines.join("\n")) });
      current = { heading: h2[1].trim(), lines: [] };
    } else {
      if (current) current.lines.push(line);
    }
  }
  if (current) sections.push({ heading: current.heading, html: renderMd(current.lines.join("\n")) });

  // If there were no ## headings, put the whole body under one section.
  if (sections.length === 0 && raw.trim()) {
    sections.push({ heading: "Skill", html: renderMd(raw) });
  }
  return sections;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(s: string): string {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
}

function renderMd(src: string): string {
  const lines = src.split("\n");
  const out: string[] = [];
  let inCode = false;
  let codeBuf: string[] = [];
  let listType: "ol" | "ul" | null = null;
  let paraBuf: string[] = [];

  const flushPara = () => {
    if (paraBuf.length) {
      out.push(`<p>${renderInline(paraBuf.join(" "))}</p>`);
      paraBuf = [];
    }
  };
  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCode) {
        out.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        flushPara();
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(line);
      continue;
    }

    const olMatch = line.match(/^\s*\d+\.\s+(.+)$/);
    const ulMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (olMatch || ulMatch) {
      flushPara();
      const want: "ol" | "ul" = olMatch ? "ol" : "ul";
      if (listType !== want) {
        closeList();
        out.push(`<${want}>`);
        listType = want;
      }
      const content = (olMatch ?? ulMatch)![1];
      out.push(`<li>${renderInline(content)}</li>`);
      continue;
    }

    if (line.trim() === "") {
      flushPara();
      closeList();
      continue;
    }

    paraBuf.push(line);
  }

  flushPara();
  closeList();
  if (inCode) out.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
  return out.join("\n");
}
