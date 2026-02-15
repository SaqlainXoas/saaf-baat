"""
End-to-end deterministic test for Phase 4 (Clustering) + Phase 5 (Analysis).

No network calls, no API keys, no database.  Synthetic 768-dim embeddings are
generated with a fixed seed so the test is fully reproducible.

Flow
----
1. 10 synthetic RawArticles in 3 topical groups:
     - IMF / economy  : articles 0-3  (4 articles)
     - security       : articles 4-6  (3 articles)
     - city / traffic : articles 7-9  (3 articles)
2. Synthetic embeddings: 3 random unit-vector centres (seed=42), noise=0.01,
   L2-normalised.  Articles are assigned to centres by group.
3. ClusteringService(min_clusters=2, min_cluster_size=2).cluster(embeddings)
   → expect 3 clusters, 0 noise, algorithm=hdbscan.
4. create_cluster_mapping(…) → per-cluster similarity > 0.7.
5. AnalysisService with real spaCy + real YAML rules on each cluster.
6. Per-cluster assertions (see inline comments).
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from src.agents.analysis import (
    AnalysisService,
    ConsensusDetector,
    EntityExtractor,
    RuleBasedClassifier,
)
from src.agents.clustering import ClusteringService, create_cluster_mapping
from src.db.models import RawArticle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _make_article(source: str, headline: str, main_text: str, idx: int) -> RawArticle:
    return RawArticle(
        id=uuid4(),
        source=source,
        url=f"https://test.example.com/e2e-{idx}",
        headline=headline,
        main_text=main_text,
    )


def _generate_embeddings(group_sizes: list[int], dim: int = 768, seed: int = 42) -> np.ndarray:
    """Create tight clusters around random unit-vector centres."""
    rng = np.random.default_rng(seed)

    n_groups = len(group_sizes)
    centres = rng.standard_normal((n_groups, dim)).astype(np.float32)
    # L2-normalise centres
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)

    rows: list[np.ndarray] = []
    for centre, size in zip(centres, group_sizes):
        noise = rng.normal(0, 0.01, size=(size, dim)).astype(np.float32)
        vecs = centre[np.newaxis, :] + noise
        # L2-normalise each vector
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        rows.append(vecs)

    return np.vstack(rows).astype(np.float32)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

IMF_ARTICLES = [
    _make_article(
        "dawn",
        "IMF Approves Bailout for Pakistan",
        "The International Monetary Fund has approved a multi-billion dollar bailout "
        "for Pakistan after extended negotiations in Washington. The package is designed "
        "to stabilise the Pakistani rupee and curb inflation. The State Bank of Pakistan "
        "welcomed the decision, saying it will boost investor confidence. Economists "
        "expect the rupee to strengthen against the dollar in the coming weeks.",
        0,
    ),
    _make_article(
        "tribune",
        "Pakistan Secures IMF Financial Support",
        "Pakistan has secured crucial financial support from The International Monetary "
        "Fund following talks held in Washington. The agreement includes conditions around "
        "tax revenue and budget deficit targets. Finance Minister briefed the assembly on "
        "the deal, highlighting the importance of IMF backing for economic stability. "
        "The rupee has already shown signs of recovery in interbank trading.",
        1,
    ),
    _make_article(
        "geo",
        "IMF Review Concludes with Positive Outcome for Pakistan",
        "The International Monetary Fund completed its review of Pakistan's economic "
        "programme in Washington with a positive assessment. Inflation and rupee "
        "depreciation remain key concerns, but the IMF noted progress on tax collection "
        "targets. The State Bank of Pakistan said foreign reserves have improved "
        "marginally. Markets reacted positively to the news.",
        2,
    ),
    _make_article(
        "dawn",
        "Economy Shows Signs of Recovery After IMF Deal",
        "Pakistan's economy is showing early signs of recovery following the "
        "International Monetary Fund bailout agreed in Washington. GDP growth "
        "forecasts have been revised upward by international analysts. The "
        "rupee gained ground against the dollar in currency markets. "
        "Tax revenue collection exceeded targets for the first time this fiscal year.",
        3,
    ),
]

SECURITY_ARTICLES = [
    _make_article(
        "dawn",
        "Security Forces Neutralise Militant Cell in Balochistan",
        "Pakistan security forces conducted a successful operation against a "
        "militant cell in Balochistan, neutralising three terrorists. The "
        "police confirmed the incident after a dawn raid. Law enforcement "
        "officials praised the security team for preventing a major attack. "
        "The operation was carried out following intelligence warnings.",
        4,
    ),
    _make_article(
        "tribune",
        "Police Arrest Terror Suspects in Karachi",
        "Karachi police arrested five suspects linked to a terror network "
        "following an overnight security operation. The crime investigation "
        "unit said the suspects were planning an attack on critical "
        "infrastructure. Security alerts have been issued across the city. "
        "Law enforcement agencies are coordinating with federal authorities.",
        5,
    ),
    _make_article(
        "geo",
        "Terror Incident Averted in Lahore Thanks to Police Action",
        "A potential terror incident was averted in Lahore after police "
        "arrested individuals planning an attack on a public gathering. "
        "The security establishment confirmed the plot was disrupted in time. "
        "Crime prevention units have been placed on high alert across Punjab. "
        "The incident highlights ongoing security challenges in the country.",
        6,
    ),
]

CITY_ARTICLES = [
    _make_article(
        "dawn",
        "Metro Bus Route Extended to New Islamabad Sectors",
        "The Islamabad metro bus service has been extended to cover three "
        "new residential sectors, improving transport connectivity for "
        "thousands of commuters. The municipal authority announced the "
        "infrastructure upgrade after months of construction. Traffic on "
        "the main highway is expected to ease as more residents use public transport.",
        7,
    ),
    _make_article(
        "tribune",
        "Lahore Traffic Snarls Due to Road Construction",
        "Lahore residents faced severe traffic congestion today as road "
        "construction work blocked a major highway route. The municipal "
        "corporation issued an advisory for commuters to use alternative "
        "transport options. Metro bus services are running on time and "
        "remain the best option for those travelling through the city centre.",
        8,
    ),
    _make_article(
        "geo",
        "Islamabad Infrastructure Project Nears Completion",
        "A major infrastructure project in Islamabad is nearing completion "
        "and is expected to significantly reduce traffic on arterial roads. "
        "The municipal authority confirmed that the metro extension will be "
        "operational by next month. Transport planners say the project will "
        "benefit over two hundred thousand daily commuters.",
        9,
    ),
]

ALL_ARTICLES = IMF_ARTICLES + SECURITY_ARTICLES + CITY_ARTICLES
GROUP_SIZES = [len(IMF_ARTICLES), len(SECURITY_ARTICLES), len(CITY_ARTICLES)]  # [4, 3, 3]


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


def test_e2e_phases4_5():
    # ---- Phase 4: Clustering ------------------------------------------------
    embeddings = _generate_embeddings(GROUP_SIZES)
    assert embeddings.shape == (10, 768)

    service = ClusteringService(min_clusters=2, min_cluster_size=2)
    result = service.cluster(embeddings)

    assert result.num_clusters == 3, f"Expected 3 clusters, got {result.num_clusters}"
    assert result.noise_ratio == 0.0, f"Expected 0 noise, got {result.noise_ratio}"
    assert result.algorithm_used == "hdbscan"

    # ---- Cluster mapping & similarity ----------------------------------------
    article_ids = [str(a.id) for a in ALL_ARTICLES]
    mapping = create_cluster_mapping(article_ids, result.labels, embeddings)

    assert len(mapping) == 3

    for cid, info in mapping.items():
        assert info["similarity"] > 0.7, (
            f"Cluster {cid} similarity {info['similarity']:.3f} < 0.7"
        )

    # ---- Phase 5: Analysis ---------------------------------------------------
    rules_path = _CONFIG_DIR / "classification_rules.yaml"
    extractor = EntityExtractor()  # real en_core_web_sm
    detector = ConsensusDetector(min_agreement_ratio=1.0)
    classifier = RuleBasedClassifier.from_yaml(rules_path)
    analysis_svc = AnalysisService(
        entity_extractor=extractor,
        consensus_detector=detector,
        classifier=classifier,
    )

    # Build label → article group mapping from clustering output
    label_to_articles: dict[int, list[RawArticle]] = {}
    for idx, label in enumerate(result.labels):
        label_to_articles.setdefault(int(label), []).append(ALL_ARTICLES[idx])

    # Identify which cluster label corresponds to which group by checking
    # which articles ended up together (indices 0-3 = IMF, 4-6 = security, 7-9 = city)
    label_to_group: dict[int, str] = {}
    for label, arts in label_to_articles.items():
        indices = {ALL_ARTICLES.index(a) for a in arts}
        if indices <= {0, 1, 2, 3}:
            label_to_group[label] = "imf"
        elif indices <= {4, 5, 6}:
            label_to_group[label] = "security"
        elif indices <= {7, 8, 9}:
            label_to_group[label] = "city"
        else:
            pytest.fail(f"Cluster label {label} mixes article groups: indices={indices}")

    analyzed: dict[str, object] = {}
    for label, arts in label_to_articles.items():
        cluster_uuid = uuid4()
        feed = analysis_svc.analyze_cluster(cluster_uuid, arts)
        analyzed[label_to_group[label]] = feed

    # ---- Per-cluster assertions ----------------------------------------------

    # IMF / economy cluster
    imf_feed = analyzed["imf"]
    assert imf_feed.category == "economy", (
        f"IMF cluster category={imf_feed.category}, expected economy"
    )
    assert "💳 WALLET" in imf_feed.impact_labels, (
        f"IMF cluster impact_labels={imf_feed.impact_labels}, expected WALLET"
    )
    confirmed_texts = {e.text for e in imf_feed.confirmed_facts}
    assert "Pakistan" in confirmed_texts, (
        f"IMF confirmed_facts texts={confirmed_texts}, expected Pakistan"
    )

    # Security cluster
    sec_feed = analyzed["security"]
    assert sec_feed.category == "security", (
        f"Security cluster category={sec_feed.category}, expected security"
    )
    assert "🛡️ SAFETY" in sec_feed.impact_labels, (
        f"Security cluster impact_labels={sec_feed.impact_labels}, expected SAFETY"
    )

    # City / traffic cluster — NER for city names is imprecise, so only structural checks
    city_feed = analyzed["city"]
    assert city_feed.headline, "City cluster headline must be non-empty"
    assert 0.0 <= city_feed.classification_confidence <= 1.0
    assert len(city_feed.source_attribution) > 0

    # ---- Universal assertions (all clusters) ---------------------------------
    for group_name, feed in analyzed.items():
        assert feed.headline, f"{group_name}: headline must be non-empty"
        assert feed.classification_confidence is not None
        assert 0.0 <= feed.classification_confidence <= 1.0, (
            f"{group_name}: confidence {feed.classification_confidence} out of [0,1]"
        )
        assert len(feed.source_attribution) > 0, (
            f"{group_name}: source_attribution must be non-empty"
        )
