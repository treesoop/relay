import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-32 text-center">
      <div className="label mb-6">404 · no such entry</div>
      <h1 className="display text-5xl md:text-7xl leading-tight mb-8">
        Not in the commons.
      </h1>
      <p className="text-[var(--color-ink-soft)] mb-10">
        The skill you asked for doesn&apos;t exist — it may have been retired, or the
        id may be misspelled.
      </p>
      <Link
        href="/skills"
        className="label border-b border-[var(--color-ink)] pb-1 hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-colors"
      >
        browse what&apos;s there →
      </Link>
    </div>
  );
}
