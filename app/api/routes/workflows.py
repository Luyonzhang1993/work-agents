"""Workflow catalog and dynamic run endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.workflow import (
    WorkflowCatalogResponse,
    WorkflowDefinitionResponse,
    WorkflowRunResponse,
)
from app.services.workflow_registry import WorkflowRegistry, get_workflow_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=WorkflowCatalogResponse)
async def list_workflows(
    registry: WorkflowRegistry = Depends(get_workflow_registry),
) -> WorkflowCatalogResponse:
    return WorkflowCatalogResponse(workflows=registry.catalog())


@router.get("/{workflow_id}", response_model=WorkflowDefinitionResponse)
async def get_workflow_definition(
    workflow_id: str,
    registry: WorkflowRegistry = Depends(get_workflow_registry),
) -> WorkflowDefinitionResponse:
    registration = registry.registration(_normalize_workflow_id(workflow_id))
    if registration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    return registration.runtime.definition()


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def run_workflow(
    workflow_id: str,
    arguments: dict[str, Any],
    registry: WorkflowRegistry = Depends(get_workflow_registry),
) -> WorkflowRunResponse:
    registration = registry.registration(_normalize_workflow_id(workflow_id))
    if registration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    return await registration.runtime.run(arguments)


def _normalize_workflow_id(workflow_id: str) -> str:
    if workflow_id.startswith("workflow:"):
        return workflow_id
    return f"workflow:{workflow_id}"
