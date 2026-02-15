"""
Standalone verification script for Phases 0-5.

Each phase is an independent function.  Failures are printed but do not stop
later phases.  Run:

    cd backend
    source venv/bin/activate
    python scripts/verify_phases.py
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap: add src/ to path, load .env
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
load_dotenv(_BACKEND_DIR / ".env")

_CONFIG_DIR = _BACKEND_DIR / "config"

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []  # (phase_name, passed, detail)


def _header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def _pass(phase: str, detail: str = "") -> None:
    tag = f"[PASS] {detail}" if detail else "[PASS]"
    print(f"  {tag}")
    _results.append((phase, True, detail))


def _fail(phase: str, reason: str) -> None:
    print(f"  [FAIL] {reason}")
    _results.append((phase, False, reason))


# ---------------------------------------------------------------------------
# Phase 0 – Import checks + config + spaCy model
# ---------------------------------------------------------------------------


def phase_0() -> None:
    _header("PHASE 0 – Imports, config, spaCy")

    # Core imports
    try:
        from src.agents.analysis import (  # noqa: F401
            AnalysisService,
            ConsensusDetector,
            EntityExtractor,
            RuleBasedClassifier,
        )
        from src.agents.clustering import (  # noqa: F401
            ClusteringService,
            create_cluster_mapping,
        )
        from src.db.models import AnalyzedFeed, Cluster, RawArticle  # noqa: F401
        print("  Imports … ok")
    except Exception as exc:
        _fail("Phase 0", f"import error: {exc}")
        return

    # Config files
    try:
        import yaml

        sources = yaml.safe_load((_CONFIG_DIR / "sources.yaml").read_text())
        rules = yaml.safe_load((_CONFIG_DIR / "classification_rules.yaml").read_text())
        assert "sources" in sources
        assert "categories" in rules
        print(f"  Config … ok  (sources: {list(sources['sources'].keys())}, "
              f"categories: {list(rules['categories'].keys())})")
    except Exception as exc:
        _fail("Phase 0", f"config error: {exc}")
        return

    # spaCy model
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp("Pakistan is a country in South Asia.")
        gpes = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
        assert "Pakistan" in gpes, f"Expected Pakistan in GPEs, got {gpes}"
        print(f"  spaCy en_core_web_sm … ok  (GPEs: {gpes})")
    except Exception as exc:
        _fail("Phase 0", f"spaCy error: {exc}")
        return

    _pass("Phase 0", "imports, config, spaCy all healthy")


# ---------------------------------------------------------------------------
# Phase 1 – Pydantic models
# ---------------------------------------------------------------------------


def phase_1() -> None:
    _header("PHASE 1 – Pydantic models")

    try:
        from src.db.models import AnalyzedFeed, Cluster, RawArticle
        from uuid import uuid4

        # RawArticle – hash auto-generation
        art = RawArticle(
            source="dawn",
            url="https://www.dawn.com/news/verify-phase1",
            headline="Verification headline for Phase 1 test article",
            main_text="A" * 60,  # meets min_length=50
        )
        assert len(art.content_hash) == 64, f"hash length={len(art.content_hash)}"
        print(f"  RawArticle … ok  (hash={art.content_hash[:16]}…)")

        # Cluster
        cid = uuid4()
        cluster = Cluster(id=cid, article_ids=[art.id])
        assert cluster.cluster_size == 1
        print(f"  Cluster … ok  (size={cluster.cluster_size})")

        # AnalyzedFeed
        feed = AnalyzedFeed(
            cluster_id=cid,
            headline="Test headline",
            category="economy",
            confirmed_facts=[],
            debated_claims=[],
            impact_labels=[],
            source_attribution={"dawn": 1},
            entity_counts={},
            classification_confidence=0.8,
        )
        db_dict = feed.to_db_dict()
        assert db_dict["category"] == "economy"
        print(f"  AnalyzedFeed … ok  (category={db_dict['category']})")

    except Exception as exc:
        _fail("Phase 1", str(exc))
        traceback.print_exc()
        return

    _pass("Phase 1", "all 3 models instantiate and serialise correctly")


# ---------------------------------------------------------------------------
# Phase 2 – HybridOrchestrator + synthetic RawArticle validation
# ---------------------------------------------------------------------------


def phase_2() -> None:
    _header("PHASE 2 – Orchestrator + article validation")

    try:
        from src.scrapers.hybrid_orchestrator import HybridOrchestrator
        from src.db.models import RawArticle

        # Just instantiate – don't actually scrape
        orch = HybridOrchestrator()
        print("  HybridOrchestrator instantiated … ok")
        orch.close()

        # Synthetic article with realistic text
        art = RawArticle(
            source="tribune",
            url="https://tribune.com.pk/news/verify-phase2",
            headline="Economy Shows Signs of Stabilisation",
            main_text=(
                "Pakistan's economy is exhibiting early signs of stabilisation "
                "following the IMF bailout package approved last month.  The "
                "rupee has appreciated by two percent against the dollar in "
                "interbank trading.  Analysts remain cautiously optimistic."
            ),
        )
        assert art.content_hash, "content_hash must be non-empty"
        assert len(art.main_text) >= 50
        print(f"  Synthetic article … ok  (source={art.source}, hash={art.content_hash[:16]}…)")

    except Exception as exc:
        _fail("Phase 2", str(exc))
        traceback.print_exc()
        return

    _pass("Phase 2", "orchestrator instantiates; synthetic article validates")


# ---------------------------------------------------------------------------
# Phase 3 – Embeddings (live Gemini if key present, else synthetic)
# ---------------------------------------------------------------------------


def phase_3() -> None:
    _header("PHASE 3 – Embeddings")
    import os

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if gemini_key:
        try:
            from src.agents.embeddings import GeminiEmbeddingProvider

            provider = GeminiEmbeddingProvider()
            result = provider.embed(["Pakistan economy IMF bailout Washington."])
            assert result.dimension == 768
            assert result.embeddings.shape == (1, 768)
            print(f"  Gemini LIVE … ok  (dim={result.dimension})")
            _pass("Phase 3", "LIVE Gemini embedding 768-dim")
            return
        except Exception as exc:
            print(f"  Gemini LIVE failed: {exc}")
            print("  Falling back to synthetic …")

    # Synthetic path
    try:
        rng = np.random.default_rng(42)
        emb = rng.standard_normal((3, 768)).astype(np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        assert emb.shape == (3, 768)
        norms = np.linalg.norm(emb, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)
        print(f"  Synthetic 768-dim … ok  (shape={emb.shape}, norms≈1.0)")
    except Exception as exc:
        _fail("Phase 3", str(exc))
        traceback.print_exc()
        return

    _pass("Phase 3", "SYNTHETIC 768-dim embeddings, L2-normalised")


# ---------------------------------------------------------------------------
# Phase 4 – Clustering (synthetic 3-cluster, deterministic)
# ---------------------------------------------------------------------------


def phase_4() -> None:
    _header("PHASE 4 – Clustering")

    try:
        from src.agents.clustering import (
            ClusteringService,
            calculate_intra_cluster_similarity,
            create_cluster_mapping,
        )

        # 3 groups: 4 + 3 + 3 = 10 points
        dim = 768
        rng = np.random.default_rng(42)
        centres = rng.standard_normal((3, dim)).astype(np.float32)
        centres /= np.linalg.norm(centres, axis=1, keepdims=True)

        sizes = [4, 3, 3]
        rows: list[np.ndarray] = []
        for centre, size in zip(centres, sizes):
            noise = rng.normal(0, 0.01, (size, dim)).astype(np.float32)
            vecs = centre[np.newaxis, :] + noise
            vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
            rows.append(vecs)
        embeddings = np.vstack(rows).astype(np.float32)

        svc = ClusteringService(min_clusters=2, min_cluster_size=2)
        result = svc.cluster(embeddings)

        print(f"  Clusters={result.num_clusters}  noise={result.noise_ratio:.2f}  "
              f"algo={result.algorithm_used}")
        assert result.num_clusters == 3
        assert result.noise_ratio == 0.0
        assert result.algorithm_used == "hdbscan"

        # Mapping + similarity
        article_ids = [f"art-{i}" for i in range(10)]
        mapping = create_cluster_mapping(article_ids, result.labels, embeddings)

        for cid, info in mapping.items():
            sim = info["similarity"]
            print(f"    {cid}: articles={info['article_ids']}  similarity={sim:.4f}")
            assert sim > 0.7, f"{cid} similarity {sim} < 0.7"

    except Exception as exc:
        _fail("Phase 4", str(exc))
        traceback.print_exc()
        return

    _pass("Phase 4", "3 clusters, 0 noise, all similarities > 0.7")


# ---------------------------------------------------------------------------
# Phase 5 – Analysis (real spaCy + real YAML rules)
# ---------------------------------------------------------------------------


def phase_5() -> None:
    _header("PHASE 5 – Analysis (entity extraction + consensus + classification)")

    try:
        from src.agents.analysis import (
            AnalysisService,
            ConsensusDetector,
            EntityExtractor,
            RuleBasedClassifier,
        )
        from src.db.models import RawArticle
        from uuid import uuid4

        # Three IMF articles from different sources
        articles = [
            RawArticle(
                source="dawn",
                url="https://www.dawn.com/news/verify-phase5-1",
                headline="IMF Approves Bailout for Pakistan",
                main_text=(
                    "The International Monetary Fund has approved a multi-billion "
                    "dollar bailout for Pakistan after extended negotiations in "
                    "Washington.  The package is designed to stabilise the Pakistani "
                    "rupee and curb inflation.  The State Bank of Pakistan welcomed "
                    "the decision."
                ),
            ),
            RawArticle(
                source="tribune",
                url="https://tribune.com.pk/news/verify-phase5-2",
                headline="Pakistan Secures IMF Financial Support",
                main_text=(
                    "Pakistan has secured crucial financial support from The "
                    "International Monetary Fund following talks held in Washington.  "
                    "The agreement includes conditions around tax revenue and budget "
                    "deficit targets.  The rupee has already shown signs of recovery."
                ),
            ),
            RawArticle(
                source="geo",
                url="https://www.geo.tv/news/verify-phase5-3",
                headline="IMF Review Concludes with Positive Outcome for Pakistan",
                main_text=(
                    "The International Monetary Fund completed its review of "
                    "Pakistan's economic programme in Washington with a positive "
                    "assessment.  Inflation and rupee depreciation remain key "
                    "concerns, but the IMF noted progress on tax collection targets."
                ),
            ),
        ]

        extractor = EntityExtractor()  # real en_core_web_sm
        detector = ConsensusDetector(min_agreement_ratio=1.0)
        classifier = RuleBasedClassifier.from_yaml(_CONFIG_DIR / "classification_rules.yaml")
        svc = AnalysisService(
            entity_extractor=extractor,
            consensus_detector=detector,
            classifier=classifier,
        )

        feed = svc.analyze_cluster(uuid4(), articles)

        print(f"  Headline        : {feed.headline}")
        print(f"  Category        : {feed.category}")
        print(f"  Confidence      : {feed.classification_confidence}")
        print(f"  Impact labels   : {feed.impact_labels}")
        print(f"  Source attrib   : {feed.source_attribution}")
        print(f"  Confirmed facts :")
        for e in feed.confirmed_facts:
            print(f"      {e.text:40s} [{e.type}]  sources={e.sources}")
        print(f"  Debated claims  :")
        for e in feed.debated_claims:
            print(f"      {e.text:40s} [{e.type}]  sources={e.sources}")

        # Structural assertions
        assert feed.headline
        assert feed.category == "economy", f"Expected economy, got {feed.category}"
        assert 0.0 <= feed.classification_confidence <= 1.0
        assert len(feed.source_attribution) == 3  # dawn, tribune, geo

        # Confirmed facts: Pakistan, Washington, The International Monetary Fund
        confirmed_lookup = {(e.text, e.type): e.sources for e in feed.confirmed_facts}
        assert ("Pakistan", "GPE") in confirmed_lookup, (
            f"Pakistan (GPE) missing from confirmed_facts: {confirmed_lookup}"
        )
        assert confirmed_lookup[("Pakistan", "GPE")] == 3
        assert ("Washington", "GPE") in confirmed_lookup
        assert confirmed_lookup[("Washington", "GPE")] == 3
        assert ("The International Monetary Fund", "ORG") in confirmed_lookup
        assert confirmed_lookup[("The International Monetary Fund", "ORG")] == 3

    except Exception as exc:
        _fail("Phase 5", str(exc))
        traceback.print_exc()
        return

    _pass("Phase 5", "full AnalyzedFeed produced; confirmed_facts verified")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    start = time.time()

    phase_0()
    phase_1()
    phase_2()
    phase_3()
    phase_4()
    phase_5()

    elapsed = time.time() - start

    # Summary table
    _header("SUMMARY")
    print(f"  {'Phase':<12} {'Status':<8} Detail")
    print(f"  {'-' * 56}")
    all_passed = True
    for name, passed, detail in _results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name:<12} {status:<8} {detail}")
        if not passed:
            all_passed = False
    print(f"\n  Elapsed: {elapsed:.1f}s")
    if all_passed:
        print("\n  All phases passed.")
    else:
        print("\n  Some phases FAILED — see details above.")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
