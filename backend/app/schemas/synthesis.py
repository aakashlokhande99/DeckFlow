"""Structured Pydantic contracts for consulting synthesis and evidence citation."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from app.db.enums import ConfidenceLevel


class SynthesisFinding(BaseModel):
    """Material factual finding derived strictly from evidence."""
    id: str = Field(..., description="Unique finding key, e.g. F1, F2")
    finding: str = Field(..., description="Material factual finding with precise data points")
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="UUID strings of EvidenceClaims supporting this finding",
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.medium,
        description="Assessed confidence level based on source credibility",
    )
    is_uncertain: bool = Field(
        default=False,
        description="True if claim lacks definitive empirical proof",
    )


class SynthesisImplication(BaseModel):
    """Business or strategic consequence of one or more findings."""
    id: str = Field(..., description="Unique implication key, e.g. I1, I2")
    finding_ids: List[str] = Field(
        default_factory=list,
        description="IDs of findings this implication stems from",
    )
    implication: str = Field(..., description="Commercial, economic, or operational consequence")


class SynthesisRecommendation(BaseModel):
    """Actionable consulting recommendation."""
    id: str = Field(..., description="Unique recommendation key, e.g. R1, R2")
    action: str = Field(..., description="Specific, executable strategic action")
    timeframe: str = Field(..., description="Target execution window (e.g. 0-6 months, 6-18 months)")
    priority: str = Field(default="high", description="high | medium | low")
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="Underlying evidence claim IDs supporting this action",
    )


class SynthesisRisk(BaseModel):
    """Identified execution, financial, or regulatory risk."""
    id: str = Field(..., description="Unique risk key, e.g. RK1")
    risk: str = Field(..., description="Description of the risk")
    severity: str = Field(default="medium", description="critical | high | medium | low")
    mitigation: str = Field(..., description="Recommended mitigation playbook or countermeasure")


class SynthesisGap(BaseModel):
    """Identified research or data gap that requires further diligence."""
    id: str = Field(..., description="Unique gap key, e.g. G1")
    gap_description: str = Field(..., description="Specific question or data metric lacking evidence")
    impact_on_decision: str = Field(..., description="How this uncertainty affects executive decisions")


class SynthesisCitation(BaseModel):
    """Explicit bibliographic citation linked to a registered Source."""
    source_id: str = Field(..., description="UUID of registered Source record")
    citation_label: str = Field(..., description="Human-readable reference label, e.g. [1] McKinsey (2024)")
    url: str = Field(..., description="Canonical source URL")


class ConsultingSynthesis(BaseModel):
    """Top-level consulting synthesis report strictly grounded in collected evidence."""
    executive_summary: str = Field(
        ...,
        description="2-3 paragraph executive-level synthesis framing the strategic conclusion",
    )
    findings: List[SynthesisFinding] = Field(
        default_factory=list,
        description="Key factual findings with evidence links",
    )
    implications: List[SynthesisImplication] = Field(
        default_factory=list,
        description="Strategic implications for the executive stakeholder",
    )
    recommendations: List[SynthesisRecommendation] = Field(
        default_factory=list,
        description="Prioritized, actionable recommendations",
    )
    risks: List[SynthesisRisk] = Field(
        default_factory=list,
        description="Identified risks and proposed mitigations",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Methodological limitations of the research",
    )
    gaps: List[SynthesisGap] = Field(
        default_factory=list,
        description="Information gaps requiring deeper investigation",
    )
    citations: List[SynthesisCitation] = Field(
        default_factory=list,
        description="Complete list of consulted sources with IDs",
    )
