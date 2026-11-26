"""Regression test runner for evaluation benchmarks.

Executes ground truth evaluation suites, records score histories,
and fails with EvaluationRegressionError when citation coverage, grounding,
completeness, or schema quality regresses below baseline thresholds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set
import structlog
from pydantic import BaseModel, Field

from app.evaluation.grounding_eval import EvaluationScoreCard, GroundingEvaluator
from app.schemas.project import ResearchPlan
from app.schemas.synthesis import ConsultingSynthesis

logger = structlog.get_logger(__name__)


class EvaluationRegressionError(Exception):
    """Raised when an evaluation test case violates minimum quality thresholds."""
    pass


class EvaluationTestCase(BaseModel):
    """Benchmark test case containing inputs and candidate synthesis."""

    case_id: str
    description: str
    plan: ResearchPlan
    valid_evidence_ids: List[str]
    synthesis: ConsultingSynthesis


class RegressionRunner:
    """Orchestrates batch evaluation and enforces zero-regression quality gates."""

    def __init__(self, evaluator: GroundingEvaluator | None = None) -> None:
        self.evaluator = evaluator or GroundingEvaluator()

    def run_suite(
        self,
        test_cases: List[EvaluationTestCase],
        fail_fast: bool = False,
    ) -> Dict[str, Any]:
        """Execute evaluation suite across all benchmark test cases."""
        results: Dict[str, EvaluationScoreCard] = {}
        failures: List[Dict[str, Any]] = []

        for case in test_cases:
            card = self.evaluator.evaluate_all(
                synthesis=case.synthesis,
                valid_evidence_ids=set(case.valid_evidence_ids),
                plan=case.plan,
            )
            results[case.case_id] = card

            if not card.passed:
                fail_info = {
                    "case_id": case.case_id,
                    "description": case.description,
                    "composite_score": card.composite_score,
                    "grounding": card.grounding_score,
                    "coverage": card.citation_coverage,
                    "completeness": card.completeness_score,
                    "schema": card.schema_conformance,
                }
                failures.append(fail_info)
                logger.warning("evaluation_regression_detected", **fail_info)

                if fail_fast:
                    raise EvaluationRegressionError(
                        f"Regression detected in test case '{case.case_id}': "
                        f"grounding={card.grounding_score}, coverage={card.citation_coverage}"
                    )

        total = len(test_cases)
        passed_count = total - len(failures)
        pass_rate = (passed_count / total) if total > 0 else 1.0

        summary = {
            "total_cases": total,
            "passed_cases": passed_count,
            "failed_cases": len(failures),
            "pass_rate": round(pass_rate, 4),
            "results": {cid: card.model_dump() for cid, card in results.items()},
            "failures": failures,
        }

        if failures:
            raise EvaluationRegressionError(
                f"{len(failures)}/{total} benchmark test cases failed quality regression gate: {failures}"
            )

        logger.info(
            "evaluation_suite_passed",
            total_cases=total,
            pass_rate=pass_rate,
        )
        return summary
