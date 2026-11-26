"""Day 15 tests: Observability telemetry, grounding metrics, and regression suite."""

from __future__ import annotations

import time
import pytest

from app.db.enums import ConfidenceLevel
from app.evaluation.grounding_eval import GroundingEvaluator
from app.evaluation.regression_runner import (
    EvaluationRegressionError,
    EvaluationTestCase,
    RegressionRunner,
)
from app.observability.langfuse import TraceRecord, tracer
from app.schemas.project import ResearchPlan
from app.schemas.synthesis import (
    ConsultingSynthesis,
    SynthesisFinding,
    SynthesisGap,
    SynthesisImplication,
    SynthesisRecommendation,
    SynthesisRisk,
)


@pytest.fixture
def sample_plan() -> ResearchPlan:
    return ResearchPlan(
        questions=[
            "What is the capital cost per kilowatt for small modular reactors?",
            "What is the licensing timeline required by the Nuclear Regulatory Commission?",
        ],
        search_queries=["SMR capital cost per kW", "NRC SMR licensing timeline"],
    )


@pytest.fixture
def high_quality_synthesis() -> ConsultingSynthesis:
    return ConsultingSynthesis(
        executive_summary="Small modular reactors average $4,500/kW capital costs with NRC licensing taking 36 to 48 months.",
        findings=[
            SynthesisFinding(
                id="F1",
                finding="Capital costs average $4,500/kW for overnight construction in nth-of-a-kind plants.",
                evidence_ids=["ev-valid-001"],
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            ),
            SynthesisFinding(
                id="F2",
                finding="NRC licensing review schedules range between 36 and 48 months for standard designs.",
                evidence_ids=["ev-valid-002"],
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            ),
        ],
        implications=[
            SynthesisImplication(
                id="I1",
                finding_ids=["F1"],
                implication="CapEx parity with advanced natural gas combined cycle requires carbon pricing offsets.",
            )
        ],
        recommendations=[
            SynthesisRecommendation(
                id="R1",
                action="Form consortia with utility co-investors to share pre-licensing design costs.",
                timeframe="0-6 months",
                priority="high",
            )
        ],
        risks=[
            SynthesisRisk(
                id="RK1",
                risk="First-of-a-kind fabrication lead time extensions beyond 24 months.",
                severity="medium",
                mitigation="Pre-order heavy forgings and qualify secondary forge suppliers.",
            )
        ],
        limitations=[],
        gaps=[
            SynthesisGap(
                id="G1",
                gap_description="Supply chain availability for high-assay low-enriched uranium fuel.",
                impact_on_decision="May delay reactor initial fuel loading schedule.",
            )
        ],
    )


def test_tracer_records_latency_tokens_cost() -> None:
    """Verify observability tracer measures latency, token estimations, and cost tracking."""
    tracer.clear()

    with tracer.span(
        name="test_llm_synthesis",
        run_type="llm",
        project_id="proj-123",
        prompt_text="Detailed executive query prompt containing several words.",
    ) as ctx:
        time.sleep(0.01)  # Simulate 10ms execution
        ctx["output_text"] = "Generated structured response payload."
        ctx["metadata"]["model"] = "gpt-4o"

    traces = tracer.get_recent_traces()
    assert len(traces) == 1
    t = traces[0]
    assert t.name == "test_llm_synthesis"
    assert t.run_type == "llm"
    assert t.project_id == "proj-123"
    assert t.latency_ms >= 5.0
    assert t.input_tokens > 0
    assert t.output_tokens > 0
    assert t.estimated_cost_usd > 0.0
    assert t.status == "success"
    assert t.metadata["model"] == "gpt-4o"


def test_grounding_evaluator_perfect_score(
    high_quality_synthesis: ConsultingSynthesis,
    sample_plan: ResearchPlan,
) -> None:
    """Verify high quality synthesis achieves 1.0 grounding and passes evaluation thresholds."""
    valid_ids = {"ev-valid-001", "ev-valid-002"}
    evaluator = GroundingEvaluator()

    scorecard = evaluator.evaluate_all(
        synthesis=high_quality_synthesis,
        valid_evidence_ids=valid_ids,
        plan=sample_plan,
    )
    assert scorecard.grounding_score == 1.0
    assert scorecard.citation_coverage == 1.0
    assert scorecard.completeness_score == 1.0
    assert scorecard.schema_conformance == 1.0
    assert scorecard.composite_score == 1.0
    assert scorecard.passed is True


def test_grounding_evaluator_penalizes_hallucinations_and_missing(
    high_quality_synthesis: ConsultingSynthesis,
) -> None:
    """Verify evaluator catches ungrounded and hallucinated evidence citations."""
    valid_ids = {"ev-valid-001"}  # ev-valid-002 is missing/hallucinated

    evaluator = GroundingEvaluator()
    g_score, details = evaluator.evaluate_grounding(high_quality_synthesis, valid_ids)

    # 1 of 2 findings cited ev-valid-002 which is invalid, so grounding is 50%
    assert g_score == 0.5
    assert details["grounded_findings"] == 1
    assert len(details["issues"]) == 1
    assert details["issues"][0]["reason"] == "hallucinated_ids"


def test_coverage_evaluator_measures_question_alignment(
    high_quality_synthesis: ConsultingSynthesis,
    sample_plan: ResearchPlan,
) -> None:
    """Verify citation coverage checks alignment between questions and findings."""
    evaluator = GroundingEvaluator()

    # Both questions are clearly addressed in the findings
    cov_score, details = evaluator.evaluate_coverage(high_quality_synthesis, sample_plan)
    assert cov_score == 1.0
    assert details["covered_questions"] == 2

    # Add unrelated question
    sample_plan.questions.append("What are offshore wind transmission interconnection costs in the North Sea?")
    cov_score_unrelated, details_unrelated = evaluator.evaluate_coverage(high_quality_synthesis, sample_plan)
    assert cov_score_unrelated < 1.0
    assert details_unrelated["covered_questions"] == 2


def test_regression_runner_passes_clean_benchmark(
    high_quality_synthesis: ConsultingSynthesis,
    sample_plan: ResearchPlan,
) -> None:
    """Verify regression suite executes cleanly and reports passed summary."""
    runner = RegressionRunner()
    case = EvaluationTestCase(
        case_id="smr-benchmark-01",
        description="Standard SMR economic synthesis benchmark",
        plan=sample_plan,
        valid_evidence_ids=["ev-valid-001", "ev-valid-002"],
        synthesis=high_quality_synthesis,
    )

    summary = runner.run_suite([case])
    assert summary["total_cases"] == 1
    assert summary["passed_cases"] == 1
    assert summary["failed_cases"] == 0
    assert summary["pass_rate"] == 1.0


def test_regression_runner_fails_on_degraded_synthesis(
    high_quality_synthesis: ConsultingSynthesis,
    sample_plan: ResearchPlan,
) -> None:
    """Verify zero-regression quality gate fails when citations are hallucinated."""
    runner = RegressionRunner()
    # Provide no valid evidence IDs, making all citations hallucinated
    degraded_case = EvaluationTestCase(
        case_id="degraded-synthesis-02",
        description="Degraded synthesis with hallucinated evidence IDs",
        plan=sample_plan,
        valid_evidence_ids=[],  # No valid evidence IDs!
        synthesis=high_quality_synthesis,
    )

    with pytest.raises(EvaluationRegressionError, match="failed quality regression gate"):
        runner.run_suite([degraded_case])
