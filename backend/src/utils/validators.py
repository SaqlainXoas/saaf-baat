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

    Sources are RSS/sitemap-based: each one declares a tier and at least one
    endpoint. There is no HTML `sections` discovery path any more.

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

    for source_name, source_data in sources.items():
        if not isinstance(source_data, dict):
            errors.append(f"Source '{source_name}' must be a mapping")
            continue

        for required in ("url", "tier", "enabled"):
            if required not in source_data:
                errors.append(f"Source '{source_name}' missing required field: {required}")

        if "url" in source_data:
            parsed_url = urlparse(str(source_data["url"]))
            if not parsed_url.scheme or not parsed_url.netloc:
                errors.append(f"Source '{source_name}' has invalid URL")

        if "tier" in source_data and str(source_data["tier"]).upper() not in {"A", "B"}:
            errors.append(f"Source '{source_name}' tier must be A or B")

        endpoint_counts = []
        for key in ("feed_urls", "sitemap_urls"):
            value = source_data.get(key, [])
            if not isinstance(value, list):
                errors.append(f"Source '{source_name}' {key} must be a list")
                continue
            endpoint_counts.append(len(value))

        if source_data.get("enabled") and not any(endpoint_counts):
            errors.append(
                f"Source '{source_name}' is enabled but declares no feed_urls or sitemap_urls"
            )

    return {"valid": len(errors) == 0, "errors": errors}


