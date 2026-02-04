"""
Validation utilities for articles and configuration.
"""
from typing import Any, Dict, List
from urllib.parse import urlparse


def validate_article_structure(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that an article has all required fields and proper structure.

    Args:
        article: Dictionary containing article data

    Returns:
        Dict with keys:
            - valid (bool): Whether article is valid
            - errors (List[str]): List of validation errors
    """
    errors: List[str] = []
    required_fields = ["source", "url", "headline", "main_text"]

    # Check required fields exist
    for field in required_fields:
        if field not in article:
            errors.append(f"Missing required field: {field}")
        elif not article[field] or (isinstance(article[field], str) and not article[field].strip()):
            errors.append(f"Field '{field}' is empty")

    # Validate URL format if present
    if "url" in article and article["url"]:
        parsed_url = urlparse(article["url"])
        if not parsed_url.scheme or not parsed_url.netloc:
            errors.append("Invalid URL format")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_sources_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate sources configuration structure.

    Args:
        config: Dictionary containing sources configuration

    Returns:
        Dict with keys:
            - valid (bool): Whether config is valid
            - errors (List[str]): List of validation errors
    """
    errors: List[str] = []

    if "sources" not in config:
        errors.append("Missing 'sources' key in configuration")
        return {"valid": False, "errors": errors}

    sources = config["sources"]
    if not isinstance(sources, dict):
        errors.append("'sources' must be a dictionary")
        return {"valid": False, "errors": errors}

    if len(sources) < 2:
        errors.append("At least 2 sources must be configured")

    # Validate each source
    for source_name, source_data in sources.items():
        required_fields = ["url", "feed_url", "sections", "enabled"]

        for field in required_fields:
            if field not in source_data:
                errors.append(f"Source '{source_name}' missing required field: {field}")

        # Validate URL if present
        if "url" in source_data:
            parsed_url = urlparse(source_data["url"])
            if not parsed_url.scheme or not parsed_url.netloc:
                errors.append(f"Source '{source_name}' has invalid URL")

        # Validate sections is a list
        if "sections" in source_data and not isinstance(source_data["sections"], list):
            errors.append(f"Source '{source_name}' sections must be a list")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_classification_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate classification rules configuration structure.

    Args:
        config: Dictionary containing classification configuration

    Returns:
        Dict with keys:
            - valid (bool): Whether config is valid
            - errors (List[str]): List of validation errors
    """
    errors: List[str] = []

    required_keys = ["categories", "impact_labels"]
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required key: {key}")

    if "categories" in config:
        if not isinstance(config["categories"], dict):
            errors.append("'categories' must be a dictionary")
        elif len(config["categories"]) == 0:
            errors.append("At least one category must be defined")

    if "impact_labels" in config:
        if not isinstance(config["impact_labels"], dict):
            errors.append("'impact_labels' must be a dictionary")
        elif len(config["impact_labels"]) == 0:
            errors.append("At least one impact label must be defined")

    return {"valid": len(errors) == 0, "errors": errors}
