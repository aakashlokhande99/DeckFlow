"""Standalone Interactive HTML Presentation Viewer Generator.

Generates an offline, single-file HTML presentation deck with embedded CSS and vanilla JS.
Supports 16:9 widescreen presentation mode, executive document scroll mode,
keyboard shortcuts, touch swipe gestures, speaker notes drawer, overview slide grid,
dynamic corporate theming via CSS variables, and print-to-PDF stylesheet.

NON-NEGOTIABLE RULE: No HTML export before research synthesis is approved.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import SlideLayout
from app.db.models import Insight, Project, SlideSpec, Source
from app.presentation.templates import CorporateTemplate, get_template

logger = structlog.get_logger(__name__)


class HTMLGateError(Exception):
    """Raised when HTML presentation export is attempted on unapproved research."""
    pass


class HTMLPresentationGenerator:
    """Generates a self-contained, interactive HTML presentation viewer."""

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

    async def generate(
        self,
        project_id: uuid.UUID,
        initial_view: str = "presentation",
    ) -> Tuple[str, int, str]:
        """Generate standalone HTML presentation file for approved project.

        Args:
            project_id: Project identifier.
            initial_view: 'presentation' or 'document'.

        Returns:
            Tuple of (file_path, file_size_bytes, sha256_hash)
        """
        # 1. Fetch project
        p_stmt = select(Project).where(Project.id == project_id)
        project = (await self.db.execute(p_stmt)).scalar_one_or_none()
        if not project:
            raise HTMLGateError(f"Project {project_id} not found.")

        # 2. Gate check: insight must be approved
        i_stmt = (
            select(Insight)
            .where(Insight.project_id == project_id)
            .order_by(Insight.version.desc())
        )
        insight = (await self.db.execute(i_stmt)).scalars().first()
        if not insight or not insight.is_approved:
            raise HTMLGateError(
                f"Cannot generate HTML deck: research synthesis for project {project_id} has not been approved by a human reviewer."
            )

        # 3. Fetch sources and slide specs
        s_stmt = select(Source).where(Source.project_id == project_id)
        sources = (await self.db.execute(s_stmt)).scalars().all()
        source_map = {str(src.id): src for src in sources}

        sl_stmt = select(SlideSpec).where(SlideSpec.project_id == project_id).order_by(SlideSpec.slide_order.asc())
        slide_specs = (await self.db.execute(sl_stmt)).scalars().all()
        if not slide_specs:
            raise HTMLGateError(
                f"Cannot generate HTML deck: no slide specs found for project {project_id}."
            )

        # 4. Generate HTML content
        html_content = self._render_full_html(project, insight, slide_specs, source_map, initial_view)

        # 5. Save to disk
        filename = f"consulting_deck_{project_id}.html"
        file_path = os.path.abspath(os.path.join(self.output_dir, filename))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        raw_bytes = html_content.encode("utf-8")
        file_size = len(raw_bytes)
        file_hash = hashlib.sha256(raw_bytes).hexdigest()

        logger.info(
            "html_viewer_generated_successfully",
            project_id=str(project_id),
            file_path=file_path,
            file_size_bytes=file_size,
            slides_count=len(slide_specs),
            template=self.template.id,
        )

        return file_path, file_size, file_hash

    def _render_full_html(
        self,
        project: Project,
        insight: Insight,
        slide_specs: List[SlideSpec],
        source_map: Dict[str, Source],
        initial_view: str,
    ) -> str:
        """Render complete HTML5 document string with embedded styles and script."""
        p = self.template.palette
        f = self.template.fonts

        # Render slides HTML
        slides_html_list = []
        overview_cards_list = []
        notes_dict = {}

        for idx, spec in enumerate(slide_specs):
            slide_num = idx + 1
            slide_html = self._render_slide_content(spec, slide_num, project, source_map)
            slides_html_list.append(
                f'<section class="slide {"active" if idx == 0 else ""}" id="slide-{slide_num}" data-slide-index="{idx}">\n'
                f'{slide_html}\n'
                f'</section>'
            )

            # Overview modal item
            overview_cards_list.append(
                f'<div class="overview-card" onclick="goToSlide({idx})">\n'
                f'  <span class="overview-num">0{slide_num}</span>\n'
                f'  <div class="overview-title">{html.escape(spec.title)}</div>\n'
                f'  <div class="overview-layout">{html.escape(spec.layout)}</div>\n'
                f'</div>'
            )

            # Notes
            cites = [
                html.escape(source_map[sid].title or source_map[sid].canonical_url)
                for sid in (spec.source_ids or [])
                if sid in source_map
            ]
            notes_dict[idx] = {
                "title": html.escape(spec.title or ""),
                "takeaway": html.escape(spec.key_message or ""),
                "layout": html.escape(spec.layout or ""),
                "citations": cites,
            }

        slides_joined = "\n".join(slides_html_list)
        overview_joined = "\n".join(overview_cards_list)
        notes_json = json.dumps(notes_dict).replace("</", "<\\/")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        is_doc_mode = "mode-document" if initial_view == "document" else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{html.escape(project.topic)} | Executive Consulting Deck</title>
  <style>
    :root {{
      --color-primary: {p.primary};
      --c-primary: {p.primary};
      --color-secondary: {p.secondary};
      --c-secondary: {p.secondary};
      --color-accent: {p.accent};
      --c-accent: {p.accent};
      --color-accent-light: {p.accent_light};
      --c-accent-light: {p.accent_light};
      --color-background: {p.background};
      --c-background: {p.background};
      --color-card-bg: {p.card_bg};
      --c-card-bg: {p.card_bg};
      --color-border: {p.border};
      --c-border: {p.border};
      --color-text-dark: {p.text_dark};
      --c-text-dark: {p.text_dark};
      --color-text-muted: {p.text_muted};
      --c-text-muted: {p.text_muted};
      --color-white: {p.white};
      --c-white: {p.white};
      --color-high-risk: {p.high_risk};
      --c-high-risk: {p.high_risk};
      --color-med-risk: {p.med_risk};
      --c-med-risk: {p.med_risk};
      --color-low-risk: {p.low_risk};
      --c-low-risk: {p.low_risk};
      --font-heading: "{f.heading}", system-ui, -apple-system, sans-serif;
      --font-body: "{f.body}", system-ui, -apple-system, sans-serif;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background: #0B0F17;
      color: var(--color-text-dark);
      font-family: var(--font-body);
      min-height: 100vh;
      overflow-x: hidden;
      display: flex;
      flex-direction: column;
    }}

    /* Top Progress Bar */
    #progress-bar {{
      position: fixed;
      top: 0;
      left: 0;
      height: 3px;
      background: var(--color-accent);
      width: 0%;
      z-index: 100;
      transition: width 0.25s ease-out;
    }}

    /* Main Deck Stage */
    .deck-container {{
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      perspective: 1000px;
    }}

    .slide-viewport {{
      width: 100%;
      max-width: 1200px;
      aspect-ratio: 16 / 9;
      background: var(--color-background);
      border-radius: 8px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}

    /* Slide Content & Layouts */
    .slide {{
      display: none;
      flex-direction: column;
      height: 100%;
      width: 100%;
      padding: 36px 48px 24px;
      position: relative;
    }}

    .slide.active {{
      display: flex;
    }}

    .slide-header {{
      margin-bottom: 24px;
    }}

    .action-title {{
      font-family: var(--font-heading);
      font-size: 24px;
      font-weight: 700;
      color: var(--color-primary);
      margin-bottom: 4px;
      line-height: 1.25;
    }}

    .key-message {{
      font-size: 14px;
      color: var(--color-text-muted);
      line-height: 1.4;
    }}

    .slide-body {{
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }}

    .source-footer {{
      margin-top: auto;
      padding-top: 12px;
      font-size: 10px;
      color: var(--color-text-muted);
      border-top: 1px solid var(--color-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    /* Hero Title Slide Layout */
    .slide-hero {{
      background: var(--color-primary);
      color: var(--color-white);
      height: 100%;
      padding: 56px 64px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }}

    .hero-accent-bar {{
      width: 48px;
      height: 5px;
      background: var(--color-accent);
      margin-bottom: 24px;
      border-radius: 2px;
    }}

    .hero-title {{
      font-family: var(--font-heading);
      font-size: 38px;
      font-weight: 800;
      color: var(--color-white);
      margin-bottom: 16px;
      line-height: 1.2;
    }}

    .hero-subtitle {{
      font-size: 18px;
      color: #94A3B8;
      max-width: 800px;
      line-height: 1.5;
      margin-bottom: 48px;
    }}

    .hero-metadata {{
      display: flex;
      gap: 32px;
      font-size: 13px;
      color: #94A3B8;
      border-top: 1px solid rgba(255, 255, 255, 0.15);
      padding-top: 20px;
    }}

    /* Executive Summary Layout */
    .callout-box {{
      background: var(--color-accent-light);
      border-left: 4px solid var(--color-accent);
      padding: 16px 20px;
      border-radius: 4px;
      margin-bottom: 24px;
      font-size: 14px;
      line-height: 1.5;
    }}

    .pillars-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }}

    .pillar-card {{
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 20px;
    }}

    .pillar-num {{
      font-family: var(--font-heading);
      font-size: 13px;
      font-weight: 700;
      color: var(--color-accent);
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    .pillar-text {{
      font-size: 13px;
      line-height: 1.45;
      color: var(--color-text-dark);
    }}

    /* Two Column Layout */
    .two-col-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
    }}

    .col-card {{
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 24px;
    }}

    .col-heading {{
      font-family: var(--font-heading);
      font-size: 16px;
      font-weight: 700;
      color: var(--color-primary);
      margin-bottom: 16px;
    }}

    .col-bullets {{
      list-style: none;
    }}

    .col-bullets li {{
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 10px;
      position: relative;
      padding-left: 18px;
    }}

    .col-bullets li::before {{
      content: "•";
      position: absolute;
      left: 0;
      color: var(--color-accent);
      font-weight: bold;
    }}

    /* Three Insight Layout */
    .insights-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }}

    .insight-card {{
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 20px;
    }}

    .insight-badge {{
      font-family: var(--font-heading);
      font-size: 24px;
      font-weight: 800;
      color: var(--color-accent);
      margin-bottom: 6px;
    }}

    .insight-title {{
      font-family: var(--font-heading);
      font-size: 15px;
      font-weight: 700;
      color: var(--color-primary);
      margin-bottom: 10px;
    }}

    .insight-desc {{
      font-size: 12.5px;
      line-height: 1.45;
      color: var(--color-text-dark);
    }}

    /* Comparison Table Layout */
    .table-container {{
      width: 100%;
      border-collapse: collapse;
      border: 1px solid var(--color-border);
      border-radius: 6px;
      overflow: hidden;
      font-size: 12.5px;
    }}

    .table-container th {{
      background: var(--color-primary);
      color: var(--color-white);
      text-align: left;
      padding: 10px 14px;
      font-family: var(--font-heading);
      font-weight: 700;
    }}

    .table-container td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--color-border);
      line-height: 1.4;
    }}

    .table-container tr:nth-child(even) td {{
      background: var(--color-card-bg);
    }}

    /* Roadmap Layout */
    .roadmap-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }}

    .roadmap-card {{
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 20px;
    }}

    .phase-badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 4px;
      background: var(--color-accent-light);
      color: var(--color-accent);
      margin-bottom: 12px;
    }}

    /* Risk Matrix Layout */
    .risk-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }}

    .risk-card {{
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 20px;
    }}

    .severity-pill {{
      display: inline-block;
      font-size: 10px;
      font-weight: 800;
      padding: 2px 8px;
      border-radius: 3px;
      margin-bottom: 10px;
      letter-spacing: 0.5px;
    }}

    .sev-high {{ background: #FEE2E2; color: var(--color-high-risk); }}
    .sev-medium {{ background: #FEF3C7; color: var(--color-med-risk); }}
    .sev-low {{ background: #DCFCE7; color: var(--color-low-risk); }}

    /* Scorecard Layout */
    .scorecard-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
    }}

    .scorecard-table th {{
      background: var(--color-primary);
      color: var(--color-white);
      padding: 10px 12px;
      text-align: left;
      font-family: var(--font-heading);
    }}

    .scorecard-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--color-border);
    }}

    .scorecard-table tr:nth-child(even) td {{
      background: var(--color-card-bg);
    }}

    .status-badge {{
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 0.5px;
    }}

    .status-badge.on-track {{ color: var(--color-low-risk); }}
    .status-badge.watch {{ color: var(--color-med-risk); }}
    .status-badge.critical {{ color: var(--color-high-risk); }}

    /* Metrics Layout */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }}

    .metric-card {{
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 20px 16px;
      display: flex;
      flex-direction: column;
    }}

    .metric-label {{
      font-size: 11px;
      font-weight: 700;
      color: var(--color-text-muted);
      text-transform: uppercase;
      margin-bottom: 12px;
      letter-spacing: 0.5px;
    }}

    .metric-value {{
      font-family: var(--font-heading);
      font-size: 32px;
      font-weight: 800;
      color: var(--color-primary);
      margin-bottom: 8px;
    }}

    .metric-delta {{
      font-size: 11px;
      font-weight: 700;
      color: var(--color-accent);
      margin-bottom: 10px;
    }}

    .metric-subtext {{
      font-size: 11px;
      color: var(--color-text-muted);
      line-height: 1.35;
      margin-top: auto;
    }}

    /* Floating Navigation Controls */
    .nav-bar {{
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(15, 23, 42, 0.9);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 9999px;
      padding: 6px 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      z-index: 50;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }}

    .nav-btn {{
      background: transparent;
      border: none;
      color: #94A3B8;
      font-size: 13px;
      cursor: pointer;
      padding: 6px 10px;
      border-radius: 6px;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      gap: 4px;
    }}

    .nav-btn:hover {{
      color: #FFFFFF;
      background: rgba(255, 255, 255, 0.1);
    }}

    .nav-counter {{
      color: #F8FAFC;
      font-size: 12px;
      font-weight: 600;
      padding: 0 4px;
      user-select: none;
    }}

    .nav-divider {{
      width: 1px;
      height: 16px;
      background: rgba(255, 255, 255, 0.2);
    }}

    /* Speaker Notes Drawer */
    #notes-drawer {{
      position: fixed;
      top: 0;
      right: -400px;
      width: 380px;
      height: 100vh;
      background: #181E29;
      color: #E2E8F0;
      border-left: 1px solid #334155;
      box-shadow: -10px 0 30px rgba(0, 0, 0, 0.5);
      z-index: 90;
      padding: 24px;
      transition: right 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
    }}

    #notes-drawer.open {{
      right: 0;
    }}

    .drawer-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      border-bottom: 1px solid #334155;
      padding-bottom: 12px;
    }}

    .drawer-title {{
      font-family: var(--font-heading);
      font-size: 16px;
      font-weight: 700;
      color: #FFFFFF;
    }}

    .drawer-close {{
      background: transparent;
      border: none;
      color: #94A3B8;
      cursor: pointer;
      font-size: 18px;
    }}

    .drawer-body {{
      flex: 1;
      overflow-y: auto;
      font-size: 13px;
      line-height: 1.5;
    }}

    .drawer-section {{
      margin-bottom: 20px;
    }}

    .drawer-label {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--color-accent);
      margin-bottom: 6px;
      letter-spacing: 0.5px;
    }}

    /* Overview Modal Grid */
    #overview-modal {{
      position: fixed;
      inset: 0;
      background: rgba(11, 15, 23, 0.85);
      backdrop-filter: blur(8px);
      z-index: 95;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 32px;
    }}

    #overview-modal.open {{
      display: flex;
    }}

    .overview-content {{
      background: #181E29;
      border: 1px solid #334155;
      border-radius: 12px;
      width: 100%;
      max-width: 1000px;
      max-height: 85vh;
      overflow-y: auto;
      padding: 28px;
    }}

    .overview-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 16px;
      margin-top: 20px;
    }}

    .overview-card {{
      background: #0B0F17;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 16px;
      cursor: pointer;
      transition: all 0.2s ease;
    }}

    .overview-card:hover {{
      border-color: var(--color-accent);
      transform: translateY(-2px);
    }}

    .overview-num {{
      font-size: 11px;
      font-weight: 700;
      color: var(--color-accent);
    }}

    .overview-title {{
      font-size: 13px;
      font-weight: 600;
      color: #FFFFFF;
      margin: 6px 0;
      line-height: 1.3;
    }}

    .overview-layout {{
      font-size: 10px;
      color: #64748B;
      text-transform: uppercase;
    }}

    /* Executive Document Mode */
    body.mode-document {{
      background: #F1F5F9;
      color: var(--color-text-dark);
    }}

    body.mode-document .deck-container {{
      padding: 32px 16px 80px;
      display: block;
    }}

    body.mode-document .slide-viewport {{
      max-width: 900px;
      aspect-ratio: auto;
      margin: 0 auto;
      background: transparent;
      box-shadow: none;
      border-radius: 0;
      gap: 32px;
    }}

    body.mode-document .slide {{
      display: flex !important;
      background: var(--color-background);
      border-radius: 8px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
      margin-bottom: 24px;
      min-height: 480px;
    }}

    /* Print Stylesheet */
    @media print {{
      body {{
        background: #FFFFFF !important;
        color: #000000 !important;
      }}
      #progress-bar, .nav-bar, #notes-drawer, #overview-modal {{
        display: none !important;
      }}
      .deck-container, .slide-viewport {{
        padding: 0 !important;
        margin: 0 !important;
        max-width: none !important;
        aspect-ratio: auto !important;
        box-shadow: none !important;
      }}
      .slide {{
        display: flex !important;
        page-break-after: always !important;
        break-inside: avoid !important;
        width: 100% !important;
        height: 100vh !important;
        box-shadow: none !important;
        border: none !important;
        padding: 32px !important;
      }}
    }}
  </style>
</head>
<body class="{is_doc_mode}">
  <div id="progress-bar"></div>

  <main class="deck-container">
    <div class="slide-viewport" id="viewport">
      {slides_joined}
    </div>
  </main>

  <!-- Navigation Bar -->
  <nav class="nav-bar" aria-label="Deck navigation">
    <button class="nav-btn" onclick="prevSlide()" title="Previous slide (Left Arrow)">◀ Prev</button>
    <span class="nav-counter" id="slide-indicator">1 / {len(slide_specs)}</span>
    <button class="nav-btn" onclick="nextSlide()" title="Next slide (Right Arrow / Space)">Next ▶</button>
    <div class="nav-divider"></div>
    <button class="nav-btn" onclick="toggleOverview()" title="Slide Overview Grid (O)">Grid</button>
    <button class="nav-btn" onclick="toggleNotes()" title="Speaker Notes (S)">Notes</button>
    <button class="nav-btn" onclick="toggleMode()" title="Toggle Doc Mode (M)">Doc View</button>
    <button class="nav-btn" onclick="toggleFullscreen()" title="Fullscreen (F)">⛶</button>
  </nav>

  <!-- Speaker Notes Drawer -->
  <aside id="notes-drawer" aria-label="Speaker notes">
    <div class="drawer-header">
      <h3 class="drawer-title">Speaker Notes</h3>
      <button class="drawer-close" onclick="toggleNotes()">✕</button>
    </div>
    <div class="drawer-body" id="drawer-content">
      <!-- Injected dynamically via JS -->
    </div>
  </aside>

  <!-- Overview Grid Modal -->
  <div id="overview-modal" onclick="closeOverviewIfBackdrop(event)">
    <div class="overview-content">
      <div class="drawer-header">
        <h3 class="drawer-title">Deck Overview ({len(slide_specs)} Slides)</h3>
        <button class="drawer-close" onclick="toggleOverview()">✕</button>
      </div>
      <div class="overview-grid">
        {overview_joined}
      </div>
    </div>
  </div>

  <script>
    (function() {{
      const totalSlides = {len(slide_specs)};
      const notesData = {notes_json};
      let currentSlide = 0;
      let notesOpen = false;
      let overviewOpen = false;

      function updateSlide() {{
        const slides = document.querySelectorAll('.slide');
        slides.forEach((s, idx) => {{
          if (idx === currentSlide) {{
            s.classList.add('active');
          }} else {{
            s.classList.remove('active');
          }}
        }});

        // Indicator & progress
        const ind = document.getElementById('slide-indicator');
        if (ind) ind.textContent = (currentSlide + 1) + ' / ' + totalSlides;

        const pb = document.getElementById('progress-bar');
        if (pb) pb.style.width = (((currentSlide + 1) / totalSlides) * 100) + '%';

        // Update speaker notes
        renderNotes(currentSlide);
      }}

      function renderNotes(idx) {{
        const content = document.getElementById('drawer-content');
        if (!content) return;
        const note = notesData[idx] || {{}};
        let citesHtml = '';
        if (note.citations && note.citations.length > 0) {{
          citesHtml = note.citations.map(c => '<li>' + c + '</li>').join('');
        }} else {{
          citesHtml = '<li>No specific external source citation for this slide.</li>';
        }}

        content.innerHTML = `
          <div class="drawer-section">
            <div class="drawer-label">Slide 0${{idx + 1}} Action Title</div>
            <p><strong>${{note.title || ''}}</strong></p>
          </div>
          <div class="drawer-section">
            <div class="drawer-label">Executive Takeaway</div>
            <p>${{note.takeaway || ''}}</p>
          </div>
          <div class="drawer-section">
            <div class="drawer-label">Layout Architecture</div>
            <p><code>${{note.layout || ''}}</code></p>
          </div>
          <div class="drawer-section">
            <div class="drawer-label">Referenced Sources & Evidence</div>
            <ul style="padding-left: 18px; margin-top: 4px;">${{citesHtml}}</ul>
          </div>
        `;
      }}

      window.nextSlide = function() {{
        if (currentSlide < totalSlides - 1) {{
          currentSlide++;
          updateSlide();
        }}
      }};

      window.prevSlide = function() {{
        if (currentSlide > 0) {{
          currentSlide--;
          updateSlide();
        }}
      }};

      window.goToSlide = function(idx) {{
        if (idx >= 0 && idx < totalSlides) {{
          currentSlide = idx;
          updateSlide();
          if (overviewOpen) toggleOverview();
        }}
      }};

      window.toggleNotes = function() {{
        notesOpen = !notesOpen;
        const drawer = document.getElementById('notes-drawer');
        if (drawer) drawer.classList.toggle('open', notesOpen);
      }};

      window.toggleOverview = function() {{
        overviewOpen = !overviewOpen;
        const modal = document.getElementById('overview-modal');
        if (modal) modal.classList.toggle('open', overviewOpen);
      }};

      window.closeOverviewIfBackdrop = function(e) {{
        if (e.target && e.target.id === 'overview-modal') {{
          toggleOverview();
        }}
      }};

      window.toggleMode = function() {{
        document.body.classList.toggle('mode-document');
      }};

      window.toggleFullscreen = function() {{
        if (!document.fullscreenElement) {{
          document.documentElement.requestFullscreen().catch(() => {{}});
        }} else {{
          if (document.exitFullscreen) {{
            document.exitFullscreen().catch(() => {{}});
          }}
        }}
      }};

      // Keyboard navigation
      window.addEventListener('keydown', function(e) {{
        if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {{
          e.preventDefault();
          nextSlide();
        }} else if (e.key === 'ArrowLeft' || e.key === 'PageUp' || e.key === 'Backspace') {{
          e.preventDefault();
          prevSlide();
        }} else if (e.key === 'Home') {{
          e.preventDefault();
          goToSlide(0);
        }} else if (e.key === 'End') {{
          e.preventDefault();
          goToSlide(totalSlides - 1);
        }} else if (e.key === 'f' || e.key === 'F') {{
          e.preventDefault();
          toggleFullscreen();
        }} else if (e.key === 's' || e.key === 'S') {{
          e.preventDefault();
          toggleNotes();
        }} else if (e.key === 'o' || e.key === 'O') {{
          e.preventDefault();
          toggleOverview();
        }} else if (e.key === 'm' || e.key === 'M') {{
          e.preventDefault();
          toggleMode();
        }} else if (e.key === 'Escape') {{
          if (overviewOpen) toggleOverview();
          if (notesOpen) toggleNotes();
        }}
      }});

      // Touch navigation
      let touchStartX = 0;
      window.addEventListener('touchstart', function(e) {{
        touchStartX = e.changedTouches[0].clientX;
      }}, false);

      window.addEventListener('touchend', function(e) {{
        const touchEndX = e.changedTouches[0].clientX;
        const diffX = touchEndX - touchStartX;
        if (diffX < -50) {{
          nextSlide();
        }} else if (diffX > 50) {{
          prevSlide();
        }}
      }}, false);

      // Initialize
      updateSlide();
    }})();
  </script>
</body>
</html>
"""

    def _render_slide_content(
        self,
        spec: SlideSpec,
        slide_num: int,
        project: Project,
        source_map: Dict[str, Source],
    ) -> str:
        """Render layout-specific HTML structure."""
        layout = spec.layout
        content = spec.content or {}

        # Footer HTML helper
        cites_list = [
            source_map[sid].title or source_map[sid].canonical_url
            for sid in (spec.source_ids or [])
            if sid in source_map
        ]
        footer_cites = ", ".join(cites_list[:3]) if cites_list else ""
        source_footer_html = f"""
        <footer class="source-footer">
          <span>Sources: {html.escape(footer_cites) if footer_cites else "Primary Consulting Synthesis"}</span>
          <span>Slide 0{slide_num} • Confidential</span>
        </footer>
        """

        header_html = f"""
        <header class="slide-header">
          <h2 class="action-title">{html.escape(spec.title)}</h2>
          <p class="key-message">{html.escape(spec.key_message)}</p>
        </header>
        """

        if layout == SlideLayout.title.value:
            return f"""
            <div class="slide-hero">
              <div class="hero-accent-bar"></div>
              <h1 class="hero-title">{html.escape(spec.title)}</h1>
              <p class="hero-subtitle">{html.escape(spec.key_message)}</p>
              <div class="hero-metadata">
                <span><strong>Audience:</strong> {html.escape(project.audience or "Executive Leadership")}</span>
                <span><strong>Geography:</strong> {html.escape(project.geography or "Global")}</span>
                <span><strong>Time Horizon:</strong> {html.escape(project.time_horizon or "Medium Term")}</span>
              </div>
            </div>
            """

        elif layout == SlideLayout.executive_summary.value:
            summary_txt = content.get("summary", spec.key_message)
            pillars = content.get("key_takeaways", ["Empirical Finding", "Strategic Priority", "Risk Control"])
            pillars_html = "".join([
                f"""<div class="pillar-card">
                  <div class="pillar-num">Pillar 0{i+1}</div>
                  <div class="pillar-text">{html.escape(str(p_txt))}</div>
                </div>"""
                for i, p_txt in enumerate(pillars[:3])
            ])
            return f"""
            {header_html}
            <div class="slide-body">
              <div class="callout-box">
                <strong>Executive Takeaway:</strong> {html.escape(summary_txt)}
              </div>
              <div class="pillars-grid">
                {pillars_html}
              </div>
            </div>
            {source_footer_html}
            """

        elif layout == SlideLayout.three_insight.value:
            cards = content.get("cards", [])
            if not cards:
                cards = [
                    {"number": "01", "title": "Market Acceleration", "text": "Rapid expansion driven by enterprise customer pull."},
                    {"number": "02", "title": "Margin Expansion", "text": "Automation efficiencies reduce marginal unit delivery costs."},
                    {"number": "03", "title": "Competitive Moat", "text": "High barrier to entry through specialized domain telemetry."},
                ]
            cards_html = "".join([
                f"""<div class="insight-card">
                  <div class="insight-badge">{html.escape(str(c.get("number", f"0{i+1}")))}</div>
                  <div class="insight-title">{html.escape(str(c.get("title", f"Insight {i+1}")))}</div>
                  <div class="insight-desc">{html.escape(str(c.get("text", "")))}</div>
                </div>"""
                for i, c in enumerate(cards[:3])
            ])
            return f"""
            {header_html}
            <div class="slide-body">
              <div class="insights-grid">
                {cards_html}
              </div>
            </div>
            {source_footer_html}
            """

        elif layout == SlideLayout.comparison.value:
            headers = content.get("headers", ["Dimension", "Status Quo", "Proposed Solution", "Impact"])
            rows = content.get("rows", [
                ["Architecture", "Fragmented point solutions", "Unified autonomous agent engine", "40% lower maintenance"],
                ["Velocity", "Manual weeks-long cycles", "Hours to verified synthesized deck", "10x faster execution"],
                ["Governance", "Ad-hoc human review", "Rigorous human-in-the-loop gates", "Audit-ready provenance"],
            ])
            th_html = "".join([f"<th>{html.escape(h)}</th>" for h in headers])
            tr_html = "".join([
                "<tr>" + "".join([f"<td>{html.escape(str(col))}</td>" for col in r]) + "</tr>"
                for r in rows
            ])
            return f"""
            {header_html}
            <div class="slide-body">
              <table class="table-container">
                <thead><tr>{th_html}</tr></thead>
                <tbody>{tr_html}</tbody>
              </table>
            </div>
            {source_footer_html}
            """

        elif layout == SlideLayout.roadmap.value:
            phases = content.get("phases", [
                {"phase": "Phase 1: Foundation", "timing": "Months 1-3", "milestones": ["Core API integration", "Data ingestion pipeline", "Security baseline audit"]},
                {"phase": "Phase 2: Acceleration", "timing": "Months 4-6", "milestones": ["Pilot deployment", "User feedback telemetry", "Scale evaluation suite"]},
                {"phase": "Phase 3: Scale", "timing": "Months 7-12", "milestones": ["Global rollout", "Multi-region redundancy", "Continuous optimization"]},
            ])
            phases_html = "".join([
                f"""<div class="roadmap-card">
                  <span class="phase-badge">{html.escape(str(p.get("timing", "")))}</span>
                  <div class="insight-title">{html.escape(str(p.get("phase", f"Phase {i+1}")))}</div>
                  <ul class="col-bullets">
                    {"".join([f"<li>{html.escape(str(m))}</li>" for m in p.get("milestones", [])])}
                  </ul>
                </div>"""
                for i, p in enumerate(phases[:3])
            ])
            return f"""
            {header_html}
            <div class="slide-body">
              <div class="roadmap-grid">
                {phases_html}
              </div>
            </div>
            {source_footer_html}
            """

        elif layout == SlideLayout.risk_matrix.value:
            risks = content.get("risks", [
                {"risk": "Data Privacy & Regulatory Shift", "severity": "high", "mitigation": "Automated compliance checks and sovereign VPC deployment."},
                {"risk": "Legacy Integration Overhead", "severity": "medium", "mitigation": "Modular REST/gRPC wrappers with staged deprecation."},
                {"risk": "Model Drift & Flakiness", "severity": "low", "mitigation": "Continuous evaluation benchmarks with automated quality gates."},
            ])
            risks_html = "".join([
                f"""<div class="risk-card">
                  <span class="severity-pill sev-{html.escape(str(r.get("severity", "medium")).lower())}">
                    [{html.escape(str(r.get("severity", "medium")).upper())} SEVERITY]
                  </span>
                  <div class="insight-title">{html.escape(str(r.get("risk", "Operational Risk")))}</div>
                  <div class="insight-desc">
                    <strong>Mitigation:</strong> {html.escape(str(r.get("mitigation", "")))}
                  </div>
                </div>"""
                for r in risks[:3]
            ])
            return f"""
            {header_html}
            <div class="slide-body">
              <div class="risk-grid">
                {risks_html}
              </div>
            </div>
            {source_footer_html}
            """

        elif layout == SlideLayout.scorecard.value:
            dimensions = content.get("dimensions", [])
            if not dimensions and "rows" in content:
                dimensions = content.get("rows", [])
            if not dimensions:
                dimensions = [
                    {"dimension": "Market Attractiveness", "weight": "30%", "score": "High (4.5/5)", "status": "green", "key_finding": "TAM growing at 24% CAGR driven by enterprise adoption."},
                    {"dimension": "Competitive Moat", "weight": "25%", "score": "Medium (3.2/5)", "status": "amber", "key_finding": "Defensible IP portfolio but open-source pressure mounting."},
                    {"dimension": "Regulatory Feasibility", "weight": "25%", "score": "Low (2.0/5)", "status": "red", "key_finding": "Stringent regulatory compliance overhead and certification delays."},
                    {"dimension": "Financial Return", "weight": "20%", "score": "High (4.8/5)", "status": "green", "key_finding": "Payback period under 18 months with >35% IRR."},
                ]

            rows_html = []
            for d in dimensions:
                if isinstance(d, dict):
                    dim = d.get("dimension", "Evaluation Area")
                    weight = d.get("weight", "25%")
                    score = d.get("score", "3.0/5")
                    status = str(d.get("status", "green")).lower()
                    finding = d.get("key_finding", "")
                elif isinstance(d, (list, tuple)):
                    dim = d[0] if len(d) > 0 else "Dimension"
                    weight = d[1] if len(d) > 1 else "25%"
                    score = d[2] if len(d) > 2 else "3.0/5"
                    status = str(d[3]).lower() if len(d) > 3 else "green"
                    finding = d[4] if len(d) > 4 else ""
                else:
                    dim, weight, score, status, finding = str(d), "25%", "3.0/5", "green", ""

                if "green" in status or "high" in status or "pass" in status:
                    badge_cls, badge_text = "on-track", "● ON TRACK"
                elif "red" in status or "low" in status or "fail" in status:
                    badge_cls, badge_text = "critical", "▲ CRITICAL"
                else:
                    badge_cls, badge_text = "watch", "◆ WATCH"

                rows_html.append(
                    f"<tr>"
                    f"<td><strong>{html.escape(dim)}</strong></td>"
                    f"<td>{html.escape(weight)}</td>"
                    f"<td>{html.escape(score)}</td>"
                    f"<td><span class='status-badge {badge_cls}'>{badge_text}</span></td>"
                    f"<td>{html.escape(finding)}</td>"
                    f"</tr>"
                )

            return f"""
            {header_html}
            <div class="slide-body">
              <table class="scorecard-table">
                <thead>
                  <tr>
                    <th>Dimension</th>
                    <th>Weight</th>
                    <th>Score / Rating</th>
                    <th>Status</th>
                    <th>Strategic Finding</th>
                  </tr>
                </thead>
                <tbody>
                  {"".join(rows_html)}
                </tbody>
              </table>
            </div>
            {source_footer_html}
            """

        elif layout == SlideLayout.metrics.value:
            metrics = content.get("metrics", [])
            if not metrics and "cards" in content:
                metrics = content.get("cards", [])
            if not metrics:
                metrics = [
                    {"label": "Projected TAM (2030)", "value": "$48.5B", "delta": "+28% YoY", "subtext": "Global enterprise cloud software expansion"},
                    {"label": "Unit Margin Lift", "value": "+1,350 bps", "delta": "vs. Status Quo", "subtext": "Driven by automation and API efficiency"},
                    {"label": "Payback Velocity", "value": "14 Mo.", "delta": "-6 Mo. faster", "subtext": "Rapid breakeven on initial capital deployment"},
                    {"label": "Scrap / Defect Rate", "value": "< 4.2%", "delta": "from 18.5%", "subtext": "Continuous quality assurance integration"},
                ]
            cards_html = "".join([
                f"""<div class="metric-card">
                  <div class="metric-label">{html.escape(str(m.get("label", "Metric")).upper())}</div>
                  <div class="metric-value">{html.escape(str(m.get("value", "100%")))}</div>
                  <div class="metric-delta">▲ {html.escape(str(m.get("delta", "")))}</div>
                  <div class="metric-subtext">{html.escape(str(m.get("subtext", "")))}</div>
                </div>"""
                for m in metrics[:4]
            ])
            return f"""
            {header_html}
            <div class="slide-body">
              <div class="metrics-grid">
                {cards_html}
              </div>
            </div>
            {source_footer_html}
            """

        elif layout == SlideLayout.closing.value:
            cta = content.get("call_to_action", "Executive approval requested for Phase 1 project mobilization.")
            action_items = content.get("action_items", [
                "Establish core governance steering committee.",
                "Approve initial capital resource allocation.",
                "Authorize vendor architecture and pilot deployment.",
            ])
            items_html = "".join([f"<li>✔  {html.escape(item)}</li>" for item in action_items])
            return f"""
            {header_html}
            <div class="slide-body">
              <div class="callout-box">
                <strong>Executive Action Call:</strong> {html.escape(cta)}
              </div>
              <div class="col-card">
                <div class="col-heading">Immediate Decision Gates & 30-Day Priorities</div>
                <ul class="col-bullets">
                  {items_html}
                </ul>
              </div>
            </div>
            {source_footer_html}
            """

        else:
            # Default two_column layout
            left_col = content.get("left_column", {})
            right_col = content.get("right_column", {})
            left_hdr = left_col.get("heading", "Strategic Dynamics")
            left_bullets = "".join([f"<li>{html.escape(b)}</li>" for b in left_col.get("bullets", ["Strategic shift towards autonomous operations."])])
            right_hdr = right_col.get("heading", "Execution Factors")
            right_bullets = "".join([f"<li>{html.escape(b)}</li>" for b in right_col.get("bullets", ["Cross-functional alignment and telemetry tracking."])])

            return f"""
            {header_html}
            <div class="slide-body">
              <div class="two-col-grid">
                <div class="col-card">
                  <div class="col-heading">{html.escape(left_hdr)}</div>
                  <ul class="col-bullets">{left_bullets}</ul>
                </div>
                <div class="col-card">
                  <div class="col-heading">{html.escape(right_hdr)}</div>
                  <ul class="col-bullets">{right_bullets}</ul>
                </div>
              </div>
            </div>
            {source_footer_html}
            """
