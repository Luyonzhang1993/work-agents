"""Management API for MCP service definitions."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.persistence.database import get_db
from app.persistence import mcp_services as repo
from app.services.mcp_registry import refresh_mcp_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/manage/mcp", tags=["manage-mcp"])


class MCPServiceIn(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1)
    module: str = Field(min_length=1)
    command: str | None = None
    description: str = ""
    timeout: float = 10
    enabled: bool = True


class MCPServiceUpdate(BaseModel):
    name: str | None = None
    module: str | None = None
    command: str | None = None
    description: str | None = None
    timeout: float | None = None
    enabled: bool | None = None


@router.get("")
async def list_services() -> list[dict]:
    db = await get_db()
    try:
        return await repo.list_all(db)
    finally:
        await db.close()


@router.post("", status_code=201)
async def create_service(body: MCPServiceIn) -> dict:
    db = await get_db()
    try:
        existing = await repo.get_by_id(db, body.id)
        if existing:
            raise HTTPException(409, f"Service '{body.id}' already exists")
        await repo.create(db, body.id, body.name, body.module,
                          command=body.command, description=body.description,
                          timeout=body.timeout, enabled=body.enabled)
    finally:
        await db.close()
    await refresh_mcp_registry()
    return {"id": body.id, "status": "created"}


@router.put("/{service_id}")
async def update_service(service_id: str, body: MCPServiceUpdate) -> dict:
    db = await get_db()
    try:
        if await repo.get_by_id(db, service_id) is None:
            raise HTTPException(404, "Not found")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await repo.update(db, service_id, **updates)
    finally:
        await db.close()
    await refresh_mcp_registry()
    return {"id": service_id, "status": "updated"}


@router.delete("/{service_id}")
async def delete_service(service_id: str) -> dict:
    db = await get_db()
    try:
        deleted = await repo.delete(db, service_id)
    finally:
        await db.close()
    if not deleted:
        raise HTTPException(404, "Not found")
    await refresh_mcp_registry()
    return {"id": service_id, "status": "deleted"}
