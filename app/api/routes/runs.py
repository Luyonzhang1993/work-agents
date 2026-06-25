"""REST endpoints for inspecting persisted runs and their events."""

import logging

from fastapi import APIRouter, HTTPException, status

from app.persistence import runs as run_repo
from app.persistence.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict:
    db = await get_db()
    try:
        run = await run_repo.get_run(db, run_id)
    finally:
        await db.close()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )
    return run


@router.get("/{run_id}/events")
async def get_run_events(run_id: str) -> dict:
    db = await get_db()
    try:
        events = await run_repo.get_events(db, run_id)
    finally:
        await db.close()

    return {"run_id": run_id, "events": events}
