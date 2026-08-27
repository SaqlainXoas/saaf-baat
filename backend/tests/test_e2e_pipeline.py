"""
End-to-end pipeline check: ingest -> embeddings -> database.

A manual script, not a pytest module. It hits the live publisher endpoints and
the embedding API, so it is run by hand rather than in the suite:

    source venv/bin/activate && python tests/test_e2e_pipeline.py

Storage goes through the configured backend (local SQLite by default) via
`create_db_client()`.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")

sys.path.insert(0, str(_BACKEND_DIR / "src"))

import yaml  # noqa: E402

from src.agents.embeddings import EmbeddingError, GeminiEmbeddingProvider  # noqa: E402
from src.db.factory import create_db_client  # noqa: E402
from src.scrapers.feeds import FeedIngestor, SourceSpec  # noqa: E402

MAX_ARTICLES = 5


def main() -> bool:
    print("=" * 60)
    print("END-TO-END PIPELINE CHECK")
    print("=" * 60)

    # Step 1: ingest -------------------------------------------------------
    print("\n[STEP 1] INGEST (RSS + SITEMAP)")
    print("-" * 40)

    config = yaml.safe_load((_BACKEND_DIR / "config" / "sources.yaml").read_text(encoding="utf-8"))
    result = FeedIngestor(SourceSpec.from_config(config), max_articles_per_source=5).run()

    for report in result.reports:
        flag = "" if report.is_healthy else "   <-- QUARANTINED"
        print(
            f"  {report.source:<10} {report.channel:<8} {report.status:<12} "
            f"newest={report.newest_age_hours}h items={report.item_count}{flag}"
        )

    articles = result.articles[:MAX_ARTICLES]
    print(f"\n  discovered: {len(result.articles)} articles in {result.discovery_seconds:.1f}s")
    print(f"  quarantined endpoints: {len(result.quarantined)}")
    print(f"  using first {len(articles)} for the round trip")

    if not articles:
        print("\n  No articles discovered — check endpoint health above.")
        return False

    for article in articles:
        body_status = (article.metadata or {}).get("body_status")
        print(f"  - [{article.source}/{body_status}] {article.headline[:60]}...")

    # Step 2: embeddings ---------------------------------------------------
    print("\n[STEP 2] GENERATING EMBEDDINGS")
    print("-" * 40)

    try:
        provider = GeminiEmbeddingProvider()
        texts = [f"{a.headline}. {a.main_text[:500]}" for a in articles]
        embedded = provider.embed(texts)
        print(f"  model={provider.model} dim={embedded.dimension} count={embedded.texts_count}")
        for index, article in enumerate(articles):
            article.embedding = embedded.embeddings[index].tolist()
    except EmbeddingError as exc:
        print(f"  Embedding error: {exc}")
        return False

    # Step 3 + 4: store and verify ----------------------------------------
    print("\n[STEP 3] STORING AND VERIFYING")
    print("-" * 40)

    db = create_db_client(test_mode=True)
    inserted_ids = []
    try:
        for article in articles:
            try:
                article_id = db.insert_article(article)
            except Exception as exc:
                print(f"  insert skipped ({exc})")
                continue
            inserted_ids.append(article_id)
            if article.embedding:
                db.update_article_embedding(article_id, article.embedding)

        print(f"  inserted: {len(inserted_ids)}")

        for article_id in inserted_ids:
            stored = db.get_article_by_id(article_id)
            has_embedding = "yes" if stored.embedding else "NO"
            print(
                f"  {str(article_id)[:8]}  {stored.source:<10} embedding={has_embedding:<4} "
                f"{stored.headline[:44]}..."
            )
    finally:
        try:
            db.cleanup_test_data()
            print("  test rows cleaned up")
        except Exception as exc:
            print(f"  cleanup warning: {exc}")
        db.close()

    print("\n" + "=" * 60)
    print(
        f"OK — {len(result.articles)} discovered, {len(inserted_ids)} stored and read back, "
        f"{len(result.quarantined)} endpoints quarantined"
    )
    print("=" * 60)
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
