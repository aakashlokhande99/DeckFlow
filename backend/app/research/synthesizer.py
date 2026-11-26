"""Consulting synthesis engine: synthesizes grounded consulting insights from stored evidence."""

from __future__ import annotations

import uuid
from typing import List, Optional, Tuple
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ConfidenceLevel
from app.db.models import EvidenceClaim, Insight, Project, Source
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.schemas.synthesis import ConsultingSynthesis

logger = structlog.get_logger(__name__)

PROMPT_VERSION = "v1"

SYNTHESIS_SYSTEM_PROMPT = """You are a senior partner at an elite strategy consultancy (McKinsey, BCG, Bain).
Your task is to synthesize collected empirical evidence into an authoritative executive consulting briefing.

NON-NEGOTIABLE GROUNDING RULES:
1. Strict Grounding: Every material factual finding and recommendation MUST reference the exact Evidence ID(s) from the provided evidence dossier.
2. No Hallucinations: If a claim is not supported by the evidence, DO NOT assert it as fact. Instead, record it as a research gap or mark it as is_uncertain=true.
3. Evidence Hierarchy: Prioritize claims from internal client documents ([Source: filename.pdf] or [Source: filename.txt]) as empirical ground-truth baseline data for the client's current situation. Use external research to benchmark, validate, and fill gaps.
4. Structured Reasoning:
   - Executive Summary: Crisp, top-down synthesis answering the core client question.
   - Findings: Empirical facts with exact evidence_ids.
   - Implications: Strategic and commercial consequences of the findings.
   - Recommendations: Actionable, prioritized steps with clear time horizons.
   - Risks & Mitigations: Critical execution bottlenecks and recommended countermeasures.
   - Gaps & Limitations: Information missing from public sources requiring internal client data or second-round diligence.
"""


class ConsultingSynthesizer:
    """Transforms stored EvidenceClaims into a structured ConsultingSynthesis report."""

    def __init__(
        self,
        db: AsyncSession,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        self.db = db
        self.llm = llm_provider or get_llm_provider()

    async def synthesize(
        self,
        project_id: uuid.UUID,
        version: int = 1,
    ) -> Tuple[ConsultingSynthesis, Insight]:
        """Synthesize findings from stored evidence and persist an Insight record."""
        # 1. Retrieve project
        project_stmt = select(Project).where(Project.id == project_id)
        project = (await self.db.execute(project_stmt)).scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found.")

        # 2. Retrieve all evidence claims and sources for this project
        claims_stmt = (
            select(EvidenceClaim)
            .where(EvidenceClaim.project_id == project_id)
            .order_by(EvidenceClaim.created_at)
        )
        claims = (await self.db.execute(claims_stmt)).scalars().all()

        sources_stmt = select(Source).where(Source.project_id == project_id)
        sources = (await self.db.execute(sources_stmt)).scalars().all()

        sources_by_id = {s.id: s for s in sources}
        valid_claim_ids = {str(c.id) for c in claims}

        logger.info(
            "synthesizing_evidence",
            project_id=str(project_id),
            evidence_count=len(claims),
            sources_count=len(sources),
        )

        # 3. Format evidence dossier for the prompt
        evidence_lines: list[str] = []
        for c in claims:
            source_labels = []
            for s_id in (c.source_ids or []):
                src = sources_by_id.get(s_id)
                if src:
                    if src.canonical_url.startswith("uploaded://"):
                        fname = (src.raw_metadata or {}).get("filename", src.title or "Document")
                        source_labels.append(f"Source: {fname}")
                    else:
                        source_labels.append(f"{src.publisher or 'Source'} ({src.canonical_url})")

            source_desc = ", ".join(source_labels) if source_labels else "Direct Source"
            flag = " [UNCERTAIN]" if c.is_uncertain else ""
            evidence_lines.append(f"- Evidence ID [{c.id}]{flag} [{source_desc}]: {c.claim_text}")

        evidence_text = "\n".join(evidence_lines) if evidence_lines else "No empirical evidence collected."

        user_prompt = f"""Synthesize an executive consulting report for the following project:

Client Topic: {project.topic}
Business Objective: {project.objective}
Target Audience: {project.audience or 'Executive Leadership'}
Geographic Scope: {project.geography or 'Global'}
Time Horizon: {project.time_horizon or 'Unspecified'}
Additional Strategic Context: {project.additional_context or 'None'}

COLLECTED EMPIRICAL EVIDENCE DOSSIER:
{evidence_text}

INSTRUCTIONS:
- Derive findings strictly from the evidence above.
- Populate evidence_ids for every finding using the exact UUIDs listed in brackets (e.g. ['{list(valid_claim_ids)[0] if valid_claim_ids else "uuid"}']).
- Synthesize commercial implications and actionable recommendations.
- List any unresolved uncertainties or data shortages under 'gaps'.
"""

        # 4. Generate structured synthesis via LLM
        synthesis: ConsultingSynthesis = await self.llm.generate_structured(
            prompt=user_prompt,
            response_model=ConsultingSynthesis,
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            temperature=0.1,
        )

        # 5. Post-validation: verify that cited evidence_ids actually exist in DB
        for finding in synthesis.findings:
            cited_valid = [eid for eid in finding.evidence_ids if eid in valid_claim_ids]
            if len(cited_valid) < len(finding.evidence_ids) or not finding.evidence_ids:
                # Unsupported claim or missing citation: flag as uncertain
                finding.is_uncertain = True
                finding.confidence = ConfidenceLevel.uncertain
                finding.evidence_ids = cited_valid

        # 6. Persist Insight record
        insight = Insight(
            project_id=project_id,
            executive_summary=synthesis.executive_summary,
            findings=[f.model_dump() for f in synthesis.findings],
            implications=[i.model_dump() for i in synthesis.implications],
            recommendations=[r.model_dump() for r in synthesis.recommendations],
            risks=[rk.model_dump() for rk in synthesis.risks],
            limitations=synthesis.limitations,
            gaps=[g.model_dump() for g in synthesis.gaps],
            citations=[c.model_dump() for c in synthesis.citations],
            version=version,
            prompt_version=PROMPT_VERSION,
        )
        self.db.add(insight)
        await self.db.flush()

        logger.info(
            "synthesis_completed",
            insight_id=str(insight.id),
            findings_count=len(synthesis.findings),
            recommendations_count=len(synthesis.recommendations),
        )

        return synthesis, insight
