import type { Metadata } from "next";
import Link from "next/link";
import { fraunces, plexSans, jetbrainsMono } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "Relay — Shared skill memory for coding agents",
  description:
    "Browse the Relay commons — skills captured in-session by Claude Code agents, with the failure log preserved.",
  openGraph: {
    title: "Relay",
    description: "Shared skill memory for coding agents.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const fontClasses = `${fraunces.variable} ${plexSans.variable} ${jetbrainsMono.variable}`;
  return (
    <html lang="en" className={`h-full ${fontClasses}`}>
      <body className="min-h-screen">
        <header className="border-b border-[var(--color-rule)]">
          <div className="max-w-7xl mx-auto px-6 md:px-10 h-16 flex items-center justify-between">
            <Link href="/" className="flex items-baseline gap-3">
              <span className="display text-2xl tracking-tight">Relay</span>
              <span className="label hidden md:inline">the commons</span>
            </Link>
            <nav className="flex items-center gap-6">
              <Link href="/skills" className="label hover:text-[var(--color-ink)] transition-colors">
                browse
              </Link>
              <a
                href="https://github.com/treesoop/relay"
                className="label hover:text-[var(--color-ink)] transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                github ↗
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-[var(--color-rule)] mt-24">
          <div className="max-w-7xl mx-auto px-6 md:px-10 py-10 flex flex-col md:flex-row justify-between gap-4 text-sm">
            <div className="label">
              Relay · shared skill memory for coding agents
            </div>
            <div className="flex gap-6 label">
              <Link href="/" className="hover:text-[var(--color-ink)] transition-colors">
                home
              </Link>
              <Link href="/skills" className="hover:text-[var(--color-ink)] transition-colors">
                browse
              </Link>
              <a
                href="https://github.com/treesoop/relay"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-[var(--color-ink)] transition-colors"
              >
                source
              </a>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
