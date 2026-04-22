import type { Attempt } from "@/lib/api";

/**
 * Vertical case-file view of what the agent tried.
 * Failures get strikethrough text + an explanatory "failed because" note.
 * The winning attempt is flagged with an accent rule and a bold marker.
 */
export function AttemptsTimeline({ attempts }: { attempts: Attempt[] }) {
  if (!attempts || attempts.length === 0) {
    return (
      <p className="text-sm text-[var(--color-ink-faint)] italic">
        No attempts recorded for this skill.
      </p>
    );
  }

  return (
    <ol className="relative pl-8 border-l border-[var(--color-rule)]">
      {attempts.map((a, i) => {
        const worked = !!a.worked;
        return (
          <li
            key={i}
            className="relative pb-7 last:pb-0"
            style={{ marginTop: i === 0 ? 0 : undefined }}
          >
            {/* node on the spine */}
            <span
              className="absolute -left-[33px] top-[7px] w-[10px] h-[10px] rounded-full"
              style={{
                background: worked ? "var(--color-success)" : "var(--color-fail)",
                boxShadow: `0 0 0 4px var(--color-paper)`,
              }}
            />
            {worked ? (
              <div>
                <div
                  className="label mb-1"
                  style={{ color: "var(--color-success)" }}
                >
                  What worked
                </div>
                <p className="display text-xl leading-tight">
                  {a.worked}
                </p>
              </div>
            ) : (
              <div>
                <div
                  className="label mb-1"
                  style={{ color: "var(--color-fail)" }}
                >
                  Attempt {i + 1} · failed
                </div>
                <p className="text-base leading-snug line-through decoration-[var(--color-fail)] decoration-1 text-[var(--color-ink-soft)]">
                  {a.tried}
                </p>
                {a.failed_because && (
                  <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
                    <span className="mono text-xs" style={{ color: "var(--color-fail)" }}>
                      ↳{" "}
                    </span>
                    {a.failed_because}
                  </p>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
