"""Tests for Corporate Brand Templates, Palettes, and Themed Presentation Rendering."""

from __future__ import annotations

import io
import os
import uuid
import pytest
from pptx import Presentation
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec
from app.presentation.renderer import PresentationRenderer, hex_to_rgb
from app.presentation.templates import (
    BAIN_CRIMSON,
    BCG_EMERALD,
    GOLDMAN_SLATE,
    MCKINSEY_NAVY,
    MODERN_TECH,
    get_template,
    list_templates,
)
from app.schemas.template import BrandPalette, CorporateTemplate, FontSchema


def test_hex_color_validation():
    """Verify that BrandPalette validates hex color format strictly."""
    # Valid 6-digit hex
    palette = BrandPalette(primary="#0F172A", accent="#2563EB")
    assert palette.primary == "#0F172A"
    assert palette.accent == "#2563EB"

    # Valid 3-digit hex
    palette_short = BrandPalette(primary="#FFF")
    assert palette_short.primary == "#FFF"

    # Invalid formats should raise ValidationError
    invalid_cases = ["#ZZZZZZ", "0F172A", "#12345", "red", "#1234567", "#"]
    for inv in invalid_cases:
        with pytest.raises(ValidationError):
            BrandPalette(primary=inv)


def test_preset_templates_integrity():
    """Verify all 5 built-in enterprise templates are valid and populated."""
    templates = list_templates()
    assert len(templates) == 5

    ids = {t.id for t in templates}
    assert ids == {
        "mckinsey_navy",
        "bcg_emerald",
        "bain_crimson",
        "goldman_slate",
        "modern_tech",
    }

    # Verify McKinsey Navy default
    mck = get_template("mckinsey_navy")
    assert mck.palette.primary == "#0F172A"
    assert mck.palette.accent == "#2563EB"
    assert mck.fonts.heading == "Calibri"

    # Verify BCG Emerald
    bcg = get_template("bcg_emerald")
    assert bcg.palette.primary == "#064E3B"
    assert bcg.palette.accent == "#059669"
    assert bcg.fonts.heading == "Arial"

    # Verify Bain Crimson
    bain = get_template("bain_crimson")
    assert bain.palette.primary == "#881337"
    assert bain.palette.accent == "#E11D48"
    assert bain.fonts.heading == "Georgia"

    # Verify Goldman Slate
    goldman = get_template("goldman_slate")
    assert goldman.palette.primary == "#18181B"
    assert goldman.palette.accent == "#D97706"
    assert goldman.fonts.heading == "Trebuchet MS"

    # Verify Modern Tech
    tech = get_template("modern_tech")
    assert tech.palette.primary == "#0F172A"
    assert tech.palette.accent == "#0D9488"
    assert tech.fonts.heading == "Segoe UI"

    # Fallback to default
    assert get_template("non_existent").id == "mckinsey_navy"
    assert get_template(None).id == "mckinsey_navy"


def test_hex_to_rgb_conversion():
    """Verify hex string to pptx RGBColor conversion."""
    rgb = hex_to_rgb("#0F172A")
    assert rgb[0] == 15
    assert rgb[1] == 23
    assert rgb[2] == 42

    rgb_short = hex_to_rgb("#FFF")
    assert rgb_short[0] == 255
    assert rgb_short[1] == 255
    assert rgb_short[2] == 255


@pytest.mark.asyncio
async def test_themed_pptx_rendering_with_custom_template(
    db_session: AsyncSession, tmp_path: os.PathLike
):
    """Verify PPTX generation with custom corporate template (BCG Emerald)."""
    project = Project(
        topic="Sustainable Aviation Fuel Supply Chain",
        objective="Assess feedstock availability and refining economics.",
        audience="Airline C-Suite",
        geography="North America",
        time_horizon="2025-2035",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        id=uuid.uuid4(),
        project_id=project.id,
        executive_summary="SAF blending mandates drive 38% CAGR through 2030.",
        is_approved=True,
        version=1,
    )
    db_session.add(insight)
    await db_session.flush()

    # Add slides including scorecard and metrics layouts
    s1 = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=1,
        title="Sustainable Aviation Fuel",
        key_message="Mandates require rapid capital deployment.",
        layout=SlideLayout.title.value,
    )
    s2 = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=2,
        title="Commercial Feasibility Scorecard",
        key_message="Strategic evaluation across regulatory and feedstock pillars.",
        layout=SlideLayout.scorecard.value,
        content={
            "dimensions": [
                {
                    "dimension": "Feedstock Security",
                    "weight": "35%",
                    "score": "Medium (3.2/5)",
                    "status": "amber",
                    "key_finding": "HEFA used cooking oil supplies face regional competition.",
                },
                {
                    "dimension": "Regulatory Mandate",
                    "weight": "30%",
                    "score": "High (4.8/5)",
                    "status": "green",
                    "key_finding": "EU ReFuelEU and US IRA 40B provide multi-year price floors.",
                },
                {
                    "dimension": "Refining Capex Velocity",
                    "weight": "35%",
                    "score": "Low (2.4/5)",
                    "status": "red",
                    "key_finding": "EPC delays and catalyst lead times average 28 months.",
                },
            ]
        },
    )
    s3 = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=3,
        title="Operational Scale Metrics",
        key_message="Key volume, margin, and carbon reduction milestones.",
        layout=SlideLayout.metrics.value,
        content={
            "metrics": [
                {
                    "label": "Annual Capacity (2030)",
                    "value": "2.4B Gal.",
                    "delta": "+45% YoY",
                    "subtext": "Global planned commercial production",
                },
                {
                    "label": "Green Premium Lift",
                    "value": "+$1.85 / Gal",
                    "delta": "vs. Jet-A",
                    "subtext": "Supported by compliance credits",
                },
                {
                    "label": "Lifecycle GHG Cut",
                    "value": "-84%",
                    "delta": "vs. Fossil Baseline",
                    "subtext": "Certified CORSIA methodology",
                },
                {
                    "label": "Off-take Certainty",
                    "value": "92%",
                    "delta": "Contracted",
                    "subtext": "Tier-1 commercial passenger airline commitments",
                },
            ]
        },
    )
    db_session.add_all([s1, s2, s3])
    await db_session.commit()

    # Render with BCG Emerald
    bcg_template = get_template("bcg_emerald")
    renderer = PresentationRenderer(
        db=db_session, output_dir=str(tmp_path), template=bcg_template
    )
    artifact = await renderer.render(project.id)

    assert os.path.exists(artifact.file_path)
    assert artifact.file_size_bytes > 0
    assert len(artifact.pptx_hash) == 64

    # Verify PPTX structure
    prs = Presentation(artifact.file_path)
    assert len(prs.slides) == 3

    # Slide 2 should have a table (scorecard)
    s2_slide = prs.slides[1]
    tables = [shape for shape in s2_slide.shapes if shape.has_table]
    assert len(tables) == 1
    table = tables[0].table
    assert len(table.columns) == 5
    assert len(table.rows) == 4  # Header + 3 dimensions
    assert table.cell(0, 0).text == "Dimension"
    assert table.cell(0, 3).text == "Status"

    # Slide 3 should have metric shapes
    s3_slide = prs.slides[2]
    text_content = " ".join([shape.text for shape in s3_slide.shapes if shape.has_text_frame])
    assert "2.4B Gal." in text_content
    assert "-84%" in text_content
