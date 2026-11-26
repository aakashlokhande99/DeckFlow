"""SerpAPI search provider implementation using async HTTP."""

from __future__ import annotations

from typing import Any, List
import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.research.search_base import SearchError, SearchProvider, SearchResult, SearchTimeoutError

logger = structlog.get_logger(__name__)


class SerpAPIProvider(SearchProvider):
    """Web search provider powered by SerpAPI."""

    SERPAPI_URL = "https://serpapi.com/search.json"

    def __init__(
        self,
        api_key: str,
        timeout: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    async def search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs: Any,
    ) -> List[SearchResult]:
        if not self.api_key:
            raise SearchError("SerpAPI API key is not configured.")

        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",
            "num": num_results,
        }

        @retry(
            retry=retry_if_exception_type((httpx.NetworkError, httpx.HTTPStatusError)),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            reraise=True,
        )
        async def _execute() -> List[SearchResult]:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(self.SERPAPI_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                results: List[SearchResult] = []
                organic_results = data.get("organic_results", [])

                for item in organic_results[:num_results]:
                    link = item.get("link")
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    source = item.get("source") or item.get("displayed_link")
                    date = item.get("date")

                    if link:
                        results.append(
                            SearchResult(
                                title=title,
                                url=link,
                                snippet=snippet,
                                publisher=source,
                                pub_date=date,
                            )
                        )
                return results

            except httpx.TimeoutException as exc:
                raise SearchTimeoutError(f"SerpAPI search timed out after {self.timeout}s: {exc}") from exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    raise  # triggers retry
                raise SearchError(f"SerpAPI error HTTP {exc.response.status_code}: {exc.response.text}") from exc
            except Exception as exc:
                if isinstance(exc, (SearchError, SearchTimeoutError)):
                    raise
                raise SearchError(f"SerpAPI query failed: {exc}") from exc

        return await _execute()
