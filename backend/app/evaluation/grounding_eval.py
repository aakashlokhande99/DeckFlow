"""Evaluation metrics for consulting synthesis: grounding, citation coverage, completeness, and schema conformance."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from app.schemas.project import ResearchPlan
from app.schemas.synthesis import ConsultingSynthesis


class EvaluationScoreCard(BaseModel):
    """Evaluation scoring output across all 4 quality dimensions."""

    grounding_score: float = Field(..., ge=0.0, le=1.0, description="Ratio of verified evidence citations")
    citation_coverage: float = Field(..., ge=0.0, le=1.0, description="Fraction of research plan questions covered")
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Presence of all mandatory consulting sections")
    schema_conformance: float = Field(..., ge=0.0, le=1.0, description="Pydantic schema validation result")
    composite_score: float = Field(..., ge=0.0, le=1.0, description="Weighted composite quality score")
    passed: bool = Field(..., description="Whether synthesis meets all minimum release criteria")
    details: Dict[str, Any] = Field(default_factory=dict)


class GroundingEvaluator:
    """Computes rigorous quantitative quality scores for consulting syntheses."""

    def __init__(
        self,
        min_grounding: float = 0.85,
        min_coverage: float = 0.80,
        min_completeness: float = 0.90,
        min_schema: float = 1.0,
    ) -> None:
        self.min_grounding = min_grounding
        self.min_coverage = min_coverage
        self.min_completeness = min_completeness
        self.min_schema = min_schema

    def evaluate_grounding(
        self,
        synthesis: ConsultingSynthesis,
        valid_evidence_ids: Set[str],
    ) -> tuple[float, dict]:
        """Score percentage of factual findings grounded in valid evidence."""
        findings = synthesis.findings or []
        if not findings:
            return 1.0, {"total": 0, "grounded": 0, "hallucinated_or_missing": []}

        grounded_count = 0
        issues = []

        for f in findings:
            if f.is_uncertain:
                # Explicitly marked as uncertain / hypothesis, not a hallucination
                grounded_count += 1
                continue

            if not f.evidence_ids:
                issues.append({"finding_id": f.id, "reason": "missing_citations"})
                continue

            # Check if all cited evidence IDs exist
            hallucinated = [eid for eid in f.evidence_ids if eid not in valid_evidence_ids]
            if hallucinated:
                issues.append({"finding_id": f.id, "reason": "hallucinated_ids", "ids": hallucinated})
            else:
                grounded_count += 1

        score = grounded_count / len(findings)
        return round(score, 4), {
            "total_findings": len(findings),
            "grounded_findings": grounded_count,
            "issues": issues,
        }

    def evaluate_coverage(
        self,
        synthesis: ConsultingSynthesis,
        plan: Optional[ResearchPlan],
    ) -> tuple[float, dict]:
        """Score fraction of research plan questions answered by synthesized findings."""
        if not plan or not plan.questions:
            return 1.0, {"total_questions": 0, "covered_questions": 0}

        text_parts = [
            synthesis.executive_summary or "",
            *(f.finding for f in (synthesis.findings or [])),
            *(imp.implication for imp in (synthesis.implications or [])),
            *(rec.action for rec in (synthesis.recommendations or [])),
            *(rk.risk + " " + rk.mitigation for rk in (synthesis.risks or [])),
            *(g.gap_description for g in (synthesis.gaps or [])),
        ]
        corpus_text = " ".join(text_parts).lower()

        # Expand common consulting / engineering acronyms
        acronym_expansions = {
            "nrc": "nuclear regulatory commission",
            "smr": "small modular reactor",
            "ev": "electric vehicle",
            "capex": "capital expenditure",
            "opex": "operational expenditure",
            "cagr": "compound annual growth rate",
            "iea": "international energy agency",
        }
        for acr, expansion in acronym_expansions.items():
            if acr in corpus_text:
                corpus_text += f" {expansion}"
            if expansion in corpus_text:
                corpus_text += f" {acr}"

        covered_count = 0
        question_details = []
        stop_words = {
            "what", "are", "the", "and", "for", "is", "how", "why", "with", "from",
            "in", "to", "of", "required", "by", "does", "can", "a", "an"
        }

        for q in plan.questions:
            # Extract key nouns/words > 3 chars
            tokens = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 3 and w not in stop_words]
            if not tokens:
                covered_count += 1
                question_details.append({"question": q, "covered": True, "overlap": 1.0})
                continue

            matches = sum(1 for t in tokens if t in corpus_text)
            overlap_ratio = matches / len(tokens)
            is_covered = (matches >= 2) or (overlap_ratio >= 0.25) or (len(tokens) <= 2 and matches >= 1)

            if is_covered:
                covered_count += 1

            question_details.append({
                "question": q,
                "covered": is_covered,
                "matches": matches,
                "total_tokens": len(tokens),
                "overlap_ratio": round(overlap_ratio, 2),
            })

        score = covered_count / len(plan.questions)
        return round(score, 4), {
            "total_questions": len(plan.questions),
            "covered_questions": covered_count,
            "question_details": question_details,
        }

    def evaluate_completeness(self, synthesis: ConsultingSynthesis) -> tuple[float, dict]:
        """Score presence and minimum substance of all required consulting sections."""
        checks = {
            "executive_summary": bool(synthesis.executive_summary and len(synthesis.executive_summary.strip()) >= 20),
            "findings": bool(synthesis.findings and len(synthesis.findings) >= 1),
            "implications": bool(synthesis.implications and len(synthesis.implications) >= 1),
            "recommendations": bool(synthesis.recommendations and len(synthesis.recommendations) >= 1),
            "risks": bool(synthesis.risks and len(synthesis.risks) >= 1),
            "gaps_or_limitations": bool((synthesis.gaps and len(synthesis.gaps) >= 1) or (synthesis.limitations and len(synthesis.limitations) >= 1)),
        }
        passed_count = sum(1 for v in checks.values() if v)
        score = passed_count / len(checks)
        return round(score, 4), {"section_checks": checks, "passed_sections": passed_count, "total_sections": len(checks)}

    def evaluate_schema(self, raw_data: Dict[str, Any]) -> tuple[float, dict]:
        """Score Pydantic schema validation conformance."""
        try:
            ConsultingSynthesis.model_validate(raw_data)
            return 1.0, {"valid": True, "error": None}
        except Exception as exc:
            return 0.0, {"valid": False, "error": str(exc)}

    def evaluate_all(
        self,
        synthesis: ConsultingSynthesis,
        valid_evidence_ids: Set[str],
        plan: Optional[ResearchPlan] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> EvaluationScoreCard:
        """Compute composite evaluation scorecard across all 4 pillars."""
        g_score, g_details = self.evaluate_grounding(synthesis, valid_evidence_ids)
        c_score, c_details = self.evaluate_coverage(synthesis, plan)
        comp_score, comp_details = self.evaluate_completeness(synthesis)

        s_score = 1.0
        s_details = {"valid": True}
        if raw_data is not None:
            s_score, s_details = self.evaluate_schema(raw_data)

        # Composite weighted score: Grounding 40%, Coverage 25%, Completeness 25%, Schema 10%
        composite = (0.40 * g_score) + (0.25 * c_score) + (0.25 * comp_score) + (0.10 * s_score)

        passed = (
            g_score >= self.min_grounding
            and c_score >= self.min_coverage
            and comp_score >= self.min_completeness
            and s_score >= self.min_schema
        )

        return EvaluationScoreCard(
            grounding_score=g_score,
            citation_coverage=c_score,
            completeness_score=comp_score,
            schema_conformance=s_score,
            composite_score=round(composite, 4),
            passed=passed,
            details={
                "grounding": g_details,
                "coverage": c_details,
                "completeness": comp_details,
                "schema": s_details,
            },
        )
