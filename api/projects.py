import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rag import get_supabase_client
from local_paths import delete_local_project_path, get_local_project_path, set_local_project_path

projects_router = APIRouter()

PROJECT_KEY_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class ProjectCreate(BaseModel):
    project_key: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    project_path: Optional[str] = None


class ProjectUpdate(BaseModel):
    display_name: str = Field(min_length=1)
    project_path: Optional[str] = None


def validate_project_key(project_key: str) -> str:
    cleaned = project_key.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="project_key is required.")
    if not PROJECT_KEY_PATTERN.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail="project_key must be lowercase letters, numbers, dashes, or underscores.",
        )
    return cleaned


@projects_router.get("/projects")
def list_projects() -> list[dict]:
    try:
        supabase = get_supabase_client()
        result = (
            supabase.table("projects")
            .select("project_key,display_name,created_at,updated_at")
            .order("created_at", desc=False)
            .execute()
        )
        items = result.data or []
        for item in items:
            item["project_path"] = get_local_project_path(item.get("project_key", "")) or ""
        return items
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load projects: {exc}") from exc


@projects_router.post("/projects")
def create_project(body: ProjectCreate) -> dict:
    project_key = validate_project_key(body.project_key)
    display_name = body.display_name.strip()
    project_path = body.project_path.strip() if body.project_path else ""
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required.")
    if body.project_path is not None and not project_path:
        raise HTTPException(status_code=400, detail="project_path cannot be empty.")

    try:
        supabase = get_supabase_client()
        existing = (
            supabase.table("projects")
            .select("project_key")
            .eq("project_key", project_key)
            .limit(1)
            .execute()
        )
        if existing.data:
            raise HTTPException(status_code=409, detail="project_key already exists.")

        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "project_key": project_key,
            "display_name": display_name,
            "updated_at": now,
        }
        result = supabase.table("projects").insert(payload).execute()
        if project_path:
            set_local_project_path(project_key, project_path)
        response = result.data[0] if result.data else payload
        response["project_path"] = project_path
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create project: {exc}") from exc


@projects_router.put("/projects/{project_key}")
def update_project(project_key: str, body: ProjectUpdate) -> dict:
    cleaned_key = validate_project_key(project_key)
    display_name = body.display_name.strip()
    project_path = body.project_path.strip() if body.project_path else ""
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required.")
    if body.project_path is not None and not project_path:
        raise HTTPException(status_code=400, detail="project_path cannot be empty.")

    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()
        payload = {"display_name": display_name, "updated_at": now}
        result = (
            supabase.table("projects")
            .update(payload)
            .eq("project_key", cleaned_key)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="project not found.")
        if project_path:
            set_local_project_path(cleaned_key, project_path)
        response = result.data[0]
        response["project_path"] = project_path or get_local_project_path(cleaned_key) or ""
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update project: {exc}") from exc


@projects_router.delete("/projects/{project_key}")
def delete_project(project_key: str) -> dict:
    cleaned_key = validate_project_key(project_key)
    try:
        supabase = get_supabase_client()
        sources = (
            supabase.table("sources")
            .select("id")
            .eq("project_key", cleaned_key)
            .limit(1)
            .execute()
        )
        if sources.data:
            raise HTTPException(status_code=409, detail="project has sources")

        result = (
            supabase.table("projects")
            .delete()
            .eq("project_key", cleaned_key)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="project not found.")
        delete_local_project_path(cleaned_key)
        return {"deleted": True, "project_key": cleaned_key}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {exc}") from exc
