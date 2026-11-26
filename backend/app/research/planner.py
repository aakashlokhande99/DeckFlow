"""Research planning service: transforms project brief into a structured ResearchPlan."""

from __future__ import annotations

import structlog
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.schemas.project import ProjectBrief, ResearchPlan

logger = structlog.get_logger(__name__)

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You are a senior strategy consulting engagement manager at a top-tier management consultancy (McKinsey, BCG, Bain).
Your role is to decompose executive client questions into rigorous, hypothesis-driven research plans.

Your research plans must:
1. Formulate mutually exclusive, collectively exhaustive (MECE) research questions.
2. Design high-yield, specific Google search queries targeting reputable institutional sources (e.g. consulting reports, industry regulators, leading research institutes, academic studies, earnings transcripts).
3. Explicitly define what is IN SCOPE and what is EXCLUDED to prevent scope creep.
4. Scale research breadth according to the requested depth:
   - quick: 3 focused questions, 4-6 targeted queries
   - standard: 5-7 comprehensive questions, 8-12 targeted queries
   - deep: 8-12 exhaustive questions, 15-20 multi-angle queries
5. If internal client documents or strategic context are provided, treat them as the primary ground truth; formulate targeted web queries to benchmark, corroborate, and fill external data gaps.
"""


class ResearchPlanner:
    """Service to create a typed ResearchPlan from a ProjectBrief."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm = llm_provider or get_llm_provider()

    async def plan(self, brief: ProjectBrief) -> ResearchPlan:
        """Generate a structured ResearchPlan matching the project brief."""
        logger.info(
            "generating_research_plan",
            topic=brief.topic,
            research_depth=brief.research_depth,
            prompt_version=PROMPT_VERSION,
        )

        prompt = f"""Generate a comprehensive, structured research plan for the following consulting engagement:

Topic: {brief.topic}
Business Objective: {brief.objective}
Target Audience: {brief.audience or 'Executive Leadership'}
Geographic Scope: {brief.geography or 'Global'}
Time Horizon: {brief.time_horizon or 'Unspecified'}
Additional Strategic Context: {brief.additional_context or 'None'}
Research Depth: {brief.research_depth}

Requirements:
- Formulate precise research questions addressing market size/dynamics, competitive moves, commercial economics, execution bottlenecks, and key risks.
- Formulate effective search queries containing industry terminology, operators, and target publication types.
- Specify clear scope boundaries and concrete exclusions.
"""

        plan: ResearchPlan = await self.llm.generate_structured(
            prompt=prompt,
            response_model=ResearchPlan,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
        )

        logger.info(
            "research_plan_generated",
            questions_count=len(plan.questions),
            queries_count=len(plan.search_queries),
            exclusions_count=len(plan.exclusions),
        )
        return plan
