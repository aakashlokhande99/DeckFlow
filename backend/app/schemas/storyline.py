"""Pydantic schemas for slide storyline generation, outline review, and slide specs."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.db.enums import SlideLayout


class SlideItem(BaseModel):
    """Specification of an individual slide in a consulting storyline."""

    id: Optional[str] = Field(
        default=None, description="SlideSpec UUID if persisted in DB"
    )
    slide_order: int = Field(
        ..., ge=1, description="Contiguous 1-based order in presentation deck"
    )
    title: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="Action title / governing thought summarizing the slide",
    )
    key_message: str = Field(
        ...,
        min_length=5,
        description="One-sentence executive takeaway for the slide header",
    )
    layout: SlideLayout = Field(
        default=SlideLayout.two_column,
        description="Target slide visual layout template",
    )
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured content payload (e.g. bullets, cards, comparison columns, risks)",
    )
    source_ids: List[str] = Field(
        default_factory=list,
        description="Source IDs or evidence citation IDs supporting factual assertions on this slide",
    )
    is_approved: bool = Field(
        default=False,
        description="Whether this slide spec has been accepted by the reviewer",
    )


class StorylineOutline(BaseModel):
    """Complete 8-12 slide consulting deck storyline."""

    project_id: str
    insight_id: str
    slides: List[SlideItem] = Field(..., min_length=1)
    is_approved: bool = False
    total_slides: int = 0


class StorylineUpdateRequest(BaseModel):
    """Payload to edit, reorder, or approve slide specs."""

    slides: List[SlideItem] = Field(
        ..., min_length=1, description="Updated list of slides with valid contiguous order"
    )
    approve_all: bool = Field(
        default=False,
        description="If True, marks all slides and the storyline as approved for PPTX rendering",
    )
