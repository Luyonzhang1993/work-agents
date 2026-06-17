import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.schemas.workflow import (
    TravelWorkflowRunRequest,
    WorkflowDefinitionResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
)
from app.services.langgraph_travel_workflow import (
    LangGraphTravelWorkflowService,
    event_to_sse,
    get_langgraph_travel_workflow_service,
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


@router.get("/travel-planner", response_model=WorkflowDefinitionResponse)
async def get_travel_planner_workflow(
    workflow_service: LangGraphTravelWorkflowService = Depends(
        get_langgraph_travel_workflow_service
    ),
) -> WorkflowDefinitionResponse:
    return workflow_service.definition()


@router.post("/travel-planner/run", response_model=WorkflowRunResponse)
async def run_travel_planner_workflow(
    request: TravelWorkflowRunRequest,
    workflow_service: LangGraphTravelWorkflowService = Depends(
        get_langgraph_travel_workflow_service
    ),
) -> WorkflowRunResponse:
    try:
        return await workflow_service.run(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unhandled LangGraph travel workflow API failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Travel workflow request failed unexpectedly",
        ) from exc


@router.post("/travel-planner/stream")
async def stream_travel_planner_workflow(
    request: TravelWorkflowRunRequest,
    workflow_service: LangGraphTravelWorkflowService = Depends(
        get_langgraph_travel_workflow_service
    ),
) -> StreamingResponse:
    async def event_stream():
        try:
            async for event in workflow_service.stream(request):
                yield event_to_sse(event)
        except Exception as exc:
            yield event_to_sse(workflow_service.failed_event(exc))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
