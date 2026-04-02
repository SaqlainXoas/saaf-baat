"""
Shared pytest fixtures for all tests.
"""
import os
import sys
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

# Load environment variables from .env file in backend/
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Add src to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir / "src"))

def _truthy_env(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Make network/credentialed suites opt-in.

    We load `backend/.env` for local dev convenience, which can set real
    SUPABASE/GEMINI keys. Without an opt-in guard, `pytest` would attempt live
    calls and fail/flap on machines without network access.
    """
    markexpr = (getattr(config.option, "markexpr", None) or "").strip().lower()
    wants_integration = "integration" in markexpr
    wants_slow = "slow" in markexpr

    run_integration = _truthy_env("SAAF_RUN_INTEGRATION_TESTS") or wants_integration
    run_slow = _truthy_env("SAAF_RUN_SLOW_TESTS") or wants_slow

    if not run_integration:
        skip_integration = pytest.mark.skip(
            reason="integration tests disabled (set SAAF_RUN_INTEGRATION_TESTS=1 or run with -m integration)"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)

    if not run_slow:
        skip_slow = pytest.mark.skip(
            reason="slow tests disabled (set SAAF_RUN_SLOW_TESTS=1 or run with -m slow)"
        )
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


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
