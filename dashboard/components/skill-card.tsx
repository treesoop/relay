import Link from "next/link";
import type { Skill } from "@/lib/api";
import { ConfidenceBar } from "./confidence-bar";

export function SkillCard({ skill, index = 0 }: { skill: Skill; index?: number }) {
  const sym = skill.metadata.problem?.symptom ?? "";
  const langs = skill.metadata.context?.languages ?? [];
  return (
    <Link
      href={`/skills/${skill.id}`}
      className="group block border border-[var(--color-rule)] bg-[var(--color-paper)] hover:bg-[var(--color-paper-deep)] transition-colors p-7 enter"
      style={{ animationDelay: `${Math.min(index * 40, 600)}ms` }}
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <h3 className="display text-2xl leading-[1.05] flex-1 group-hover:text-[var(--color-accent)] transition-colors">
          {skill.name}
        </h3>
        <span className="mono text-[10px] tabular-nums text-[var(--color-ink-faint)] shrink-0">
          {skill.id.slice(0, 10)}…
        </span>
      </div>
      {sym && (
        <p className="text-sm text-[var(--color-ink-soft)] leading-relaxed mb-6 line-clamp-3">
          {sym}
        </p>
      )}
      <div className="flex items-center justify-between gap-4 pt-4 border-t border-[var(--color-rule)]">
        <ConfidenceBar confidence={skill.confidence} showLabel />
        <div className="flex items-center gap-3 label shrink-0">
          <span>
            {skill.good_count}↑ {skill.bad_count}↓
          </span>
          {langs[0] && <span className="hidden sm:inline">· {langs[0]}</span>}
        </div>
      </div>
    </Link>
  );
}
