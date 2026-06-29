from typing import Any

from pydantic import BaseModel, Field


class WorkflowCatalogItem(BaseModel):
    id: str
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowCatalogResponse(BaseModel):
    workflows: list[WorkflowCatalogItem]


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


class WorkflowEvent(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
