"""Day 10 tests: Synthesis Quality Gate checks (citations, coverage, contradictions, duplicates) and revision versioning."""

from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ConfidenceLevel
from app.db.models import EvidenceClaim, Insight, Project
from app.research.quality_gate import SynthesisQualityGate
from app.schemas.project import ResearchPlan
from app.schemas.synthesis import (
    ConsultingSynthesis,
    SynthesisCitation,
    SynthesisFinding,
    SynthesisGap,
    SynthesisImplication,
    SynthesisRecommendation,
    SynthesisRisk,
)


@pytest.fixture
def base_plan() -> ResearchPlan:
    return ResearchPlan(
        questions=[
            "What is the capital expenditure breakdown for commercial SMR deployments?",
            "What are the nuclear licensing requirements under NRC Part 53?",
            "What are the supply chain bottlenecks for high-assay low-enriched uranium (HALEU)?",
        ],
        search_queries=["smr capex breakdown", "nrc part 53 licensing", "haleu supply chain"],
        scope_notes="Focuses on US and OECD markets.",
        exclusions=["Fusion reactors"],
    )


def test_quality_gate_passes_healthy_synthesis(base_plan: ResearchPlan) -> None:
    synthesis = ConsultingSynthesis(
        executive_summary="SMR deployments feature projected capital expenditure of $4,500/kW with NRC Part 53 regulatory framework maturing and HALEU supply chain being the critical bottleneck.",
        findings=[
            SynthesisFinding(
                id="F1",
                finding="Average SMR capital expenditure benchmarks stand at $4,500 per kW.",
                evidence_ids=["eid-1"],
                confidence=ConfidenceLevel.high,
            ),
            SynthesisFinding(
                id="F2",
                finding="NRC Part 53 establishes risk-informed, performance-based licensing rules for advanced nuclear reactors.",
                evidence_ids=["eid-2"],
                confidence=ConfidenceLevel.high,
            ),
            SynthesisFinding(
                id="F3",
                finding="HALEU supply chain faces acute bottleneck due to domestic enrichment facility deficit.",
                evidence_ids=["eid-3"],
                confidence=ConfidenceLevel.high,
            ),
        ],
        implications=[
            SynthesisImplication(id="I1", finding_ids=["F1", "F2"], implication="Faster licensing reduces financing carry costs.")
        ],
        recommendations=[
            SynthesisRecommendation(
                id="R1",
                action="Secure forward contracts with commercial HALEU deconversion providers.",
                timeframe="0-12 months",
                priority="high",
                evidence_ids=["eid-3"],
            )
        ],
        risks=[
            SynthesisRisk(id="RK1", risk="Enrichment delay.", severity="high", mitigation="Offtake agreements.")
        ],
        limitations=["Market pricing based on early non-binding offtake letters."],
        gaps=[],
        citations=[
            SynthesisCitation(source_id="src-1", citation_label="[1] NRC Report", url="https://nrc.gov/doc")
        ],
    )

    gate = SynthesisQualityGate()
    result = gate.evaluate(synthesis=synthesis, plan=base_plan)

    assert result.passed is True
    assert result.overall_score >= 0.85
    assert result.citation_completeness_score == 1.0
    assert result.question_coverage_score == 1.0
    assert result.actionability_score == 1.0
    assert len(result.issues) == 0


def test_quality_gate_fails_missing_citations(base_plan: ResearchPlan) -> None:
    synthesis = ConsultingSynthesis(
        executive_summary="Summary of findings with thin citations.",
        findings=[
            SynthesisFinding(id="F1", finding="Finding without any evidence citation.", evidence_ids=[]),
            SynthesisFinding(id="F2", finding="Another uncited finding.", evidence_ids=[]),
            SynthesisFinding(id="F3", finding="Only one cited finding.", evidence_ids=["eid-1"]),
        ],
        recommendations=[
            SynthesisRecommendation(
                id="R1",
                action="Action with sufficient timeframe and priority.",
                timeframe="6-12 months",
                priority="high",
                evidence_ids=["eid-1"],
            )
        ],
    )

    gate = SynthesisQualityGate(min_citation_threshold=0.80)
    result = gate.evaluate(synthesis=synthesis, plan=base_plan)

    assert result.passed is False
    assert result.citation_completeness_score < 0.50
    assert "F1" in result.uncited_finding_ids
    assert "F2" in result.uncited_finding_ids


def test_quality_gate_fails_thin_question_coverage(base_plan: ResearchPlan) -> None:
    # Synthesis completely omits NRC licensing and HALEU questions
    synthesis = ConsultingSynthesis(
        executive_summary="Report focusing solely on cost metrics without addressing regulatory or fuel supply questions.",
        findings=[
            SynthesisFinding(
                id="F1",
                finding="Average capital expenditure stands at $4,500 per kW for advanced reactors.",
                evidence_ids=["eid-1"],
            )
        ],
        recommendations=[
            SynthesisRecommendation(
                id="R1",
                action="Establish benchmark tracking for capital expenditure.",
                timeframe="3-6 months",
                priority="medium",
                evidence_ids=["eid-1"],
            )
        ],
    )

    gate = SynthesisQualityGate()
    result = gate.evaluate(synthesis=synthesis, plan=base_plan)

    assert result.passed is False
    assert result.question_coverage_score < 0.70
    assert len(result.unaddressed_questions) >= 2


def test_quality_gate_detects_contradictions(base_plan: ResearchPlan) -> None:
    contradictory_claim = EvidenceClaim(
        project_id=uuid.uuid4(),
        claim_text="LCOE is reported at $60/MWh by vendor but independent studies report $140/MWh.",
        is_contradiction=True,
    )

    synthesis = ConsultingSynthesis(
        executive_summary="Reactor economics summary.",
        findings=[
            SynthesisFinding(id="F1", finding="LCOE estimates are conflicting.", evidence_ids=["eid-1"])
        ],
        recommendations=[
            SynthesisRecommendation(id="R1", action="Execute third-party cost audit.", timeframe="1-3 months", priority="high")
        ],
    )

    gate = SynthesisQualityGate()
    result = gate.evaluate(synthesis=synthesis, plan=base_plan, evidence_claims=[contradictory_claim])

    assert len(result.contradictions_detected) > 0
    assert any("contradiction" in issue.lower() for issue in result.issues)


def test_quality_gate_detects_redundant_duplicate_findings() -> None:
    synthesis = ConsultingSynthesis(
        executive_summary="Summary with repetitive claims.",
        findings=[
            SynthesisFinding(
                id="F1",
                finding="SMR capital costs average $4,500 per kilowatt across North American sites.",
                evidence_ids=["eid-1"],
            ),
            SynthesisFinding(
                id="F2",
                # 90%+ vocabulary match
                finding="SMR capital costs average $4,500 per kilowatt across North American sites.",
                evidence_ids=["eid-1"],
            ),
        ],
        recommendations=[
            SynthesisRecommendation(id="R1", action="Perform capital allocation plan.", timeframe="3-6 months", priority="high")
        ],
    )

    gate = SynthesisQualityGate()
    result = gate.evaluate(synthesis=synthesis)

    assert result.passed is False
    assert len(result.duplicate_findings) > 0


@pytest.mark.asyncio
async def test_revision_versioning_preserves_audit_history(db_session: AsyncSession) -> None:
    """Validate that revisions increment version number without silent claim deletion."""
    project = Project(
        topic="Green Hydrogen Electrolyzer Capex",
        objective="Assess PEM vs Alkaline stack costs.",
        audience="Industrial Decarbonization Fund",
        geography="EU & US",
        time_horizon="2025-2030",
    )
    db_session.add(project)
    await db_session.flush()

    # 1. Version 1 Insight
    v1_insight = Insight(
        project_id=project.id,
        executive_summary="V1 Initial Assessment: High stack degradation rates.",
        findings=[{"id": "F1", "finding": "Stack degradation is 1.5% per 1,000 hours."}],
        version=1,
    )
    db_session.add(v1_insight)
    await db_session.flush()

    # 2. Version 2 Revised Insight
    v2_insight = Insight(
        project_id=project.id,
        executive_summary="V2 Revised Assessment: Enhanced catalyst reduces degradation to 0.8%.",
        findings=[
            {"id": "F1", "finding": "Stack degradation is 1.5% per 1,000 hours."},
            {"id": "F2", "finding": "Enhanced catalyst reduces degradation to 0.8%."},
        ],
        version=2,
    )
    db_session.add(v2_insight)
    await db_session.flush()

    # 3. Verify both versions exist simultaneously
    stmt = (
        select(Insight)
        .where(Insight.project_id == project.id)
        .order_by(Insight.version.asc())
    )
    all_insights = (await db_session.execute(stmt)).scalars().all()

    assert len(all_insights) == 2
    assert all_insights[0].version == 1
    assert "V1" in all_insights[0].executive_summary
    assert all_insights[1].version == 2
    assert "V2" in all_insights[1].executive_summary
