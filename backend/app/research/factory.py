"""Search provider factory."""

from __future__ import annotations

from app.core.config import settings
from app.research.mock_search import MockSearchProvider
from app.research.search_base import SearchProvider
from app.research.serpapi import SerpAPIProvider


def get_search_provider(provider_name: str | None = None) -> SearchProvider:
    """Return configured search provider."""
    name = (provider_name or settings.SEARCH_PROVIDER or "serpapi").lower()

    if name == "mock":
        return MockSearchProvider()

    if name == "serpapi":
        api_key = settings.SERPAPI_KEY.get_secret_value() if settings.SERPAPI_KEY else ""
        if not api_key:
            # Fallback to mock search in development/test if no key configured
            return MockSearchProvider()
        return SerpAPIProvider(api_key=api_key)

    raise ValueError(f"Unsupported search provider: {name}")
