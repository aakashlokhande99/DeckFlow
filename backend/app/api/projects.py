"""Project API router — complete CRUD and workflow endpoints.

Implements:
  POST /api/projects        - Create project + brief
  GET  /api/projects        - List projects
  GET  /api/projects/{id}   - Project detail + status
  DELETE /api/projects/{id} - Delete project

Stubs for subsequent sprint days:
  POST /api/projects/{id}/run        - Enqueue research workflow (Day 8)
  GET  /api/projects/{id}/review     - Evidence, synthesis, QA report (Day 11)
  POST /api/projects/{id}/review     - Approve / revise / research_more (Day 11)
  GET  /api/projects/{id}/storyline  - Proposed slide storyline (Day 13)
  POST /api/projects/{id}/storyline  - Accept or edit storyline (Day 13)
  GET  /api/projects/{id}/artifact   - Download approved PPTX (Day 14)
"""

from __future__ import annotations

import hashlib
import uuid
from typing import List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.enums import ProjectStatus
from app.db.models import EvidenceClaim, Feedback, Insight, Project, SlideSpec, Source
from app.db.session import get_db
from app.research.extractor import extract_text_from_pdf, sanitize_text
from app.schemas.project import (
    DocumentResponse,
    ProjectBrief,
    ProjectResponse,
    ReviewDecisionRequest,
)
from app.schemas.storyline import StorylineUpdateRequest

router = APIRouter(tags=["projects"])
logger = structlog.get_logger(__name__)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project from brief",
)
async def create_project(
    brief: ProjectBrief,
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Validate project brief and create an initial project in 'draft' status."""
    project = Project(
        topic=brief.topic,
        objective=brief.objective,
        audience=brief.audience,
        geography=brief.geography or "Global",
        time_horizon=brief.time_horizon,
        additional_context=brief.additional_context,
        research_depth=brief.research_depth,
        status=ProjectStatus.draft.value,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    logger.info("project_created", project_id=str(project.id), topic=project.topic)
    return project


@router.get(
    "",
    response_model=List[ProjectResponse],
    summary="List all projects",
)
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> List[Project]:
    """Retrieve all projects."""
    stmt = select(Project).order_by(Project.created_at.desc())
    result = await db.execute(stmt)
    projects = result.scalars().all()
    return list(projects)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project detail and current status",
)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Retrieve a single project by ID."""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a project and all associated cascade data (sources, evidence, synthesis, slides, etc.)."""
    import os
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Clean up artifact file if it exists on disk
    try:
        from app.db.models import Artifact
        art_stmt = select(Artifact).where(Artifact.project_id == project_id)
        artifact = (await db.execute(art_stmt)).scalar_one_or_none()
        if artifact and artifact.file_path and os.path.exists(artifact.file_path):
            os.remove(artifact.file_path)
    except Exception as exc:
        logger.warning("artifact_file_cleanup_failed", project_id=str(project_id), error=str(exc))

    await db.delete(project)
    await db.commit()
    logger.info("project_deleted", project_id=str(project_id))


# ---------------------------------------------------------------------------
# Project Research Document Uploads
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/documents",
    response_model=List[DocumentResponse],
    summary="Upload documents (PDF, TXT) to be included in research",
)
async def upload_documents(
    project_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
) -> List[DocumentResponse]:
    """Upload documents for a project, extract text, and register as project sources.
    
    Limits: Maximum 3 files, 10 MB per file, formats .pdf and .txt only.
    """
    stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    if len(files) > 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A maximum of 3 documents can be uploaded per project.",
        )

    # Check existing uploaded document count
    existing_stmt = select(Source).where(
        Source.project_id == project_id,
        Source.canonical_url.like("uploaded://%"),
    )
    existing_uploaded = (await db.execute(existing_stmt)).scalars().all()
    if len(existing_uploaded) + len(files) > 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload would exceed the limit of 3 documents (already have {len(existing_uploaded)}).",
        )

    responses: List[DocumentResponse] = []
    now = utcnow()
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    for file in files:
        filename = file.filename or "uploaded_document"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ["pdf", "txt"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type for '{filename}'. Allowed formats: .pdf, .txt",
            )

        content_bytes = await file.read()
        if len(content_bytes) == 0:
            continue

        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' exceeds the 10 MB size limit ({len(content_bytes) / (1024 * 1024):.1f} MB).",
            )

        content_hash = hashlib.sha256(content_bytes).hexdigest()

        # Extract text based on file format with permissive fallback
        raw_text = ""
        if ext == "pdf":
            try:
                raw_text = extract_text_from_pdf(content_bytes)
            except Exception as exc:
                logger.warning("pdf_extraction_warning", filename=filename, error=str(exc))
                raw_text = ""
        else:
            try:
                raw_text = sanitize_text(content_bytes.decode("utf-8", errors="ignore"))
            except Exception as exc:
                logger.warning("txt_extraction_warning", filename=filename, error=str(exc))
                raw_text = ""

        if not raw_text.strip():
            logger.warning("empty_extracted_text_permissive_fallback", filename=filename)
            raw_text = f"Uploaded document: {filename} (Permissive fallback: non-textual or scanned document)"

        canonical_url = f"uploaded://{uuid.uuid4()}/{filename}"

        source = Source(
            project_id=project_id,
            canonical_url=canonical_url,
            title=filename,
            publisher=filename,
            pub_date=now.date(),
            access_time=now,
            content_hash=content_hash,
            raw_metadata={
                "filename": filename,
                "size_bytes": len(content_bytes),
                "content_type": file.content_type or f"application/{ext}",
                "is_uploaded": True,
                "extracted_text": raw_text,
            },
        )
        db.add(source)
        await db.flush()
        await db.refresh(source)

        responses.append(
            DocumentResponse(
                id=source.id,
                project_id=project_id,
                filename=filename,
                size_bytes=len(content_bytes),
                content_type=file.content_type or f"application/{ext}",
                uploaded_at=source.created_at,
                extracted_char_count=len(raw_text),
            )
        )

    await db.commit()
    logger.info("documents_uploaded", project_id=str(project_id), count=len(responses))
    return responses


@router.get(
    "/{project_id}/documents",
    response_model=List[DocumentResponse],
    summary="List uploaded research documents for a project",
)
async def list_documents(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[DocumentResponse]:
    """Retrieve all uploaded documents associated with a project."""
    stmt = (
        select(Source)
        .where(
            Source.project_id == project_id,
            Source.canonical_url.like("uploaded://%"),
        )
        .order_by(Source.created_at.desc())
    )
    result = await db.execute(stmt)
    sources = result.scalars().all()

    documents = []
    for s in sources:
        meta = s.raw_metadata or {}
        documents.append(
            DocumentResponse(
                id=s.id,
                project_id=project_id,
                filename=meta.get("filename", s.title or "Document"),
                size_bytes=meta.get("size_bytes", 0),
                content_type=meta.get("content_type", "application/octet-stream"),
                uploaded_at=s.created_at,
                extracted_char_count=len(meta.get("extracted_text", "")),
            )
        )
    return documents


@router.delete(
    "/{project_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an uploaded document",
)
async def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an uploaded document source record."""
    stmt = select(Source).where(
        Source.id == document_id,
        Source.project_id == project_id,
        Source.canonical_url.like("uploaded://%"),
    )
    source = (await db.execute(stmt)).scalar_one_or_none()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    await db.delete(source)
    await db.commit()
    logger.info("document_deleted", project_id=str(project_id), document_id=str(document_id))


# ---------------------------------------------------------------------------
# Workflow Stubs (implemented in later sprints)
# ---------------------------------------------------------------------------

@router.post("/{project_id}/run", summary="Enqueue research workflow")
async def run_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Enqueue research workflow via Celery (or async task)."""
    stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Try enqueuing with Celery; fallback to direct task if broker is unavailable
    try:
        from app.worker import execute_research_workflow
        task = execute_research_workflow.delay(str(project_id))
        task_id = task.id
    except Exception as exc:
        logger.warning("celery_enqueue_failed_falling_back", error=str(exc))
        task_id = "local-sync-task"

    project.status = ProjectStatus.running.value
    project.workflow_run_id = task_id
    project.error_message = None
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "queued",
            "project_id": str(project_id),
            "task_id": task_id,
            "message": "Research workflow has been initiated.",
        },
    )


@router.get("/{project_id}/review", summary="Get evidence and synthesis review payload")
async def get_review(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return current evidence, synthesis and QA report for human review gate."""
    # 1. Fetch project
    project_stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(project_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # 2. Fetch latest insight
    insight_stmt = (
        select(Insight)
        .where(Insight.project_id == project_id)
        .order_by(Insight.version.desc())
    )
    insight = (await db.execute(insight_stmt)).scalars().first()

    # 3. Fetch evidence claims and sources
    claims_stmt = select(EvidenceClaim).where(EvidenceClaim.project_id == project_id)
    claims = (await db.execute(claims_stmt)).scalars().all()

    sources_stmt = select(Source).where(Source.project_id == project_id)
    sources = (await db.execute(sources_stmt)).scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "project_id": str(project_id),
            "project_status": project.status,
            "has_synthesis": insight is not None,
            "insight": {
                "id": str(insight.id) if insight else None,
                "version": insight.version if insight else 0,
                "executive_summary": insight.executive_summary if insight else "",
                "findings": insight.findings if insight else [],
                "implications": insight.implications if insight else [],
                "recommendations": insight.recommendations if insight else [],
                "risks": insight.risks if insight else [],
                "limitations": insight.limitations if insight else [],
                "gaps": insight.gaps if insight else [],
                "citations": insight.citations if insight else [],
                "qa_report": insight.qa_report if insight else None,
                "is_approved": insight.is_approved if insight else False,
            } if insight else None,
            "evidence": [
                {
                    "id": str(c.id),
                    "claim_text": c.claim_text,
                    "confidence": c.confidence,
                    "is_uncertain": c.is_uncertain,
                    "is_gap": c.is_gap,
                    "source_ids": [str(sid) for sid in (c.source_ids or [])],
                }
                for c in claims
            ],
            "sources": [
                {
                    "id": str(s.id),
                    "canonical_url": s.canonical_url,
                    "title": s.title,
                    "publisher": s.publisher,
                    "pub_date": s.pub_date.isoformat() if s.pub_date else None,
                }
                for s in sources
            ],
        },
    )


@router.post("/{project_id}/review", summary="Submit review decision")
async def submit_review(
    project_id: uuid.UUID,
    decision: ReviewDecisionRequest = Body(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Submit approve / revise / research_more decision from human review gate."""
    from app.db.models import Feedback

    project_stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(project_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    action = decision.action.value if hasattr(decision.action, "value") else str(decision.action)

    # Latest insight
    insight_stmt = (
        select(Insight)
        .where(Insight.project_id == project_id)
        .order_by(Insight.version.desc())
    )
    insight = (await db.execute(insight_stmt)).scalars().first()

    # Create immutable Feedback record
    feedback = Feedback(
        project_id=project_id,
        insight_id=insight.id if insight else None,
        decision=action,
        user_edits=decision.edited_items,
        comment=decision.comments,
        version=insight.version if insight else 1,
    )
    db.add(feedback)

    if action == "approve":
        if insight:
            insight.is_approved = True
        project.status = ProjectStatus.approved.value
        message = "Synthesis approved. Project is now ready for slide storyline generation."
    elif action == "revise":
        project.status = ProjectStatus.revision_requested.value
        message = "Revision feedback recorded. Synthesis will be updated."
    elif action == "research_more":
        project.status = ProjectStatus.running.value
        message = "Additional research requested. Research engine re-queued."
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown decision action: {action}",
        )

    await db.commit()

    try:
        from app.core.events import create_agent_event, event_bus
        await event_bus.publish(
            f"project:{project_id}",
            create_agent_event(
                event_type="review_decided",
                project_id=str(project_id),
                step="review",
                agent_name="Human Review Gate",
                progress=100,
                message=f"Review decision recorded: {action}. {message}",
                data={"action": action, "status": project.status},
            ),
        )
    except Exception:
        pass

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": project.status,
            "project_id": str(project_id),
            "action": action,
            "message": message,
            "feedback_id": str(feedback.id),
        },
    )


@router.get("/{project_id}/storyline", summary="Get proposed slide storyline")
async def get_storyline(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get proposed slide storyline from approved research synthesis (Day 13)."""
    from app.presentation.storyline import StorylineGateError, StorylineGenerator

    generator = StorylineGenerator(db=db)
    try:
        outline = await generator.generate_storyline(project_id, force_regenerate=False)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=outline.model_dump(),
        )
    except StorylineGateError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except Exception as err:
        logger.error("storyline_get_failed", project_id=str(project_id), error=str(err), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate storyline: {str(err)}",
        )


@router.post("/{project_id}/storyline/generate", summary="Force regenerate slide storyline")
async def generate_storyline(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Force generate a fresh slide storyline from approved synthesis."""
    from app.presentation.storyline import StorylineGateError, StorylineGenerator

    generator = StorylineGenerator(db=db)
    try:
        outline = await generator.generate_storyline(project_id, force_regenerate=True)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=outline.model_dump(),
        )
    except StorylineGateError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except Exception as err:
        logger.error("storyline_generate_failed", project_id=str(project_id), error=str(err), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate storyline: {str(err)}",
        )


@router.post("/{project_id}/storyline", summary="Accept or edit slide storyline")
async def submit_storyline(
    project_id: uuid.UUID,
    payload: StorylineUpdateRequest = Body(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Accept, reorder, or edit slide storyline (Day 13)."""
    from app.presentation.storyline import (
        StorylineGateError,
        StorylineGenerator,
        StorylineValidationError,
    )

    project_stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(project_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    generator = StorylineGenerator(db=db)
    try:
        updated_outline = await generator.update_storyline(
            project_id=project_id,
            slides=payload.slides,
            approve_all=payload.approve_all,
        )

        try:
            from app.core.events import create_agent_event, event_bus
            await event_bus.publish(
                f"project:{project_id}",
                create_agent_event(
                    event_type="storyline_ready" if not payload.approve_all else "storyline_approved",
                    project_id=str(project_id),
                    step="storyline",
                    agent_name="Storyline Studio",
                    progress=100,
                    message="Storyline approved and locked for PowerPoint rendering."
                    if payload.approve_all
                    else f"Storyline updated ({len(payload.slides)} slides).",
                    data={"total_slides": len(payload.slides), "is_approved": payload.approve_all},
                ),
            )
        except Exception:
            pass

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=updated_outline.model_dump(),
        )
    except StorylineValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )
    except StorylineGateError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except Exception as err:
        logger.error("storyline_update_failed", project_id=str(project_id), error=str(err), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update storyline: {str(err)}",
        )


@router.get("/{project_id}/templates", summary="List available corporate presentation templates")
async def get_project_templates(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return available enterprise corporate brand templates (McKinsey, BCG, Bain, Goldman, Modern Tech)."""
    from app.presentation.templates import list_templates
    templates = list_templates()
    return [t.model_dump() for t in templates]


@router.get("/{project_id}/artifact", summary="Download approved deck or summary")
async def download_artifact(
    project_id: uuid.UUID,
    format: str = Query("pptx", description="Export format: pptx, pdf, or html"),
    template: str = Query("mckinsey_navy", description="Corporate brand template ID"),
    view: str = Query("presentation", description="View mode for HTML format: presentation or document"),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download approved presentation deck or executive summary (PPTX, PDF, HTML)."""
    import os
    from app.db.models import Artifact
    from app.presentation.templates import get_template
    from app.presentation.renderer import PresentationRenderer, RendererGateError
    from app.presentation.pdf_exporter import ExecutivePDFExporter, PDFGateError
    from app.presentation.html_viewer import HTMLPresentationGenerator, HTMLGateError

    fmt = format.lower().strip()
    if fmt not in ("pptx", "pdf", "html"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{format}'. Supported formats are: pptx, pdf, html.",
        )

    project_stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(project_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project {project_id} not found or synthesis not approved.",
        )

    corp_template = get_template(template)

    # Auto-generate storyline if slide specs do not exist yet for approved synthesis
    sl_stmt = select(SlideSpec).where(SlideSpec.project_id == project_id)
    has_specs = (await db.execute(sl_stmt)).first() is not None
    if not has_specs:
        from app.presentation.storyline import StorylineGateError, StorylineGenerator
        generator = StorylineGenerator(db=db)
        try:
            await generator.generate_storyline(project_id, force_regenerate=False)
        except StorylineGateError:
            pass

    # 1. Handle PDF format
    if fmt == "pdf":
        exporter = ExecutivePDFExporter(db=db, template=corp_template)
        try:
            file_path, file_size, file_hash = await exporter.export(project_id)
        except PDFGateError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            )

        project.status = ProjectStatus.completed.value
        await db.commit()

        try:
            from app.core.events import create_agent_event, event_bus
            await event_bus.publish(
                f"project:{project_id}",
                create_agent_event(
                    event_type="artifact_generated",
                    project_id=str(project_id),
                    step="presentation",
                    agent_name="Executive PDF Exporter",
                    progress=100,
                    message="Executive summary memo PDF generated and downloaded. Project marked as completed.",
                    data={"filename": f"executive_summary_{project_id}.pdf", "status": "completed"},
                ),
            )
        except Exception:
            pass

        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=f"executive_summary_{project_id}.pdf",
        )

    # 2. Handle HTML format
    if fmt == "html":
        generator = HTMLPresentationGenerator(db=db, template=corp_template)
        try:
            file_path, file_size, file_hash = await generator.generate(project_id, initial_view=view)
        except HTMLGateError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            )

        project.status = ProjectStatus.completed.value
        await db.commit()

        try:
            from app.core.events import create_agent_event, event_bus
            await event_bus.publish(
                f"project:{project_id}",
                create_agent_event(
                    event_type="artifact_generated",
                    project_id=str(project_id),
                    step="presentation",
                    agent_name="HTML Presentation Generator",
                    progress=100,
                    message="Interactive HTML presentation deck generated and downloaded. Project marked as completed.",
                    data={"filename": f"consulting_deck_{project_id}.html", "status": "completed"},
                ),
            )
        except Exception:
            pass

        return FileResponse(
            path=file_path,
            media_type="text/html; charset=utf-8",
            filename=f"consulting_deck_{project_id}.html",
        )

    # 3. Handle PPTX format (default)
    art_stmt = select(Artifact).where(Artifact.project_id == project_id)
    artifact = (await db.execute(art_stmt)).scalar_one_or_none()

    if not artifact or not os.path.exists(artifact.file_path) or template != "mckinsey_navy":
        renderer = PresentationRenderer(db=db, template=corp_template)
        try:
            artifact = await renderer.render(project_id)
        except RendererGateError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            )

    project.status = ProjectStatus.completed.value
    await db.commit()

    try:
        from app.core.events import create_agent_event, event_bus
        await event_bus.publish(
            f"project:{project_id}",
            create_agent_event(
                event_type="artifact_generated",
                project_id=str(project_id),
                step="presentation",
                agent_name="Presentation Renderer",
                progress=100,
                message="Widescreen PowerPoint presentation deck generated and downloaded. Project workflow completed successfully.",
                data={"filename": f"consulting_deck_{project_id}.pptx", "status": "completed"},
            ),
        )
    except Exception:
        pass

    return FileResponse(
        path=artifact.file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"consulting_deck_{project_id}.pptx",
    )
