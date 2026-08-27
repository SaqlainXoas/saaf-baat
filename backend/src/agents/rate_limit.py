"""
Shared rate-limit handling for the Gemini-backed agents.

Phase 1 found that `embed()` matched `"resource exhausted"` while the API
actually says `RESOURCE_EXHAUSTED`, so real 429s were raised as generic
failures and skipped the retry path entirely. That fix lives here now rather
than in one module, because triage and adjudication hit the same quota with
the same error shape.
"""

from __future__ import annotations

import re

# The API is not consistent about casing or wording, and a miss here costs a
# whole run's worth of work, so the match is deliberately broad.
_RATE_LIMIT_MARKERS = (
    "resource exhausted",
    "resource_exhausted",
    "rate limit",
    "quota",
    "429",
)


def is_rate_limit_message(message: str) -> bool:
    """True when an error message describes a quota or rate-limit refusal."""
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


def retry_after_seconds(message: str) -> float | None:
    """Pull the server's own retry hint out of a rate-limit message."""
    match = re.search(r"[Pp]lease retry in ([0-9.]+)s", message or "")
    if not match:
        match = re.search(r"'retryDelay': '(\d+)s'", message or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


__all__ = ["is_rate_limit_message", "retry_after_seconds"]
