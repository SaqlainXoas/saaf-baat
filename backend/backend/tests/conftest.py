"""
Shared pytest fixtures for all tests.
"""
import sys
from pathlib import Path

import pytest
import yaml

# Add src to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir / "src"))


@pytest.fixture
def config_dir():
    """Return path to config directory."""
    return backend_dir / "config"


@pytest.fixture
def sources_config(config_dir):
    """Load sources.yaml configuration."""
    with open(config_dir / "sources.yaml", "r") as f:
        return yaml.safe_load(f)


@pytest.fixture
def classification_config(config_dir):
    """Load classification_rules.yaml configuration."""
    with open(config_dir / "classification_rules.yaml", "r") as f:
        return yaml.safe_load(f)


@pytest.fixture
def sample_article():
    """Sample article for testing."""
    return {
        "source": "dawn",
        "url": "https://www.dawn.com/news/test-article",
        "headline": "Test Article Headline",
        "main_text": "This is a test article about economy and inflation in Pakistan.",
        "author": "Test Author",
        "publish_date": "2024-01-15T10:00:00Z",
    }


@pytest.fixture
def sample_articles():
    """Multiple sample articles for testing clustering."""
    return [
        {
            "id": "1",
            "source": "dawn",
            "headline": "Rupee falls against dollar",
            "main_text": "The Pakistani rupee depreciated against the US dollar today...",
        },
        {
            "id": "2",
            "source": "tribune",
            "headline": "Dollar gains value against rupee",
            "main_text": "Currency markets saw the dollar strengthen against rupee...",
        },
        {
            "id": "3",
            "source": "express",
            "headline": "Traffic jam on Shahrah-e-Faisal",
            "main_text": "Heavy traffic was reported on Karachi's main road...",
        },
    ]
