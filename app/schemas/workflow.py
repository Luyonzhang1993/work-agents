from typing import Any

from pydantic import BaseModel, Field


class WorkflowStepDefinition(BaseModel):
    id: str
    name: str
    type: str
    tool: str | None = None


class WorkflowDefinitionResponse(BaseModel):
    id: str
    name: str
    description: str
    steps: list[WorkflowStepDefinition]


class WorkflowRunRequest(BaseModel):
    symbol: str = Field(default="AMD", min_length=1)


class WorkflowStepResult(BaseModel):
    id: str
    name: str
    status: str
    output: dict[str, Any]


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    status: str
    steps: list[WorkflowStepResult]
    report: str
    error: dict[str, Any] | None = None
