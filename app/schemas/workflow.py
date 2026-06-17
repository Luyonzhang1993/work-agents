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


class TravelWorkflowRunRequest(BaseModel):
    destination: str = Field(default="杭州", min_length=1)
    duration_days: int = Field(default=3, ge=1, le=14)
    budget_level: str = Field(
        default="comfort",
        pattern="^(budget|comfort|premium)$",
    )
    traveler_type: str = Field(default="couple", min_length=1)
    interests: list[str] = Field(
        default_factory=lambda: ["local_food", "culture", "city_walk"],
    )


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
