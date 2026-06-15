import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
)
from app.services.mcp_client import MCPError
from app.services.workflow_service import WorkflowService, get_workflow_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/finance-report", response_model=WorkflowDefinitionResponse)
async def get_finance_report_workflow(
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowDefinitionResponse:
    return workflow_service.finance_report_definition()


@router.post("/finance-report/run", response_model=WorkflowRunResponse)
async def run_finance_report_workflow(
    request: WorkflowRunRequest,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowRunResponse:
    try:
        return await workflow_service.run_finance_report(request)
    except MCPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unhandled workflow API failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workflow request failed unexpectedly",
        ) from exc
