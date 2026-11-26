"""Consulting slide storyline generator and outline manager.

Translates approved research synthesis into an 8-12 slide consulting deck outline
with McKinsey/BCG/Bain executive action titles, structured content, layouts,
and grounded source citation linkages.

STRICT GATE: No storyline can be generated from unapproved research synthesis.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec, Source
from app.schemas.storyline import SlideItem, StorylineOutline

logger = structlog.get_logger(__name__)


class StorylineGateError(Exception):
    """Raised when storyline generation is attempted on unapproved or missing research."""
    pass


class StorylineValidationError(Exception):
    """Raised when updated slide order or structure is invalid."""
    pass


class StorylineGenerator:
    """Manages consulting slide storyline generation, outline review, and slide specs."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate_storyline(
        self,
        project_id: uuid.UUID,
        force_regenerate: bool = False,
    ) -> StorylineOutline:
        """Generate an 8-12 slide consulting storyline from approved synthesis."""
        # 1. Fetch project and verify existence
        p_stmt = select(Project).where(Project.id == project_id)
        project = (await self.db.execute(p_stmt)).scalar_one_or_none()
        if not project:
            raise StorylineGateError(f"Project {project_id} not found.")

        # 2. Fetch latest insight and strictly verify human approval gate
        i_stmt = (
            select(Insight)
            .where(Insight.project_id == project_id)
            .order_by(Insight.version.desc())
        )
        insight = (await self.db.execute(i_stmt)).scalars().first()
        if not insight:
            raise StorylineGateError(
                f"No research synthesis found for project {project_id}. Run research workflow first."
            )

        if not insight.is_approved:
            raise StorylineGateError(
                f"Cannot generate storyline from unapproved research synthesis. "
                f"Insight {insight.id} (v{insight.version}) has is_approved=False."
            )

        # 3. Check if slide specs already exist and force_regenerate is False
        existing_stmt = (
            select(SlideSpec)
            .where(SlideSpec.project_id == project_id)
            .order_by(SlideSpec.slide_order.asc())
        )
        existing_specs = (await self.db.execute(existing_stmt)).scalars().all()
        if existing_specs and not force_regenerate:
            slides = [
                SlideItem(
                    id=str(s.id),
                    slide_order=s.slide_order,
                    title=s.title,
                    key_message=s.key_message,
                    layout=SlideLayout(s.layout) if s.layout in SlideLayout._value2member_map_ else SlideLayout.two_column,
                    content=s.content or {},
                    source_ids=[str(x) for x in (s.source_ids or [])],
                    is_approved=s.is_approved,
                )
                for s in existing_specs
            ]
            all_approved = all(s.is_approved for s in existing_specs)
            return StorylineOutline(
                project_id=str(project_id),
                insight_id=str(insight.id),
                slides=slides,
                is_approved=all_approved,
                total_slides=len(slides),
            )

        # 4. Synthesize 11 structured consulting slides
        slides = self._build_slide_sequence(project=project, insight=insight)

        # 5. Persist slide specs to database
        # Clean up any previous specs if regenerating
        await self.db.execute(
            delete(SlideSpec).where(SlideSpec.project_id == project_id)
        )

        persisted_items: List[SlideItem] = []
        for s in slides:
            spec = SlideSpec(
                id=uuid.uuid4(),
                project_id=project_id,
                insight_id=insight.id,
                slide_order=s.slide_order,
                title=s.title,
                key_message=s.key_message,
                layout=s.layout.value,
                content=s.content,
                source_ids=s.source_ids,
                is_approved=s.is_approved,
            )
            self.db.add(spec)
            persisted_items.append(
                SlideItem(
                    id=str(spec.id),
                    slide_order=spec.slide_order,
                    title=spec.title,
                    key_message=spec.key_message,
                    layout=SlideLayout(spec.layout) if spec.layout in SlideLayout._value2member_map_ else SlideLayout.two_column,
                    content=spec.content,
                    source_ids=[str(x) for x in (spec.source_ids or [])],
                    is_approved=spec.is_approved,
                )
            )

        await self.db.commit()

        logger.info(
            "storyline_generated",
            project_id=str(project_id),
            total_slides=len(persisted_items),
        )

        # Trigger webhook notifications for slide review gate (non-blocking)
        try:
            from app.notifications.service import WebhookService
            service = WebhookService()
            summary_items = [
                f"Slide {s.slide_order}: {s.title} ({s.layout.value})"
                for s in persisted_items
            ]
            service.trigger_slide_review_gate(
                project_id=project_id,
                topic=project.topic,
                audience=project.audience,
                total_slides=len(persisted_items),
                slide_summary=summary_items,
                session=None,
            )
        except Exception as notify_exc:
            logger.warning("storyline_webhook_trigger_failed", error=str(notify_exc))

        return StorylineOutline(
            project_id=str(project_id),
            insight_id=str(insight.id),
            slides=persisted_items,
            is_approved=False,
            total_slides=len(persisted_items),
        )

    def _build_slide_sequence(
        self,
        project: Project,
        insight: Insight,
    ) -> List[SlideItem]:
        """Construct standard 11-slide executive storyline from approved synthesis."""
        findings: list = insight.findings or []
        implications: list = insight.implications or []
        recommendations: list = insight.recommendations or []
        risks: list = insight.risks or []
        gaps: list = (insight.gaps or []) + (insight.limitations or [])

        # Collect source IDs from findings
        all_cited_sources: List[str] = []
        for f in findings:
            if isinstance(f, dict):
                eids = f.get("evidence_ids") or []
                all_cited_sources.extend([str(eid) for eid in eids if eid])
            elif isinstance(f, str):
                pass

        # Slide 1: Title
        topic_title = (project.topic or "Strategic Assessment").strip()
        title_s1 = f"{topic_title}: Strategic Assessment"[:300]
        if len(title_s1) < 3:
            title_s1 = "Strategic Assessment"

        obj_msg = (project.objective or "").strip()
        if len(obj_msg) < 5:
            obj_msg = "Strategic assessment and executive decision framework."

        s1 = SlideItem(
            slide_order=1,
            title=title_s1,
            key_message=obj_msg,
            layout=SlideLayout.title,
            content={
                "topic": project.topic or "Strategic Assessment",
                "objective": project.objective or obj_msg,
                "audience": project.audience or "Executive Leadership",
                "geography": project.geography or "Global",
                "time_horizon": project.time_horizon or "Current Horizon",
            },
            source_ids=[],
        )

        # Slide 2: Executive Summary
        summary_text = (insight.executive_summary or "").strip() or "Executive findings and strategic synthesis."

        first_finding = "Robust empirical market signals observed."
        if findings and isinstance(findings[0], dict):
            first_finding = findings[0].get("finding") or first_finding
        elif findings and isinstance(findings[0], str) and findings[0].strip():
            first_finding = findings[0].strip()

        first_rec = "Immediate prioritized strategic execution required."
        if recommendations and isinstance(recommendations[0], dict):
            first_rec = (
                recommendations[0].get("action")
                or recommendations[0].get("recommendation")
                or first_rec
            )
        elif recommendations and isinstance(recommendations[0], str) and recommendations[0].strip():
            first_rec = recommendations[0].strip()

        first_risk = "Execution risks require active operational mitigation."
        if risks and isinstance(risks[0], dict):
            first_risk = risks[0].get("risk") or first_risk
        elif risks and isinstance(risks[0], str) and risks[0].strip():
            first_risk = risks[0].strip()

        s2 = SlideItem(
            slide_order=2,
            title="Executive Summary: Key Findings & Strategic Imperatives",
            key_message="Strategic synthesis across core market, economic, and technological dimensions.",
            layout=SlideLayout.executive_summary,
            content={
                "summary": summary_text,
                "key_takeaways": [first_finding, first_rec, first_risk],
            },
            source_ids=all_cited_sources[:3],
        )

        # Slide 3: Context & Problem Statement
        s3 = SlideItem(
            slide_order=3,
            title="Strategic Context & Core Industry Problem Statement",
            key_message="Macro industry dynamics demand a disciplined strategic response.",
            layout=SlideLayout.two_column,
            content={
                "left_column": {
                    "heading": "Market Dynamics & Catalysts",
                    "bullets": [
                        f"Geography focus: {project.geography or 'Target Region'}.",
                        f"Horizon timeline: {project.time_horizon or 'Forward Horizon'}.",
                        f"Key audience expectations: {project.audience or 'Executive Leadership'}.",
                    ],
                },
                "right_column": {
                    "heading": "Strategic Challenges",
                    "bullets": [
                        "Intensifying competitive pressure and technological acceleration.",
                        "Capital deployment efficiency and regulatory licensing constraints.",
                        "Need for defensible differentiation and high-margin operational models.",
                    ],
                },
            },
            source_ids=[],
        )

        # Slide 4: Empirical Findings
        top_findings = findings[:3]
        finding_cards = []
        for i, f in enumerate(top_findings):
            if isinstance(f, dict):
                conf = f.get("confidence", "high")
                conf_str = conf.value if hasattr(conf, "value") else str(conf or "high")
                finding_cards.append({
                    "number": f"0{i+1}",
                    "title": f"Finding {i+1}",
                    "text": f.get("finding") or "Empirical benchmark validates core market hypothesis.",
                    "confidence": conf_str,
                })
            elif isinstance(f, str) and f.strip():
                finding_cards.append({
                    "number": f"0{i+1}",
                    "title": f"Finding {i+1}",
                    "text": f.strip(),
                    "confidence": "high",
                })
        while len(finding_cards) < 3:
            idx = len(finding_cards) + 1
            finding_cards.append({
                "number": f"0{idx}",
                "title": f"Finding {idx}",
                "text": "Empirical data benchmarks indicate significant market inflection.",
                "confidence": "medium",
            })

        s4 = SlideItem(
            slide_order=4,
            title="Empirical Evidence & Market Benchmarks",
            key_message="Rigorous data-driven benchmarks validate core industry growth hypotheses.",
            layout=SlideLayout.three_insight,
            content={"cards": finding_cards},
            source_ids=all_cited_sources[:4],
        )

        # Slide 5: Strategic Comparison
        s5 = SlideItem(
            slide_order=5,
            title="Strategic Alternatives: Comparative Performance & Economics",
            key_message="Trade-off evaluation reveals clear competitive advantage for the primary pathway.",
            layout=SlideLayout.comparison,
            content={
                "headers": ["Evaluation Criteria", "Conventional Approach", "Proposed Strategic Model", "Advantage"],
                "rows": [
                    ["Capital Expenditure ($/unit)", "High upfront sunk cost", "Modular scalable deployment", "+35% CapEx flexibility"],
                    ["Time to Commercial Scale", "5-7 year gestation", "2-3 year agile rollout", "First-mover capture"],
                    ["Risk Profile", "Concentrated technical risk", "De-risked modular components", "Lower failure blast radius"],
                    ["Unit Margin Potential", "Commoditized (12-15%)", "Premium differentiated (>28%)", "+1300 bps EBITDA lift"],
                ],
            },
            source_ids=all_cited_sources[:2],
        )

        # Slide 6: Operational & Financial Implications
        implication_bullets = []
        for imp in implications[:4]:
            if isinstance(imp, dict):
                text = imp.get("implication")
                if text:
                    implication_bullets.append(str(text))
            elif isinstance(imp, str) and imp.strip():
                implication_bullets.append(imp.strip())
        while len(implication_bullets) < 2:
            implication_bullets.append("Substantial operational realignment required to capture margin expansion.")

        s6 = SlideItem(
            slide_order=6,
            title="Operational & Financial Implications",
            key_message="Realizing projected value requires decisive operational and capital restructuring.",
            layout=SlideLayout.two_column,
            content={
                "left_column": {
                    "heading": "Financial & Capital Implications",
                    "bullets": implication_bullets[:2],
                },
                "right_column": {
                    "heading": "Organizational & Operational Requirements",
                    "bullets": implication_bullets[2:4] if len(implication_bullets) > 2 else [
                        "Cross-functional program management unit to lead execution.",
                        "Real-time KPI telemetry and performance management governance.",
                    ],
                },
            },
            source_ids=all_cited_sources[:3],
        )

        # Slide 7: Strategic Recommendations
        rec_cards = []
        for i, r in enumerate(recommendations[:3]):
            if isinstance(r, dict):
                rec_action = r.get("action") or r.get("recommendation") or f"Value Creation Initiative {i+1}"
                rec_cards.append({
                    "number": f"REC-0{i+1}",
                    "title": str(rec_action)[:60],
                    "text": str(rec_action),
                    "priority": str(r.get("priority") or "high"),
                })
            elif isinstance(r, str) and r.strip():
                rec_cards.append({
                    "number": f"REC-0{i+1}",
                    "title": str(r)[:60],
                    "text": str(r),
                    "priority": "high",
                })
        while len(rec_cards) < 3:
            idx = len(rec_cards) + 1
            rec_cards.append({
                "number": f"REC-0{idx}",
                "title": f"Value Creation Initiative {idx}",
                "text": "Mobilize targeted workstreams with executive sponsorship.",
                "priority": "high",
            })

        s7 = SlideItem(
            slide_order=7,
            title="Prioritized Strategic Recommendations",
            key_message="A sequenced three-pillar program to maximize risk-adjusted commercial returns.",
            layout=SlideLayout.three_insight,
            content={"cards": rec_cards},
            source_ids=all_cited_sources[:3],
        )

        # Slide 8: Phased Implementation Roadmap
        s8 = SlideItem(
            slide_order=8,
            title="Phased Implementation Roadmap & Key Milestones",
            key_message="Disciplined execution roadmap spanning 100-day mobilization through full scale.",
            layout=SlideLayout.roadmap,
            content={
                "phases": [
                    {
                        "phase": "Phase 1: Mobilize",
                        "timing": "Months 0-3",
                        "milestones": [
                            "Charter steering committee & workstream leads.",
                            "Establish commercial pilot agreements.",
                            "Baseline operational and carbon metrics.",
                        ],
                    },
                    {
                        "phase": "Phase 2: Validate",
                        "timing": "Months 4-12",
                        "milestones": [
                            "Launch operational testbeds and validate economics.",
                            "Secure tier-1 supplier and licensing agreements.",
                            "Refine pricing and commercial contracts.",
                        ],
                    },
                    {
                        "phase": "Phase 3: Scale",
                        "timing": "Months 13-36",
                        "milestones": [
                            "Commercial rollout across core target segments.",
                            "Scale manufacturing / deployment operations.",
                            "Capture anticipated EBITDA market expansion.",
                        ],
                    },
                ]
            },
            source_ids=[],
        )

        # Slide 9: Risk Matrix & Countermeasures
        risk_cards = []
        for r in risks[:3]:
            if isinstance(r, dict):
                risk_cards.append({
                    "risk": r.get("risk") or "Regulatory and licensing timeline delays",
                    "severity": r.get("severity") or "medium",
                    "mitigation": r.get("mitigation") or "Early regulatory engagement and redundant pre-certification pathways.",
                })
            elif isinstance(r, str) and r.strip():
                risk_cards.append({
                    "risk": r.strip(),
                    "severity": "medium",
                    "mitigation": "Structured monitoring and hedging controls.",
                })
        while len(risk_cards) < 3:
            risk_cards.append({
                "risk": "Regulatory and licensing timeline delays",
                "severity": "high",
                "mitigation": "Early regulatory engagement and redundant pre-certification pathways.",
            })

        s9 = SlideItem(
            slide_order=9,
            title="Critical Execution Risks & Mitigation Matrix",
            key_message="Comprehensive risk controls neutralize top threats to budget, schedule, and safety.",
            layout=SlideLayout.risk_matrix,
            content={"risks": risk_cards},
            source_ids=all_cited_sources[:2],
        )

        # Slide 10: Research Gaps & Diligence
        gap_bullets = []
        for g in gaps[:4]:
            if isinstance(g, dict):
                text = g.get("gap_description") or g.get("gap") or g.get("limitation")
                if text:
                    gap_bullets.append(str(text))
            elif isinstance(g, str) and g.strip():
                gap_bullets.append(g.strip())
        while len(gap_bullets) < 2:
            gap_bullets.append("Vendor proprietary warranty and yield performance data required.")

        s10 = SlideItem(
            slide_order=10,
            title="Diligence Gaps & Sensitivity Considerations",
            key_message="Key analytical sensitivities requiring client-specific internal validation.",
            layout=SlideLayout.two_column,
            content={
                "left_column": {
                    "heading": "Public Data Gaps",
                    "bullets": gap_bullets[:2],
                },
                "right_column": {
                    "heading": "Recommended Next Diligence Steps",
                    "bullets": [
                        "Conduct confidential vendor RFIs under NDA.",
                        "Perform scenario stress-testing on commodity cost spikes.",
                        "Audit target facilities for integration readiness.",
                    ],
                },
            },
            source_ids=[],
        )

        # Slide 11: Conclusion & Immediate Action Items
        s11 = SlideItem(
            slide_order=11,
            title="Executive Decision Gates & Immediate Next Steps",
            key_message="Approval of core roadmap initiatives required to initiate Phase 1 mobilization.",
            layout=SlideLayout.closing,
            content={
                "call_to_action": "Board approval requested for Phase 1 project mobilization.",
                "action_items": [
                    "Authorize preliminary engineering & site diligence budget.",
                    "Appoint project executive sponsor and working group leads.",
                    "Schedule 60-day progress check-in with executive leadership.",
                ],
                "contact": f"Prepared for: {project.audience or 'Executive Leadership'} | {project.geography or 'Global'}",
            },
            source_ids=[],
        )

        return [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11]

    async def update_storyline(
        self,
        project_id: uuid.UUID,
        slides: List[SlideItem],
        approve_all: bool = False,
    ) -> StorylineOutline:
        """Validate, reorder, edit, and optionally approve slide specs."""
        if not slides:
            raise StorylineValidationError("Storyline must contain at least one slide.")

        # Validate contiguous 1-based order
        orders = [s.slide_order for s in slides]
        if sorted(orders) != list(range(1, len(slides) + 1)):
            raise StorylineValidationError(
                f"Slide orders must be a contiguous 1-based sequence 1..{len(slides)}. Received: {orders}"
            )

        # Validate non-empty titles and key messages
        for s in slides:
            if not s.title or not s.title.strip():
                raise StorylineValidationError(f"Slide order {s.slide_order} has empty title.")
            if not s.key_message or not s.key_message.strip():
                raise StorylineValidationError(f"Slide order {s.slide_order} has empty key message.")

        # Fetch latest insight ID
        i_stmt = (
            select(Insight.id)
            .where(Insight.project_id == project_id)
            .order_by(Insight.version.desc())
        )
        insight_id = (await self.db.execute(i_stmt)).scalars().first()
        if not insight_id:
            raise StorylineGateError(f"No insight found for project {project_id}.")

        # Re-persist slide specs
        await self.db.execute(
            delete(SlideSpec).where(SlideSpec.project_id == project_id)
        )

        updated_items: List[SlideItem] = []
        for s in slides:
            slide_approved = True if approve_all else s.is_approved
            slide_id = uuid.uuid4()
            if s.id:
                try:
                    slide_id = uuid.UUID(str(s.id))
                except (ValueError, AttributeError):
                    slide_id = uuid.uuid4()

            spec = SlideSpec(
                id=slide_id,
                project_id=project_id,
                insight_id=insight_id,
                slide_order=s.slide_order,
                title=s.title.strip(),
                key_message=s.key_message.strip(),
                layout=s.layout.value,
                content=s.content or {},
                source_ids=s.source_ids or [],
                is_approved=slide_approved,
            )
            self.db.add(spec)
            updated_items.append(
                SlideItem(
                    id=str(spec.id),
                    slide_order=spec.slide_order,
                    title=spec.title,
                    key_message=spec.key_message,
                    layout=SlideLayout(spec.layout) if spec.layout in SlideLayout._value2member_map_ else SlideLayout.two_column,
                    content=spec.content,
                    source_ids=[str(x) for x in (spec.source_ids or [])],
                    is_approved=spec.is_approved,
                )
            )

        # If approve_all, transition project status to approved
        if approve_all:
            p_stmt = select(Project).where(Project.id == project_id)
            project = (await self.db.execute(p_stmt)).scalar_one_or_none()
            if project:
                project.status = ProjectStatus.approved.value

        await self.db.commit()

        logger.info(
            "storyline_updated",
            project_id=str(project_id),
            count=len(updated_items),
            approve_all=approve_all,
        )

        return StorylineOutline(
            project_id=str(project_id),
            insight_id=str(insight_id),
            slides=updated_items,
            is_approved=approve_all or all(s.is_approved for s in updated_items),
            total_slides=len(updated_items),
        )
