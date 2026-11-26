"""URL normalization and canonicalization utilities."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query parameters commonly used for marketing/tracking that should be stripped
TRACKING_PARAMS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
})


def canonicalize_url(url: str) -> str:
    """Normalize a URL to its canonical form for deduplication.

    1. Lowercase scheme and netloc (hostname + port).
    2. Strip trailing slash on empty or single-slash paths.
    3. Remove fragments (#...).
    4. Strip common analytics/tracking query parameters (utm_*, gclid, etc.).
    5. Sort remaining query parameters for deterministic equivalence.
    """
    if not url or not isinstance(url, str):
        return ""

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url.strip()

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Normalize default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Normalize path
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # Clean query parameters
    filtered_params = []
    if parsed.query:
        for key, val in parse_qsl(parsed.query, keep_blank_values=False):
            if key.lower() not in TRACKING_PARAMS:
                filtered_params.append((key, val))

    # Sort query parameters deterministically
    filtered_params.sort(key=lambda pair: (pair[0], pair[1]))
    clean_query = urlencode(filtered_params)

    # Reconstruct without fragment
    return urlunparse((scheme, netloc, path, "", clean_query, ""))
