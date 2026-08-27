from __future__ import annotations

from urllib.parse import urlparse


def _host_aliases(host: str) -> set[str]:
    normalized = (host or "").strip().lower()
    if not normalized:
        return set()
    aliases = {normalized}
    if normalized.startswith("www."):
        aliases.add(normalized[4:])
    else:
        aliases.add(f"www.{normalized}")
    return aliases


def host_allowed_for_base(url: str, base_url: str) -> bool:
    """
    Allow only the configured host and its bare/www equivalent.

    This intentionally does not allow arbitrary subdomains. For the current
    morning-brief sources, strict same-site host matching is safer than broad
    subdomain acceptance because lifestyle/media subdomains can pollute the
    scrape budget.
    """

    try:
        url_host = (urlparse(url).hostname or "").lower()
        base_host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        return False

    if not url_host or not base_host:
        return False

    return url_host in _host_aliases(base_host)


def canonicalize_url_for_dedup(url: str) -> str:
    """
    Normalize article URLs for run-to-run dedup checks.

    We intentionally strip query strings and fragments because news publishers
    often vary those while pointing at the same article.
    """

    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return (url or "").strip()

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    scheme = (parsed.scheme or "https").lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    return f"{scheme}://{host}{path}"
