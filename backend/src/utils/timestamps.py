"""Publisher timestamps shared by the API and pipeline."""
from datetime import datetime, timezone

from src.db.models import RawArticle


def trusted_article_timestamp(article: RawArticle, max_publish_skew_hours: int = 36) -> datetime:
    """
    When the event happened, per the publisher.

    The skew heuristics this replaced inferred from page content what the feed
    states directly. They are unreachable now: ingest drops any item with no
    publish_date and quarantines any endpoint whose newest item is stale, so
    every stored article already has a publisher date inside the window
    (`issues.md` I-6). `max_publish_skew_hours` is kept for call compatibility.
    """
    published = article.publish_date
    if published is not None:
        return published if published.tzinfo else published.replace(tzinfo=timezone.utc)
    scraped = article.scraped_at
    return scraped if scraped.tzinfo else scraped.replace(tzinfo=timezone.utc)

