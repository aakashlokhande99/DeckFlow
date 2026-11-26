"""Day 3 API tests: project CRUD, brief validation, error handling, DB session."""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient


VALID_BRIEF = {
    "topic": "Future of Autonomous Mobility 2030",
    "objective": "Evaluate level 4 and 5 commercialization timeline and economic feasibility.",
    "audience": "Board of Directors, Global Automotive OEM",
    "geography": "Global (Focus on US, EU, China)",
    "time_horizon": "2025-2030",
    "research_depth": "deep",
}


@pytest.mark.asyncio
async def test_create_project_success(async_client: AsyncClient) -> None:
    """Test valid project creation returns 201 and valid ProjectResponse."""
    response = await async_client.post("/api/projects", json=VALID_BRIEF)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["topic"] == VALID_BRIEF["topic"]
    assert data["objective"] == VALID_BRIEF["objective"]
    assert data["audience"] == VALID_BRIEF["audience"]
    assert data["geography"] == VALID_BRIEF["geography"]
    assert data["time_horizon"] == VALID_BRIEF["time_horizon"]
    assert data["research_depth"] == "deep"
    assert data["status"] == "draft"
    assert data["workflow_run_id"] is None
    assert data["error_message"] is None
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_project_invalid_brief(async_client: AsyncClient) -> None:
    """Test invalid brief returns 422 Unprocessable Entity."""
    # Empty topic
    invalid_brief = {**VALID_BRIEF, "topic": ""}
    response = await async_client.post("/api/projects", json=invalid_brief)
    assert response.status_code == 422
    assert "detail" in response.json()

    # Topic too short (< 3 chars)
    invalid_brief = {**VALID_BRIEF, "topic": "AI"}
    response = await async_client.post("/api/projects", json=invalid_brief)
    assert response.status_code == 422

    # Objective too short (< 10 chars)
    invalid_brief = {**VALID_BRIEF, "objective": "short"}
    response = await async_client.post("/api/projects", json=invalid_brief)
    assert response.status_code == 422

    # Invalid research_depth enum value
    invalid_brief = {**VALID_BRIEF, "research_depth": "ultra-deep"}
    response = await async_client.post("/api/projects", json=invalid_brief)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_projects(async_client: AsyncClient) -> None:
    """Test GET /api/projects lists created projects."""
    # Create two projects
    brief_1 = {**VALID_BRIEF, "topic": "Project Alpha"}
    brief_2 = {**VALID_BRIEF, "topic": "Project Beta"}

    res1 = await async_client.post("/api/projects", json=brief_1)
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    res2 = await async_client.post("/api/projects", json=brief_2)
    assert res2.status_code == 201
    id2 = res2.json()["id"]

    list_res = await async_client.get("/api/projects")
    assert list_res.status_code == 200
    projects = list_res.json()
    assert isinstance(projects, list)
    project_ids = [p["id"] for p in projects]
    assert id1 in project_ids
    assert id2 in project_ids


@pytest.mark.asyncio
async def test_get_project_detail(async_client: AsyncClient) -> None:
    """Test GET /api/projects/{id} returns single project detail."""
    create_res = await async_client.post("/api/projects", json=VALID_BRIEF)
    project_id = create_res.json()["id"]

    get_res = await async_client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    project = get_res.json()
    assert project["id"] == project_id
    assert project["topic"] == VALID_BRIEF["topic"]


@pytest.mark.asyncio
async def test_get_missing_project_404(async_client: AsyncClient) -> None:
    """Test GET /api/projects/{non_existent_id} returns 404."""
    random_id = str(uuid.uuid4())
    response = await async_client.get(f"/api/projects/{random_id}")
    assert response.status_code == 404
    assert f"Project {random_id} not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_project_success(async_client: AsyncClient) -> None:
    """Test DELETE /api/projects/{id} deletes the project and returns 204."""
    create_res = await async_client.post("/api/projects", json=VALID_BRIEF)
    project_id = create_res.json()["id"]

    del_res = await async_client.delete(f"/api/projects/{project_id}")
    assert del_res.status_code == 204

    # Verify project is gone
    get_res = await async_client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_missing_project_404(async_client: AsyncClient) -> None:
    """Test DELETE /api/projects/{non_existent_id} returns 404."""
    random_id = str(uuid.uuid4())
    response = await async_client.delete(f"/api/projects/{random_id}")
    assert response.status_code == 404
    assert f"Project {random_id} not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_health_endpoints(async_client: AsyncClient) -> None:
    """Test GET /api/health and /api/health/db."""
    res = await async_client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res_db = await async_client.get("/api/health/db")
    assert res_db.status_code == 200
    assert res_db.json()["database"] == "connected"


@pytest.mark.asyncio
async def test_workflow_endpoints_enforce_gate(async_client: AsyncClient) -> None:
    """Test that workflow endpoints require valid approved projects and enforce gates."""
    pid = str(uuid.uuid4())
    # Unapproved or non-existent project fails gate with 400
    assert (await async_client.get(f"/api/projects/{pid}/storyline")).status_code == 400
    assert (await async_client.get(f"/api/projects/{pid}/artifact")).status_code == 400
