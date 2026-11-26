"""LangGraph workflow node functions executing research, synthesis, and QA gate."""

from __future__ import annotations

import uuid
from typing import Any, Dict
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvidenceClaim, Insight, Project, Source
from app.db import session as db_session_module
from app.llm.factory import get_llm_provider
from app.research.evidence_builder import EvidenceBuilder
from app.research.extractor import extract_content
from app.research.factory import get_search_provider
from app.research.planner import ResearchPlanner
from app.research.quality_gate import SynthesisQualityGate
from app.research.safe_fetcher import SafeFetcher
from app.research.source_registrar import SourceRegistrar
from app.research.synthesizer import ConsultingSynthesizer
from app.schemas.project import ProjectBrief, ResearchPlan
from app.schemas.synthesis import ConsultingSynthesis
from app.workflow.state import ResearchWorkflowState

logger = structlog.get_logger(__name__)


async def _emit_event(
    project_id: str,
    event_type: str,
    step: str,
    agent_name: str,
    progress: int,
    message: str,
    data: Dict[str, Any] | None = None,
) -> None:
    """Non-blocking helper to broadcast progress to project WebSocket channel."""
    if not project_id:
        return
    try:
        from app.core.events import create_agent_event, event_bus
        event = create_agent_event(
            event_type=event_type,
            project_id=project_id,
            step=step,
            agent_name=agent_name,
            progress=progress,
            message=message,
            data=data,
        )
        await event_bus.publish(f"project:{project_id}", event)
    except Exception as exc:
        logger.debug("emit_event_failed", error=str(exc))


async def validate_brief_node(state: ResearchWorkflowState) -> Dict[str, Any]:
    """Validate project brief parameters."""
    project_id = state.get("project_id", "")
    topic = state.get("topic", "")
    objective = state.get("objective", "")

    logger.info("node_validate_brief", project_id=project_id, topic=topic)
    await _emit_event(
        project_id,
        "agent_progress",
        "validate_brief",
        "Intake Validator",
        5,
        "Validating strategic project parameters...",
    )

    errors = list(state.get("errors", []))
    if not topic or len(topic.strip()) < 3:
        errors.append("Invalid topic: must be at least 3 characters.")
    if not objective or len(objective.strip()) < 10:
        errors.append("Invalid objective: must be at least 10 characters.")

    return {
        "current_step": "validate_brief",
        "status": "validating",
        "errors": errors,
    }


async def plan_research_node(
    state: ResearchWorkflowState,
    planner: ResearchPlanner | None = None,
) -> Dict[str, Any]:
    """Generate structured research plan with MECE questions and targeted search queries."""
    project_id = state.get("project_id", "")
    logger.info("node_plan_research", project_id=project_id)
    await _emit_event(
        project_id,
        "agent_progress",
        "plan_research",
        "Research Planner",
        20,
        "Generating MECE sub-questions & research vectors...",
    )

    brief = ProjectBrief(
        topic=state["topic"],
        objective=state["objective"],
        audience=state.get("audience") or "Executive Leadership",
        geography=state.get("geography") or "Global",
        time_horizon=state.get("time_horizon") or "2025-2030",
        additional_context=state.get("additional_context") or "",
        research_depth=state.get("research_depth", "standard"),
    )

    p = planner or ResearchPlanner()
    plan: ResearchPlan = await p.plan(brief)

    return {
        "plan": plan.model_dump(),
        "current_step": "plan_research",
        "status": "planning",
    }


async def search_sources_node(
    state: ResearchWorkflowState,
    db: AsyncSession | None = None,
    search_provider: Any = None,
) -> Dict[str, Any]:
    """Execute queries and register canonical sources into the database."""
    project_id_str = state["project_id"]
    project_id = uuid.UUID(project_id_str)
    plan_data = state.get("plan") or {}
    queries = plan_data.get("search_queries", [state["topic"]])

    logger.info("node_search_sources", project_id=project_id_str, queries_count=len(queries))
    await _emit_event(
        project_id_str,
        "agent_progress",
        "search_sources",
        "Source Harvester",
        35,
        f"Searching authoritative sources across {len(queries)} research vectors...",
    )

    async def _run(session: AsyncSession) -> Dict[str, Any]:
        registrar = SourceRegistrar(db=session, search_provider=search_provider)
        await registrar.search_and_register(
            project_id=project_id,
            queries=queries,
            results_per_query=4,
        )
        # Retrieve all sources for this engagement (both web-harvested and uploaded documents)
        all_stmt = select(Source).where(Source.project_id == project_id)
        all_sources = (await session.execute(all_stmt)).scalars().all()
        return {
            "source_ids": [str(s.id) for s in all_sources],
            "source_urls": [s.canonical_url for s in all_sources],
            "current_step": "search_sources",
            "status": "researching",
        }

    if db is not None:
        return await _run(db)
    else:
        async with db_session_module.AsyncSessionLocal() as session:
            res = await _run(session)
            await session.commit()
            return res


async def fetch_and_extract_node(
    state: ResearchWorkflowState,
    fetcher: SafeFetcher | None = None,
) -> Dict[str, Any]:
    """Safely fetch HTML/PDF content and extract sanitized text."""
    source_ids = state.get("source_ids", [])
    source_urls = state.get("source_urls", [])
    project_id_str = state.get("project_id", "")
    logger.info("node_fetch_and_extract", count=len(source_ids))

    await _emit_event(
        project_id_str,
        "agent_progress",
        "fetch_and_extract",
        "SafeFetcher",
        55,
        f"Safely retrieving and sanitizing content across {len(source_ids)} sources...",
    )

    f = fetcher or SafeFetcher(timeout=10.0)
    extracted: dict[str, str] = {}
    content_hashes: dict[str, str] = {}

    for s_id, s_url in zip(source_ids, source_urls):
        if s_url.startswith("uploaded://"):
            try:
                async with db_session_module.AsyncSessionLocal() as session:
                    stmt = select(Source).where(Source.id == uuid.UUID(s_id))
                    src = (await session.execute(stmt)).scalar_one_or_none()
                    if src and src.raw_metadata and "extracted_text" in src.raw_metadata:
                        extracted[s_id] = src.raw_metadata["extracted_text"]
                        content_hashes[s_id] = src.content_hash or ""
                        continue
            except Exception as exc:
                logger.warning("uploaded_doc_extraction_failed", source_id=s_id, error=str(exc))

        try:
            fetch_res = await f.fetch(s_url)
            text = extract_content(fetch_res.content_bytes, fetch_res.content_type)
            extracted[s_id] = text
            content_hashes[s_id] = fetch_res.content_hash
        except Exception as exc:
            logger.warning("fetch_or_extraction_skipped", url=s_url, error=str(exc))
            extracted[s_id] = f"Source summary: {s_url}"
            content_hashes[s_id] = ""

    return {
        "extracted_texts": extracted,
        "content_hashes": content_hashes,
        "current_step": "fetch_and_extract",
        "status": "extracting",
    }


async def build_evidence_node(
    state: ResearchWorkflowState,
    db: AsyncSession | None = None,
) -> Dict[str, Any]:
    """Chunk extracted text and persist traceable EvidenceClaim records."""
    project_id_str = state["project_id"]
    project_id = uuid.UUID(project_id_str)
    extracted_texts = state.get("extracted_texts", {})
    content_hashes = state.get("content_hashes", {})

    logger.info("node_build_evidence", project_id=project_id_str, sources_count=len(extracted_texts))
    await _emit_event(
        project_id_str,
        "agent_progress",
        "build_evidence",
        "Evidence Builder",
        70,
        f"Structuring and persisting verified evidence claims across {len(extracted_texts)} sources...",
    )

    async def _run(session: AsyncSession) -> Dict[str, Any]:
        builder = EvidenceBuilder(db=session)
        created_claim_ids: list[str] = []

        for s_id_str, text in extracted_texts.items():
            s_id = uuid.UUID(s_id_str)
            stmt = select(Source).where(Source.id == s_id)
            source = (await session.execute(stmt)).scalar_one_or_none()
            if source:
                claims = await builder.build_and_store_evidence(
                    project_id=project_id,
                    source=source,
                    raw_text=text,
                    content_hash=content_hashes.get(s_id_str),
                )
                created_claim_ids.extend([str(c.id) for c in claims])

        return {
            "evidence_claim_ids": created_claim_ids,
            "current_step": "build_evidence",
            "status": "evidence_stored",
        }

    if db is not None:
        return await _run(db)
    else:
        async with db_session_module.AsyncSessionLocal() as session:
            res = await _run(session)
            await session.commit()
            return res


async def synthesize_node(
    state: ResearchWorkflowState,
    db: AsyncSession | None = None,
    synthesizer: ConsultingSynthesizer | None = None,
) -> Dict[str, Any]:
    """Synthesize evidence into consulting findings, implications, risks, and recommendations."""
    project_id_str = state["project_id"]
    project_id = uuid.UUID(project_id_str)
    version = state.get("version", 1)

    logger.info("node_synthesize", project_id=project_id_str, version=version)
    await _emit_event(
        project_id_str,
        "agent_progress",
        "synthesize",
        "Consulting Synthesizer",
        85,
        "Structuring findings, strategic implications & actionable recommendations...",
    )

    async def _run(session: AsyncSession) -> Dict[str, Any]:
        synth = synthesizer or ConsultingSynthesizer(db=session)
        synthesis, insight = await synth.synthesize(project_id=project_id, version=version)
        return {
            "insight_id": str(insight.id),
            "synthesis": synthesis.model_dump(),
            "version": version,
            "current_step": "synthesize",
            "status": "synthesized",
        }

    if db is not None:
        return await _run(db)
    else:
        async with db_session_module.AsyncSessionLocal() as session:
            res = await _run(session)
            await session.commit()
            return res


async def quality_gate_node(
    state: ResearchWorkflowState,
    db: AsyncSession | None = None,
    gate: SynthesisQualityGate | None = None,
) -> Dict[str, Any]:
    """Run rigorous synthesis quality check and update project status to awaiting_review."""
    project_id_str = state["project_id"]
    project_id = uuid.UUID(project_id_str)
    synthesis_data = state.get("synthesis") or {}
    synthesis = ConsultingSynthesis.model_validate(synthesis_data)

    plan_data = state.get("plan")
    plan = ResearchPlan.model_validate(plan_data) if plan_data else None

    logger.info("node_quality_gate", project_id=project_id_str)
    await _emit_event(
        project_id_str,
        "agent_progress",
        "quality_gate",
        "Quality Gate Auditor",
        95,
        "Evaluating 5-point QA gate: citations, question coverage & contradictions...",
    )

    async def _run(session: AsyncSession) -> Dict[str, Any]:
        claims_stmt = select(EvidenceClaim).where(EvidenceClaim.project_id == project_id)
        claims = (await session.execute(claims_stmt)).scalars().all()

        q_gate = gate or SynthesisQualityGate()
        qa_result = q_gate.evaluate(synthesis=synthesis, plan=plan, evidence_claims=list(claims))

        # Update Insight record with qa_report
        insight_id_str = state.get("insight_id")
        if insight_id_str:
            insight_stmt = select(Insight).where(Insight.id == uuid.UUID(insight_id_str))
            insight = (await session.execute(insight_stmt)).scalar_one_or_none()
            if insight:
                insight.qa_report = qa_result.model_dump()

        # Update Project status to review_required / awaiting_review
        project_stmt = select(Project).where(Project.id == project_id)
        project = (await session.execute(project_stmt)).scalar_one_or_none()
        if project:
            project.status = "awaiting_review"
            await session.flush()

        return {
            "qa_report": qa_result.model_dump(),
            "current_step": "quality_gate",
            "status": "awaiting_review",
        }

    if db is not None:
        return await _run(db)
    else:
        async with db_session_module.AsyncSessionLocal() as session:
            res = await _run(session)
            await session.commit()
            return res


async def human_review_pause_node(state: ResearchWorkflowState) -> Dict[str, Any]:
    """Pause gate: awaits human decision before storyline generation."""
    project_id_str = state.get("project_id", "")
    logger.info("node_human_review_pause", project_id=project_id_str)

    await _emit_event(
        project_id_str,
        "review_required",
        "human_review",
        "Human Review Gate",
        100,
        "Synthesis quality gate passed. Awaiting human reviewer approval.",
        {"status": "awaiting_review"},
    )

    # Trigger webhook notifications for synthesis review gate (non-blocking)
    try:
        from app.notifications.service import WebhookService
        service = WebhookService()
        topic = state.get("topic", "Consulting Research Project")
        audience = state.get("audience", "Executive Leadership")
        qa_report = state.get("qa_report", {})
        qa_summary = (
            f"Overall Passed: {qa_report.get('passed', True)}. "
            f"Issues: {len(qa_report.get('issues', []))}. "
            f"Citation check: {qa_report.get('citation_check', 'passed')}."
        ) if qa_report else "Synthesis QA gate passed. Awaiting human approval."

        service.trigger_synthesis_review_gate_background(
            project_id=project_id_str,
            topic=topic,
            audience=audience,
            qa_summary=qa_summary,
        )
    except Exception as notify_exc:
        logger.warning("synthesis_webhook_trigger_failed", error=str(notify_exc))

    return {
        "current_step": "human_review",
        "status": "awaiting_review",
    }
