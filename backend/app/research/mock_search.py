"""Mock Search provider for offline tests and predictable integration testing."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.research.search_base import SearchProvider, SearchResult, SearchTimeoutError


class MockSearchProvider(SearchProvider):
    """Deterministic search provider for offline testing."""

    def __init__(
        self,
        default_results: Optional[List[SearchResult]] = None,
        query_results: Optional[Dict[str, List[SearchResult]]] = None,
        simulate_timeout: bool = False,
        call_delay_seconds: float = 0.0,
    ) -> None:
        self.default_results = default_results or [
            SearchResult(
                title="McKinsey: The economic potential of generative AI",
                url="https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-economic-potential-of-generative-ai",
                snippet="The next productivity frontier: Generative AI's impact on productivity could add trillions of dollars.",
                publisher="McKinsey & Company",
                pub_date="2023-06-14",
            ),
            SearchResult(
                title="Gartner: Generative AI in Financial Services",
                url="https://www.gartner.com/en/articles/generative-ai-financial-services",
                snippet="Explore how generative AI models are transforming banking operations and customer personalization.",
                publisher="Gartner",
                pub_date="2024-01-10",
            ),
        ]
        self.query_results = query_results or {}
        self.simulate_timeout = simulate_timeout
        self.call_delay_seconds = call_delay_seconds
        self.executed_queries: list[str] = []

    async def search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs: Any,
    ) -> List[SearchResult]:
        self.executed_queries.append(query)
        if self.call_delay_seconds > 0:
            await asyncio.sleep(self.call_delay_seconds)
        if self.simulate_timeout:
            raise SearchTimeoutError("Simulated mock search timeout")

        if query in self.query_results:
            return self.query_results[query][:num_results]

        return self.default_results[:num_results]
