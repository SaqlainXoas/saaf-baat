from __future__ import annotations

import re
from typing import Any, Sequence

from src.api.dtos import EntityDTO

MAX_CONFIRMED_FACTS = 8
MAX_DEBATED_CLAIMS = 12
MAX_ENTITY_TEXT_LENGTH = 140

_WHITESPACE_RE = re.compile(r"\s+")
_URL_PREFIX_RE = re.compile(r"^https?://", re.IGNORECASE)


def _normalize_text(text: str, max_length: int = MAX_ENTITY_TEXT_LENGTH) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", (text or "").strip())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 1].rstrip()}…"


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
        try:
            sources = max(int(raw.get("sources", 1)), 1)
        except Exception:
            sources = 1

        dto_rows.append(EntityDTO(text=text, type=entity_type, sources=sources))

    dto_rows.sort(key=lambda row: (-row.sources, row.type, row.text.lower()))
    return dto_rows[:limit]
