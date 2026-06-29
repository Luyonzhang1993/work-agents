"""Workflow catalog and dynamic run endpoints."""

import logging

from fastapi import APIRouter, Depends

from app.schemas.workflow import WorkflowCatalogResponse
from app.services.workflow_registry import WorkflowRegistry, get_workflow_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=WorkflowCatalogResponse)
async def list_workflows(
    registry: WorkflowRegistry = Depends(get_workflow_registry),
) -> WorkflowCatalogResponse:
    return WorkflowCatalogResponse(workflows=registry.catalog())
