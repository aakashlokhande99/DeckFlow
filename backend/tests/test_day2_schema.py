"""Day 2 tests — domain schema, enums, and model structure."""

from __future__ import annotations

import uuid


def test_all_enums_importable() -> None:
    from app.db.enums import (
        ArtifactType,
        ConfidenceLevel,
        ProjectStatus,
        ResearchDepth,
        ReviewDecision,
        SlideLayout,
    )

    assert ProjectStatus.draft.value == "draft"
    assert ProjectStatus.awaiting_review.value == "awaiting_review"
    assert ResearchDepth.deep.value == "deep"
    assert ReviewDecision.research_more.value == "research_more"
    assert SlideLayout.risk_matrix.value == "risk_matrix"
    assert ConfidenceLevel.uncertain.value == "uncertain"
    assert ArtifactType.pptx.value == "pptx"


def test_all_models_importable() -> None:
    from app.db.models import (
        Artifact,
        EvidenceClaim,
        Feedback,
        Insight,
        Project,
        SlideSpec,
        Source,
    )

    # Verify table names
    assert Project.__tablename__ == "projects"
    assert Source.__tablename__ == "sources"
    assert EvidenceClaim.__tablename__ == "evidence_claims"
    assert Insight.__tablename__ == "insights"
    assert Feedback.__tablename__ == "feedback"
    assert SlideSpec.__tablename__ == "slide_specs"
    assert Artifact.__tablename__ == "artifacts"


def test_project_model_columns() -> None:
    from app.db.models import Project

    cols = {c.name for c in Project.__table__.columns}
    required = {
        "id", "created_at", "updated_at", "topic", "objective",
        "audience", "geography", "time_horizon", "research_depth",
        "status", "workflow_run_id", "error_message",
    }
    assert required <= cols


def test_source_unique_constraint() -> None:
    from app.db.models import Source

    constraint_names = {c.name for c in Source.__table__.constraints}
    assert "uq_sources_project_url" in constraint_names


def test_source_project_fk() -> None:
    from app.db.models import Source

    fk_targets = {
        list(col.foreign_keys)[0].target_fullname
        for col in Source.__table__.columns
        if col.foreign_keys
    }
    assert "projects.id" in fk_targets


def test_evidence_claim_has_source_ids_array() -> None:
    from sqlalchemy.dialects.postgresql import ARRAY
    from app.db.models import EvidenceClaim, StringArray

    col = EvidenceClaim.__table__.columns["source_ids"]
    assert isinstance(col.type, (ARRAY, StringArray))


def test_insight_jsonb_fields() -> None:
    from sqlalchemy.dialects.postgresql import JSONB
    from app.db.models import Insight

    jsonb_fields = ["findings", "implications", "recommendations",
                    "risks", "limitations", "gaps", "citations"]
    for field in jsonb_fields:
        col = Insight.__table__.columns[field]
        assert isinstance(col.type, JSONB), f"{field} should be JSONB"


def test_migration_file_exists() -> None:
    import os
    path = os.path.join(
        os.path.dirname(__file__), "..", "app", "db", "migrations", "versions", "0001_initial_schema.py"
    )
    assert os.path.exists(path), "Migration file 0001_initial_schema.py not found"


def test_migration_has_correct_revision() -> None:
    import importlib.util
    import os
    file_path = os.path.join(
        os.path.dirname(__file__), "..", "app", "db", "migrations", "versions", "0001_initial_schema.py"
    )
    spec = importlib.util.spec_from_file_location("initial_schema_migration", os.path.abspath(file_path))
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "0001"
    assert m.down_revision is None
