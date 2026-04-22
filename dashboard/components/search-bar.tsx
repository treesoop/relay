"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";

export function SearchBar({
  initialQuery = "",
  placeholder = "ask the commons…",
  size = "lg",
}: {
  initialQuery?: string;
  placeholder?: string;
  size?: "lg" | "md";
}) {
  const [q, setQ] = useState(initialQuery);
  const [isPending, startTransition] = useTransition();
  const router = useRouter();
  const searchParams = useSearchParams();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = q.trim();
    if (!trimmed) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set("q", trimmed);
    startTransition(() => {
      router.push(`/skills?${params.toString()}`);
    });
  };

  const isLg = size === "lg";

  return (
    <form onSubmit={submit} className="w-full group">
      <div
        className="flex items-center gap-4 border-b-2 border-[var(--color-ink)] focus-within:border-[var(--color-accent)] transition-colors"
      >
        <span
          className={`label shrink-0 ${isLg ? "pl-1" : ""}`}
          style={{ color: "var(--color-accent)" }}
        >
          /search
        </span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder}
          className={`flex-1 bg-transparent outline-none py-3 placeholder:text-[var(--color-ink-faint)] ${
            isLg ? "display text-3xl md:text-4xl leading-tight" : "text-base"
          }`}
          type="text"
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="submit"
          disabled={isPending}
          className={`label shrink-0 px-2 py-1 hover:text-[var(--color-accent)] transition-colors disabled:opacity-50`}
        >
          {isPending ? "searching" : "↵"}
        </button>
      </div>
    </form>
  );
}
