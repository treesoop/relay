from __future__ import annotations

import re

# Order matters: more specific patterns first so generic ones don't swallow them.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"), "[REDACTED:api_key]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws_key]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "[REDACTED:github_token]"),
    (re.compile(r"(?<![A-Za-z0-9._+-])[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED:email]"),
    (re.compile(r"(?<=[?&])(?:token|access_token|api_key|apikey)=[A-Za-z0-9._\-]{16,}"), "[REDACTED:token]"),
]


def mask_pii(text: str) -> str:
    """Apply PII regex masks. Idempotent — running on already-masked text is a no-op."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
