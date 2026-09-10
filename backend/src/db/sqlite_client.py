"""
Local SQLite client for Saaf Baat database operations.

Implements the same public surface as `SupabaseClient` so the pipeline, the
API routes, and the scripts can talk to either backend unchanged. Chosen as
the default so the product runs with zero external dependencies; swapping to
Postgres later means adding a client with the same methods, not rewriting
callers.

Storage notes:
- UUIDs are stored as TEXT.
- Timestamps are stored as fixed-width ISO-8601 UTC TEXT, which makes
  lexicographic comparison equivalent to chronological comparison.
- Embeddings, JSON blobs, and arrays are stored as JSON TEXT. Vector math
  already happens in numpy inside the pipeline, so no database-side vector
  support is needed.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID

from .errors import (
    DatabaseError,
    DBConnectionError,
    DuplicateArticleError,
    NotFoundError,
)
from .models import (
    AnalyzedFeed,
    ArticleList,
    Cluster,
    ClusterList,
    FeedList,
    RawArticle,
)

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema_sqlite.sql"

DEFAULT_SQLITE_PATH = _BACKEND_DIR / "data" / "saafbaat.db"


def default_sqlite_path() -> Path:
    """Resolve the SQLite file path, honouring SAAF_SQLITE_PATH."""
    raw = (os.getenv("SAAF_SQLITE_PATH") or "").strip()
    if not raw:
        return DEFAULT_SQLITE_PATH
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (_BACKEND_DIR / path)


# ==========================================
# Encoding helpers
# ==========================================


def _to_utc(value: datetime) -> datetime:
    """Naive datetimes are treated as UTC, matching the Postgres columns."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    """Fixed-width ISO-8601 UTC so TEXT ordering matches time ordering."""
    if value is None:
        return None
    return _to_utc(value).isoformat(timespec="microseconds")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(raw: Any, fallback: Any) -> Any:
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _row_to_article(row: sqlite3.Row) -> RawArticle:
    return RawArticle(
        id=row["id"],
        source=row["source"],
        url=row["url"],
        headline=row["headline"],
        main_text=row["main_text"],
        author=row["author"],
        publish_date=row["publish_date"],
        scraped_at=row["scraped_at"],
        content_hash=row["content_hash"],
        cluster_id=row["cluster_id"],
        embedding=_loads(row["embedding"], None),
        metadata=_loads(row["metadata"], {}),
    )


def _row_to_cluster(row: sqlite3.Row) -> Cluster:
    return Cluster(
        id=row["id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        article_ids=_loads(row["article_ids"], []),
        centroid_embedding=_loads(row["centroid_embedding"], None),
        representative_article_id=row["representative_article_id"],
        avg_similarity=row["avg_similarity"],
        algorithm_used=row["algorithm_used"],
        metadata=_loads(row["metadata"], {}),
    )


def _row_to_feed(row: sqlite3.Row) -> AnalyzedFeed:
    return AnalyzedFeed.from_db_dict(
        {
            "id": row["id"],
            "cluster_id": row["cluster_id"],
            "created_at": row["created_at"],
            "headline": row["headline"],
            "summary": row["summary"],
            "category": row["category"],
            "confirmed_facts": _loads(row["confirmed_facts"], []),
            "debated_claims": _loads(row["debated_claims"], []),
            "impact_labels": _loads(row["impact_labels"], []),
            "source_attribution": _loads(row["source_attribution"], {}),
            "entity_counts": _loads(row["entity_counts"], {}),
            "classification_confidence": row["classification_confidence"],
            "is_published": bool(row["is_published"]),
            "metadata": _loads(row["metadata"], {}),
        }
    )


class SqliteClient:
    """
    Local-file client for the Saaf Baat database.

    Usage:
        client = SqliteClient()
        article_id = client.insert_article(article)
        articles = client.get_articles_by_source("dawn")
    """

    TABLE_RAW_ARTICLES = "raw_articles"
    TABLE_CLUSTERS = "clusters"
    TABLE_ANALYZED_FEED = "analyzed_feed"

    def __init__(
        self,
        path: Optional[Path | str] = None,
        test_mode: bool = False,
    ):
        """
        Args:
            path: SQLite file path. Defaults to SAAF_SQLITE_PATH, then
                  backend/data/saafbaat.db. Pass ":memory:" for ephemeral use.
            test_mode: Track inserted rows so cleanup_test_data() can remove them.
        """
        self.test_mode = test_mode
        self._memory_conn: Optional[sqlite3.Connection] = None

        if path is None:
            self.path = default_sqlite_path()
        elif str(path) == ":memory:":
            self.path = Path(":memory:")
        else:
            self.path = Path(path).expanduser()

        self._test_article_ids: List[str] = []
        self._test_cluster_ids: List[str] = []
        self._test_feed_ids: List[str] = []

        try:
            self._init_storage()
        except sqlite3.Error as exc:
            raise DBConnectionError(f"Failed to open SQLite database at {self.path}: {exc}") from exc

    # ==========================================
    # Connection management
    # ==========================================

    @property
    def is_memory(self) -> bool:
        return str(self.path) == ":memory:"

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not self.is_memory:
            # WAL keeps the daily pipeline writing while the API reads.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_storage(self) -> None:
        if not self.is_memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_memory:
            # An in-memory database only survives while its connection is open.
            self._memory_conn = self._new_connection()
        self._apply_schema()

    def _apply_schema(self) -> None:
        schema = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection, committing on success and rolling back on error."""
        if self._memory_conn is not None:
            conn = self._memory_conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return

        conn = self._new_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def is_connected(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(f"SELECT id FROM {self.TABLE_RAW_ARTICLES} LIMIT 1").fetchone()
            return True
        except Exception as exc:
            logger.error(f"Connection check failed: {exc}")
            return False

    # ==========================================
    # Article Operations
    # ==========================================

    _ARTICLE_COLUMNS = (
        "id, source, url, headline, main_text, author, publish_date, "
        "scraped_at, content_hash, cluster_id, embedding, metadata"
    )

    @staticmethod
    def _article_params(article: RawArticle) -> tuple:
        return (
            str(article.id),
            article.source,
            article.url,
            article.headline,
            article.main_text,
            article.author,
            _iso(article.publish_date),
            _iso(article.scraped_at) or _iso(datetime.now(timezone.utc)),
            article.content_hash,
            str(article.cluster_id) if article.cluster_id else None,
            _dumps(article.embedding) if article.embedding else None,
            _dumps(article.metadata or {}),
        )

    def _insert_article(self, conn: sqlite3.Connection, article: RawArticle) -> UUID:
        try:
            conn.execute(
                f"INSERT INTO {self.TABLE_RAW_ARTICLES} ({self._ARTICLE_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._article_params(article),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper():
                raise DuplicateArticleError(f"Article already exists: {article.url}") from exc
            raise DatabaseError(f"Failed to insert article: {exc}") from exc
        if self.test_mode:
            self._test_article_ids.append(str(article.id))
        return article.id

    def insert_article(self, article: RawArticle) -> UUID:
        """Insert a single article. Raises DuplicateArticleError on url/hash clash."""
        try:
            with self._connect() as conn:
                return self._insert_article(conn, article)
        except (DuplicateArticleError, DatabaseError):
            raise
        except Exception as exc:
            raise DatabaseError(f"Failed to insert article: {exc}") from exc

    def batch_insert_articles(self, articles: ArticleList) -> List[UUID]:
        """Insert many articles in one transaction, skipping duplicates."""
        if not articles:
            return []

        inserted_ids: List[UUID] = []
        try:
            with self._connect() as conn:
                for article in articles:
                    try:
                        inserted_ids.append(self._insert_article(conn, article))
                    except DuplicateArticleError:
                        logger.warning(f"Skipping duplicate article: {article.url}")
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError(f"Batch insert failed: {exc}") from exc
        return inserted_ids

    def _query_articles(self, where: str, params: tuple, order: str, limit: Optional[int]) -> ArticleList:
        sql = f"SELECT {self._ARTICLE_COLUMNS} FROM {self.TABLE_RAW_ARTICLES}"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        if limit is not None:
            sql += " LIMIT ?"
            params = params + (int(limit),)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_article(row) for row in rows]

    def get_article_by_id(self, article_id: UUID | str) -> RawArticle:
        """Retrieve article by ID."""
        try:
            articles = self._query_articles("id = ?", (str(article_id),), "", 1)
        except Exception as exc:
            raise DatabaseError(f"Failed to get article: {exc}") from exc
        if not articles:
            raise NotFoundError(f"Article not found: {article_id}")
        return articles[0]

    def get_articles_by_ids(self, article_ids: List[Any]) -> ArticleList:
        """Retrieve multiple articles by their IDs."""
        if not article_ids:
            return []
        str_ids = tuple(str(aid) for aid in article_ids)
        placeholders = ",".join("?" for _ in str_ids)
        try:
            return self._query_articles(f"id IN ({placeholders})", str_ids, "", None)
        except Exception as exc:
            raise DatabaseError(f"Failed to get articles: {exc}") from exc

    def get_articles_by_source(self, source: str, limit: int = 100) -> ArticleList:
        """Get articles from a specific news source."""
        try:
            return self._query_articles("source = ?", (source,), "scraped_at DESC", limit)
        except Exception as exc:
            raise DatabaseError(f"Failed to get articles by source: {exc}") from exc

    def get_articles_in_date_range(self, start: str, end: str, limit: int = 500) -> ArticleList:
        """Get articles published within an inclusive YYYY-MM-DD date range."""
        try:
            return self._query_articles(
                "publish_date >= ? AND publish_date <= ?",
                (f"{start}T00:00:00.000000+00:00", f"{end}T23:59:59.999999+00:00"),
                "publish_date DESC",
                limit,
            )
        except Exception as exc:
            raise DatabaseError(f"Failed to get articles by date range: {exc}") from exc

    def get_articles_without_embeddings(self, limit: int = 100) -> ArticleList:
        """Get articles that haven't been embedded yet."""
        try:
            return self._query_articles("embedding IS NULL", (), "scraped_at DESC", limit)
        except Exception as exc:
            raise DatabaseError(f"Failed to get articles without embeddings: {exc}") from exc

    def get_articles_without_clusters(self, limit: int = 100) -> ArticleList:
        """Get articles that haven't been assigned to a cluster."""
        try:
            return self._query_articles("cluster_id IS NULL", (), "scraped_at DESC", limit)
        except Exception as exc:
            raise DatabaseError(f"Failed to get articles without clusters: {exc}") from exc

    def get_articles_without_clusters_since(
        self, since: datetime, limit: Optional[int] = None
    ) -> ArticleList:
        """Get unclustered articles scraped since a given timestamp."""
        try:
            return self._query_articles(
                "cluster_id IS NULL AND scraped_at >= ?", (_iso(since),), "scraped_at DESC", limit
            )
        except Exception as exc:
            raise DatabaseError(f"Failed to get recent unclustered articles: {exc}") from exc

    def get_articles_with_embeddings_since(
        self, since: datetime, limit: Optional[int] = None
    ) -> ArticleList:
        """Get articles with embeddings scraped since a given timestamp."""
        try:
            return self._query_articles(
                "embedding IS NOT NULL AND scraped_at >= ?", (_iso(since),), "scraped_at DESC", limit
            )
        except Exception as exc:
            raise DatabaseError(f"Failed to get recent embedded articles: {exc}") from exc

    def get_recent_articles(self, limit: int = 50) -> ArticleList:
        """Get most recently scraped articles."""
        try:
            return self._query_articles("", (), "scraped_at DESC", limit)
        except Exception as exc:
            raise DatabaseError(f"Failed to get recent articles: {exc}") from exc

    def get_articles_since(self, since: datetime, limit: int = 2000) -> ArticleList:
        """Get articles scraped since a given timestamp (for local dedup/indexing)."""
        try:
            return self._query_articles("scraped_at >= ?", (_iso(since),), "scraped_at DESC", limit)
        except Exception as exc:
            raise DatabaseError(f"Failed to get articles since {since}: {exc}") from exc

    def update_article_embedding(self, article_id: Any, embedding: List[float]) -> None:
        """Update article's embedding vector."""
        try:
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE {self.TABLE_RAW_ARTICLES} SET embedding = ? WHERE id = ?",
                    (_dumps(list(embedding)), str(article_id)),
                )
        except Exception as exc:
            raise DatabaseError(f"Failed to update article embedding: {exc}") from exc

    def update_article_body(
        self, article_id: Any, main_text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Replace an article's body after a lazy fetch.

        content_hash is intentionally left untouched: it is the row's dedup
        identity and must stay stable when the body is upgraded.
        """
        try:
            with self._connect() as conn:
                if metadata is None:
                    conn.execute(
                        f"UPDATE {self.TABLE_RAW_ARTICLES} SET main_text = ? WHERE id = ?",
                        (main_text, str(article_id)),
                    )
                else:
                    conn.execute(
                        f"UPDATE {self.TABLE_RAW_ARTICLES} SET main_text = ?, metadata = ? "
                        "WHERE id = ?",
                        (main_text, _dumps(dict(metadata)), str(article_id)),
                    )
        except Exception as exc:
            raise DatabaseError(f"Failed to update article body: {exc}") from exc

    def update_article_metadata(self, article_id: Any, metadata: Dict[str, Any]) -> None:
        """Replace an article's metadata blob (used to persist triage verdicts)."""
        try:
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE {self.TABLE_RAW_ARTICLES} SET metadata = ? WHERE id = ?",
                    (_dumps(dict(metadata)), str(article_id)),
                )
        except Exception as exc:
            raise DatabaseError(f"Failed to update article metadata: {exc}") from exc

    def assign_to_cluster(self, article_id: Any, cluster_id: Any) -> None:
        """Assign article to a cluster."""
        try:
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE {self.TABLE_RAW_ARTICLES} SET cluster_id = ? WHERE id = ?",
                    (str(cluster_id), str(article_id)),
                )
        except Exception as exc:
            raise DatabaseError(f"Failed to assign article to cluster: {exc}") from exc

    def clear_cluster_assignments_since(self, since: datetime) -> int:
        """Clear cluster_id for articles scraped since the given timestamp."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    f"UPDATE {self.TABLE_RAW_ARTICLES} SET cluster_id = NULL "
                    "WHERE scraped_at >= ? AND cluster_id IS NOT NULL",
                    (_iso(since),),
                )
                return int(cursor.rowcount or 0)
        except Exception as exc:
            raise DatabaseError(f"Failed clearing cluster assignments: {exc}") from exc

    def delete_article(self, article_id: Any) -> None:
        """Delete an article."""
        try:
            with self._connect() as conn:
                conn.execute(
                    f"DELETE FROM {self.TABLE_RAW_ARTICLES} WHERE id = ?", (str(article_id),)
                )
        except Exception as exc:
            raise DatabaseError(f"Failed to delete article: {exc}") from exc

    def delete_raw_articles_older_than(self, cutoff: datetime) -> int:
        """Delete raw_articles with scraped_at older than cutoff."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self.TABLE_RAW_ARTICLES} WHERE scraped_at < ?", (_iso(cutoff),)
                )
                return int(cursor.rowcount or 0)
        except Exception as exc:
            raise DatabaseError(f"Failed to prune raw articles: {exc}") from exc

    # ==========================================
    # Cluster Operations
    # ==========================================

    _CLUSTER_COLUMNS = (
        "id, created_at, updated_at, article_ids, centroid_embedding, "
        "representative_article_id, cluster_size, avg_similarity, algorithm_used, metadata"
    )

    def create_cluster(
        self,
        cluster_id: Any = None,
        article_ids: Optional[List[Any]] = None,
        centroid_embedding: Optional[List[float]] = None,
        algorithm_used: str = "hdbscan",
    ) -> UUID:
        """Create a new cluster and return its UUID."""
        cluster = Cluster(
            article_ids=[UUID(str(aid)) for aid in (article_ids or [])],
            algorithm_used=algorithm_used,
        )
        if cluster_id:
            cluster.id = UUID(str(cluster_id))

        try:
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO {self.TABLE_CLUSTERS} ({self._CLUSTER_COLUMNS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(cluster.id),
                        _iso(cluster.created_at),
                        _iso(cluster.updated_at),
                        _dumps([str(aid) for aid in cluster.article_ids]),
                        _dumps(list(centroid_embedding)) if centroid_embedding else None,
                        str(cluster.representative_article_id)
                        if cluster.representative_article_id
                        else None,
                        cluster.cluster_size,
                        cluster.avg_similarity,
                        cluster.algorithm_used,
                        _dumps(cluster.metadata or {}),
                    ),
                )
            if self.test_mode:
                self._test_cluster_ids.append(str(cluster.id))
            return cluster.id
        except Exception as exc:
            raise DatabaseError(f"Failed to create cluster: {exc}") from exc

    def get_cluster_by_id(self, cluster_id: Any) -> Cluster:
        """Retrieve cluster by ID."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    f"SELECT {self._CLUSTER_COLUMNS} FROM {self.TABLE_CLUSTERS} WHERE id = ?",
                    (str(cluster_id),),
                ).fetchone()
        except Exception as exc:
            raise DatabaseError(f"Failed to get cluster: {exc}") from exc
        if row is None:
            raise NotFoundError(f"Cluster not found: {cluster_id}")
        return _row_to_cluster(row)

    def get_all_clusters(
        self, limit: Optional[int] = 100, *, order: str = "recent"
    ) -> ClusterList:
        """Get clusters, newest first by default or biggest first on request.

        `order="size"` exists because the limit truncates. Ordered by
        `created_at` it drops whichever clusters happened to be written last,
        which is unrelated to whether anyone should read them: on 2026-08-25 a
        run produced 570 clusters, the analysis stage looked at 200, and the
        two most-corroborated stories of the day - Imran Khan's hospital
        transfer at 7 sources and the Munir visit to Iran at 6 - fell outside
        the window and were never analysed at all. If a limit has to discard
        something it should discard the singletons.
        """
        clause = "cluster_size DESC, created_at DESC" if order == "size" else "created_at DESC"
        try:
            with self._connect() as conn:
                query = (
                    f"SELECT {self._CLUSTER_COLUMNS} FROM {self.TABLE_CLUSTERS} "
                    f"ORDER BY {clause}"
                )
                rows = (
                    conn.execute(f"{query} LIMIT ?", (int(limit),)).fetchall()
                    if limit is not None
                    else conn.execute(query).fetchall()
                )
            return [_row_to_cluster(row) for row in rows]
        except Exception as exc:
            raise DatabaseError(f"Failed to get clusters: {exc}") from exc

    def update_cluster_articles(self, cluster_id: Any, article_ids: List[Any]) -> None:
        """Update the articles in a cluster."""
        try:
            str_ids = [str(aid) for aid in article_ids]
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE {self.TABLE_CLUSTERS} "
                    "SET article_ids = ?, cluster_size = ?, updated_at = ? WHERE id = ?",
                    (
                        _dumps(str_ids),
                        len(str_ids),
                        _iso(datetime.now(timezone.utc)),
                        str(cluster_id),
                    ),
                )
        except Exception as exc:
            raise DatabaseError(f"Failed to update cluster articles: {exc}") from exc

    def delete_cluster(self, cluster_id: Any) -> None:
        """Delete a cluster."""
        try:
            with self._connect() as conn:
                conn.execute(f"DELETE FROM {self.TABLE_CLUSTERS} WHERE id = ?", (str(cluster_id),))
        except Exception as exc:
            raise DatabaseError(f"Failed to delete cluster: {exc}") from exc

    def delete_clusters_older_than(self, cutoff: datetime) -> int:
        """Delete clusters with created_at older than cutoff."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self.TABLE_CLUSTERS} WHERE created_at < ?", (_iso(cutoff),)
                )
                return int(cursor.rowcount or 0)
        except Exception as exc:
            raise DatabaseError(f"Failed to prune clusters: {exc}") from exc

    # ==========================================
    # Analyzed Feed Operations
    # ==========================================

    _FEED_COLUMNS = (
        "id, cluster_id, created_at, headline, summary, category, confirmed_facts, "
        "debated_claims, impact_labels, source_attribution, entity_counts, "
        "classification_confidence, is_published, metadata"
    )

    def analyzed_feed_exists(self, cluster_id: Any) -> bool:
        """Return True if an analyzed_feed row exists for the given cluster_id."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    f"SELECT 1 FROM {self.TABLE_ANALYZED_FEED} WHERE cluster_id = ? LIMIT 1",
                    (str(cluster_id),),
                ).fetchone()
            return row is not None
        except Exception as exc:
            raise DatabaseError(f"Failed to check analyzed feed existence: {exc}") from exc

    def insert_analyzed_feed(self, feed: Any) -> UUID:
        """Insert an analyzed story into the feed and return its UUID."""
        try:
            if isinstance(feed, dict):
                feed = AnalyzedFeed(**feed)

            data = feed.to_db_dict()
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO {self.TABLE_ANALYZED_FEED} ({self._FEED_COLUMNS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(feed.id),
                        str(feed.cluster_id),
                        _iso(feed.created_at),
                        feed.headline,
                        feed.summary,
                        str(feed.category),
                        _dumps(data.get("confirmed_facts") or []),
                        _dumps(data.get("debated_claims") or []),
                        _dumps([str(label) for label in (feed.impact_labels or [])]),
                        _dumps(dict(feed.source_attribution or {})),
                        _dumps(dict(feed.entity_counts or {})),
                        feed.classification_confidence,
                        1 if feed.is_published else 0,
                        _dumps(dict(feed.metadata or {})),
                    ),
                )
            if self.test_mode:
                self._test_feed_ids.append(str(feed.id))
            return feed.id
        except Exception as exc:
            raise DatabaseError(f"Failed to insert analyzed feed: {exc}") from exc

    def get_analyzed_feed_by_id(self, feed_id: Any) -> AnalyzedFeed:
        """Retrieve analyzed feed item by ID."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    f"SELECT {self._FEED_COLUMNS} FROM {self.TABLE_ANALYZED_FEED} WHERE id = ?",
                    (str(feed_id),),
                ).fetchone()
        except Exception as exc:
            raise DatabaseError(f"Failed to get feed item: {exc}") from exc
        if row is None:
            raise NotFoundError(f"Feed item not found: {feed_id}")
        return _row_to_feed(row)

    def get_analyzed_feed_by_cluster_id(self, cluster_id: Any) -> AnalyzedFeed:
        """Retrieve the newest analyzed feed item for a cluster."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    f"SELECT {self._FEED_COLUMNS} FROM {self.TABLE_ANALYZED_FEED} "
                    "WHERE cluster_id = ? ORDER BY created_at DESC LIMIT 1",
                    (str(cluster_id),),
                ).fetchone()
        except Exception as exc:
            raise DatabaseError(f"Failed to get feed item by cluster: {exc}") from exc
        if row is None:
            raise NotFoundError(f"Feed item not found for cluster: {cluster_id}")
        return _row_to_feed(row)

    def get_analyzed_feed(
        self,
        category: Optional[str] = None,
        impact_label: Optional[str] = None,
        limit: int = 50,
        published_only: bool = True,
    ) -> FeedList:
        """Get analyzed feed with optional category/impact filters."""
        clauses: List[str] = []
        params: List[Any] = []
        if published_only:
            clauses.append("is_published = 1")
        if category:
            clauses.append("category = ?")
            params.append(category)

        sql = f"SELECT {self._FEED_COLUMNS} FROM {self.TABLE_ANALYZED_FEED}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"

        # impact_labels is a JSON array, so it is filtered in Python. The brief
        # is a handful of rows per day, so the extra rows read are negligible.
        if not impact_label:
            sql += " LIMIT ?"
            params.append(int(limit))

        try:
            with self._connect() as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()
        except Exception as exc:
            raise DatabaseError(f"Failed to get analyzed feed: {exc}") from exc

        feeds = [_row_to_feed(row) for row in rows]
        if impact_label:
            feeds = [f for f in feeds if impact_label in [str(x) for x in (f.impact_labels or [])]]
            feeds = feeds[: int(limit)]
        return feeds

    def delete_analyzed_feed(self, feed_id: Any) -> None:
        """Delete an analyzed feed item."""
        try:
            with self._connect() as conn:
                conn.execute(
                    f"DELETE FROM {self.TABLE_ANALYZED_FEED} WHERE id = ?", (str(feed_id),)
                )
        except Exception as exc:
            raise DatabaseError(f"Failed to delete feed item: {exc}") from exc

    def delete_analyzed_feed_by_cluster_id(self, cluster_id: Any) -> int:
        """Delete all analyzed feed rows for a cluster."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self.TABLE_ANALYZED_FEED} WHERE cluster_id = ?",
                    (str(cluster_id),),
                )
                return int(cursor.rowcount or 0)
        except Exception as exc:
            raise DatabaseError(f"Failed deleting feed rows for cluster: {exc}") from exc

    def delete_analyzed_feed_older_than(self, cutoff: datetime) -> int:
        """Delete analyzed_feed rows with created_at older than cutoff."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self.TABLE_ANALYZED_FEED} WHERE created_at < ?",
                    (_iso(cutoff),),
                )
                return int(cursor.rowcount or 0)
        except Exception as exc:
            raise DatabaseError(f"Failed to prune analyzed feed: {exc}") from exc

    # ==========================================
    # Schema & Utility Operations
    # ==========================================

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Return the column names for a table."""
        try:
            with self._connect() as conn:
                rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        except Exception as exc:
            raise DatabaseError(f"Failed to get table schema: {exc}") from exc
        if not rows:
            raise DatabaseError(f"Failed to get table schema: unknown table {table_name}")
        return {"columns": [row["name"] for row in rows]}

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def close(self) -> None:
        """Close the persistent connection used by in-memory databases."""
        if self._memory_conn is not None:
            self._memory_conn.close()
            self._memory_conn = None

    # ==========================================
    # Test Mode & Cleanup
    # ==========================================

    def cleanup_test_data(self) -> None:
        """Remove rows created while test_mode=True."""
        if not self.test_mode:
            logger.warning("cleanup_test_data called but test_mode is False")
            return

        for feed_id in self._test_feed_ids:
            try:
                self.delete_analyzed_feed(feed_id)
            except Exception as exc:
                logger.warning(f"Failed to cleanup feed {feed_id}: {exc}")

        for cluster_id in self._test_cluster_ids:
            try:
                self.delete_cluster(cluster_id)
            except Exception as exc:
                logger.warning(f"Failed to cleanup cluster {cluster_id}: {exc}")

        for article_id in self._test_article_ids:
            try:
                self.delete_article(article_id)
            except Exception as exc:
                logger.warning(f"Failed to cleanup article {article_id}: {exc}")

        self._test_article_ids.clear()
        self._test_cluster_ids.clear()
        self._test_feed_ids.clear()

        logger.info("Test data cleanup complete")


__all__ = ["SqliteClient", "default_sqlite_path", "DEFAULT_SQLITE_PATH"]
