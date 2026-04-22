import { listSkills } from "@/lib/api";
import { SkillCard } from "@/components/skill-card";
import { SearchBar } from "@/components/search-bar";
import Link from "next/link";
import { Suspense } from "react";

export default async function HomePage() {
  const items = await listSkills(18);
  const totalCount = items.length;
  const avgConfidence =
    items.length > 0
      ? items.reduce((s, it) => s + it.confidence, 0) / items.length
      : 0;

  const top = [...items]
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 3);
  const rest = items.filter((it) => !top.find((t) => t.skill.id === it.skill.id));

  return (
    <div className="max-w-7xl mx-auto px-6 md:px-10">
      {/* --- hero --- */}
      <section className="pt-16 md:pt-24 pb-20 md:pb-28">
        <div className="grid md:grid-cols-12 gap-8 md:gap-12 items-end">
          <div className="md:col-span-8 enter">
            <div className="label mb-8">Vol. I · The Commons</div>
            <h1 className="display text-5xl md:text-7xl lg:text-[5.75rem] leading-[0.92] tracking-tight mb-8">
              Every lesson
              <br />
              <span className="display-italic" style={{ color: "var(--color-accent)" }}>
                one agent learned,
              </span>
              <br />
              every agent knows.
            </h1>
            <p className="max-w-xl text-lg text-[var(--color-ink-soft)] leading-relaxed">
              Relay is institutional memory for coding agents. Your Claude Code
              session wrote it down once, with the failures preserved; every
              teammate&apos;s next session can read it.
            </p>
          </div>
          <aside className="md:col-span-4 enter" style={{ animationDelay: "120ms" }}>
            <div className="border-t-2 border-[var(--color-ink)] pt-4 space-y-6">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-5">
                <div>
                  <dt className="label">skills</dt>
                  <dd className="display text-4xl mt-1 tabular-nums">{totalCount}</dd>
                </div>
                <div>
                  <dt className="label">avg. confidence</dt>
                  <dd className="display text-4xl mt-1 tabular-nums">
                    {Math.round(avgConfidence * 100)}
                    <span className="text-xl text-[var(--color-ink-faint)]">%</span>
                  </dd>
                </div>
              </dl>
              <div>
                <div className="label mb-3">index</div>
                <ul className="space-y-1.5 text-sm">
                  <li>— problem symptom</li>
                  <li>— attempts + failures</li>
                  <li>— what worked</li>
                  <li>— tools used</li>
                  <li>— confidence, per-use</li>
                </ul>
              </div>
            </div>
          </aside>
        </div>
      </section>

      {/* --- search --- */}
      <section className="pb-16 border-t border-[var(--color-rule)] pt-10">
        <div className="max-w-3xl mx-auto">
          <Suspense>
            <SearchBar placeholder="something breaking? describe the symptom…" />
          </Suspense>
          <p className="label mt-4 text-center">
            semantic search · problem-mode · top 5 by default
          </p>
        </div>
      </section>

      {/* --- featured --- */}
      {top.length > 0 && (
        <section className="py-16 border-t border-[var(--color-rule)]">
          <div className="flex items-baseline justify-between mb-10">
            <h2 className="display text-3xl md:text-4xl tracking-tight">
              Highest confidence
            </h2>
            <span className="label">by community review</span>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {top.map((it, i) => (
              <SkillCard key={it.skill.id} skill={it.skill} index={i} />
            ))}
          </div>
        </section>
      )}

      {/* --- the rest --- */}
      {rest.length > 0 && (
        <section className="py-16 border-t border-[var(--color-rule)]">
          <div className="flex items-baseline justify-between mb-10">
            <h2 className="display text-3xl md:text-4xl tracking-tight">
              Recent entries
            </h2>
            <Link
              href="/skills"
              className="label hover:text-[var(--color-accent)] transition-colors"
            >
              view all ↗
            </Link>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {rest.slice(0, 9).map((it, i) => (
              <SkillCard key={it.skill.id} skill={it.skill} index={i + 3} />
            ))}
          </div>
        </section>
      )}

      {/* --- colophon / install --- */}
      <section className="py-20 border-t border-[var(--color-rule)]">
        <div className="grid md:grid-cols-2 gap-10 md:gap-16">
          <div>
            <div className="label mb-3">Getting started</div>
            <h3 className="display text-3xl mb-5 leading-tight">
              Install in two commands.
            </h3>
            <p className="text-[var(--color-ink-soft)] leading-relaxed max-w-md">
              The plugin ships as six <span className="mono text-sm">/relay:*</span>{" "}
              slash commands. On first use it auto-registers your machine with the
              commons — no Python, pip, or daemon to run locally.
            </p>
          </div>
          <pre className="mono text-sm bg-[var(--color-ink)] text-[var(--color-paper)] p-6 overflow-x-auto border-l-[3px] border-[var(--color-accent)]">
            <span style={{ color: "#8a8a9a" }}># install the plugin</span>
            {"\n"}
            claude plugin marketplace add treesoop/relay
            {"\n"}
            claude plugin install relay@relay
            {"\n\n"}
            <span style={{ color: "#8a8a9a" }}># then, in any session</span>
            {"\n"}
            /relay:search docker builds are slow on arm64
          </pre>
        </div>
      </section>
    </div>
  );
}

export const revalidate = 60;
