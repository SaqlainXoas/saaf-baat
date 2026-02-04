"""
Supabase client for Saaf Baat database operations.

Provides:
- Connection management with retry logic
- CRUD operations for articles, clusters, and analyzed feed
- Batch operations for efficiency
- Test mode with automatic cleanup
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions

from .models import RawArticle, Cluster, AnalyzedFeed, ArticleList, ClusterList, FeedList


logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class DBConnectionError(DatabaseError):
    """Failed to connect to database."""
    pass


class DuplicateArticleError(DatabaseError):
    """Article with same URL or content_hash already exists."""
    pass


class NotFoundError(DatabaseError):
    """Requested record not found."""
    pass


class SupabaseClient:
    """
    Client for interacting with Supabase PostgreSQL database.
    
    Features:
    - Automatic retry on transient failures
    - Batch operations for efficiency
    - Test mode with cleanup
    - Connection pooling via Supabase client
    
    Usage:
        client = SupabaseClient()
        article_id = client.insert_article(article)
        articles = client.get_articles_by_source("dawn")
    """
    
    # Table names
    TABLE_RAW_ARTICLES = "raw_articles"
    TABLE_CLUSTERS = "clusters"
    TABLE_ANALYZED_FEED = "analyzed_feed"
    
    @staticmethod
    def _parse_embedding(data: dict) -> dict:
        """Parse embedding from PostgreSQL vector string format."""
        if data.get("embedding") and isinstance(data["embedding"], str):
            embedding_str = data["embedding"]
            data["embedding"] = [float(x) for x in embedding_str.strip("[]").split(",")]
        return data
    
    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
        test_mode: bool = False,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize Supabase client.
        
        Args:
            url: Supabase project URL (defaults to SUPABASE_URL env var)
            key: Supabase API key (defaults to SUPABASE_KEY env var)
            test_mode: If True, prefixes tables for isolation and enables cleanup
            max_retries: Number of retries on transient failures
            retry_delay: Seconds to wait between retries
        """
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        self.test_mode = test_mode
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client: Optional[Client] = None
        self._test_article_ids: List[str] = []
        self._test_cluster_ids: List[str] = []
        self._test_feed_ids: List[str] = []
        
        if not self.url or not self.key:
            raise DBConnectionError(
                "Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_KEY "
                "environment variables or pass them to the constructor."
            )
    
    @property
    def client(self) -> Client:
        """Lazy-initialize Supabase client with retry logic."""
        if self._client is None:
            self._client = self._connect_with_retry()
        return self._client
    
    def _connect_with_retry(self) -> Client:
        """Attempt connection with retries on failure."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                options = SyncClientOptions(
                    postgrest_client_timeout=30,
                    storage_client_timeout=30,
                )
                client = create_client(self.url, self.key, options=options)
                logger.info(f"Connected to Supabase (attempt {attempt + 1})")
                return client
            except Exception as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
        
        raise DBConnectionError(f"Failed to connect after {self.max_retries} attempts: {last_error}")
    
    def is_connected(self) -> bool:
        """Check if client is connected and functional."""
        try:
            # Simple health check query
            self.client.table(self.TABLE_RAW_ARTICLES).select("id").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False
    
    # ==========================================
    # Article Operations
    # ==========================================
    
    def insert_article(self, article: RawArticle) -> UUID:
        """
        Insert a single article into raw_articles table.
        
        Args:
            article: RawArticle model instance
            
        Returns:
            UUID of inserted article
            
        Raises:
            DuplicateArticleError: If article URL or content_hash already exists
        """
        try:
            data = article.to_db_dict()
            response = self.client.table(self.TABLE_RAW_ARTICLES).insert(data).execute()
            
            if response.data:
                article_id = response.data[0]["id"]
                if self.test_mode:
                    self._test_article_ids.append(article_id)
                return UUID(article_id)
            
            raise DatabaseError("Insert returned no data")
            
        except Exception as e:
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg or "23505" in error_msg:
                raise DuplicateArticleError(f"Article already exists: {article.url}")
            raise DatabaseError(f"Failed to insert article: {e}")
    
    def batch_insert_articles(self, articles: ArticleList) -> List[UUID]:
        """
        Insert multiple articles efficiently.
        
        Args:
            articles: List of RawArticle instances
            
        Returns:
            List of inserted article UUIDs
        """
        if not articles:
            return []
        
        inserted_ids = []
        # Process in batches of 50 to avoid payload limits
        batch_size = 50
        
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            data = [article.to_db_dict() for article in batch]
            
            try:
                response = self.client.table(self.TABLE_RAW_ARTICLES).insert(data).execute()
                
                if response.data:
                    for item in response.data:
                        article_id = item["id"]
                        inserted_ids.append(UUID(article_id))
                        if self.test_mode:
                            self._test_article_ids.append(article_id)
                            
            except Exception as e:
                error_msg = str(e).lower()
                if "duplicate" in error_msg or "unique" in error_msg:
                    # Try inserting one by one to skip duplicates
                    for article in batch:
                        try:
                            article_id = self.insert_article(article)
                            inserted_ids.append(article_id)
                        except DuplicateArticleError:
                            logger.warning(f"Skipping duplicate article: {article.url}")
                else:
                    raise DatabaseError(f"Batch insert failed: {e}")
        
        return inserted_ids
    
    def get_article_by_id(self, article_id: UUID | str) -> RawArticle:
        """Retrieve article by ID."""
        try:
            response = (
                self.client.table(self.TABLE_RAW_ARTICLES)
                .select("*")
                .eq("id", str(article_id))
                .single()
                .execute()
            )
            
            if response.data:
                return RawArticle(**self._parse_embedding(response.data))
            
            raise NotFoundError(f"Article not found: {article_id}")
            
        except NotFoundError:
            raise
        except Exception as e:
            if "PGRST116" in str(e):  # Supabase "no rows returned" error
                raise NotFoundError(f"Article not found: {article_id}")
            raise DatabaseError(f"Failed to get article: {e}")
    
    def get_articles_by_ids(self, article_ids: List[Any]) -> ArticleList:
        """Retrieve multiple articles by their IDs."""
        if not article_ids:
            return []
        
        try:
            str_ids = [str(aid) for aid in article_ids]
            response = (
                self.client.table(self.TABLE_RAW_ARTICLES)
                .select("*")
                .in_("id", str_ids)
                .execute()
            )
            
            return [RawArticle(**self._parse_embedding(item)) for item in response.data]
            
        except Exception as e:
            raise DatabaseError(f"Failed to get articles: {e}")
    
    def get_articles_by_source(self, source: str, limit: int = 100) -> ArticleList:
        """Get articles from a specific news source."""
        try:
            response = (
                self.client.table(self.TABLE_RAW_ARTICLES)
                .select("*")
                .eq("source", source)
                .order("scraped_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            return [RawArticle(**self._parse_embedding(item)) for item in response.data]
            
        except Exception as e:
            raise DatabaseError(f"Failed to get articles by source: {e}")
    
    def get_articles_in_date_range(
        self, 
        start: str, 
        end: str, 
        limit: int = 500
    ) -> ArticleList:
        """
        Get articles published within date range.
        
        Args:
            start: Start date (YYYY-MM-DD format)
            end: End date (YYYY-MM-DD format)
            limit: Maximum articles to return
        """
        try:
            response = (
                self.client.table(self.TABLE_RAW_ARTICLES)
                .select("*")
                .gte("publish_date", f"{start}T00:00:00Z")
                .lte("publish_date", f"{end}T23:59:59Z")
                .order("publish_date", desc=True)
                .limit(limit)
                .execute()
            )
            
            return [RawArticle(**self._parse_embedding(item)) for item in response.data]
            
        except Exception as e:
            raise DatabaseError(f"Failed to get articles by date range: {e}")
    
    def get_articles_without_embeddings(self, limit: int = 100) -> ArticleList:
        """Get articles that haven't been embedded yet."""
        try:
            response = (
                self.client.table(self.TABLE_RAW_ARTICLES)
                .select("*")
                .is_("embedding", "null")
                .order("scraped_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            return [RawArticle(**self._parse_embedding(item)) for item in response.data]
            
        except Exception as e:
            raise DatabaseError(f"Failed to get articles without embeddings: {e}")
    
    def get_articles_without_clusters(self, limit: int = 100) -> ArticleList:
        """Get articles that haven't been assigned to a cluster."""
        try:
            response = (
                self.client.table(self.TABLE_RAW_ARTICLES)
                .select("*")
                .is_("cluster_id", "null")
                .order("scraped_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            return [RawArticle(**self._parse_embedding(item)) for item in response.data]
            
        except Exception as e:
            raise DatabaseError(f"Failed to get articles without clusters: {e}")
    
    def get_recent_articles(self, limit: int = 50) -> ArticleList:
        """Get most recently scraped articles."""
        try:
            response = (
                self.client.table(self.TABLE_RAW_ARTICLES)
                .select("*")
                .order("scraped_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            return [RawArticle(**self._parse_embedding(item)) for item in response.data]
            
        except Exception as e:
            raise DatabaseError(f"Failed to get recent articles: {e}")
    
    def update_article_embedding(
        self, 
        article_id: Any, 
        embedding: List[float]
    ) -> None:
        """Update article's embedding vector."""
        try:
            self.client.table(self.TABLE_RAW_ARTICLES).update(
                {"embedding": embedding}
            ).eq("id", str(article_id)).execute()
            
        except Exception as e:
            raise DatabaseError(f"Failed to update article embedding: {e}")
    
    def assign_to_cluster(self, article_id: Any, cluster_id: Any) -> None:
        """Assign article to a cluster."""
        try:
            self.client.table(self.TABLE_RAW_ARTICLES).update(
                {"cluster_id": str(cluster_id)}
            ).eq("id", str(article_id)).execute()
            
        except Exception as e:
            raise DatabaseError(f"Failed to assign article to cluster: {e}")
    
    def delete_article(self, article_id: Any) -> None:
        """Delete an article."""
        try:
            self.client.table(self.TABLE_RAW_ARTICLES).delete().eq(
                "id", str(article_id)
            ).execute()
            
        except Exception as e:
            raise DatabaseError(f"Failed to delete article: {e}")
    
    # ==========================================
    # Cluster Operations
    # ==========================================
    
    def create_cluster(
        self,
        cluster_id: Any = None,
        article_ids: Optional[List[Any]] = None,
        centroid_embedding: Optional[List[float]] = None,
        algorithm_used: str = "hdbscan",
    ) -> UUID:
        """
        Create a new cluster.
        
        Args:
            cluster_id: Optional cluster ID (generated if not provided)
            article_ids: List of article IDs in this cluster
            centroid_embedding: Cluster centroid vector
            algorithm_used: Clustering algorithm name
            
        Returns:
            UUID of created cluster
        """
        cluster = Cluster(
            article_ids=[UUID(str(aid)) for aid in (article_ids or [])],
            algorithm_used=algorithm_used,
        )
        if cluster_id:
            cluster.id = UUID(str(cluster_id))
        
        try:
            data = cluster.to_db_dict()
            if centroid_embedding:
                data["centroid_embedding"] = centroid_embedding
            
            response = self.client.table(self.TABLE_CLUSTERS).insert(data).execute()
            
            if response.data:
                cid = response.data[0]["id"]
                if self.test_mode:
                    self._test_cluster_ids.append(cid)
                return UUID(cid)
            
            raise DatabaseError("Cluster insert returned no data")
            
        except Exception as e:
            raise DatabaseError(f"Failed to create cluster: {e}")
    
    def get_cluster_by_id(self, cluster_id: Any) -> Cluster:
        """Retrieve cluster by ID."""
        try:
            response = (
                self.client.table(self.TABLE_CLUSTERS)
                .select("*")
                .eq("id", str(cluster_id))
                .single()
                .execute()
            )
            
            if response.data:
                # Convert article_ids strings back to UUIDs
                data = response.data
                if data.get("article_ids"):
                    data["article_ids"] = [UUID(aid) for aid in data["article_ids"]]
                # Parse centroid_embedding from PostgreSQL VECTOR string format
                if data.get("centroid_embedding"):
                    embedding_str = data["centroid_embedding"]
                    if isinstance(embedding_str, str):
                        data["centroid_embedding"] = [
                            float(x) for x in embedding_str.strip("[]").split(",")
                        ]
                return Cluster(**data)
            
            raise NotFoundError(f"Cluster not found: {cluster_id}")
            
        except NotFoundError:
            raise
        except Exception as e:
            if "PGRST116" in str(e):
                raise NotFoundError(f"Cluster not found: {cluster_id}")
            raise DatabaseError(f"Failed to get cluster: {e}")
    
    def get_all_clusters(self, limit: int = 100) -> ClusterList:
        """Get all clusters, ordered by creation date."""
        try:
            response = (
                self.client.table(self.TABLE_CLUSTERS)
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            clusters = []
            for item in response.data:
                if item.get("article_ids"):
                    item["article_ids"] = [UUID(aid) for aid in item["article_ids"]]
                # Parse centroid_embedding from PostgreSQL VECTOR string format
                if item.get("centroid_embedding"):
                    embedding_str = item["centroid_embedding"]
                    if isinstance(embedding_str, str):
                        # VECTOR format: "[0.1,0.2,0.3,...]"
                        item["centroid_embedding"] = [
                            float(x) for x in embedding_str.strip("[]").split(",")
                        ]
                clusters.append(Cluster(**item))
            
            return clusters
            
        except Exception as e:
            raise DatabaseError(f"Failed to get clusters: {e}")
    
    def update_cluster_articles(
        self, 
        cluster_id: Any, 
        article_ids: List[Any]
    ) -> None:
        """Update the articles in a cluster."""
        try:
            str_ids = [str(aid) for aid in article_ids]
            self.client.table(self.TABLE_CLUSTERS).update(
                {"article_ids": str_ids, "cluster_size": len(str_ids)}
            ).eq("id", str(cluster_id)).execute()
            
        except Exception as e:
            raise DatabaseError(f"Failed to update cluster articles: {e}")
    
    def delete_cluster(self, cluster_id: Any) -> None:
        """Delete a cluster."""
        try:
            self.client.table(self.TABLE_CLUSTERS).delete().eq(
                "id", str(cluster_id)
            ).execute()
            
        except Exception as e:
            raise DatabaseError(f"Failed to delete cluster: {e}")
    
    # ==========================================
    # Analyzed Feed Operations
    # ==========================================
    
    def insert_analyzed_feed(self, feed: Any) -> UUID:
        """
        Insert analyzed story into feed.
        
        Args:
            feed: AnalyzedFeed instance or dict with feed data
            
        Returns:
            UUID of inserted feed item
        """
        try:
            if isinstance(feed, dict):
                feed = AnalyzedFeed(**feed)
            
            data = feed.to_db_dict()
            response = self.client.table(self.TABLE_ANALYZED_FEED).insert(data).execute()
            
            if response.data:
                feed_id = response.data[0]["id"]
                if self.test_mode:
                    self._test_feed_ids.append(feed_id)
                return UUID(feed_id)
            
            raise DatabaseError("Feed insert returned no data")
            
        except Exception as e:
            raise DatabaseError(f"Failed to insert analyzed feed: {e}")
    
    def get_analyzed_feed_by_id(self, feed_id: Any) -> AnalyzedFeed:
        """Retrieve analyzed feed item by ID."""
        try:
            response = (
                self.client.table(self.TABLE_ANALYZED_FEED)
                .select("*")
                .eq("id", str(feed_id))
                .single()
                .execute()
            )
            
            if response.data:
                return AnalyzedFeed.from_db_dict(response.data)
            
            raise NotFoundError(f"Feed item not found: {feed_id}")
            
        except NotFoundError:
            raise
        except Exception as e:
            if "PGRST116" in str(e):
                raise NotFoundError(f"Feed item not found: {feed_id}")
            raise DatabaseError(f"Failed to get feed item: {e}")
    
    def get_analyzed_feed(
        self,
        category: Optional[str] = None,
        impact_label: Optional[str] = None,
        limit: int = 50,
        published_only: bool = True,
    ) -> FeedList:
        """
        Get analyzed feed with optional filters.
        
        Args:
            category: Filter by category (e.g., 'economy', 'politics')
            impact_label: Filter by impact label (e.g., '💳 WALLET')
            limit: Maximum items to return
            published_only: Only return published items
        """
        try:
            query = self.client.table(self.TABLE_ANALYZED_FEED).select("*")
            
            if published_only:
                query = query.eq("is_published", True)
            
            if category:
                query = query.eq("category", category)
            
            if impact_label:
                query = query.contains("impact_labels", [impact_label])
            
            response = query.order("created_at", desc=True).limit(limit).execute()
            
            return [AnalyzedFeed.from_db_dict(item) for item in response.data]
            
        except Exception as e:
            raise DatabaseError(f"Failed to get analyzed feed: {e}")
    
    def delete_analyzed_feed(self, feed_id: Any) -> None:
        """Delete an analyzed feed item."""
        try:
            self.client.table(self.TABLE_ANALYZED_FEED).delete().eq(
                "id", str(feed_id)
            ).execute()
            
        except Exception as e:
            raise DatabaseError(f"Failed to delete feed item: {e}")
    
    # ==========================================
    # Schema & Utility Operations
    # ==========================================
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """
        Get schema information for a table.
        
        Note: This requires access to information_schema which may be 
        restricted in Supabase. Returns column names if available.
        """
        try:
            # Simple approach: get one row and infer columns
            response = self.client.table(table_name).select("*").limit(1).execute()
            
            if response.data:
                return {"columns": list(response.data[0].keys())}
            
            # If no data, we can't easily get schema without information_schema access
            return {"columns": [], "note": "Table exists but is empty"}
            
        except Exception as e:
            raise DatabaseError(f"Failed to get table schema: {e}")
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        try:
            self.client.table(table_name).select("id").limit(1).execute()
            return True
        except Exception:
            return False
    
    # ==========================================
    # Test Mode & Cleanup
    # ==========================================
    
    def cleanup_test_data(self) -> None:
        """
        Clean up data created during test mode.
        Only works if test_mode=True was set during initialization.
        """
        if not self.test_mode:
            logger.warning("cleanup_test_data called but test_mode is False")
            return
        
        # Delete in reverse order to respect foreign keys
        for feed_id in self._test_feed_ids:
            try:
                self.delete_analyzed_feed(feed_id)
            except Exception as e:
                logger.warning(f"Failed to cleanup feed {feed_id}: {e}")
        
        for cluster_id in self._test_cluster_ids:
            try:
                self.delete_cluster(cluster_id)
            except Exception as e:
                logger.warning(f"Failed to cleanup cluster {cluster_id}: {e}")
        
        for article_id in self._test_article_ids:
            try:
                self.delete_article(article_id)
            except Exception as e:
                logger.warning(f"Failed to cleanup article {article_id}: {e}")
        
        # Clear tracking lists
        self._test_article_ids.clear()
        self._test_cluster_ids.clear()
        self._test_feed_ids.clear()
        
        logger.info("Test data cleanup complete")
