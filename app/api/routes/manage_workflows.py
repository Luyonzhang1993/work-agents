"""Management CRUD API for workflow definitions.

Provides full create / read / update / delete over the user's local
workflow store.  System-bundled workflows can also be listed but
cannot be deleted (they are re-seeded on restart).
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.persistence.database import get_db
from app.persistence import workflows as wf_repo
from app.services.workflow_registry import refresh_dynamic_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/manage/workflows", tags=["manage-workflows"])

# ── Schemas ──


class WorkflowDefinitionIn(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1)
    description: str = ""
    definition: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] | None = None
    enabled: bool | None = None


# ── Routes ──


@router.get("")
async def list_workflows() -> list[dict[str, Any]]:
    db = await get_db()
    try:
        rows = await wf_repo.list_all(db)
    finally:
        await db.close()

    # Parse JSON definition field for the response
    for row in rows:
        if isinstance(row.get("definition"), str):
            try:
                row["definition"] = json.loads(row["definition"])
            except json.JSONDecodeError:
                row["definition"] = {}
        row["enabled"] = bool(row.get("enabled"))
    return rows


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict[str, Any]:
    db = await get_db()
    try:
        row = await wf_repo.get_by_id(db, workflow_id)
    finally:
        await db.close()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if isinstance(row.get("definition"), str):
        try:
            row["definition"] = json.loads(row["definition"])
        except json.JSONDecodeError:
            row["definition"] = {}
    row["enabled"] = bool(row.get("enabled"))
    return row


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workflow(body: WorkflowDefinitionIn) -> dict[str, Any]:
    db = await get_db()
    try:
        existing = await wf_repo.get_by_id(db, body.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workflow '{body.id}' already exists",
            )
        await wf_repo.create(
            db,
            workflow_id=body.id,
            name=body.name,
            description=body.description,
            definition=body.definition,
            enabled=body.enabled,
        )
    finally:
        await db.close()

    await refresh_dynamic_registry()
    return {"id": body.id, "status": "created"}


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    body: WorkflowDefinitionUpdate,
) -> dict[str, Any]:
    db = await get_db()
    try:
        existing = await wf_repo.get_by_id(db, workflow_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
        updates: dict[str, Any] = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.description is not None:
            updates["description"] = body.description
        if body.definition is not None:
            updates["definition"] = body.definition
        if body.enabled is not None:
            updates["enabled"] = body.enabled

        if updates:
            await wf_repo.update(db, workflow_id, **updates)
    finally:
        await db.close()

    await refresh_dynamic_registry()
    return {"id": workflow_id, "status": "updated"}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str) -> dict[str, Any]:
    db = await get_db()
    try:
        deleted = await wf_repo.delete(db, workflow_id)
    finally:
        await db.close()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )
    await refresh_dynamic_registry()
    return {"id": workflow_id, "status": "deleted"}
