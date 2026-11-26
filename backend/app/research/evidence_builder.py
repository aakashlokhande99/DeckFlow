"""Evidence chunking and claim creation service."""

from __future__ import annotations

import re
import uuid
from typing import List
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ConfidenceLevel
from app.db.models import EvidenceClaim, Source

logger = structlog.get_logger(__name__)

# Noise filter to discard generic web boilerplate before creating evidence claims
DISCARD_PATTERNS = [
    re.compile(r"(?i)all\s+rights\s+reserved"),
    re.compile(r"(?i)cookie\s+(preferences|policy|notice)"),
    re.compile(r"(?i)terms\s+of\s+service"),
    re.compile(r"(?i)privacy\s+policy"),
    re.compile(r"(?i)sign\s+in\s+to\s+your\s+account"),
]


def chunk_text(
    text: str,
    target_chunk_size: int = 600,
    min_chunk_size: int = 80,
    overlap: int = 80,
) -> List[str]:
    """Split clean text into coherent paragraph- and sentence-aligned chunks."""
    if not text:
        return []

    # Split by double linebreaks (paragraphs) first
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) >= min_chunk_size]
    chunks: list[str] = []

    for para in paragraphs:
        if len(para) <= target_chunk_size:
            if not any(pat.search(para) for pat in DISCARD_PATTERNS):
                chunks.append(para)
        else:
            # Sub-split long paragraphs by sentences
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current_chunk: list[str] = []
            current_len = 0

            for s in sentences:
                if current_len + len(s) > target_chunk_size and current_chunk:
                    chunk_str = " ".join(current_chunk)
                    if not any(pat.search(chunk_str) for pat in DISCARD_PATTERNS):
                        chunks.append(chunk_str)
                    current_chunk = [s]
                    current_len = len(s)
                else:
                    current_chunk.append(s)
                    current_len += len(s)

            if current_chunk:
                chunk_str = " ".join(current_chunk)
                if len(chunk_str) >= min_chunk_size and not any(pat.search(chunk_str) for pat in DISCARD_PATTERNS):
                    chunks.append(chunk_str)

    return chunks


class EvidenceBuilder:
    """Processes extracted source text and creates traceable EvidenceClaim records."""

    def __init__(self, db: AsyncSession, max_chunks_per_source: int = 15) -> None:
        self.db = db
        self.max_chunks_per_source = max_chunks_per_source

    async def build_and_store_evidence(
        self,
        project_id: uuid.UUID,
        source: Source,
        raw_text: str,
        content_hash: str | None = None,
    ) -> List[EvidenceClaim]:
        """Chunk text, link evidence to source, and persist EvidenceClaim records."""
        if content_hash:
            source.content_hash = content_hash

        chunks = chunk_text(raw_text)
        selected_chunks = chunks[: self.max_chunks_per_source]

        claims: list[EvidenceClaim] = []
        for chunk in selected_chunks:
            # Detect whether chunk contains explicit markers of uncertainty or gaps
            is_uncertain = bool(re.search(r"(?i)\b(uncertain|unclear|unproven|estimated|speculative)\b", chunk))
            is_gap = bool(re.search(r"(?i)\b(lack of data|data gap|unknown|unverified)\b", chunk))

            claim = EvidenceClaim(
                project_id=project_id,
                source_ids=[source.id],
                claim_text=chunk,
                confidence=ConfidenceLevel.medium.value if not is_uncertain else ConfidenceLevel.uncertain.value,
                is_uncertain=is_uncertain,
                is_gap=is_gap,
            )
            self.db.add(claim)
            claims.append(claim)

        if claims:
            await self.db.flush()
            logger.info(
                "evidence_claims_created",
                source_id=str(source.id),
                claims_count=len(claims),
                project_id=str(project_id),
            )

        return claims
