from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.validators import validate_sources_config

router = APIRouter()

_BACKEND_DIR = Path(__file__).resolve().parents[3]


class Source(BaseModel):
    name: str
    url: str
    tier: str
    feed_urls: List[str] = []
    sitemap_urls: List[str] = []
    enabled: bool


def _sources_yaml_path() -> Path:
    env_path = os.getenv("SAAF_SOURCES_YAML")
    return Path(env_path) if env_path else (_BACKEND_DIR / "config" / "sources.yaml")


@router.get("/sources", response_model=list[Source])
def list_sources() -> list[Source]:
    data = yaml.safe_load(_sources_yaml_path().read_text(encoding="utf-8"))
    verdict = validate_sources_config(data)
    if not verdict["valid"]:
        # FastAPI will render this as a 500; config should be valid in prod.
        raise RuntimeError(f"Invalid sources config: {verdict['errors']}")

    sources: Dict[str, Any] = (data.get("sources") or {}).copy()
    out: list[Source] = []
    for name, spec in sources.items():
        out.append(
            Source(
                name=name,
                url=str(spec.get("url", "")),
                tier=str(spec.get("tier", "B")).upper(),
                feed_urls=[str(u) for u in (spec.get("feed_urls") or [])],
                sitemap_urls=[str(u) for u in (spec.get("sitemap_urls") or [])],
                enabled=bool(spec.get("enabled", False)),
            )
        )
    return sorted(out, key=lambda s: s.name)

