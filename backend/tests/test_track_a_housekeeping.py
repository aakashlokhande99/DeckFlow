"""Automated tests for Sprint 7 Track A: Housekeeping & Critical Spec Obligations."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from app.core.config import settings
from app.worker import cleanup_old_artifacts


class TestHousekeepingAndSpecObligations:
    """Verify repo hygiene, configuration completeness, and artifact lifecycle."""

    def test_gitignore_contains_required_exclusions(self):
        """Root .gitignore must exclude deliverable artifacts, generated decks, and secrets."""
        gitignore_path = Path(".gitignore")
        assert gitignore_path.exists(), "Root .gitignore must exist"
        
        content = gitignore_path.read_text(encoding="utf-8")
        assert "artifacts/*" in content or "artifacts/" in content
        assert "*.pptx" in content
        assert "*.pdf" in content
        assert "*.html" in content
        assert ".env" in content

    def test_env_example_documents_all_config_fields(self):
        """.env.example must exist and document essential configuration keys."""
        example_path = Path(".env.example")
        assert example_path.exists(), "Root .env.example must exist"
        
        content = example_path.read_text(encoding="utf-8")
        required_keys = [
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY",
            "ENVIRONMENT",
            "LOG_LEVEL",
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
            "LLM_PROVIDER",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "SEARCH_PROVIDER",
            "SERPAPI_KEY",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_HOST",
            "SLACK_WEBHOOK_URL",
            "TEAMS_WEBHOOK_URL",
            "FRONTEND_BASE_URL",
            "ARTIFACT_RETENTION_DAYS",
        ]
        for key in required_keys:
            assert f"{key}=" in content or f"{key} " in content, f"Missing {key} in .env.example"

    def test_artifact_retention_days_setting(self):
        """Settings object must expose an integer ARTIFACT_RETENTION_DAYS property."""
        assert hasattr(settings, "ARTIFACT_RETENTION_DAYS")
        assert isinstance(settings.ARTIFACT_RETENTION_DAYS, int)
        assert settings.ARTIFACT_RETENTION_DAYS > 0

    def test_cleanup_old_artifacts_task_callable(self, tmp_path):
        """cleanup_old_artifacts periodic task runs cleanly and respects retention cutoff."""
        # Create dummy old file and new file in a test temp directory
        old_file = tmp_path / "test_old_deck.pptx"
        old_file.write_text("dummy", encoding="utf-8")
        
        # Set modification time back 10 days
        ten_days_ago = os.path.getmtime(old_file) - (10 * 86400)
        os.utime(old_file, (ten_days_ago, ten_days_ago))
        
        new_file = tmp_path / "test_new_deck.pptx"
        new_file.write_text("dummy", encoding="utf-8")
        
        # Run cleanup with mock directory
        import unittest.mock as mock
        with mock.patch("app.worker.Path.is_dir", return_value=True), \
             mock.patch("app.worker.Path.iterdir", return_value=[old_file, new_file]):
            result = cleanup_old_artifacts(retention_days=7)
            
        assert result["status"] == "success"
        assert result["deleted_count"] == 1
        assert not old_file.exists()
        assert new_file.exists()
