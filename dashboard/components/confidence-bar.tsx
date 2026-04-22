/**
 * Thin horizontal bar showing the server-calculated confidence for a skill.
 * No gradient, no color shift — a single ink fill against a rule.
 * The accent color only shows up when confidence is high enough to bet on.
 */
export function ConfidenceBar({
  confidence,
  showLabel = false,
}: {
  confidence: number;
  showLabel?: boolean;
}) {
  const pct = Math.max(0, Math.min(1, confidence));
  const hi = pct >= 0.7;
  return (
    <div className="flex items-center gap-3 w-full">
      <div
        className="relative flex-1 h-[2px] bg-[var(--color-rule)]"
        aria-label={`Confidence ${Math.round(pct * 100)}%`}
      >
        <div
          className="absolute inset-y-0 left-0"
          style={{
            width: `${pct * 100}%`,
            background: hi ? "var(--color-accent)" : "var(--color-ink-soft)",
          }}
        />
      </div>
      {showLabel && (
        <span className="mono text-xs text-[var(--color-ink-soft)] tabular-nums">
          {Math.round(pct * 100)}
        </span>
      )}
    </div>
  );
}
