"""
Scraper orchestrator for coordinating multi-source scraping.

Handles:
- Parallel scraping with asyncio
- Automatic method selection (newspaper4k -> news-please -> playwright)
- Rate limiting and error handling
- Deduplication
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import yaml

from src.db.models import RawArticle
from src.scrapers.base import (
    BaseScraper,
    ContentExtractionError,
    InvalidURLError,
    ScrapingError,
)
from src.scrapers.newspaper4k_scraper import Newspaper4kScraper
from src.scrapers.newsplease_scraper import NewsPleaseScraaper
from src.scrapers.playwright_scraper import PlaywrightScraper


logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Invalid scraper configuration."""
    pass


@dataclass
class SourceConfig:
    """Configuration for a news source."""
    name: str
    url: str
    method: str = "newspaper4k"  # newspaper4k, newsplease, playwright
    sections: List[str] = field(default_factory=list)
    rate_limit: float = 1.0
    max_articles: int = 50
    language: str = "en"
    enabled: bool = True
    # Playwright-specific
    wait_for_selector: Optional[str] = None
    scroll_depth: int = 3


@dataclass
class ScrapingResult:
    """Result from scraping operation."""
    source: str
    articles: List[RawArticle]
    errors: List[str]
    duration_seconds: float
    method_used: str


def load_scraper_config(config_path: str) -> Dict[str, Any]:
    """
    Load scraper configuration from YAML file.
    
    Args:
        config_path: Path to sources.yaml
        
    Returns:
        Parsed configuration dict
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigValidationError(f"Config file not found: {config_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    validate_scraper_config(config)
    return config


def validate_scraper_config(config: Dict[str, Any]) -> None:
    """
    Validate scraper configuration.
    
    Args:
        config: Configuration dict to validate
        
    Raises:
        ConfigValidationError: If config is invalid
    """
    if not config:
        raise ConfigValidationError("Empty configuration")
    
    if "sources" not in config:
        raise ConfigValidationError("Missing 'sources' key in configuration")
    
    sources = config["sources"]
    if not isinstance(sources, dict):
        raise ConfigValidationError("'sources' must be a dictionary")
    
    valid_methods = {"newspaper4k", "newsplease", "playwright"}
    
    for source_name, source_config in sources.items():
        if not isinstance(source_config, dict):
            raise ConfigValidationError(f"Source '{source_name}' must be a dictionary")
        
        # Check required fields
        if "url" not in source_config:
            raise ConfigValidationError(f"Source '{source_name}' missing 'url' field")
        
        # Validate method
        method = source_config.get("method", "newspaper4k")
        if method not in valid_methods:
            raise ConfigValidationError(
                f"Source '{source_name}' has invalid method '{method}'. "
                f"Valid methods: {valid_methods}"
            )


class ScraperOrchestrator:
    """
    Orchestrates scraping across multiple news sources.
    
    Features:
    - Parallel scraping with configurable workers
    - Automatic fallback (newspaper4k -> news-please -> playwright)
    - Deduplication via content hash
    - Centralized error handling and logging
    """
    
    # Scraper class mapping
    SCRAPER_CLASSES: Dict[str, Type[BaseScraper]] = {
        "newspaper4k": Newspaper4kScraper,
        "newsplease": NewsPleaseScraaper,
        "playwright": PlaywrightScraper,
    }
    
    # Fallback order
    FALLBACK_ORDER = ["newspaper4k", "newsplease", "playwright"]
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        sources: Optional[List[str]] = None,
        max_workers: int = 4,
        enable_fallback: bool = True,
    ):
        """
        Initialize orchestrator.
        
        Args:
            config_path: Path to sources.yaml config file
            sources: Optional list of source names to use (filters config)
            max_workers: Maximum parallel workers for scraping
            enable_fallback: Whether to try alternative scrapers on failure
        """
        self.config_path = config_path or "config/sources.yaml"
        self.max_workers = max_workers
        self.enable_fallback = enable_fallback
        
        # Load configuration
        self._config = load_scraper_config(self.config_path)
        self._source_configs: Dict[str, SourceConfig] = {}
        
        # Parse source configurations
        for name, cfg in self._config["sources"].items():
            if sources is not None and name not in sources:
                continue
            if not cfg.get("enabled", True):
                continue
            
            self._source_configs[name] = SourceConfig(
                name=name,
                url=cfg["url"],
                method=cfg.get("method", "newspaper4k"),
                sections=cfg.get("sections", []),
                rate_limit=cfg.get("rate_limit", 1.0),
                max_articles=cfg.get("max_articles", 50),
                language=cfg.get("language", "en"),
                enabled=cfg.get("enabled", True),
                wait_for_selector=cfg.get("wait_for_selector"),
                scroll_depth=cfg.get("scroll_depth", 3),
            )
        
        # Track seen content hashes for deduplication
        self._seen_hashes: set = set()
        
        logger.info(f"Orchestrator initialized with {len(self._source_configs)} sources")
    
    @property
    def total_sources(self) -> int:
        """Total number of configured sources."""
        return len(self._source_configs)
    
    def _create_scraper(self, source_config: SourceConfig, method: str) -> BaseScraper:
        """Create scraper instance for given source and method."""
        scraper_class = self.SCRAPER_CLASSES[method]
        
        kwargs: Dict[str, Any] = {
            "source": source_config.name,
            "base_url": source_config.url,
            "rate_limit": source_config.rate_limit,
        }
        
        if method == "newspaper4k":
            kwargs["language"] = source_config.language
        elif method == "playwright":
            kwargs["wait_for_selector"] = source_config.wait_for_selector
            kwargs["scroll_depth"] = source_config.scroll_depth
        
        return scraper_class(**kwargs)
    
    def scrape_url(self, url: str, source: str = "unknown") -> Optional[RawArticle]:
        """
        Scrape a single URL with automatic fallback.
        
        Args:
            url: Article URL to scrape
            source: Source name for the article
            
        Returns:
            RawArticle if successful, None if all methods fail
        """
        methods = self.FALLBACK_ORDER if self.enable_fallback else [self.FALLBACK_ORDER[0]]
        
        for method in methods:
            try:
                # Create temporary config
                temp_config = SourceConfig(name=source, url=url, method=method)
                scraper = self._create_scraper(temp_config, method)
                
                with scraper:
                    article = scraper.extract_article(url)
                    logger.info(f"Scraped {url} using {method}")
                    return article
                    
            except (ContentExtractionError, InvalidURLError) as e:
                logger.warning(f"Method {method} failed for {url}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error with {method} for {url}: {e}")
                continue
        
        logger.error(f"All methods failed for {url}")
        return None
    
    def scrape_source(self, source_name: str) -> ScrapingResult:
        """
        Scrape all articles from a single source.
        
        Args:
            source_name: Name of the source to scrape
            
        Returns:
            ScrapingResult with articles and errors
        """
        start_time = datetime.now()
        articles: List[RawArticle] = []
        errors: List[str] = []
        method_used = ""
        
        if source_name not in self._source_configs:
            errors.append(f"Unknown source: {source_name}")
            return ScrapingResult(
                source=source_name,
                articles=[],
                errors=errors,
                duration_seconds=0,
                method_used="none",
            )
        
        source_config = self._source_configs[source_name]
        methods = (
            self.FALLBACK_ORDER if self.enable_fallback else [source_config.method]
        )
        
        # Start with configured method
        if source_config.method in methods:
            methods.remove(source_config.method)
            methods.insert(0, source_config.method)
        
        for method in methods:
            try:
                scraper = self._create_scraper(source_config, method)
                
                with scraper:
                    # Get section URLs
                    section_urls = source_config.sections or [source_config.url]
                    
                    for section_url in section_urls:
                        try:
                            scraped = scraper.scrape_section(
                                section_url,
                                max_articles=source_config.max_articles,
                            )
                            
                            # Deduplicate
                            for article in scraped:
                                if article.content_hash not in self._seen_hashes:
                                    self._seen_hashes.add(article.content_hash)
                                    articles.append(article)
                                else:
                                    logger.debug(f"Duplicate skipped: {article.url}")
                                    
                        except Exception as e:
                            errors.append(f"Section {section_url}: {e}")
                    
                    if articles:
                        method_used = method
                        break  # Success, don't try fallback
                        
            except Exception as e:
                errors.append(f"Method {method}: {e}")
                continue
        
        duration = (datetime.now() - start_time).total_seconds()
        
        logger.info(
            f"Scraped {len(articles)} articles from {source_name} "
            f"in {duration:.2f}s using {method_used or 'none'}"
        )
        
        return ScrapingResult(
            source=source_name,
            articles=articles,
            errors=errors,
            duration_seconds=duration,
            method_used=method_used or "none",
        )
    
    def scrape_all_sources(self) -> List[RawArticle]:
        """
        Scrape all configured sources in parallel.
        
        Returns:
            Combined list of articles from all sources
        """
        all_articles: List[RawArticle] = []
        all_results: List[ScrapingResult] = []
        
        start_time = datetime.now()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.scrape_source, source_name): source_name
                for source_name in self._source_configs.keys()
            }
            
            for future in as_completed(futures):
                source_name = futures[future]
                try:
                    result = future.result()
                    all_results.append(result)
                    all_articles.extend(result.articles)
                except Exception as e:
                    logger.error(f"Failed to scrape {source_name}: {e}")
        
        total_duration = (datetime.now() - start_time).total_seconds()
        
        # Log summary
        total_errors = sum(len(r.errors) for r in all_results)
        successful_sources = sum(1 for r in all_results if r.articles)
        
        logger.info(
            f"Scraping complete: {len(all_articles)} articles from "
            f"{successful_sources}/{len(self._source_configs)} sources "
            f"in {total_duration:.2f}s ({total_errors} errors)"
        )
        
        return all_articles
    
    def get_scraping_summary(self) -> Dict[str, Any]:
        """Get summary of configured sources and their status."""
        return {
            "total_sources": self.total_sources,
            "sources": {
                name: {
                    "url": cfg.url,
                    "method": cfg.method,
                    "sections": len(cfg.sections),
                    "enabled": cfg.enabled,
                }
                for name, cfg in self._source_configs.items()
            },
            "fallback_enabled": self.enable_fallback,
            "max_workers": self.max_workers,
        }
