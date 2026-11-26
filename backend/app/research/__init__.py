"""Research engine modules: search, fetching, extraction, planning, source registration, evidence, synthesis, and QA gate."""

from app.research.evidence_builder import EvidenceBuilder, chunk_text
from app.research.extractor import (
    extract_content,
    extract_text_from_html,
    extract_text_from_pdf,
    sanitize_text,
)
from app.research.factory import get_search_provider
from app.research.mock_search import MockSearchProvider
from app.research.planner import ResearchPlanner
from app.research.quality_gate import QACheckResult, SynthesisQualityGate
from app.research.safe_fetcher import (
    ContentSizeExceededError,
    FetchError,
    FetchResponse,
    SafeFetcher,
    SSRFBlockedError,
    UnsupportedContentTypeError,
)
from app.research.search_base import (
    SearchError,
    SearchProvider,
    SearchResult,
    SearchTimeoutError,
)
from app.research.serpapi import SerpAPIProvider
from app.research.source_registrar import SourceRegistrar
from app.research.synthesizer import ConsultingSynthesizer
from app.research.url_utils import canonicalize_url

__all__ = [
    "SearchProvider",
    "SearchResult",
    "SearchError",
    "SearchTimeoutError",
    "SerpAPIProvider",
    "MockSearchProvider",
    "get_search_provider",
    "ResearchPlanner",
    "SourceRegistrar",
    "canonicalize_url",
    "SafeFetcher",
    "FetchResponse",
    "FetchError",
    "SSRFBlockedError",
    "ContentSizeExceededError",
    "UnsupportedContentTypeError",
    "extract_text_from_html",
    "extract_text_from_pdf",
    "extract_content",
    "sanitize_text",
    "EvidenceBuilder",
    "chunk_text",
    "ConsultingSynthesizer",
    "SynthesisQualityGate",
    "QACheckResult",
]
