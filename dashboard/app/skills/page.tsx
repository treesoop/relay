import { listSkills, search } from "@/lib/api";
import { SkillCard } from "@/components/skill-card";
import { SearchBar } from "@/components/search-bar";
import { Suspense } from "react";

export default async function SkillsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();

  const items = query ? await search(query, 30) : await listSkills(60);

  return (
    <div className="max-w-7xl mx-auto px-6 md:px-10 pb-20">
      {/* --- header --- */}
      <section className="pt-12 md:pt-16 pb-10">
        <div className="label mb-6">
          {query ? "results" : "archive"} · {items.length} {items.length === 1 ? "entry" : "entries"}
        </div>
        <h1 className="display text-4xl md:text-5xl tracking-tight mb-10">
          {query ? (
            <>
              <span className="text-[var(--color-ink-soft)] italic">re: </span>
              {query}
            </>
          ) : (
            "Browse the commons"
          )}
        </h1>
        <div className="max-w-3xl">
          <Suspense>
            <SearchBar
              initialQuery={query}
              placeholder={query ? query : "describe the symptom…"}
              size="md"
            />
          </Suspense>
        </div>
      </section>

      {/* --- results --- */}
      <section className="border-t border-[var(--color-rule)] pt-10">
        {items.length === 0 ? (
          <div className="py-24 text-center">
            <p className="display text-2xl text-[var(--color-ink-soft)] italic mb-3">
              Nothing in the commons matches yet.
            </p>
            <p className="label">try another query, or capture the first skill yourself</p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((it, i) => (
              <SkillCard key={it.skill.id} skill={it.skill} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export const revalidate = 60;
