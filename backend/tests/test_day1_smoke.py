"""Day 1 smoke test — no DB, no external services needed."""

from __future__ import annotations

import pytest


def test_config_imports() -> None:
    """Settings can be imported (using test env vars via conftest)."""
    from app.core.config import settings  # noqa: F401


def test_security_blocks_loopback() -> None:
    from app.core.security import is_safe_url, validate_url

    assert is_safe_url("http://127.0.0.1/secret") is False
    assert is_safe_url("http://localhost/secret") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False
    assert is_safe_url("http://10.0.0.1/internal") is False
    assert is_safe_url("http://192.168.1.1/router") is False

    with pytest.raises(ValueError, match="restricted"):
        validate_url("http://127.0.0.1/secret")


def test_security_allows_public() -> None:
    from app.core.security import is_safe_url

    # Can't do DNS in sandbox, but IP literals should work
    assert is_safe_url("https://8.8.8.8/") is True  # Google DNS — public IP
    assert is_safe_url("ftp://example.com/file") is False  # bad scheme


def test_health_router_exists() -> None:
    from app.api.health import router

    routes = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/health" in routes


def test_projects_router_exists() -> None:
    from app.api.projects import router

    routes = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "" in routes or "/" in routes
    assert "/{project_id}" in routes
    assert "/{project_id}/run" in routes
    assert "/{project_id}/review" in routes
    assert "/{project_id}/storyline" in routes
    assert "/{project_id}/artifact" in routes
