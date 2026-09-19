"""
Shared rate-limit handling for the Gemini-backed agents.

Phase 1 found that `embed()` matched `"resource exhausted"` while the API
actually says `RESOURCE_EXHAUSTED`, so real 429s were raised as generic
failures and skipped the retry path entirely. That fix lives here now rather
than in one module, because triage and adjudication hit the same quota with
the same error shape.
"""

from __future__ import annotations

import random
import re
from typing import Callable

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


# A server saying "try again" in a different way. These are not quota refusals
# and carry no retry hint, but they are just as temporary - and treating one as
# fatal cost the 2026-09-14 brief two of its cards, because a single 503 on the
# editor's second pass abandoned every remaining attempt.
_TRANSIENT_MARKERS = (
    "unavailable",
    "503",
    "500",
    "internal error",
    "internal server",
    "deadline exceeded",
    "timed out",
    "timeout",
    "overloaded",
    "try again",
)


def is_transient_message(message: str) -> bool:
    """True when an error describes a temporary server-side failure."""
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


def is_retryable_message(message: str) -> bool:
    """True when the request is worth sending again, for either reason."""
    return is_rate_limit_message(message) or is_transient_message(message)


# A busy server needs longer than a quota window. On 2026-09-19 triage got two
# 503s at 06:03-06:04 and the same model answered 200 by 06:04:53, so the
# schedule has to span about a minute - 2s/4s/8s gives up before it recovers.
_RATE_LIMIT_BACKOFF = (2.0, 4.0, 8.0, 16.0)
_TRANSIENT_BACKOFF = (5.0, 15.0, 30.0, 60.0)


def retry_delay_seconds(
    message: str,
    attempt: int,
    jitter: Callable[[float, float], float] = random.uniform,
) -> float:
    """How long to wait before retry number `attempt` (0-based).

    The server's own hint wins. Otherwise a quota refusal backs off briefly and
    anything else backs off on the longer transient schedule. Jitter keeps
    batches that failed together from all retrying in the same second.
    """
    hint = retry_after_seconds(message)
    if hint is not None:
        return hint
    if is_rate_limit_message(message):
        schedule, spread = _RATE_LIMIT_BACKOFF, 2.0
    else:
        schedule, spread = _TRANSIENT_BACKOFF, 3.0
    base = schedule[min(max(0, attempt), len(schedule) - 1)]
    return base + jitter(0.0, spread)


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


__all__ = [
    "is_rate_limit_message",
    "is_retryable_message",
    "is_transient_message",
    "retry_after_seconds",
    "retry_delay_seconds",
]
