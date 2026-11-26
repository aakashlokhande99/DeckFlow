"""Built-in Enterprise Corporate Presentation Templates.

Provides 5 pre-configured corporate templates with brand palettes and typography:
- McKinsey Navy (default)
- BCG Emerald
- Bain Crimson
- Goldman Slate
- Modern Tech
"""

from __future__ import annotations

from typing import Dict, List, Optional
from app.schemas.template import BrandPalette, CorporateTemplate, FontSchema

# 1. McKinsey Navy (Default)
MCKINSEY_NAVY = CorporateTemplate(
    id="mckinsey_navy",
    name="McKinsey Navy",
    description="Classic executive consulting theme with deep slate navy, royal blue accent, and clean Calibri typography.",
    palette=BrandPalette(
        primary="#0F172A",
        secondary="#1E293B",
        accent="#2563EB",
        accent_light="#EFF6FF",
        background="#FFFFFF",
        card_bg="#F8FAFC",
        border="#E2E8F0",
        text_dark="#1E293B",
        text_muted="#64748B",
        white="#FFFFFF",
        high_risk="#DC2626",
        med_risk="#D97706",
        low_risk="#16A34A",
    ),
    fonts=FontSchema(
        heading="Calibri",
        body="Calibri",
    ),
)

# 2. BCG Emerald
BCG_EMERALD = CorporateTemplate(
    id="bcg_emerald",
    name="BCG Emerald",
    description="Strategy-focused corporate theme with deep forest emerald, vibrant green accent, and crisp Arial typography.",
    palette=BrandPalette(
        primary="#064E3B",
        secondary="#065F46",
        accent="#059669",
        accent_light="#ECFDF5",
        background="#FFFFFF",
        card_bg="#F0FDF4",
        border="#D1FAE5",
        text_dark="#064E3B",
        text_muted="#4B5563",
        white="#FFFFFF",
        high_risk="#DC2626",
        med_risk="#D97706",
        low_risk="#059669",
    ),
    fonts=FontSchema(
        heading="Arial",
        body="Arial",
    ),
)

# 3. Bain Crimson
BAIN_CRIMSON = CorporateTemplate(
    id="bain_crimson",
    name="Bain Crimson",
    description="Results-driven executive theme featuring deep burgundy, crimson red accent, and elegant Georgia typography.",
    palette=BrandPalette(
        primary="#881337",
        secondary="#9F1239",
        accent="#E11D48",
        accent_light="#FFF1F2",
        background="#FFFFFF",
        card_bg="#FFF5F5",
        border="#FFE4E6",
        text_dark="#4C0519",
        text_muted="#701A75",
        white="#FFFFFF",
        high_risk="#BE123C",
        med_risk="#D97706",
        low_risk="#16A34A",
    ),
    fonts=FontSchema(
        heading="Georgia",
        body="Georgia",
    ),
)

# 4. Goldman Slate
GOLDMAN_SLATE = CorporateTemplate(
    id="goldman_slate",
    name="Goldman Slate",
    description="High-finance corporate identity with charcoal slate, amber gold accent, and commanding Trebuchet MS typography.",
    palette=BrandPalette(
        primary="#18181B",
        secondary="#27272A",
        accent="#D97706",
        accent_light="#FEF3C7",
        background="#FFFFFF",
        card_bg="#FAFAFA",
        border="#E4E4E7",
        text_dark="#18181B",
        text_muted="#71717A",
        white="#FFFFFF",
        high_risk="#DC2626",
        med_risk="#D97706",
        low_risk="#16A34A",
    ),
    fonts=FontSchema(
        heading="Trebuchet MS",
        body="Trebuchet MS",
    ),
)

# 5. Modern Tech
MODERN_TECH = CorporateTemplate(
    id="modern_tech",
    name="Modern Tech",
    description="Modern venture and technology consulting theme featuring midnight slate, cyber teal accent, and Segoe UI typography.",
    palette=BrandPalette(
        primary="#0F172A",
        secondary="#1E293B",
        accent="#0D9488",
        accent_light="#F0FDFA",
        background="#FFFFFF",
        card_bg="#F8FAFC",
        border="#CCFBF1",
        text_dark="#0F172A",
        text_muted="#64748B",
        white="#FFFFFF",
        high_risk="#E11D48",
        med_risk="#F59E0B",
        low_risk="#10B981",
    ),
    fonts=FontSchema(
        heading="Segoe UI",
        body="Segoe UI",
    ),
)

_PRESETS: Dict[str, CorporateTemplate] = {
    "mckinsey_navy": MCKINSEY_NAVY,
    "bcg_emerald": BCG_EMERALD,
    "bain_crimson": BAIN_CRIMSON,
    "goldman_slate": GOLDMAN_SLATE,
    "modern_tech": MODERN_TECH,
}


def get_template(template_id: Optional[str] = None) -> CorporateTemplate:
    """Retrieve template by ID, falling back to McKinsey Navy if not found or None."""
    if not template_id:
        return MCKINSEY_NAVY
    return _PRESETS.get(template_id.strip().lower(), MCKINSEY_NAVY)


def list_templates() -> List[CorporateTemplate]:
    """Return all available built-in corporate templates."""
    return list(_PRESETS.values())
