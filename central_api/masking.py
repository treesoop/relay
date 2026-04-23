from __future__ import annotations

import re

# Order matters: more specific patterns first so generic ones don't swallow them.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ----- credentials -----
    (re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"), "[REDACTED:api_key]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws_key]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "[REDACTED:github_token]"),
    (re.compile(r"(?<![A-Za-z0-9._+-])[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED:email]"),
    (re.compile(r"(?<=[?&])(?:token|access_token|api_key|apikey)=[A-Za-z0-9._\-]{16,}"), "[REDACTED:token]"),

    # ----- machine identity / internal infra -----
    # Absolute home paths — leak the user's login name + project structure.
    (re.compile(r"/Users/[^/\s]+(?=/|\s|$)"), "[REDACTED:path]"),
    (re.compile(r"/home/[^/\s]+(?=/|\s|$)"), "[REDACTED:path]"),
    (re.compile(r"[Cc]:\\Users\\[^\\\s]+"), "[REDACTED:path]"),

    # RFC1918 private IPs — leak internal network topology.
    (re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[REDACTED:private_ip]"),
    (re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"), "[REDACTED:private_ip]"),
    (re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"), "[REDACTED:private_ip]"),

    # Common internal TLDs — corp hostnames leak project/tenant names.
    (re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:internal|corp|lan)\b", re.IGNORECASE), "[REDACTED:internal_host]"),

    # AWS 12-digit account id inside an ARN — match the whole ARN prefix then rebuild with the redacted id.
    (re.compile(r"(arn:aws:[a-z0-9-]{1,20}:[a-z0-9-]{0,20}:)\d{12}"), r"\1[REDACTED:aws_acct]"),
]


def mask_pii(text: str) -> str:
    """Apply PII regex masks. Idempotent — running on already-masked text is a no-op."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
