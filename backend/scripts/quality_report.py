from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from uuid import UUID

import numpy as np
from dotenv import load_dotenv

# Allow running as a script from `backend/` (or repo root) without `python -m ...`.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
load_dotenv(_BACKEND_ROOT / ".env")

from src.agents.clustering import calculate_centroid, calculate_intra_cluster_similarity
from src.db.client import SupabaseClient


@dataclass(frozen=True)
class ClusterQuality:
    cluster_id: UUID
    articles: int
    sources: int
    avg_similarity: Optional[float]
    min_to_centroid: Optional[float]


def _norm_rows(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.where(norms <= 0, 1.0, norms)
    return x / norms


def _embedding_matrix(rows: Iterable[object]) -> Optional[np.ndarray]:
    vecs: List[np.ndarray] = []
    for a in rows:
        emb = getattr(a, "embedding", None)
        if emb is None:
            return None
        v = np.asarray(emb, dtype=np.float32)
        if v.ndim != 1 or v.size == 0:
            return None
        vecs.append(v)
    if not vecs:
        return None
    return _norm_rows(np.vstack(vecs))


def compute_cluster_quality(db: SupabaseClient, cluster_id: UUID) -> ClusterQuality:
    cluster = db.get_cluster_by_id(cluster_id)
    articles = db.get_articles_by_ids(cluster.article_ids)
    sources = len({a.source for a in articles})

    mat = _embedding_matrix(articles)
    if mat is None:
        return ClusterQuality(
            cluster_id=cluster_id,
            articles=len(articles),
            sources=sources,
            avg_similarity=None,
            min_to_centroid=None,
        )

    centroid = calculate_centroid(mat)
    sims = (mat @ centroid).astype(np.float32)
    avg_sim = float(calculate_intra_cluster_similarity(mat))
    min_sim = float(np.min(sims)) if len(sims) else None

    return ClusterQuality(
        cluster_id=cluster_id,
        articles=len(articles),
        sources=sources,
        avg_similarity=avg_sim,
        min_to_centroid=min_sim,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Saaf Baat feed quality report (DB-backed)")
    parser.add_argument("--limit", type=int, default=20, help="Number of latest stories to inspect")
    parser.add_argument("--min-avg-sim", type=float, default=0.65)
    parser.add_argument("--min-centroid-sim", type=float, default=0.70)
    parser.add_argument("--fail-on-missing-embeddings", action="store_true")
    args = parser.parse_args(argv)

    db = SupabaseClient()
    feeds = db.get_analyzed_feed(limit=max(1, int(args.limit)))

    bad = 0
    for feed in feeds:
        q = compute_cluster_quality(db, feed.cluster_id)
        head = (feed.headline or "").replace("\n", " ").strip()
        head = head[:120] + ("…" if len(head) > 120 else "")

        if q.avg_similarity is None or q.min_to_centroid is None:
            missing = "missing_embeddings"
            print(f"{q.cluster_id} articles={q.articles} sources={q.sources} {missing} {head}")
            if args.fail_on_missing_embeddings:
                bad += 1
            continue

        print(
            f"{q.cluster_id} articles={q.articles} sources={q.sources} "
            f"avg_sim={q.avg_similarity:.3f} min_centroid_sim={q.min_to_centroid:.3f} {head}"
        )

        if q.avg_similarity < float(args.min_avg_sim) or q.min_to_centroid < float(args.min_centroid_sim):
            bad += 1

    if bad:
        print(f"\nFAIL: {bad} clusters below thresholds", file=sys.stderr)
        return 2

    print("\nOK: all checked clusters meet thresholds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
