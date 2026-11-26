"""Source registrar: searches web, deduplicates canonical URLs, and registers sources."""

from __future__ import annotations

import datetime
import uuid
from typing import List, Optional
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import Source
from app.research.factory import get_search_provider
from app.research.search_base import SearchProvider, SearchResult
from app.research.url_utils import canonicalize_url

logger = structlog.get_logger(__name__)


class SourceRegistrar:
    """Orchestrates web search and idempotent source registration in database."""

    def __init__(
        self,
        db: AsyncSession,
        search_provider: Optional[SearchProvider] = None,
    ) -> None:
        self.db = db
        self.search_provider = search_provider or get_search_provider()

    async def search_and_register(
        self,
        project_id: uuid.UUID,
        queries: List[str],
        results_per_query: int = 5,
    ) -> List[Source]:
        """Execute searches for all queries, deduplicate URLs, and persist unique sources."""
        logger.info(
            "starting_source_registration",
            project_id=str(project_id),
            queries_count=len(queries),
        )

        # 1. Fetch search results across all queries
        raw_results: List[SearchResult] = []
        for q in queries:
            try:
                res = await self.search_provider.search(q, num_results=results_per_query)
                raw_results.extend(res)
            except Exception as exc:
                logger.warning("search_query_failed", query=q, error=str(exc))

        # 2. In-memory deduplication by canonical URL
        unique_candidates: dict[str, SearchResult] = {}
        for r in raw_results:
            c_url = canonicalize_url(r.url)
            if c_url and c_url not in unique_candidates:
                unique_candidates[c_url] = r

        logger.info(
            "search_candidates_discovered",
            total_raw=len(raw_results),
            unique_canonical=len(unique_candidates),
        )

        if not unique_candidates:
            return []

        # 3. Retrieve already registered canonical URLs for this project
        stmt = select(Source.canonical_url).where(Source.project_id == project_id)
        existing_result = await self.db.execute(stmt)
        existing_urls = set(existing_result.scalars().all())

        # 4. Insert new sources
        new_sources: List[Source] = []
        now = utcnow()

        for c_url, candidate in unique_candidates.items():
            if c_url in existing_urls:
                continue

            # Parse date if available
            parsed_date = None
            if candidate.pub_date:
                try:
                    # Accepts ISO format YYYY-MM-DD
                    parsed_date = datetime.date.fromisoformat(candidate.pub_date[:10])
                except Exception:
                    parsed_date = None

            source = Source(
                project_id=project_id,
                canonical_url=c_url,
                title=candidate.title or None,
                publisher=candidate.publisher or None,
                pub_date=parsed_date,
                access_time=now,
                raw_metadata={
                    "original_url": candidate.url,
                    "snippet": candidate.snippet,
                    "score": candidate.score,
                },
            )
            self.db.add(source)
            new_sources.append(source)
            existing_urls.add(c_url)

        if new_sources:
            await self.db.flush()
            logger.info("sources_persisted", count=len(new_sources), project_id=str(project_id))

        # 5. Return all active sources for this project
        all_sources_stmt = select(Source).where(Source.project_id == project_id).order_by(Source.created_at)
        all_sources = (await self.db.execute(all_sources_stmt)).scalars().all()
        return list(all_sources)
