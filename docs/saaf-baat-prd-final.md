# Saaf Baat - Product Requirements Document (PRD)

**Version:** 2.0  
**Last Updated:** February 3, 2026  
**Document Owner:** Product Lead  
**Status:** Final - Technical Implementation Specification

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Solution Overview](#solution-overview)
4. [Target Users](#target-users)
5. [User Stories & Use Cases](#user-stories--use-cases)
6. [Product Principles](#product-principles)
7. [Feature Requirements](#feature-requirements)
8. [Information Architecture](#information-architecture)
9. [Design Specifications](#design-specifications)
10. [Technical Architecture](#technical-architecture)
11. [Detailed Technical Implementation](#detailed-technical-implementation)
12. [Development Phases](#development-phases)
13. [Data & Content Strategy](#data--content-strategy)
14. [Success Metrics](#success-metrics)
15. [Development Roadmap](#development-roadmap)
16. [Risk Assessment](#risk-assessment)
17. [Open Questions & Decisions](#open-questions--decisions)

---

## Executive Summary

### Product Vision
Saaf Baat is a minimalist news intelligence platform that transforms how Pakistanis consume daily news. Instead of aggregating headlines, we synthesize multi-source coverage into clear, factual summaries that separate certainty from debate, highlight personal relevance, and respect user time.

### The Opportunity
- **Market Gap:** Pakistani news consumers spend 30-60 minutes daily across 3-5 news sources, yet still feel confused about what's factual vs. opinion
- **User Pain:** Information overload without clarity—users can't distinguish between confirmed facts and editorial interpretation
- **Behavioral Insight:** Users want to be informed, not entertained; they want utility, not engagement traps

### Core Value Proposition
> "Open once in morning. Know what matters. Close app. Get on with life."

**We deliver:**
1. 5-7 curated stories per day (not 50)
2. Multi-source fact verification (Dawn + Geo + Express Tribune + ARY + others)
3. Clear labeling: "What's Certain" vs "What's Debated"
4. Personal relevance filtering based on location, profession, interests
5. 5-8 minute daily reading time (not 45 minutes)

### Sustainability Model (Open Source / Public Utility)

**Project Identity:**  
Saaf Baat is a **non-profit, open-source initiative** to clean up Pakistan's information ecosystem. We are not a media company. We are a team of developers building a **public utility for clarity**.

**Status:** 100% Free & Open Source (FOSS)

**Philosophy:** "News as a Public Utility"  
- **0% Ads:** We will never sell your attention
- **0% Tracking:** We don't need your data  
- **100% Transparency:** Our code and sorting logic are open for audit

**The Promise:**
- **No Ads:** Strictly prohibited. Adding ads would create an incentive to generate "clicks" instead of "clarity," violating our core purpose.
- **No Paywalls:** Information clarity is a public good, not a commodity
- **No User Tracking:** We don't collect, sell, or monetize user data
- **Open Source Codebase:** Public GitHub repository so anyone can audit our algorithms and verify our neutrality

**Funding Strategy:**
- **Phase 1 (MVP):** Self-funded / bootstrapped using free-tier infrastructure
- **Phase 2 (If Needed):** Community-supported via GitHub Sponsors or similar platforms
- **Long-term:** Potential grants from journalism/civic tech foundations

**Why Open Source:**
1. **Trust Through Transparency:** Users can verify we're not manipulating stories
2. **Community Contribution:** Developers can improve our algorithms
3. **Sustainability:** No VC pressure to "monetize" or compromise principles
4. **Replicability:** Model can be adapted for other countries/languages

---

## Technical Architecture

### System Design Philosophy

Saaf Baat is architected as a **zero-cost, highly maintainable, scalable** system that delivers production-grade quality while remaining completely free to operate. The architecture prioritizes:

- **Robustness:** Multi-tier scraping with fallbacks, error handling, validation at every stage
- **Scalability:** Modular design allows adding new sources without core pipeline changes
- **Quality:** Enterprise-grade embeddings, proven clustering algorithms, transparent rule-based analysis
- **Maintainability:** Clear separation of concerns, well-documented interfaces, configuration-driven components

### Infrastructure & Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Orchestration** | GitHub Actions | Runs entire daily pipeline as scheduled cron job. Zero infrastructure cost. 2,000 minutes/month free (private repos), unlimited for public. |
| **Backend Logic** | Python + FastAPI | Superior data science ecosystem (scikit-learn, spaCy, numpy). Clean architecture for ML pipelines. |
| **Database** | Supabase (PostgreSQL) | Stores raw articles, clusters, analysis. Free tier: 500MB DB + 2GB storage. Real-time API for Next.js. |
| **Scraping (Primary)** | newspaper4k + news-please | newspaper4k: Benchmarked best accuracy, active maintenance, multilingual. news-please: Specialized news extraction as fallback. |
| **Scraping (Dynamic)** | Playwright | Handles JavaScript-heavy sites, forums, lazy-loaded content. Mimics human behavior. |
| **Embeddings (Primary)** | Google Gemini text-embedding-004 | High-quality embeddings. Generous free tier: 100 RPM, 30K tokens/min, 1K req/day. task_type='CLUSTERING' optimized. |
| **Embeddings (Fallback)** | sentence-transformers/all-MiniLM-L6-v2 | Runs locally in GitHub Actions. Zero external dependencies. Automatic activation on API failure. |
| **NLP & Analysis** | spaCy en_core_web_sm + Rule Engine | Fast, accurate NER (18 entity types vs. NLTK's 3). Production-grade, industry standard. Custom rules: transparent, maintainable. |
| **Clustering** | HDBSCAN (primary) + DBSCAN (fallback) | HDBSCAN: Superior for varying densities, auto-determines clusters, handles noise. DBSCAN: Proven fallback. Both scikit-learn compatible. |
| **Classification** | SetFit (sentence-transformers) | Few-shot learning for categories/impact labels. 67x faster than BART-MNLI, higher accuracy. Lightweight (355M params vs. GPT-3's billions). |
| **Frontend** | Next.js (TypeScript) on Vercel | Free Hobby tier. Static generation fetches from Supabase at build time for fast, cached experience. |

---

## Detailed Technical Implementation

### 1. High-Quality, Scalable Scraping Architecture

#### 1.1 Core Scraping Strategy

We implement a **multi-tier scraping system** to ensure robustness and comprehensive coverage of Pakistani news sources:

**Primary Method (Structured News Sites):**
- **Tool:** `newspaper4k` (prioritized due to superior benchmark performance)
- **Approach:** Configure site-specific profiles for Dawn, Tribune, Geo, Express Tribune, ARY, Samaa, etc.
- **Features:** Extracts headline, body text, author, publish date, top image, meta tags
- **Fallback:** `news-please` for additional extraction if newspaper4k fails on specific pages

**Secondary Method (Dynamic Content & Forums):**
- **Tool:** `Playwright` (headless browser)
- **Use Case:** JavaScript-heavy sites, forums (PakWheels, Siasat.pk), social media embeds
- **Approach:** Fully renders pages before extraction. Mimics human scrolling for lazy-loaded content

#### 1.2 Scraping Logic & Data Flow

**Daily Cron Job Schedule: 6:00 AM PKT**

1. **Orchestrator:** Master Python script (`orchestrator.py`) initiates parallel scraping tasks
2. **Scraping Workers:** Each source processed by dedicated function with appropriate method
3. **Data Validation & Cleaning:**
   - Remove boilerplate text (menus, headers, footers) using custom regex and heuristics
   - Validate essential fields: headline, main_text, url, publish_date must be present
   - Standardize date formats to UTC timestamps
   - Detect and filter duplicate articles using content hashing
4. **Storage:** Validated articles written to `raw_articles` table in Supabase with metadata (source, scrape_timestamp, raw_html_backup)

**Key Design Principle:** The scraper is built to be modular and maintainable. Adding a new source requires only creating a new configuration profile and scraping function without altering the core pipeline.

**Scraper Configuration Example:**
```yaml
sources:
  dawn:
    url: "https://www.dawn.com"
    method: "newspaper4k"
    sections: ["latest-news", "pakistan", "business"]
    rate_limit: 1  # seconds between requests
    
  geo_news:
    url: "https://www.geo.tv"
    method: "newspaper4k"
    fallback: "news-please"
    sections: ["latest", "pakistan"]
    
  pakwheels_forum:
    url: "https://www.pakwheels.com/forums"
    method: "playwright"
    scroll_depth: 3  # number of scrolls to trigger lazy loading
```

### 2. Embedding & Clustering Pipeline

#### 2.1 Embedding Service Architecture

We build a dedicated `EmbeddingService` class that abstracts the embedding source, ensuring scalability and reliability:

**Strategy:**

1. **Primary (High-Quality):** Google Gemini `text-embedding-004` API
   - Configure `task_type='CLUSTERING'` for optimal results
   - Batch requests to respect 100 RPM quota
   - Free tier limits: 100 req/min, 30K tokens/min, 1K req/day
   
2. **Fallback (Zero-Cost, Offline):** `sentence-transformers/all-MiniLM-L6-v2`
   - Runs locally in GitHub Actions runner
   - No external API calls or dependencies
   - Activated automatically if Gemini API is unreachable or quota exceeded

**Input:** List of article texts (headline + first 500 characters of main text)

**Output:** Standardized NumPy array of embeddings for all articles

**Implementation Example:**
```python
class EmbeddingService:
    def __init__(self):
        self.primary = GeminiEmbedding(api_key=os.getenv("GEMINI_API_KEY"))
        self.fallback = SentenceTransformerEmbedding(model="all-MiniLM-L6-v2")
        
    async def embed_batch(self, texts: List[str]) -> np.ndarray:
        try:
            # Try Gemini first
            embeddings = await self.primary.embed(
                texts=texts,
                task_type="CLUSTERING"
            )
            return embeddings
        except (QuotaExceeded, APIError) as e:
            logger.warning(f"Gemini API failed: {e}. Falling back to local model.")
            # Automatic fallback to sentence-transformers
            return self.fallback.embed(texts)
```

#### 2.2 Clustering & Story Formation Logic

We employ **HDBSCAN (Hierarchical Density-Based Spatial Clustering)** as our primary clustering algorithm with DBSCAN as fallback:

**Why HDBSCAN over DBSCAN:**
- **Handles varying densities:** News stories naturally have different popularity levels. HDBSCAN adapts to varying cluster densities better than standard DBSCAN
- **Robust parameter selection:** HDBSCAN requires only `min_cluster_size`, while DBSCAN needs careful tuning of `eps` and `min_samples`
- **Better noise handling:** More sophisticated outlier detection for one-off stories
- **Research backing:** Amazon's FSI news clustering uses similar approach for real-time news aggregation

**Process:**

1. **Input:** Embeddings for all new articles from current scrape cycle
2. **Similarity Calculation:** Compute pairwise cosine similarity between all embeddings
3. **Primary Clustering:** Apply HDBSCAN with `min_cluster_size` empirically tuned (typically 3-5 articles)
4. **Fallback:** Use DBSCAN if HDBSCAN fails or produces sub-optimal results (eps ~0.75 for cosine distance)
5. **Output:** Each cluster receives unique `cluster_id`. All articles sharing an ID are about same core story
6. **Storage:** `article_cluster_mappings` table in Supabase updated, linking each article to its cluster

**Implementation Example:**
```python
from hdbscan import HDBSCAN
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_similarity

class StoryClusterer:
    def __init__(self, min_cluster_size=3, min_samples=2):
        self.hdbscan = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric='cosine',
            cluster_selection_method='eom'
        )
        self.dbscan_fallback = DBSCAN(eps=0.75, min_samples=2, metric='cosine')
        
    def cluster_articles(self, embeddings: np.ndarray) -> np.ndarray:
        try:
            # Try HDBSCAN first
            cluster_labels = self.hdbscan.fit_predict(embeddings)
            
            # Validate clustering quality
            if self._is_quality_clustering(cluster_labels):
                return cluster_labels
            else:
                logger.warning("HDBSCAN quality low. Falling back to DBSCAN.")
                return self.dbscan_fallback.fit_predict(embeddings)
        except Exception as e:
            logger.error(f"HDBSCAN failed: {e}. Using DBSCAN.")
            return self.dbscan_fallback.fit_predict(embeddings)
    
    def _is_quality_clustering(self, labels: np.ndarray) -> bool:
        """Check if clustering meets quality thresholds"""
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        noise_ratio = np.sum(labels == -1) / len(labels)
        
        # Quality checks
        return (n_clusters >= 3 and  # At least 3 distinct stories
                noise_ratio < 0.3)    # Less than 30% noise
```

### 3. ML-Powered Classification & Analysis Engine

#### 3.1 Zero-Shot Classification with SetFit

We integrate **SetFit (Sentence Transformer Fine-tuning)** for intelligent categorization and impact labeling:

**Why SetFit:**
- **Efficiency:** 67x faster than BART-large-mnli zero-shot pipeline, with better accuracy
- **Few-shot learning:** Requires minimal training examples (8 per class), leverages pre-trained sentence transformers
- **Lightweight:** 355M parameters (RoBERTa-base) vs. billions for GPT-3, runs efficiently in GitHub Actions
- **Proven performance:** Surpasses GPT-3 on RAFT few-shot classification benchmark

**Implementation:**

1. **Synthetic Example Generation:** Use class names to create synthetic training examples
   - **Categories:** economy, politics, city, education, health, sports, entertainment, crime, infrastructure, international
   - **Impact labels:** 💳 WALLET, 🚦 COMMUTE, 🏢 WORK, 🛡️ SAFETY, ⚡ UTILITIES, 🏛️ GOVERNANCE

2. **Model Training:** Fine-tune sentence transformer (all-roberta-large-v1 or paraphrase-mpnet-base-v2)

3. **Inference:** Apply trained model to article clusters for categorization and impact labeling

4. **Hybrid Approach:** Combine SetFit predictions with rule-based keyword matching for robustness

**Code Example:**
```python
from setfit import SetFitModel, Trainer, TrainingArguments
from sentence_transformers.losses import CosineSimilarityLoss

class NewsClassifier:
    def __init__(self):
        self.category_model = None
        self.impact_model = None
        self._train_models()
    
    def _train_models(self):
        # Define categories with synthetic examples
        category_examples = {
            "economy": [
                "rupee falls against dollar",
                "inflation rate increases",
                "stock market crashes",
                "budget deficit widens"
            ],
            "politics": [
                "election results announced",
                "minister resigns from cabinet",
                "assembly session disrupted",
                "political party holds rally"
            ],
            # ... more categories
        }
        
        # Create training dataset
        train_dataset = self._create_dataset(category_examples)
        
        # Initialize SetFit model
        model = SetFitModel.from_pretrained("sentence-transformers/all-roberta-large-v1")
        
        # Train with minimal examples
        trainer = Trainer(
            model=model,
            train_dataset=train_dataset,
            loss_class=CosineSimilarityLoss,
            num_iterations=20,
            num_epochs=1
        )
        
        trainer.train()
        self.category_model = model
    
    def classify_cluster(self, cluster_text: str) -> Dict[str, Any]:
        """Classify a news cluster"""
        category = self.category_model.predict([cluster_text])[0]
        impact_labels = self.impact_model.predict([cluster_text])
        
        return {
            "category": category,
            "impact_labels": impact_labels,
            "confidence": self.category_model.predict_proba([cluster_text])[0]
        }
```

#### 3.2 Entity Extraction & Consensus Detection

- **Tool:** spaCy `en_core_web_sm` model (superior to NLTK with 18 entity types vs. 3)
- **Process per Cluster:**
  1. Extract named entities (Persons, Organizations, Locations, Dates, Money) from each article
  2. Perform set operations across all articles:
     - **Intersection:** Entities in ALL articles → Label as "CONFIRMED"
     - **Symmetric Difference:** Entities in SOME articles → Label as "DEBATED/INCONSISTENT"
  3. Store results in `cluster_analysis` table with entity status tags

**Implementation Example:**
```python
import spacy
from collections import Counter
from typing import List, Dict, Set

class ConsensusDetector:
    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
    
    def analyze_cluster(self, articles: List[str]) -> Dict[str, Any]:
        """Extract entities and detect consensus across articles"""
        all_entities = []
        entity_by_article = []
        
        # Extract entities from each article
        for article in articles:
            doc = self.nlp(article)
            entities = {
                (ent.text, ent.label_) 
                for ent in doc.ents 
                if ent.label_ in ["PERSON", "ORG", "GPE", "DATE", "MONEY", "EVENT"]
            }
            entity_by_article.append(entities)
            all_entities.extend(entities)
        
        # Find consensus (entities in ALL articles)
        confirmed_entities = set.intersection(*entity_by_article) if entity_by_article else set()
        
        # Find debated (entities in SOME but not ALL articles)
        all_unique = set(all_entities)
        debated_entities = all_unique - confirmed_entities
        
        # Count occurrences
        entity_counts = Counter(all_entities)
        
        return {
            "confirmed_facts": [
                {"text": ent[0], "type": ent[1], "sources": len(articles)}
                for ent in confirmed_entities
            ],
            "debated_claims": [
                {"text": ent[0], "type": ent[1], "sources": entity_counts[ent]}
                for ent in debated_entities
            ],
            "total_sources": len(articles)
        }
```

#### 3.3 Keyword-Based Rules (Supplementary)

Maintainable YAML/JSON configuration for keyword-based classification as backup:

```yaml
categories:
  economy: ["rupee", "dollar", "inflation", "budget", "psx", "imf", "tax", "gdp"]
  politics: ["election", "assembly", "minister", "pti", "pmln", "ppp", "parliament"]
  city: ["karachi", "lahore", "islamabad", "traffic", "water", "municipal"]
  education: ["school", "university", "exam", "student", "degree", "admission"]
  health: ["hospital", "doctor", "disease", "vaccine", "medicine", "treatment"]

impact_labels:
  "💳 WALLET": ["price", "increase", "tax", "salary", "petrol", "bill", "cost", "expensive"]
  "🚦 COMMUTE": ["road", "closed", "accident", "metro", "traffic", "transport", "bus"]
  "🛡️ SAFETY": ["blast", "arrest", "missing", "fire", "attack", "crime", "security"]
  "🏢 WORK": ["strike", "layoff", "hiring", "office", "salary", "promotion"]
  "⚡ UTILITIES": ["electricity", "gas", "water", "loadshedding", "outage", "supply"]
  "🏛️ GOVERNANCE": ["law", "policy", "court", "ruling", "verdict", "regulation"]
```

**Rule Engine Implementation:**
```python
import yaml
from typing import List, Dict

class RuleBasedClassifier:
    def __init__(self, rules_file: str = "classification_rules.yaml"):
        with open(rules_file) as f:
            self.rules = yaml.safe_load(f)
    
    def classify_text(self, text: str) -> Dict[str, Any]:
        """Apply keyword-based rules for classification"""
        text_lower = text.lower()
        
        # Category scoring
        category_scores = {}
        for category, keywords in self.rules['categories'].items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                category_scores[category] = score
        
        # Impact label detection
        impact_labels = []
        for label, keywords in self.rules['impact_labels'].items():
            if any(kw in text_lower for kw in keywords):
                impact_labels.append(label)
        
        # Return top category
        top_category = max(category_scores.items(), key=lambda x: x[1])[0] if category_scores else "general"
        
        return {
            "category": top_category,
            "category_confidence": category_scores.get(top_category, 0),
            "impact_labels": impact_labels
        }
```

### 4. Data Flow & System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     GitHub Actions Runner (Free)                    │
│                                                                     │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Scraper  │→ │ Embedding │→ │Clustering│→ │ Analysis Engine  │  │
│  │ (Python) │  │  Service  │  │  (HDBSCAN)│  │(spaCy + SetFit) │  │
│  └──────────┘  └───────────┘  └──────────┘  └──────────────────┘  │
│       ↓              ↓              ↓              ↓               │
│  Raw Articles → Embeddings → Cluster IDs → Analyzed Data          │
│                                                                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│              Supabase PostgreSQL (Single Source of Truth)          │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐         │
│  │raw_articles  │  │  clusters    │  │ analyzed_feed     │◄────────┤
│  │- id          │  │- cluster_id  │  │- story_card       │  Next.js│
│  │- source      │  │- article_ids │  │- certain_facts    │ Frontend│
│  │- html        │  │- centroid    │  │- debated_items    │         │
│  │- text        │  │- created_at  │  │- impact_label     │         │
│  └──────────────┘  └──────────────┘  └───────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
```

### Project Structure:


production-ready folder tree:

saaf-baat/
│
├── .github/                       # 🤖 AUTOMATION (Runs at root)
│   └── workflows/
│       ├── daily_pipeline.yml     # Triggers the Python Backend daily
│       └── frontend_test.yml      # (Optional) Checks frontend on PRs
│
├── backend/                       # 🧠 THE PYTHON WORKER (Intelligence)
│   ├── config/                    # Rules (YAML files)
│   │   ├── sources.yaml
│   │   └── classification_rules.yaml
│   ├── src/                       # Python Source Code
│   │   ├── scrapers/
│   │   ├── intelligence/
│   │   └── database/
│   ├── main.py                    # Entry point for the worker
│   └── requirements.txt           # Python dependencies (spacy, etc.)
│
├── frontend/                      # 🎨 THE USER INTERFACE (Next.js)
│   ├── app/                       # App Router (Pages & Layouts)
│   │   ├── feed/                  # The main news feed page
│   │   └── story/[id]/            # Individual story page
│   ├── components/                # UI Building Blocks
│   │   ├── StoryCard.tsx          # The Master Card component
│   │   └── ui/                    # Buttons, Badges, Icons
│   ├── lib/                       # Helpers
│   │   └── supabase.ts            # Frontend DB client
│   ├── public/                    # Images & Fonts
│   ├── package.json               # JS dependencies
│   └── next.config.js             # Vercel config
│
├── .gitignore                     # Ignore node_modules and __pycache__
└── README.md                      # Project documentation


we follow these in start then we move along the way scaling, maintable, project for open source for now dont 
put licience or other extra focus on building product first.


### Database Schema

**raw_articles**
```sql
CREATE TABLE raw_articles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(100) NOT NULL,
    url TEXT UNIQUE NOT NULL,
    headline TEXT NOT NULL,
    main_text TEXT NOT NULL,
    author VARCHAR(200),
    publish_date TIMESTAMPTZ NOT NULL,
    scrape_timestamp TIMESTAMPTZ DEFAULT NOW(),
    raw_html_backup TEXT,
    content_hash VARCHAR(64) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**clusters**
```sql
CREATE TABLE clusters (
    cluster_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_ids UUID[] NOT NULL,
    centroid_embedding VECTOR(768),
    num_sources INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**analyzed_feed**
```sql
CREATE TABLE analyzed_feed (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cluster_id UUID REFERENCES clusters(cluster_id),
    headline TEXT NOT NULL,
    category VARCHAR(50),
    confirmed_facts JSONB,
    debated_claims JSONB,
    impact_labels TEXT[],
    source_attribution JSONB,
    relevance_score FLOAT,
    publish_date TIMESTAMPTZ,
    llm_enhanced_summary TEXT,  -- For Phase 2
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Development Phases

### Phase 1: Core Product (8-10 Weeks) - **CURRENT FOCUS**

**Objective:** Deliver a complete, production-ready product with robust ML-powered analysis without LLM dependency

**Features:**
- High-quality news scraping from 20+ Pakistani sources
- Gemini-powered embeddings with sentence-transformers fallback
- HDBSCAN/DBSCAN clustering for story aggregation
- spaCy NER for entity extraction and consensus detection
- SetFit zero-shot classification for categories and impact labels
- Rule-based keyword matching as supplementary classifier
- Next.js frontend with real-time Supabase integration
- Fully automated daily pipeline via GitHub Actions

**Key Deliverables:**
- Story cards showing: headline, confirmed facts, debated claims, source attribution, impact labels
- Category filters: Economy, Politics, City News, Education, Health, etc.
- Impact badges: 💳 Wallet, 🚦 Commute, 🏢 Work, 🛡️ Safety, etc.
- Source transparency: Show which outlets reported what

**Timeline Breakdown:**
- **Weeks 1-2:** Infrastructure setup, scraper architecture, initial source integration
- **Weeks 3-4:** Embedding service, clustering pipeline, Supabase schema
- **Weeks 5-6:** NLP analysis engine (spaCy, SetFit), rule-based classification
- **Weeks 7-8:** Next.js frontend, story card UI, filtering & search
- **Weeks 9-10:** Testing, optimization, beta launch

### Phase 2: LLM Enhancement (4-6 Weeks) - **FUTURE**

**Objective:** Add optional LLM capabilities for nuanced summaries and deeper analysis while maintaining Phase 1 as fallback

**Additional Features:**
- **Gemini Flash integration:** Generate human-readable summaries from rule-based analysis
- **Bias detection:** LLM analyzes sentiment differences across sources
- **Context generation:** "Why this matters" explanations for complex stories
- **Final judge:** LLM arbitrates when rule-based system is uncertain
- **Graceful degradation:** System falls back to Phase 1 outputs if LLM unavailable

**Implementation Approach:**
- `analyzed_feed` table gains `llm_enhanced_summary` field
- Separate optional process sends Phase 1 results to Gemini Flash
- Frontend displays LLM summaries when available, Phase 1 data otherwise
- Core pipeline remains unchanged and LLM-independent

**Timeline Breakdown:**
- **Weeks 1-2:** Gemini Flash integration, prompt engineering
- **Weeks 3-4:** Enhanced summaries, bias detection, context generation
- **Weeks 5-6:** Frontend updates, A/B testing, rollout

---

## Key Design Decisions & Rationale

### Why Gemini Embeddings?
- **Quality:** State-of-the-art performance comparable to OpenAI's models
- **Generosity:** 100 RPM, 30K tokens/min, 1K req/day on free tier vs. OpenAI's 3K tokens/min
- **Optimization:** `task_type='CLUSTERING'` parameter fine-tunes for our use case
- **Fallback:** Local sentence-transformers ensure zero downtime

### Why HDBSCAN over K-Means?
- **No pre-defined K:** News story count varies daily. HDBSCAN auto-determines clusters
- **Varying densities:** Some stories covered by 20+ outlets, others by 2-3. HDBSCAN handles this
- **Noise detection:** Automatically identifies one-off stories as outliers
- **Research backing:** Amazon's FSI news clustering uses similar approach for real-time news

### Why spaCy over NLTK?
- **Production-grade:** Industry standard, optimized for speed and accuracy
- **Better NER:** 18 entity types (PERSON, ORG, GPE, DATE, MONEY, etc.) vs. NLTK's 3
- **Context awareness:** Uses dependency parsing for higher accuracy
- **Performance:** ~5x faster than NLTK on large documents

### Why SetFit over Traditional Classifiers?
- **Few-shot efficiency:** Requires only 8 examples per class vs. thousands for traditional ML
- **Speed:** 67x faster than BART-large-mnli, 5x faster than transformers pipeline
- **Accuracy:** Outperforms GPT-3 on RAFT benchmark despite being 30x smaller
- **Flexibility:** Easy to add new categories or impact labels without retraining from scratch

### Why newspaper4k over Other Scrapers?
- **Benchmark performance:** Consistently highest accuracy in article extraction benchmarks
- **Active maintenance:** Regular updates, bug fixes, modern Python support
- **Multilingual support:** Handles both English and Urdu content
- **Rich extraction:** Gets headline, body, author, date, images, meta tags in one pass

### Why GitHub Actions?
- **Zero cost:** 2,000 minutes/month free for private repos, unlimited for public
- **Sufficient compute:** 2-core CPU, 7GB RAM, 14GB SSD handles our ML workload
- **Scheduling:** Built-in cron support for daily runs
- **Version control:** Pipeline code lives with application code

---

## Success Metrics & KPIs

### Technical Metrics
- **Scraping success rate:** >95% of configured sources successfully scraped daily
- **Clustering quality:** Average cluster cohesion >0.7 (cosine similarity within cluster)
- **Entity extraction accuracy:** >85% precision on manual spot-checks
- **Pipeline execution time:** <30 minutes for full daily run
- **Classification accuracy:** >80% for categories, >75% for impact labels
- **System uptime:** >99.5% (excluding scheduled maintenance)

### User Experience Metrics
- **Time to insight:** <5 seconds to understand day's major stories
- **Engagement:** Average session >3 minutes, >5 story cards viewed
- **Retention:** >40% day-7 retention, >20% day-30 retention
- **User satisfaction:** Net Promoter Score (NPS) >30
- **Reading completion:** >60% of expanded cards read to end

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Website structure changes break scrapers | High | Medium | Multi-tier scraping with fallbacks. Automated alerts on failures. Easy config updates. |
| Gemini API quota exceeded | Medium | Low | Automatic fallback to sentence-transformers. Monitor usage. Implement batching/caching. |
| Poor clustering quality | High | Medium | Empirical parameter tuning. A/B testing. Manual review dashboard. HDBSCAN fallback to DBSCAN. |
| Supabase free tier limits hit | Medium | Low | Monitor usage closely. Optimize queries. Plan migration to self-hosted Postgres if needed. |
| GitHub Actions compute limits | Low | Low | Optimize pipeline efficiency. Cache intermediate results. Consider self-hosted runners. |

### Sustainability & Growth Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Unable to sustain $0 infrastructure | High | Low | Architect with free-tier tools. Monitor costs. Community funding as backup. |
| Low user adoption | High | Medium | Start with early adopters. Word-of-mouth growth. Clear value prop demonstration. |
| Sources block scraping | Medium | Medium | Respect robots.txt. Add delays. Use multiple IPs if needed. Playwright for JS sites. |
| Accuracy/quality issues damage trust | High | Low | Transparent methodology. User feedback loops. Manual review for sensitive topics. |

---

## Open Questions & Decisions Needed

### Product Decisions

**Q1: Should we show stories with only 2 sources?**
- **Pro:** More coverage, faster breaking news
- **Con:** Less reliable fact verification
- **Decision:** Start with 3+ sources minimum. Revisit after Month 2.

**Q2: How do we handle Urdu vs English preference?**
- **Option A:** Separate feeds (Urdu users see Urdu sources only)
- **Option B:** Unified feed, language toggle on each story
- **Decision:** TBD - test with bilingual users

**Q3: Should "breaking news" have push notifications?**
- **Pro:** Users get critical updates faster
- **Con:** Violates "respect user time" principle
- **Decision:** Opt-in only. Default is silent badge.

**Q4: Do we need user accounts or use anonymous tracking?**
- **Option A:** Account-based (email login)
- **Option B:** Anonymous (localStorage + cookie)
- **Decision:** Start anonymous (lower friction). Add accounts in Phase 2 for sync across devices.

### Technical Decisions

**Q5: Which clustering algorithm to use in production?**
- **HDBSCAN:** Better for varying densities, auto-determines K
- **DBSCAN:** Simpler, proven, requires parameter tuning
- **Decision:** ✅ **HDBSCAN primary, DBSCAN fallback** based on research and Amazon FSI use case

**Q6: Self-host or use managed services?**
- **Self-hosted:** More control, lower long-term cost
- **Managed (Vercel, Supabase):** Faster development, scalability
- **Decision:** Managed for MVP. Evaluate self-hosting at 10,000 DAU.

**Q7: How often to scrape sources?**
- **Option A:** Every 30 min (catch breaking news faster)
- **Option B:** Once daily at 6am (simpler, cheaper)
- **Decision:** Daily at 6am for MVP. Add hourly scraping for breaking news in Phase 2.

**Q8: Use SetFit or purely rule-based classification?**
- **SetFit:** More accurate, adaptable, requires minimal training
- **Rules only:** Simpler, fully transparent, easier to debug
- **Decision:** ✅ **Hybrid: SetFit primary, rules as backup** for robustness and quality

---

## Document Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | Jan 30, 2026 | Initial draft | Product Lead |
| 0.5 | Feb 1, 2026 | Added technical architecture | Engineering Lead |
| 1.0 | Feb 3, 2026 | Complete PRD for review | Product Lead |
| 1.1 | Feb 3, 2026 | Strategic pivots: Replaced passive learning with explicit mute filters (F5), added Topic Bundle feature (F1.5), updated Share mechanism with image generation (F10), implemented Unified Master Card architecture, introduced Headline Consensus algorithm, updated color psychology (amber for debated vs red for critical only) | Product Lead |
| 1.2 | Feb 3, 2026 | Final strategic refinements: Elastic Feed with dynamic volume (F1), Two-Tier Breaking News with Developing/Unverified alerts (F8), Progressive Disclosure card states, Dynamic Impact Labels (💳WALLET, 🚦COMMUTE, 🛡️SAFETY, 🏛️REALITY), Action vs. Statement filter for story selection, updated Q10 decision (category filtering via Mute implemented) | Product Lead |
| 1.3 | Feb 3, 2026 | Open Source / Public Utility pivot: Removed all business/monetization sections, replaced Business Model with Sustainability Model (100% FOSS), implemented "$0 Stack" infrastructure strategy (Vercel Hobby + Supabase Free + GitHub Actions), AI model decision pending (researching free/open-source LLMs), updated X5 reason (non-profit public service), renamed Business Risks to Sustainability & Growth Risks, removed B2B/revenue from Phase 3 roadmap | Product Lead |
| **2.0** | **Feb 3, 2026** | **Complete technical implementation specification: Detailed scraping architecture (newspaper4k + Playwright), Gemini embeddings with sentence-transformers fallback, HDBSCAN clustering with DBSCAN fallback, spaCy NER for consensus detection, SetFit for zero-shot classification, rule-based keyword engine, complete database schema, Phase 1 vs Phase 2 roadmap, comprehensive code examples, design decisions with research backing** | **Technical Lead** |

---

## Next Steps

1. **Review this PRD** with stakeholders (engineering, design)
2. **Set up development environment** (GitHub repo, Actions, Supabase project)
3. **Implement Phase 1 Week 1-2:** Scraping infrastructure with newspaper4k and Playwright
4. **Create technical spec** for embedding service and clustering pipeline
5. **Design mockups** based on design specifications
6. **Begin development** following 8-10 week timeline
7. **Establish monitoring** for scraping success rates and pipeline health

---

**Questions or feedback?** Create an issue on GitHub or contact the project lead.

**This is a living document.** Updates tracked in change log above.
