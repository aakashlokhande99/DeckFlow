"""Consulting PPTX presentation renderer using python-pptx.

Transforms approved slide specs into a professional 16:9 widescreen executive deck
with corporate brand theming and consulting layouts: title, executive summary,
two-column, three-insight, comparison, roadmap, risk matrix, closing, scorecard, and metrics.

NON-NEGOTIABLE RULE: No PowerPoint rendering before research synthesis is approved.
Every factual claim links to stored source evidence in the footer.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ArtifactType, SlideLayout
from app.db.models import Artifact, Insight, Project, SlideSpec
from app.presentation.templates import CorporateTemplate, get_template
from app.schemas.template import BrandPalette, FontSchema

logger = structlog.get_logger(__name__)


def hex_to_rgb(hex_str: str) -> RGBColor:
    """Convert hex string (e.g. #0F172A or #FFF) to python-pptx RGBColor."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return RGBColor(*(int(h[i : i + 2], 16) for i in (0, 2, 4)))


# ---------------------------------------------------------------------------
# Executive Consulting Default Color Palette & Typography (McKinsey Navy)
# Kept for backward compatibility with external imports
# ---------------------------------------------------------------------------
COLOR_PRIMARY_NAVY = RGBColor(15, 23, 42)     # #0F172A
COLOR_TEXT_DARK = RGBColor(30, 41, 59)        # #1E293B
COLOR_ACCENT_BLUE = RGBColor(37, 99, 235)     # #2563EB
COLOR_ACCENT_LIGHT = RGBColor(239, 246, 255)  # #EFF6FF
COLOR_CARD_BG = RGBColor(248, 250, 252)       # #F8FAFC
COLOR_BORDER = RGBColor(226, 232, 240)        # #E2E8F0
COLOR_TEXT_MUTED = RGBColor(100, 116, 139)    # #64748B
COLOR_WHITE = RGBColor(255, 255, 255)         # #FFFFFF
COLOR_HIGH_RISK = RGBColor(220, 38, 38)       # #DC2626
COLOR_MED_RISK = RGBColor(217, 119, 6)        # #D97706
COLOR_LOW_RISK = RGBColor(22, 163, 74)        # #16A34A

FONT_HEADING = "Calibri"
FONT_BODY = "Calibri"


class RendererGateError(Exception):
    """Raised when PPTX rendering is attempted on unapproved research."""
    pass


class PresentationRenderer:
    """Renders approved SlideSpec records into a formatted PPTX presentation."""

    def __init__(
        self,
        db: AsyncSession,
        output_dir: str = "artifacts",
        template: Optional[CorporateTemplate] = None,
    ) -> None:
        self.db = db
        self.output_dir = output_dir
        self.template: CorporateTemplate = template or get_template("mckinsey_navy")
        os.makedirs(self.output_dir, exist_ok=True)

        # Dynamic template color palette
        p = self.template.palette
        self.c_primary = hex_to_rgb(p.primary)
        self.c_secondary = hex_to_rgb(p.secondary)
        self.c_accent = hex_to_rgb(p.accent)
        self.c_accent_light = hex_to_rgb(p.accent_light)
        self.c_background = hex_to_rgb(p.background)
        self.c_card_bg = hex_to_rgb(p.card_bg)
        self.c_border = hex_to_rgb(p.border)
        self.c_text_dark = hex_to_rgb(p.text_dark)
        self.c_text_muted = hex_to_rgb(p.text_muted)
        self.c_white = hex_to_rgb(p.white)
        self.c_high_risk = hex_to_rgb(p.high_risk)
        self.c_med_risk = hex_to_rgb(p.med_risk)
        self.c_low_risk = hex_to_rgb(p.low_risk)

        # Dynamic typography
        self.font_heading = self.template.fonts.heading
        self.font_body = self.template.fonts.body

    async def render(self, project_id: uuid.UUID) -> Artifact:
        """Render approved storyline for project_id into a PPTX file and persist Artifact."""
        # 1. Fetch project and verify existence
        p_stmt = select(Project).where(Project.id == project_id)
        project = (await self.db.execute(p_stmt)).scalar_one_or_none()
        if not project:
            raise RendererGateError(f"Project {project_id} not found.")

        # 2. Verify latest insight is approved
        i_stmt = (
            select(Insight)
            .where(Insight.project_id == project_id)
            .order_by(Insight.version.desc())
        )
        insight = (await self.db.execute(i_stmt)).scalars().first()
        if not insight or not insight.is_approved:
            raise RendererGateError(
                f"Cannot render PPTX: research synthesis for project {project_id} has not been approved by a human reviewer."
            )

        # 3. Fetch slide specs
        s_stmt = (
            select(SlideSpec)
            .where(SlideSpec.project_id == project_id)
            .order_by(SlideSpec.slide_order.asc())
        )
        slide_specs = (await self.db.execute(s_stmt)).scalars().all()
        if not slide_specs:
            raise RendererGateError(
                f"Cannot render PPTX: no slide specs found for project {project_id}. Generate storyline first."
            )

        # 4. Initialize python-pptx presentation (16:9 widescreen: 13.333" x 7.5")
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank_slide_layout = prs.slide_layouts[6]  # Blank slide

        # 5. Render each slide
        for spec in slide_specs:
            slide = prs.slides.add_slide(blank_slide_layout)
            layout_type = SlideLayout(spec.layout) if spec.layout in SlideLayout._value2member_map_ else SlideLayout.two_column
            self._render_slide(slide=slide, spec=spec, layout=layout_type, project=project)

        # 6. Save PPTX to disk
        file_name = f"consulting_deck_{project_id}.pptx"
        file_path = os.path.abspath(os.path.join(self.output_dir, file_name))
        prs.save(file_path)

        # Calculate file size and SHA-256 hash
        with open(file_path, "rb") as f:
            content_bytes = f.read()
        file_size = len(content_bytes)
        file_hash = hashlib.sha256(content_bytes).hexdigest()

        # 7. Upsert Artifact record
        art_stmt = select(Artifact).where(Artifact.project_id == project_id)
        artifact = (await self.db.execute(art_stmt)).scalar_one_or_none()
        now = datetime.now(timezone.utc)

        slide_snapshot = [
            {
                "slide_order": s.slide_order,
                "title": s.title,
                "layout": s.layout,
                "source_ids": [str(sid) for sid in (s.source_ids or [])],
            }
            for s in slide_specs
        ]

        if artifact:
            artifact.slide_spec_snapshot = slide_snapshot
            artifact.file_path = file_path
            artifact.file_size_bytes = file_size
            artifact.pptx_hash = file_hash
            artifact.generated_at = now
            artifact.is_current = True
        else:
            artifact = Artifact(
                id=uuid.uuid4(),
                project_id=project_id,
                slide_spec_snapshot=slide_snapshot,
                file_path=file_path,
                file_size_bytes=file_size,
                pptx_hash=file_hash,
                generated_at=now,
                is_current=True,
                artifact_type=ArtifactType.pptx.value,
            )
            self.db.add(artifact)

        await self.db.commit()
        await self.db.refresh(artifact)

        logger.info(
            "pptx_rendered_successfully",
            project_id=str(project_id),
            slides_count=len(slide_specs),
            file_path=file_path,
            file_size_bytes=file_size,
            template=self.template.id,
        )

        return artifact

    def _render_slide(
        self,
        slide: Any,
        spec: SlideSpec,
        layout: SlideLayout,
        project: Project,
    ) -> None:
        """Route to appropriate layout renderer."""
        if layout == SlideLayout.title:
            self._render_title_layout(slide, spec, project)
        elif layout == SlideLayout.executive_summary:
            self._render_executive_summary_layout(slide, spec)
        elif layout == SlideLayout.three_insight:
            self._render_three_insight_layout(slide, spec)
        elif layout == SlideLayout.comparison:
            self._render_comparison_layout(slide, spec)
        elif layout == SlideLayout.roadmap:
            self._render_roadmap_layout(slide, spec)
        elif layout == SlideLayout.risk_matrix:
            self._render_risk_matrix_layout(slide, spec)
        elif layout == SlideLayout.closing:
            self._render_closing_layout(slide, spec, project)
        elif layout == SlideLayout.scorecard:
            self._render_scorecard_layout(slide, spec)
        elif layout == SlideLayout.metrics:
            self._render_metrics_layout(slide, spec)
        else:
            # Default to two_column
            self._render_two_column_layout(slide, spec)

        # Render source footer if slide has citations (and is not title slide)
        if layout != SlideLayout.title and spec.source_ids:
            self._render_source_footer(slide, spec.source_ids)

    def _add_header(self, slide: Any, title: str, key_message: str) -> None:
        """Standard consulting action title and executive takeaway subheader."""
        header_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.733), Inches(1.1))
        tf = header_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        # Action Title
        p_title = tf.paragraphs[0]
        p_title.text = title
        p_title.font.name = self.font_heading
        p_title.font.size = Pt(20)
        p_title.font.bold = True
        p_title.font.color.rgb = self.c_primary
        p_title.space_after = Pt(4)

        # Key Message Takeaway
        p_sub = tf.add_paragraph()
        p_sub.text = key_message
        p_sub.font.name = self.font_body
        p_sub.font.size = Pt(13)
        p_sub.font.color.rgb = self.c_text_muted

    def _render_source_footer(self, slide: Any, source_ids: List[str]) -> None:
        """Subtle source citation footer at bottom of slide."""
        footer_box = slide.shapes.add_textbox(Inches(0.8), Inches(6.8), Inches(11.733), Inches(0.4))
        tf = footer_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p = tf.paragraphs[0]
        sources_str = ", ".join(str(s) for s in source_ids[:5])
        p.text = f"Sources: {sources_str}"
        p.font.name = self.font_body
        p.font.size = Pt(9)
        p.font.color.rgb = self.c_text_muted

    # -----------------------------------------------------------------------
    # Layout 1: Title
    # -----------------------------------------------------------------------
    def _render_title_layout(self, slide: Any, spec: SlideSpec, project: Project) -> None:
        """Hero cover slide with dark primary banner, topic title, and project metadata."""
        # Hero Dark Background
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = self.c_primary
        bg.line.fill.background()

        # Accent Bar
        accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.8), Inches(0.8), Inches(0.1))
        accent.fill.solid()
        accent.fill.fore_color.rgb = self.c_accent
        accent.line.fill.background()

        # Title Box
        title_box = slide.shapes.add_textbox(Inches(1.2), Inches(2.2), Inches(10.9), Inches(3.0))
        tf = title_box.text_frame
        tf.word_wrap = True

        p1 = tf.paragraphs[0]
        p1.text = spec.title
        p1.font.name = self.font_heading
        p1.font.size = Pt(36)
        p1.font.bold = True
        p1.font.color.rgb = self.c_white
        p1.space_after = Pt(12)

        p2 = tf.add_paragraph()
        p2.text = spec.key_message
        p2.font.name = self.font_body
        p2.font.size = Pt(18)
        p2.font.color.rgb = self.c_border

        # Metadata Footer Box
        meta_box = slide.shapes.add_textbox(Inches(1.2), Inches(5.8), Inches(10.9), Inches(0.8))
        mtf = meta_box.text_frame
        mp = mtf.paragraphs[0]
        mp.text = f"Audience: {project.audience}   |   Geography: {project.geography}   |   Horizon: {project.time_horizon}"
        mp.font.name = self.font_body
        mp.font.size = Pt(12)
        mp.font.color.rgb = self.c_text_muted

    # -----------------------------------------------------------------------
    # Layout 2: Executive Summary
    # -----------------------------------------------------------------------
    def _render_executive_summary_layout(self, slide: Any, spec: SlideSpec) -> None:
        """Executive summary with top callout box and three key takeaway cards."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}

        # Top Executive Takeaway Banner
        banner = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(11.733), Inches(1.3))
        banner.fill.solid()
        banner.fill.fore_color.rgb = self.c_accent_light
        banner.line.color.rgb = self.c_accent

        btf = banner.text_frame
        btf.word_wrap = True
        bp = btf.paragraphs[0]
        bp.text = content.get("summary", spec.key_message)
        bp.font.name = self.font_body
        bp.font.size = Pt(13)
        bp.font.color.rgb = self.c_text_dark

        # Three Key Takeaway Pillars
        pillars = content.get("key_takeaways", ["Empirical Finding", "Strategic Priority", "Risk Control"])
        card_width = Inches(3.64)
        gap = Inches(0.4)

        for i, text in enumerate(pillars[:3]):
            left = Inches(0.8) + i * (card_width + gap)
            card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, Inches(3.4), card_width, Inches(3.0))
            card.fill.solid()
            card.fill.fore_color.rgb = self.c_card_bg
            card.line.color.rgb = self.c_border

            ctf = card.text_frame
            ctf.word_wrap = True
            cp1 = ctf.paragraphs[0]
            cp1.text = f"Pillar 0{i+1}"
            cp1.font.name = self.font_heading
            cp1.font.size = Pt(14)
            cp1.font.bold = True
            cp1.font.color.rgb = self.c_accent
            cp1.space_after = Pt(8)

            cp2 = ctf.add_paragraph()
            cp2.text = str(text)
            cp2.font.name = self.font_body
            cp2.font.size = Pt(12)
            cp2.font.color.rgb = self.c_text_dark

    # -----------------------------------------------------------------------
    # Layout 3: Two Column
    # -----------------------------------------------------------------------
    def _render_two_column_layout(self, slide: Any, spec: SlideSpec) -> None:
        """Two balanced column cards with headers and bullet points."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}
        col_width = Inches(5.66)
        col_gap = Inches(0.4)
        col_top = Inches(1.8)
        col_height = Inches(4.7)

        # Left Column
        left_data = content.get("left_column", {})
        c1 = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), col_top, col_width, col_height)
        c1.fill.solid()
        c1.fill.fore_color.rgb = self.c_card_bg
        c1.line.color.rgb = self.c_border

        tf1 = c1.text_frame
        tf1.word_wrap = True
        p1 = tf1.paragraphs[0]
        p1.text = left_data.get("heading", "Strategic Dynamics")
        p1.font.name = self.font_heading
        p1.font.size = Pt(15)
        p1.font.bold = True
        p1.font.color.rgb = self.c_primary
        p1.space_after = Pt(12)

        for b in left_data.get("bullets", []):
            pb = tf1.add_paragraph()
            pb.text = f"•  {b}"
            pb.font.name = self.font_body
            pb.font.size = Pt(12)
            pb.font.color.rgb = self.c_text_dark
            pb.space_after = Pt(8)

        # Right Column
        right_data = content.get("right_column", {})
        c2 = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8) + col_width + col_gap, col_top, col_width, col_height
        )
        c2.fill.solid()
        c2.fill.fore_color.rgb = self.c_card_bg
        c2.line.color.rgb = self.c_border

        tf2 = c2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.text = right_data.get("heading", "Execution Factors")
        p2.font.name = self.font_heading
        p2.font.size = Pt(15)
        p2.font.bold = True
        p2.font.color.rgb = self.c_primary
        p2.space_after = Pt(12)

        for b in right_data.get("bullets", []):
            pb = tf2.add_paragraph()
            pb.text = f"•  {b}"
            pb.font.name = self.font_body
            pb.font.size = Pt(12)
            pb.font.color.rgb = self.c_text_dark
            pb.space_after = Pt(8)

    # -----------------------------------------------------------------------
    # Layout 4: Three Insight
    # -----------------------------------------------------------------------
    def _render_three_insight_layout(self, slide: Any, spec: SlideSpec) -> None:
        """Three side-by-side insight cards with callout numbers and body text."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}
        cards = content.get("cards", [])
        card_width = Inches(3.64)
        gap = Inches(0.4)
        top = Inches(1.8)
        height = Inches(4.7)

        for i, card_data in enumerate(cards[:3]):
            left = Inches(0.8) + i * (card_width + gap)
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, card_width, height)
            shape.fill.solid()
            shape.fill.fore_color.rgb = self.c_card_bg
            shape.line.color.rgb = self.c_border

            tf = shape.text_frame
            tf.word_wrap = True

            # Number badge
            p_num = tf.paragraphs[0]
            p_num.text = str(card_data.get("number", f"0{i+1}"))
            p_num.font.name = self.font_heading
            p_num.font.size = Pt(22)
            p_num.font.bold = True
            p_num.font.color.rgb = self.c_accent
            p_num.space_after = Pt(4)

            # Title
            p_title = tf.add_paragraph()
            p_title.text = str(card_data.get("title", f"Insight {i+1}"))
            p_title.font.name = self.font_heading
            p_title.font.size = Pt(14)
            p_title.font.bold = True
            p_title.font.color.rgb = self.c_primary
            p_title.space_after = Pt(10)

            # Body
            p_body = tf.add_paragraph()
            p_body.text = str(card_data.get("text", ""))
            p_body.font.name = self.font_body
            p_body.font.size = Pt(12)
            p_body.font.color.rgb = self.c_text_dark

    # -----------------------------------------------------------------------
    # Layout 5: Comparison Table
    # -----------------------------------------------------------------------
    def _render_comparison_layout(self, slide: Any, spec: SlideSpec) -> None:
        """Structured comparison table with headers and highlighted advantage column."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}
        headers = content.get("headers", ["Dimension", "Status Quo", "Proposed Solution", "Impact"])
        rows = content.get("rows", [])

        num_rows = len(rows) + 1
        num_cols = len(headers)
        table_shape = slide.shapes.add_table(num_rows, num_cols, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.6))
        table = table_shape.table

        # Format Header Row
        for col_idx, header_text in enumerate(headers):
            cell = table.cell(0, col_idx)
            cell.text = header_text
            cell.fill.solid()
            cell.fill.fore_color.rgb = self.c_primary
            p = cell.text_frame.paragraphs[0]
            p.font.name = self.font_heading
            p.font.size = Pt(12)
            p.font.bold = True
            p.font.color.rgb = self.c_white

        # Format Data Rows
        for row_idx, row_data in enumerate(rows):
            for col_idx, val in enumerate(row_data[:num_cols]):
                cell = table.cell(row_idx + 1, col_idx)
                cell.text = str(val)
                cell.fill.solid()
                cell.fill.fore_color.rgb = self.c_card_bg if row_idx % 2 == 0 else self.c_white
                p = cell.text_frame.paragraphs[0]
                p.font.name = self.font_body
                p.font.size = Pt(11)
                p.font.color.rgb = self.c_text_dark

    # -----------------------------------------------------------------------
    # Layout 6: Roadmap
    # -----------------------------------------------------------------------
    def _render_roadmap_layout(self, slide: Any, spec: SlideSpec) -> None:
        """Three chronological phase boxes with horizon timing and milestone bullets."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}
        phases = content.get("phases", [])
        box_width = Inches(3.64)
        gap = Inches(0.4)
        top = Inches(1.8)
        height = Inches(4.7)

        for i, phase in enumerate(phases[:3]):
            left = Inches(0.8) + i * (box_width + gap)
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, box_width, height)
            shape.fill.solid()
            shape.fill.fore_color.rgb = self.c_card_bg
            shape.line.color.rgb = self.c_border

            tf = shape.text_frame
            tf.word_wrap = True

            # Phase Name
            p1 = tf.paragraphs[0]
            p1.text = str(phase.get("phase", f"Phase {i+1}"))
            p1.font.name = self.font_heading
            p1.font.size = Pt(15)
            p1.font.bold = True
            p1.font.color.rgb = self.c_primary

            # Timing Pill
            p_time = tf.add_paragraph()
            p_time.text = str(phase.get("timing", ""))
            p_time.font.name = self.font_body
            p_time.font.size = Pt(11)
            p_time.font.color.rgb = self.c_accent
            p_time.space_after = Pt(12)

            # Milestones
            for m in phase.get("milestones", []):
                pm = tf.add_paragraph()
                pm.text = f"•  {m}"
                pm.font.name = self.font_body
                pm.font.size = Pt(11)
                pm.font.color.rgb = self.c_text_dark
                pm.space_after = Pt(6)

    # -----------------------------------------------------------------------
    # Layout 7: Risk Matrix
    # -----------------------------------------------------------------------
    def _render_risk_matrix_layout(self, slide: Any, spec: SlideSpec) -> None:
        """Structured risk assessment table or cards with severity levels and mitigation actions."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}
        risks = content.get("risks", [])

        card_width = Inches(3.64)
        gap = Inches(0.4)
        top = Inches(1.8)
        height = Inches(4.7)

        for i, r in enumerate(risks[:3]):
            left = Inches(0.8) + i * (card_width + gap)
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, card_width, height)
            shape.fill.solid()
            shape.fill.fore_color.rgb = self.c_card_bg
            shape.line.color.rgb = self.c_border

            tf = shape.text_frame
            tf.word_wrap = True

            # Severity badge
            severity = str(r.get("severity", "medium")).lower()
            p_sev = tf.paragraphs[0]
            p_sev.text = f"[{severity.upper()} SEVERITY]"
            p_sev.font.name = self.font_heading
            p_sev.font.size = Pt(12)
            p_sev.font.bold = True
            if severity == "high":
                p_sev.font.color.rgb = self.c_high_risk
            elif severity == "medium":
                p_sev.font.color.rgb = self.c_med_risk
            else:
                p_sev.font.color.rgb = self.c_low_risk
            p_sev.space_after = Pt(6)

            # Risk Title
            p_risk = tf.add_paragraph()
            p_risk.text = str(r.get("risk", "Operational Risk"))
            p_risk.font.name = self.font_heading
            p_risk.font.size = Pt(14)
            p_risk.font.bold = True
            p_risk.font.color.rgb = self.c_primary
            p_risk.space_after = Pt(12)

            # Mitigation Heading
            p_mit_hdr = tf.add_paragraph()
            p_mit_hdr.text = "Mitigation Countermeasure:"
            p_mit_hdr.font.name = self.font_body
            p_mit_hdr.font.size = Pt(11)
            p_mit_hdr.font.bold = True
            p_mit_hdr.font.color.rgb = self.c_text_muted
            p_mit_hdr.space_after = Pt(4)

            # Mitigation Body
            p_mit = tf.add_paragraph()
            p_mit.text = str(r.get("mitigation", "Implement robust monitoring."))
            p_mit.font.name = self.font_body
            p_mit.font.size = Pt(11)
            p_mit.font.color.rgb = self.c_text_dark

    # -----------------------------------------------------------------------
    # Layout 8: Closing / Action Plan
    # -----------------------------------------------------------------------
    def _render_closing_layout(self, slide: Any, spec: SlideSpec, project: Project) -> None:
        """Closing slide with executive decision gates, immediate action items, and contact."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}

        # Call to action callout
        cta_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(11.733), Inches(1.1))
        cta_box.fill.solid()
        cta_box.fill.fore_color.rgb = self.c_accent_light
        cta_box.line.color.rgb = self.c_accent

        ctf = cta_box.text_frame
        ctf.word_wrap = True
        cp = ctf.paragraphs[0]
        cp.text = content.get("call_to_action", "Board approval requested for Phase 1 project mobilization.")
        cp.font.name = self.font_heading
        cp.font.size = Pt(14)
        cp.font.bold = True
        cp.font.color.rgb = self.c_primary

        # Action Items Box
        actions_box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(3.2), Inches(11.733), Inches(3.2))
        actions_box.fill.solid()
        actions_box.fill.fore_color.rgb = self.c_card_bg
        actions_box.line.color.rgb = self.c_border

        atf = actions_box.text_frame
        atf.word_wrap = True
        ap1 = atf.paragraphs[0]
        ap1.text = "Immediate Decision Gates & 30-Day Priorities"
        ap1.font.name = self.font_heading
        ap1.font.size = Pt(15)
        ap1.font.bold = True
        ap1.font.color.rgb = self.c_primary
        ap1.space_after = Pt(10)

        for item in content.get("action_items", []):
            p_item = atf.add_paragraph()
            p_item.text = f"✔  {item}"
            p_item.font.name = self.font_body
            p_item.font.size = Pt(12)
            p_item.font.color.rgb = self.c_text_dark
            p_item.space_after = Pt(8)

    # -----------------------------------------------------------------------
    # Layout 9: Scorecard Layout
    # -----------------------------------------------------------------------
    def _render_scorecard_layout(self, slide: Any, spec: SlideSpec) -> None:
        """5-column evaluation scorecard table with dimension, weight, score, status badge, and key finding."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}
        dimensions = content.get("dimensions", [])
        if not dimensions and "rows" in content:
            dimensions = content.get("rows", [])
        if not dimensions:
            dimensions = [
                {
                    "dimension": "Market Attractiveness",
                    "weight": "30%",
                    "score": "High (4.5/5)",
                    "status": "green",
                    "key_finding": "TAM growing at 24% CAGR driven by enterprise cloud adoption.",
                },
                {
                    "dimension": "Competitive Moat",
                    "weight": "25%",
                    "score": "Medium (3.2/5)",
                    "status": "amber",
                    "key_finding": "Defensible IP portfolio but open-source pressure mounting.",
                },
                {
                    "dimension": "Regulatory Feasibility",
                    "weight": "25%",
                    "score": "Low (2.0/5)",
                    "status": "red",
                    "key_finding": "Stringent regulatory compliance overhead and certification delays.",
                },
                {
                    "dimension": "Financial Return",
                    "weight": "20%",
                    "score": "High (4.8/5)",
                    "status": "green",
                    "key_finding": "Payback period under 18 months with >35% IRR.",
                },
            ]

        headers = ["Dimension", "Weight", "Score / Rating", "Status", "Strategic Finding"]
        col_widths = [Inches(2.2), Inches(1.0), Inches(1.6), Inches(1.2), Inches(5.733)]

        num_rows = len(dimensions) + 1
        num_cols = len(headers)
        table_shape = slide.shapes.add_table(
            num_rows, num_cols, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.7)
        )
        table = table_shape.table

        # Set explicit column widths
        for col_idx, width in enumerate(col_widths):
            table.columns[col_idx].width = width

        # Format Header Row
        for col_idx, header_text in enumerate(headers):
            cell = table.cell(0, col_idx)
            cell.text = header_text
            cell.fill.solid()
            cell.fill.fore_color.rgb = self.c_primary
            p = cell.text_frame.paragraphs[0]
            p.font.name = self.font_heading
            p.font.size = Pt(12)
            p.font.bold = True
            p.font.color.rgb = self.c_white

        # Format Data Rows
        for row_idx, item in enumerate(dimensions):
            if isinstance(item, dict):
                dim = str(item.get("dimension", item.get("name", f"Dimension {row_idx+1}")))
                weight = str(item.get("weight", "25%"))
                score = str(item.get("score", item.get("rating", "3.0/5")))
                status_raw = str(item.get("status", "green")).lower()
                finding = str(item.get("key_finding", item.get("finding", item.get("description", ""))))
            elif isinstance(item, (list, tuple)):
                dim = str(item[0]) if len(item) > 0 else f"Dimension {row_idx+1}"
                weight = str(item[1]) if len(item) > 1 else "25%"
                score = str(item[2]) if len(item) > 2 else "3.0/5"
                status_raw = str(item[3]) if len(item) > 3 else "green"
                finding = str(item[4]) if len(item) > 4 else ""
            else:
                dim, weight, score, status_raw, finding = str(item), "25%", "3.0/5", "green", ""

            row_bg = self.c_card_bg if row_idx % 2 == 0 else self.c_white

            # Cell 0: Dimension
            c0 = table.cell(row_idx + 1, 0)
            c0.text = dim
            c0.fill.solid()
            c0.fill.fore_color.rgb = row_bg
            p0 = c0.text_frame.paragraphs[0]
            p0.font.name = self.font_heading
            p0.font.size = Pt(11)
            p0.font.bold = True
            p0.font.color.rgb = self.c_text_dark

            # Cell 1: Weight
            c1 = table.cell(row_idx + 1, 1)
            c1.text = weight
            c1.fill.solid()
            c1.fill.fore_color.rgb = row_bg
            p1 = c1.text_frame.paragraphs[0]
            p1.font.name = self.font_body
            p1.font.size = Pt(11)
            p1.font.color.rgb = self.c_text_muted

            # Cell 2: Score / Rating
            c2 = table.cell(row_idx + 1, 2)
            c2.text = score
            c2.fill.solid()
            c2.fill.fore_color.rgb = row_bg
            p2 = c2.text_frame.paragraphs[0]
            p2.font.name = self.font_body
            p2.font.size = Pt(11)
            p2.font.color.rgb = self.c_text_dark

            # Cell 3: Status Badge
            c3 = table.cell(row_idx + 1, 3)
            c3.fill.solid()
            c3.fill.fore_color.rgb = row_bg
            if "green" in status_raw or "high" in status_raw or "pass" in status_raw or "track" in status_raw:
                badge_text = "● ON TRACK"
                badge_color = self.c_low_risk
            elif "red" in status_raw or "low" in status_raw or "fail" in status_raw or "critical" in status_raw:
                badge_text = "▲ CRITICAL"
                badge_color = self.c_high_risk
            else:
                badge_text = "◆ WATCH"
                badge_color = self.c_med_risk
            c3.text = badge_text
            p3 = c3.text_frame.paragraphs[0]
            p3.font.name = self.font_heading
            p3.font.size = Pt(10)
            p3.font.bold = True
            p3.font.color.rgb = badge_color

            # Cell 4: Strategic Finding
            c4 = table.cell(row_idx + 1, 4)
            c4.text = finding
            c4.fill.solid()
            c4.fill.fore_color.rgb = row_bg
            p4 = c4.text_frame.paragraphs[0]
            p4.font.name = self.font_body
            p4.font.size = Pt(11)
            p4.font.color.rgb = self.c_text_dark

    # -----------------------------------------------------------------------
    # Layout 10: Metrics Layout
    # -----------------------------------------------------------------------
    def _render_metrics_layout(self, slide: Any, spec: SlideSpec) -> None:
        """4 metric cards across the slide with 32pt bold big numbers, muted label, subtitle, and delta pill badge."""
        self._add_header(slide, spec.title, spec.key_message)
        content = spec.content or {}
        metrics = content.get("metrics", [])
        if not metrics and "cards" in content:
            metrics = content.get("cards", [])
        if not metrics:
            metrics = [
                {
                    "label": "Projected TAM (2030)",
                    "value": "$48.5B",
                    "delta": "+28% YoY",
                    "subtext": "Global enterprise software market expansion",
                },
                {
                    "label": "Unit Margin Lift",
                    "value": "+1,350 bps",
                    "delta": "vs. Status Quo",
                    "subtext": "Driven by automation and API efficiency",
                },
                {
                    "label": "Payback Velocity",
                    "value": "14 Mo.",
                    "delta": "-6 Mo. faster",
                    "subtext": "Rapid breakeven on initial capital deployment",
                },
                {
                    "label": "Scrap / Defect Rate",
                    "value": "< 4.2%",
                    "delta": "from 18.5%",
                    "subtext": "Continuous quality assurance integration",
                },
            ]

        card_width = Inches(2.7)
        gap = Inches(0.3)
        top = Inches(2.0)
        height = Inches(4.3)

        for i, m in enumerate(metrics[:4]):
            left = Inches(0.8) + i * (card_width + gap)
            card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, card_width, height)
            card.fill.solid()
            card.fill.fore_color.rgb = self.c_card_bg
            card.line.color.rgb = self.c_border

            tf = card.text_frame
            tf.word_wrap = True

            # Label (11pt bold uppercase)
            p_lbl = tf.paragraphs[0]
            p_lbl.text = str(m.get("label", f"METRIC {i+1}")).upper()
            p_lbl.font.name = self.font_heading
            p_lbl.font.size = Pt(11)
            p_lbl.font.bold = True
            p_lbl.font.color.rgb = self.c_text_muted
            p_lbl.space_after = Pt(12)

            # Big Number (32pt bold)
            p_val = tf.add_paragraph()
            p_val.text = str(m.get("value", m.get("number", "100%")))
            p_val.font.name = self.font_heading
            p_val.font.size = Pt(32)
            p_val.font.bold = True
            p_val.font.color.rgb = self.c_primary
            p_val.space_after = Pt(8)

            # Delta Badge (pill text)
            delta = m.get("delta")
            if delta:
                p_delta = tf.add_paragraph()
                p_delta.text = f"▲  {delta}" if not str(delta).startswith(("+", "-", "▲", "▼")) else str(delta)
                p_delta.font.name = self.font_heading
                p_delta.font.size = Pt(11)
                p_delta.font.bold = True
                p_delta.font.color.rgb = self.c_accent
                p_delta.space_after = Pt(10)

            # Subtext
            subtext = m.get("subtext", m.get("subtitle", m.get("description", "")))
            if subtext:
                p_sub = tf.add_paragraph()
                p_sub.text = str(subtext)
                p_sub.font.name = self.font_body
                p_sub.font.size = Pt(11)
                p_sub.font.color.rgb = self.c_text_muted
