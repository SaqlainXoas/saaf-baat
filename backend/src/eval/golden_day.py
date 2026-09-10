"""
Replay a recorded news day through the real pipeline.

A golden day is a directory holding the raw feed and sitemap payloads exactly
as the publishers served them, the embedding vectors that were recorded for
those articles, and a hand-written statement of what the brief should have
contained. Replaying it exercises the real parse, gate, dedup, grouping and
selection code with no network and no API keys.

Two details make the replay honest:

* **The gate sees the captured clock.** Feeds are read with `now` set to the
  capture time, so freshness behaves as it did on the day rather than
  quarantining the entire fixture as stale.
* **The pipeline sees today.** Every article timestamp is then shifted forward
  by the same delta, because clustering windows, publish-date trust and
  retention are all written against `datetime.now()`. Relative spacing between
  articles is preserved exactly.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import yaml

from src.db.factory import create_db_client
from src.eval.scoring import BriefCard, GoldenDayReport, score_brief
from src.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator, PipelineStats
from src.scrapers.feeds import FeedIngestor, IngestResult, SourceSpec

logger = logging.getLogger(__name__)

GOLDEN_DAYS_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "golden_days"

MANIFEST = "manifest.json"
EXPECTED = "expected.yaml"
SOURCES = "sources.yaml"
EMBEDDINGS = "embeddings.npz"
TRIAGE = "triage.json"
ADJUDICATION = "adjudication.json"
ENDPOINTS_DIR = "endpoints"


def read_payload(path: Path) -> bytes:
    """Read a captured endpoint payload, gzipped or not."""
    data = path.read_bytes()
    if path.suffix == ".gz":
        return gzip.decompress(data)
    return data


def embedding_key(headline: str, main_text: str) -> str:
    """
    Key a recorded vector by the text the pipeline will actually embed.

    Must stay in step with `PipelineOrchestrator.embed_articles`.
    """
    return f"{headline}. {main_text[:500]}"


@dataclass
class RecordedEmbedder:
    """Serves the vectors captured on the day; never calls the API."""

    vectors: Dict[str, np.ndarray]
    dimension: int = 768
    misses: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.misses is None:
            self.misses = []

    def _vector(self, text: str) -> np.ndarray:
        recorded = self.vectors.get(text)
        if recorded is not None:
            return recorded
        # A text that was not captured (e.g. a lazily fetched body) still has to
        # produce a stable vector, so the replay stays deterministic. It is
        # recorded as a miss so the harness can report drift.
        self.misses.append(text[:80])
        seed = abs(hash(text)) % (2**32)
        vector = np.random.default_rng(seed).normal(size=self.dimension).astype(np.float32)
        return vector / np.linalg.norm(vector)

    def embed_batch(self, texts: Sequence[str], batch_size: int = 100) -> Any:
        matrix = np.vstack([self._vector(text) for text in texts]).astype(np.float32)
        return _EmbedResult(embeddings=matrix, model="recorded", texts_count=len(texts))

    def embed(self, texts: Sequence[str]) -> Any:
        return self.embed_batch(texts)



@dataclass
class RecordedTriage:
    """
    Serves the triage verdicts captured on the day; never calls the API.

    Keyed by canonical URL rather than article id, because ids are minted
    fresh on every replay. An article with no recorded verdict is reported as
    a miss and left untriaged, exactly as a live triage failure would be —
    the replay must not invent a verdict the real pipeline would not have.
    """

    verdicts: Dict[str, Dict[str, Any]]
    misses: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.misses is None:
            self.misses = []

    def triage(self, items: Sequence[Any]) -> Any:
        from src.agents.triage import TriageResult, TriageVerdict

        resolved: Dict[str, TriageVerdict] = {}
        missing: List[str] = []
        for item in items:
            recorded = self.verdicts.get(item.url) or self.verdicts.get(item.key)
            if not recorded:
                self.misses.append(item.headline[:80])
                missing.append(item.key)
                continue
            try:
                resolved[item.key] = TriageVerdict(key=item.key, **recorded)
            except Exception:
                self.misses.append(item.headline[:80])
                missing.append(item.key)
        return TriageResult(
            verdicts=resolved,
            calls=1 if items else 0,
            failures=len(missing),
            missing_keys=missing,
        )



@dataclass
class RecordedAdjudicator:
    """
    Serves the adjudication verdicts captured on the day.

    Keyed by the sorted pair of canonical URLs, because article indices depend
    on ingest ordering and would not survive a replay. A pair with no recorded
    verdict is left undecided, so the deterministic grouping stands — the same
    thing a live adjudication outage produces.
    """

    verdicts: Dict[str, bool]
    misses: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.misses is None:
            self.misses = []

    @staticmethod
    def pair_key(left_url: str, right_url: str) -> str:
        return "\u241f".join(sorted((left_url, right_url)))

    def adjudicate(self, pairs: Sequence[Any]) -> Any:
        from src.agents.adjudication import AdjudicationResult

        verdicts: Dict[tuple, bool] = {}
        misses = 0
        for pair in pairs:
            recorded = self.verdicts.get(self.pair_key(pair.left_url, pair.right_url))
            if recorded is None:
                self.misses.append(f"{pair.left_headline[:40]} ~ {pair.right_headline[:40]}")
                misses += 1
                continue
            verdicts[pair.key] = bool(recorded)
        return AdjudicationResult(verdicts=verdicts, calls=1 if pairs else 0, failures=misses)


@dataclass
class _EmbedResult:
    embeddings: np.ndarray
    model: str
    texts_count: int

    @property
    def dimension(self) -> int:
        return int(self.embeddings.shape[1])


@dataclass(frozen=True)
class GoldenDay:
    path: Path
    captured_at: datetime
    sources_config: Dict[str, Any]
    endpoints: Dict[str, Dict[str, Any]]
    expectations: Dict[str, Any]
    embeddings: Dict[str, np.ndarray]
    triage_verdicts: Dict[str, Dict[str, Any]]
    adjudication_verdicts: Dict[str, bool]
    max_articles_per_source: Optional[int]

    @property
    def name(self) -> str:
        return self.path.name

    @classmethod
    def load(cls, path: Path | str) -> "GoldenDay":
        path = Path(path)
        manifest = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
        sources_config = yaml.safe_load((path / SOURCES).read_text(encoding="utf-8"))
        expectations = yaml.safe_load((path / EXPECTED).read_text(encoding="utf-8")) or {}

        vectors: Dict[str, np.ndarray] = {}
        embeddings_path = path / EMBEDDINGS
        if embeddings_path.exists():
            payload = np.load(embeddings_path, allow_pickle=False)
            for key, vector in zip(payload["keys"].tolist(), payload["vectors"]):
                vectors[str(key)] = vector.astype(np.float32)

        triage_verdicts: Dict[str, Dict[str, Any]] = {}
        triage_path = path / TRIAGE
        if triage_path.exists():
            triage_verdicts = json.loads(triage_path.read_text(encoding="utf-8"))

        adjudication_verdicts: Dict[str, bool] = {}
        adjudication_path = path / ADJUDICATION
        if adjudication_path.exists():
            adjudication_verdicts = json.loads(adjudication_path.read_text(encoding="utf-8"))

        captured_at = datetime.fromisoformat(str(manifest["captured_at"]).replace("Z", "+00:00"))
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)

        return cls(
            path=path,
            captured_at=captured_at,
            sources_config=sources_config,
            endpoints=dict(manifest.get("endpoints") or {}),
            expectations=expectations,
            embeddings=vectors,
            triage_verdicts=triage_verdicts,
            adjudication_verdicts=adjudication_verdicts,
            max_articles_per_source=manifest.get("max_articles_per_source"),
        )

    def fetcher(self) -> Callable[[str], tuple[int, bytes]]:
        """Serve the captured payloads; anything unrecorded is a 404."""
        base = self.path / ENDPOINTS_DIR

        def fetch(url: str) -> tuple[int, bytes]:
            record = self.endpoints.get(url)
            if record is None:
                return 404, b""
            status = int(record.get("status", 200))
            filename = record.get("file")
            if not filename:
                return status, b""
            return status, read_payload(base / str(filename))

        return fetch

    def embedder(self) -> RecordedEmbedder:
        return RecordedEmbedder(vectors=dict(self.embeddings))

    def triager(self) -> RecordedTriage:
        return RecordedTriage(verdicts=dict(self.triage_verdicts))

    def adjudicator(self) -> RecordedAdjudicator:
        return RecordedAdjudicator(verdicts=dict(self.adjudication_verdicts))


class ReplayIngestor:
    """A FeedIngestor bound to a recorded day, with timestamps shifted to now."""

    def __init__(self, day: GoldenDay, *, now: Optional[datetime] = None):
        self.day = day
        self.now = now or datetime.now(timezone.utc)
        self.shift = self.now - day.captured_at

    def run(self) -> IngestResult:
        result = FeedIngestor(
            SourceSpec.from_config(self.day.sources_config),
            fetcher=self.day.fetcher(),
            now=lambda: self.day.captured_at,
            max_articles_per_source=self.day.max_articles_per_source,
        ).run()

        for article in result.articles:
            if article.publish_date is not None:
                published = article.publish_date
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                article.publish_date = published + self.shift
            article.scraped_at = self.now
        return result


# Two reports of the same event embed at 0.95-0.97 on this corpus; two
# different events in the same domain sit near 0.82. 0.93 is inside that gap,
# so a linkage at 0.93 recovers "distinct events" independently of whatever
# thresholds the grouper was run with - which is the point: the reference must
# not move when the thing being measured moves.
EVENT_LINKAGE = 0.93


@dataclass(frozen=True)
class ClusterQuality:
    """How many articles the grouper put in the wrong group.

    Added 2026-08-25, after a live cluster was found holding four unrelated
    events - Imran Khan's hospital transfer, the Munir visit to Iran, a PM
    meeting and a Turkiye FMs call - under the headline of the smallest of
    them. Recall was 100% on both golden days at every threshold tried, so the
    harness could not see it at all: keyword matching finds its must-have
    inside a blob just as happily as inside a clean cluster.

    `merged_in` is the worse number. An article merged into a blob is a story
    the editor never sees as a candidate; a split one shows up as two
    candidates it can choose between, and `duplicate events` guards that.
    """

    clusters: int
    merged_in: int
    split_apart: int

    @property
    def misplaced(self) -> int:
        return self.merged_in + self.split_apart


def _linkage_components(matrix: "np.ndarray", threshold: float) -> List[List[int]]:
    """Single-linkage components of a cosine-similarity matrix."""
    size = len(matrix)
    similarity = matrix @ matrix.T
    seen: set = set()
    groups: List[List[int]] = []
    for start in range(size):
        if start in seen:
            continue
        stack, group = [start], []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            group.append(node)
            stack.extend(
                other
                for other in range(size)
                if other not in seen and similarity[node, other] >= threshold
            )
        groups.append(group)
    return groups


def measure_cluster_quality(articles: Sequence[Any]) -> Optional[ClusterQuality]:
    """Score the grouping against an embedding-only reference partition."""
    usable = [a for a in articles if getattr(a, "embedding", None)]
    if len(usable) < 2:
        return None

    matrix = np.array([a.embedding for a in usable], dtype=np.float32)
    matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    reference = _linkage_components(matrix, EVENT_LINKAGE)
    event_of = {index: event for event, group in enumerate(reference) for index in group}

    cluster_of = {
        index: str(article.cluster_id)
        for index, article in enumerate(usable)
        if article.cluster_id
    }
    by_cluster: Dict[str, List[int]] = {}
    for index, cluster_id in cluster_of.items():
        by_cluster.setdefault(cluster_id, []).append(index)

    merged_in = sum(
        len(members)
        for members in by_cluster.values()
        if len({event_of[index] for index in members}) > 1
    )
    split_apart = sum(
        len([i for i in group if i in cluster_of])
        for group in reference
        if len({cluster_of[i] for i in group if i in cluster_of}) > 1
    )
    return ClusterQuality(
        clusters=len(by_cluster), merged_in=merged_in, split_apart=split_apart
    )


def run_golden_day(
    day: GoldenDay,
    *,
    db_path: Path,
    live_editorial: bool = False,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> tuple[GoldenDayReport, PipelineStats]:
    """
    Run the full pipeline over a recorded day and score the brief it produces.

    Triage is replayed from recorded verdicts rather than skipped: category and
    impact come from triage now, so a run without it would measure a selection
    path production does not use. Storage goes through `create_db_client()`,
    pointed at a throwaway file.

    The story-analysis pass is tied to `live_editorial` for the same reason
    the editor is: it needs the network. The **default offline run therefore
    does not exercise story analysis at all** - do not read a green offline
    golden day as evidence about that feature.

    By default the editorial LLM is **off**, which keeps the run offline and
    deterministic — and means it scores the fallback ordering, not the brief
    production ships. `live_editorial=True` calls the real editor over the same
    recorded candidate pool: two or three LLM calls, no network for anything
    else, and the only way to A/B an editorial prompt change without waiting
    for tomorrow's news. Its output is nondeterministic, so it reports rather
    than gates, and it must never move `baseline_recall`.
    """
    os.environ["SAAF_DB_BACKEND"] = "sqlite"
    os.environ["SAAF_SQLITE_PATH"] = str(db_path)

    config = PipelineConfig(
        sources_yaml=day.path / SOURCES,
        enable_editorial_llm=bool(live_editorial),
        # Tied to the same flag. The offline run left this at the dataclass
        # default and so gave the story-analysis path zero coverage, while
        # production ran it on every card - a green golden day said nothing
        # about it at all.
        enable_story_analysis_llm=bool(live_editorial),
        recluster_recent_window=False,
        max_articles_per_source=day.max_articles_per_source or 40,
        **(config_overrides or {}),
    )

    db = create_db_client()
    # Held rather than inlined so its misses can be read back after the run:
    # a fixture whose recorded vectors no longer match the text the pipeline
    # embeds scores a pipeline nobody ships.
    embedder = day.embedder()
    try:
        runner = PipelineOrchestrator(
            config=config,
            db=db,
            ingestor=ReplayIngestor(day),  # type: ignore[arg-type]
            embedder=embedder,  # type: ignore[arg-type]
            triage_service=day.triager(),
            adjudicator=day.adjudicator(),
        )
        stats = runner.run()
        feeds = db.get_analyzed_feed(limit=100, published_only=False)
        cluster_quality = measure_cluster_quality(db.get_recent_articles(limit=5000))
    finally:
        db.close()

    cards = [BriefCard.from_feed(feed) for feed in feeds]
    report = score_brief(cards, day.expectations, day=day.name)
    report.cluster_quality = cluster_quality
    report.embedding_misses = list(embedder.misses)
    return report, stats


def available_days() -> List[Path]:
    if not GOLDEN_DAYS_DIR.exists():
        return []
    return sorted(p for p in GOLDEN_DAYS_DIR.iterdir() if (p / MANIFEST).exists())
