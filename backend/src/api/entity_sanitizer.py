from __future__ import annotations

import re
from typing import Any, Sequence

from src.api.dtos import EntityDTO

MAX_CONFIRMED_FACTS = 8
MAX_DEBATED_CLAIMS = 12
MAX_ENTITY_TEXT_LENGTH = 140

_WHITESPACE_RE = re.compile(r"\s+")
_URL_PREFIX_RE = re.compile(r"^https?://", re.IGNORECASE)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_DATE_DURATION_RE = re.compile(r"^\d+\s+(?:day|days|month|months|year|years)$")

_LOW_SIGNAL_DATES = {
    "today",
    "yesterday",
    "tomorrow",
    "daily",
    "weekly",
    "monthly",
    "last year",
    "this year",
    "earlier this year",
    "earlier this month",
    "later this year",
    "a day",
    "a month",
    "a year",
    "one day",
    "one month",
    "one year",
    "four-day",
}
_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
_MONTHS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}


def _normalize_text(text: str, max_length: int = MAX_ENTITY_TEXT_LENGTH) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", (text or "").strip())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 1].rstrip()}…"


def _should_skip_entity(text: str, entity_type: str) -> bool:
    lowered = text.lower().strip().strip("'")

    if "comments comments" in lowered:
        return True

    if entity_type != "DATE":
        return False

    if lowered in _LOW_SIGNAL_DATES or lowered in _WEEKDAYS or lowered in _MONTHS:
        return True
    if _YEAR_RE.match(lowered) or _DATE_DURATION_RE.match(lowered):
        return True
    if lowered.startswith(("a ", "an ", "the ", "last ", "next ", "earlier ", "later ")) and any(
        token in lowered for token in ("day", "month", "year")
    ):
        return True

    return False


def to_entity_dtos(entities: Sequence[Any] | None, limit: int) -> list[EntityDTO]:
    dto_rows: list[EntityDTO] = []
    for entity in entities or []:
        if hasattr(entity, "model_dump"):
            raw = entity.model_dump()
        elif isinstance(entity, dict):
            raw = entity
        else:
            continue

        text = _normalize_text(str(raw.get("text", "")))
        if len(text) < 2:
            continue
        if _URL_PREFIX_RE.match(text):
            continue

        entity_type = str(raw.get("type", "MISC"))
        if _should_skip_entity(text, entity_type):
            continue
        try:
            sources = max(int(raw.get("sources", 1)), 1)
        except Exception:
            sources = 1

        dto_rows.append(EntityDTO(text=text, type=entity_type, sources=sources))

    dto_rows.sort(key=lambda row: (-row.sources, row.type, row.text.lower()))
    return dto_rows[:limit]
