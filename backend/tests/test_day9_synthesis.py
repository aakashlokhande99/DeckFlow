"""Day 9 tests: Consulting synthesis, evidence citation mapping, and grounding verification."""

from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ConfidenceLevel
from app.db.models import EvidenceClaim, Insight, Project, Source
from app.llm.mock import MockLLMProvider
from app.research.synthesizer import ConsultingSynthesizer
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
def sample_synthesis(valid_evidence_id: str) -> ConsultingSynthesis:
    return ConsultingSynthesis(
        executive_summary="Solid-state batteries offer 40% higher gravimetric energy density but face high manufacturing scrap rates.",
        findings=[
            SynthesisFinding(
                id="F1",
                finding="Solid-state cells achieve 450 Wh/kg versus 300 Wh/kg in conventional liquid NMC811 cells.",
                evidence_ids=[valid_evidence_id],
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            ),
            SynthesisFinding(
                id="F2",
                finding="Commercial gigafactory cell cost parity will occur by 2026.",
                evidence_ids=["00000000-0000-0000-0000-000000000999"],  # Non-existent hallucinated evidence ID
                confidence=ConfidenceLevel.medium,
                is_uncertain=False,
            ),
            SynthesisFinding(
                id="F3",
                finding="Unsubstantiated claim with no cited evidence.",
                evidence_ids=[],  # Missing evidence
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            ),
        ],
        implications=[
            SynthesisImplication(
                id="I1",
                finding_ids=["F1"],
                implication="EV range can increase to 600 miles per pack without vehicle weight penalty.",
            )
        ],
        recommendations=[
            SynthesisRecommendation(
                id="R1",
                action="Form strategic joint venture with dry-electrode separator supplier.",
                timeframe="0-12 months",
                priority="high",
                evidence_ids=[valid_evidence_id],
            )
        ],
        risks=[
            SynthesisRisk(
                id="RK1",
                risk="Ceramic separator microcracking under thermal cycling.",
                severity="high",
                mitigation="Accelerate silicon-anode composite hybrid prototyping.",
            )
        ],
        limitations=["Public disclosure by tier-1 battery cell makers remains proprietary."],
        gaps=[
            SynthesisGap(
                id="G1",
                gap_description="Independent teardown data on separator cycle life after 1000 fast-charge cycles.",
                impact_on_decision="Key requirement before committing $500M+ capital expenditure.",
            )
        ],
        citations=[
            SynthesisCitation(
                source_id=str(uuid.uuid4()),
                citation_label="[1] Battery Tech Review 2024",
                url="https://batterytech.org/ssb-analysis",
            )
        ],
    )


@pytest.mark.asyncio
async def test_synthesizer_grounding_and_flagging(db_session: AsyncSession) -> None:
    # 1. Create project and source in DB
    project = Project(
        topic="Solid-State EV Battery Economics",
        objective="Analyze density breakthroughs and gigafactory feasibility.",
        audience="Automotive OEM Board",
        geography="Global",
        time_horizon="2025-2030",
    )
    db_session.add(project)
    await db_session.flush()

    source = Source(
        project_id=project.id,
        canonical_url="https://batterytech.org/ssb-analysis",
        title="Solid State Battery Analysis 2024",
        access_time=project.created_at,
    )
    db_session.add(source)
    await db_session.flush()

    # 2. Create one genuine stored EvidenceClaim
    real_claim = EvidenceClaim(
        project_id=project.id,
        source_ids=[source.id],
        claim_text="Solid-state prototype cells demonstrate 450 Wh/kg in laboratory testing.",
        confidence=ConfidenceLevel.high.value,
        is_uncertain=False,
    )
    db_session.add(real_claim)
    await db_session.flush()

    valid_evidence_id = str(real_claim.id)

    # 3. Build mock synthesis
    mock_synth = ConsultingSynthesis(
        executive_summary="Solid-state batteries provide higher energy density but cost parity is delayed.",
        findings=[
            SynthesisFinding(
                id="F1",
                finding="Solid-state cells achieve 450 Wh/kg.",
                evidence_ids=[valid_evidence_id],
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            ),
            SynthesisFinding(
                id="F2",
                finding="Cost parity achieved by 2026 (unsupported).",
                evidence_ids=["00000000-0000-0000-0000-000000000999"],  # Hallucinated ID
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            ),
            SynthesisFinding(
                id="F3",
                finding="Missing citations altogether.",
                evidence_ids=[],
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            ),
        ],
        implications=[
            SynthesisImplication(id="I1", finding_ids=["F1"], implication="Weight reduction.")
        ],
        recommendations=[
            SynthesisRecommendation(
                id="R1",
                action="Accelerate R&D joint venture.",
                timeframe="6-12 months",
                priority="high",
                evidence_ids=[valid_evidence_id],
            )
        ],
        risks=[
            SynthesisRisk(id="RK1", risk="Separator failure.", severity="high", mitigation="Add coating.")
        ],
        limitations=["Laboratory data only."],
        gaps=[
            SynthesisGap(id="G1", gap_description="Fast-charge cycle life.", impact_on_decision="Critical for warranty.")
        ],
        citations=[
            SynthesisCitation(
                source_id=str(source.id),
                citation_label="[1] Battery Tech (2024)",
                url=source.canonical_url,
            )
        ],
    )

    mock_llm = MockLLMProvider(structured_responses={"ConsultingSynthesis": mock_synth})
    synthesizer = ConsultingSynthesizer(db=db_session, llm_provider=mock_llm)

    # 4. Execute synthesis
    synthesis, insight = await synthesizer.synthesize(project_id=project.id)

    # 5. Assertions on grounding verification
    f1 = next(f for f in synthesis.findings if f.id == "F1")
    assert f1.is_uncertain is False
    assert f1.evidence_ids == [valid_evidence_id]

    f2 = next(f for f in synthesis.findings if f.id == "F2")
    # F2 hallucinated a non-existent evidence_id -> flagged as uncertain
    assert f2.is_uncertain is True
    assert f2.confidence == ConfidenceLevel.uncertain

    f3 = next(f for f in synthesis.findings if f.id == "F3")
    # F3 had no evidence_ids -> flagged as uncertain
    assert f3.is_uncertain is True
    assert f3.confidence == ConfidenceLevel.uncertain

    # 6. Verify Insight persisted into DB
    assert insight.id is not None
    assert insight.project_id == project.id
    assert insight.version == 1
    assert len(insight.findings) == 3
    assert len(insight.recommendations) == 1
    assert len(insight.gaps) == 1

    # Reload from database to confirm persistence
    db_insight = (
        await db_session.execute(select(Insight).where(Insight.id == insight.id))
    ).scalar_one_or_none()
    assert db_insight is not None
    assert db_insight.executive_summary == mock_synth.executive_summary
