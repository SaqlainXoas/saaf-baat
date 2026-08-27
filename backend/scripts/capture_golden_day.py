"""
Capture one real news day as an evaluation fixture.

Snapshots every configured endpoint exactly as the publisher served it, records
the embedding vectors for the articles that survive the health gate, and prints
the headline list you need in order to hand-write `expected.yaml`.

    python scripts/capture_golden_day.py                       # today, 40/source
    python scripts/capture_golden_day.py --max-articles 40
    python scripts/capture_golden_day.py --no-embeddings       # payloads only

The point of storing raw XML rather than parsed articles is that the replay
then exercises the real parse, gate and dedup code, not a snapshot of its
output.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

import numpy as np  # noqa: E402
import yaml  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_DIR / ".env")

from src.eval.golden_day import (  # noqa: E402
    EMBEDDINGS,
    ENDPOINTS_DIR,
    EXPECTED,
    GOLDEN_DAYS_DIR,
    MANIFEST,
    SOURCES,
    TRIAGE,
    embedding_key,
    read_payload,  # noqa: E402
)
from src.scrapers.feeds import FeedIngestor, SourceSpec, default_fetcher  # noqa: E402

EXPECTED_TEMPLATE = """# What the brief for {day} should have contained.
#
# Written by hand, from the headline list the capture script printed. This is
# the human judgement the harness measures against — it is not generated from
# pipeline output, and it should not be edited to make a failing run pass.
day: "{day}"

# Stories a Pakistani reader would expect to see. A story counts as covered
# when `min_keyword_hits` of its keywords appear in a card's headline+summary.
must_have: []

# Things the brief should not contain: opinion columns, advertorials, foreign
# tech/celebrity filler, sport.
must_not_have: []

brief_size:
  min: 10
  max: 12

# Recorded from the first run so the harness ratchets instead of failing on
# day one. Raise it as selection improves; never lower it to make a run pass.
baseline_recall: null
"""


def slugify(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:120]


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a golden-day fixture")
    parser.add_argument("--name", default=None, help="Fixture directory name (default: today)")
    parser.add_argument("--sources", default=str(_BACKEND_DIR / "config" / "sources.yaml"))
    # 40, not 15: at 15 no story clears three publishers, so the corroboration
    # oracle in derive_expectations.py finds nothing and expected.yaml comes back
    # empty. This is the same cap the live pipeline runs at.
    parser.add_argument("--max-articles", type=int, default=40, help="Per-source cap")
    parser.add_argument("--no-embeddings", action="store_true")
    parser.add_argument("--no-triage", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    captured_at = datetime.now(timezone.utc).replace(microsecond=0)
    name = args.name or captured_at.date().isoformat()
    out = GOLDEN_DAYS_DIR / name
    if out.exists() and not args.overwrite:
        print(f"{out} already exists; pass --overwrite to replace it.")
        return 1
    (out / ENDPOINTS_DIR).mkdir(parents=True, exist_ok=True)

    sources_config = yaml.safe_load(Path(args.sources).read_text(encoding="utf-8"))
    specs = SourceSpec.from_config(sources_config)

    # 1. Snapshot every endpoint verbatim ---------------------------------
    endpoints: dict[str, dict] = {}
    for spec in specs:
        for url in list(spec.feed_urls) + list(spec.sitemap_urls):
            status, payload = default_fetcher(url)
            # Gzipped: a day of raw feeds is ~3MB, and these are committed.
            filename = f"{slugify(url)}.xml.gz"
            (out / ENDPOINTS_DIR / filename).write_bytes(gzip.compress(payload))
            endpoints[url] = {"file": filename, "status": status, "bytes": len(payload)}
            print(f"  captured {status} {len(payload):>8}B  {url}")

    # 2. Replay the snapshot through the real ingest ----------------------
    def replay(url: str) -> tuple[int, bytes]:
        record = endpoints.get(url)
        if not record:
            return 404, b""
        return int(record["status"]), read_payload(out / ENDPOINTS_DIR / record["file"])

    result = FeedIngestor(
        specs,
        fetcher=replay,
        now=lambda: captured_at,
        max_articles_per_source=args.max_articles,
    ).run()

    print()
    print(f"articles: {len(result.articles)}   quarantined: {result.degraded_labels}")

    # 3. Record the embedding vectors -------------------------------------
    if not args.no_embeddings:
        from src.agents.embeddings import GeminiEmbeddingProvider

        provider = GeminiEmbeddingProvider()
        keys = [embedding_key(a.headline, a.main_text) for a in result.articles]
        print(f"embedding {len(keys)} articles (paced to the free-tier quota)...")
        embedded = provider.embed_batch(keys, batch_size=50)
        np.savez_compressed(
            out / EMBEDDINGS,
            keys=np.array(keys, dtype=object).astype(str),
            vectors=embedded.embeddings.astype(np.float32),
        )
        print(f"  wrote {EMBEDDINGS} ({(out / EMBEDDINGS).stat().st_size / 1024:.0f} KB)")


    # 3b. Record the triage verdicts --------------------------------------
    if not args.no_triage:
        from src.agents.triage import GeminiTriageService, TriageItem
        from src.utils.urls import canonicalize_url_for_dedup

        items = [
            TriageItem(
                key=canonicalize_url_for_dedup(str(a.url)),
                source=a.source,
                headline=a.headline or "",
                summary=(a.main_text or "")[:400],
                publisher_categories=list((a.metadata or {}).get("publisher_categories") or []),
                url=canonicalize_url_for_dedup(str(a.url)),
            )
            for a in result.articles
        ]
        print(f"triaging {len(items)} articles...")
        triaged = GeminiTriageService().triage(items)
        payload = {key: verdict.as_dict() for key, verdict in triaged.verdicts.items()}
        (out / TRIAGE).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  wrote {TRIAGE}: {len(payload)} verdicts, {triaged.calls} calls, {triaged.failures} failures")

    # 4. Freeze the source config and write the manifest -------------------
    (out / SOURCES).write_text(yaml.safe_dump(sources_config, sort_keys=False), encoding="utf-8")
    (out / MANIFEST).write_text(
        json.dumps(
            {
                "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
                "max_articles_per_source": args.max_articles,
                "article_count": len(result.articles),
                "quarantined": result.degraded_labels,
                "endpoints": endpoints,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    expected_path = out / EXPECTED
    if not expected_path.exists():
        expected_path.write_text(EXPECTED_TEMPLATE.format(day=name), encoding="utf-8")
        print(f"  wrote {EXPECTED} template — fill it in by hand")

    # 5. The headline list a human needs to write the expectations ---------
    print()
    print("=" * 78)
    print("HEADLINES CAPTURED (write expected.yaml from this list)")
    print("=" * 78)
    for source, articles in sorted(result.articles_by_source().items()):
        print(f"\n--- {source} ({len(articles)}) ---")
        for article in articles:
            status = (article.metadata or {}).get("body_status", "?")[:4]
            print(f"  [{status}] {article.headline[:88]}")

    print(f"\nfixture written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
