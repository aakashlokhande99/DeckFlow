"""Abstract Base Class and data models for web search providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Normalized search result returned by any search provider."""
    title: str = Field(..., description="Page or document title")
    url: str = Field(..., description="Target webpage URL")
    snippet: str = Field(default="", description="Snippet or summary text")
    publisher: Optional[str] = Field(default=None, description="Host / Publisher name")
    pub_date: Optional[str] = Field(default=None, description="Publication date if available")
    score: Optional[float] = Field(default=None, description="Relevance score or rank")


class SearchError(Exception):
    """Base exception for search provider failures."""
    pass


class SearchTimeoutError(SearchError):
    """Raised when search request times out."""
    pass


class SearchProvider(ABC):
    """Provider-neutral search interface."""

    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs: Any,
    ) -> List[SearchResult]:
        """Execute web search and return normalized results."""
        pass
