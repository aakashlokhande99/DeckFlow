"""Corporate Brand Template & Palette Pydantic Schemas.

Defines schemas for corporate brand colors, typography, and complete enterprise
presentation templates with strict hex color validation.
"""

from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator

HEX_COLOR_REGEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")


class BrandPalette(BaseModel):
    """Corporate brand color palette supporting primary, secondary, accent, background, and alerts."""
    primary: str = Field("#0F172A", description="Primary corporate brand color (hex)")
    secondary: str = Field("#1E293B", description="Secondary brand color (hex)")
    accent: str = Field("#2563EB", description="High-visibility accent color (hex)")
    accent_light: str = Field("#EFF6FF", description="Subtle accent tint for callouts (hex)")
    background: str = Field("#FFFFFF", description="Slide background color (hex)")
    card_bg: str = Field("#F8FAFC", description="Card / container background fill (hex)")
    border: str = Field("#E2E8F0", description="Container and table border color (hex)")
    text_dark: str = Field("#1E293B", description="Primary text color (hex)")
    text_muted: str = Field("#64748B", description="Secondary / citation text color (hex)")
    white: str = Field("#FFFFFF", description="Pure white (hex)")
    high_risk: str = Field("#DC2626", description="Critical / red alert badge (hex)")
    med_risk: str = Field("#D97706", description="Warning / amber alert badge (hex)")
    low_risk: str = Field("#16A34A", description="Success / green badge (hex)")

    @field_validator("*", mode="before")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        if isinstance(v, str):
            cleaned = v.strip()
            if not HEX_COLOR_REGEX.match(cleaned):
                raise ValueError(
                    f"Invalid hex color format: {v}. Expected format like #0F172A or #EFF6FF"
                )
            return cleaned
        return v


class FontSchema(BaseModel):
    """Typography specification for headings and body."""
    heading: str = Field("Calibri", description="Font family for titles, section headers, badges")
    body: str = Field("Calibri", description="Font family for body copy, bullets, table cells")


class CorporateTemplate(BaseModel):
    """Complete corporate presentation template specification."""
    id: str = Field(..., description="Unique template identifier (e.g. mckinsey_navy)")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Corporate template styling description")
    palette: BrandPalette = Field(default_factory=BrandPalette)
    fonts: FontSchema = Field(default_factory=FontSchema)
    logo_path: Optional[str] = Field(None, description="Optional path to corporate logo image")
