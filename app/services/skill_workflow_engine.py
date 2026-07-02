"""Skill workflow runtime.

Skill workflows use markdown instructions instead of a node graph. They are
best for agentic capabilities where the process is mostly judgement, policy,
and output shape rather than a fixed DAG.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowEvent,
    WorkflowRunResponse,
    WorkflowStepDefinition,
    WorkflowStepResult,
)
from app.services.llm_utils import extract_usage_details
from app.services.observability import get_observability_client
from app.services.openai_client import build_openai_client
from app.services.workflow_runtime import WorkflowRuntime

logger = logging.getLogger(__name__)

WORKFLOW_ID_PREFIX = "workflow:"


def _split_stream_text(text: str, chunk_size: int = 40) -> list[str]:
    parts = re.split(r"(?<=[。！？\n.!?])\s*", text)
    chunks: list[str] = []
    for part in parts:
        if not part:
            continue
        for i in range(0, len(part), chunk_size):
            chunks.append(part[i : i + chunk_size])
    return chunks if chunks else [text]


class SkillWorkflowEngine:
    """Execute a markdown-defined skill as one workflow capability."""

    def __init__(self, llm_client: AsyncOpenAI | None = None) -> None:
        self.settings = get_settings()
        self.llm_client = llm_client
        self.observability = get_observability_client()

    def definition_to_steps(
        self,
        workflow_id: str,
        name: str,
        description: str,
    ) -> WorkflowDefinitionResponse:
        return WorkflowDefinitionResponse(
            id=workflow_id,
            name=name,
            description=description,
            steps=[
                WorkflowStepDefinition(id="start", name="开始", type="start"),
                WorkflowStepDefinition(
                    id="skill",
                    name="执行 Skill",
                    type="skill",
                    tool="skill:markdown",
                ),
                WorkflowStepDefinition(id="end", name="结束", type="end"),
            ],
        )

    async def run(
        self,
        workflow_id: str,
        workflow_name: str,
        description: str,
        definition: dict[str, Any],
        arguments: dict[str, Any],
    ) -> WorkflowRunResponse:
        try:
            report = await self._execute_skill(
                workflow_name=workflow_name,
                description=description,
                definition=definition,
                arguments=arguments,
            )
        except Exception as exc:
            return WorkflowRunResponse(
                workflow_id=workflow_id,
                status="failed",
                steps=[
                    WorkflowStepResult(
                        id="skill",
                        name="执行 Skill",
                        status="failed",
                        output={
                            "error": str(exc),
                            "error_type": exc.__class__.__name__,
                        },
                    )
                ],
                report="",
                error={"error": str(exc), "error_type": exc.__class__.__name__},
            )

        return WorkflowRunResponse(
            workflow_id=workflow_id,
            status="completed",
            steps=[
                WorkflowStepResult(
                    id="skill",
                    name="执行 Skill",
                    status="completed",
                    output={"report": report},
                )
            ],
            report=report,
        )

    async def stream(
        self,
        workflow_id: str,
        workflow_name: str,
        description: str,
        definition: dict[str, Any],
        arguments: dict[str, Any],
    ) -> AsyncIterator[WorkflowEvent]:
        sequence = 0
        yield WorkflowEvent(
            type="workflow.started",
            data={
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "input": arguments,
                "sequence": sequence,
            },
        )
        sequence += 1

        yield WorkflowEvent(
            type="workflow.step.started",
            data={
                "step_id": "skill",
                "name": "执行 Skill",
                "message": "正在执行 Skill",
                "sequence": sequence,
            },
        )
        sequence += 1

        try:
            report = await self._execute_skill(
                workflow_name=workflow_name,
                description=description,
                definition=definition,
                arguments=arguments,
            )
        except Exception as exc:
            yield WorkflowEvent(
                type="workflow.failed",
                data={
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "step_id": "skill",
                    "sequence": sequence,
                },
            )
            return

        yield WorkflowEvent(
            type="workflow.step.completed",
            data={
                "step_id": "skill",
                "name": "执行 Skill",
                "output": {"report": report},
                "sequence": sequence,
            },
        )
        sequence += 1

        for token in _split_stream_text(report):
            yield WorkflowEvent(
                type="assistant.message.delta",
                data={"content": token, "sequence": sequence},
            )
            sequence += 1
            await asyncio.sleep(0.02)

        yield WorkflowEvent(
            type="assistant.message.completed",
            data={"content": report, "sequence": sequence},
        )
        sequence += 1

        yield WorkflowEvent(
            type="workflow.completed",
            data={
                "workflow_id": workflow_id,
                "report": report,
                "sequence": sequence,
            },
        )

    async def _execute_skill(
        self,
        workflow_name: str,
        description: str,
        definition: dict[str, Any],
        arguments: dict[str, Any],
    ) -> str:
        skill_markdown = self._skill_markdown(definition, description)
        input_text = definition.get("input_template")
        if isinstance(input_text, str) and input_text.strip():
            user_content = _resolve_template(input_text, arguments)
        else:
            user_content = (
                "Input arguments:\n"
                f"{json.dumps(arguments, ensure_ascii=False, indent=2)}"
            )

        messages = [
            {
                "role": "system",
                "content": (
                    f"You are executing the registered skill '{workflow_name}'. "
                    "Follow the skill instructions. Stay within the requested "
                    "scope and produce the requested final output.\n\n"
                    f"{skill_markdown}"
                ),
            },
            {"role": "user", "content": user_content},
        ]

        client = self._client()
        with self.observability.start_generation(
            "llm.skill_workflow",
            model=self.settings.openai_model,
            input=messages,
            metadata={
                "workflow_name": workflow_name,
                "temperature": float(
                    definition.get("temperature", self.settings.llm_temperature)
                ),
            },
        ) as generation:
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=float(
                    definition.get("temperature", self.settings.llm_temperature)
                ),
                timeout=120,
            )
            generation.update(
                output=response.model_dump(),
                usage_details=extract_usage_details(response),
            )
        return response.choices[0].message.content or ""

    def _skill_markdown(self, definition: dict[str, Any], description: str) -> str:
        inline = (
            definition.get("skill")
            or definition.get("skill_markdown")
            or definition.get("prompt")
        )
        if isinstance(inline, str) and inline.strip():
            return inline

        skill_path = definition.get("skill_path")
        if isinstance(skill_path, str) and skill_path.strip():
            return _read_workspace_file(skill_path)

        return (
            "# Skill\n\n"
            f"{description or 'Handle the user request carefully.'}\n\n"
            "## Output\n\n"
            "Return a concise, useful answer for the user."
        )

    def _client(self) -> AsyncOpenAI:
        if self.llm_client is None:
            self.llm_client = build_openai_client(self.settings)
        return self.llm_client


class SkillWorkflowAdapter(WorkflowRuntime):
    """Wraps a DB row with ``engine=skill`` into WorkflowRuntime."""

    def __init__(
        self,
        row: dict[str, Any],
        engine: SkillWorkflowEngine,
    ) -> None:
        self._engine = engine
        self._parsed = _parse_definition(row)

    @property
    def workflow_id(self) -> str:
        return self._parsed["id"]

    def definition(self) -> WorkflowDefinitionResponse:
        return self._engine.definition_to_steps(
            workflow_id=self._parsed["id"],
            name=self._parsed["name"],
            description=self._parsed["description"],
        )

    async def run(self, arguments: dict[str, Any]) -> WorkflowRunResponse:
        return await self._engine.run(
            workflow_id=self._parsed["id"],
            workflow_name=self._parsed["name"],
            description=self._parsed["description"],
            definition=self._parsed["definition"],
            arguments=arguments,
        )

    async def stream(self, arguments: dict[str, Any]) -> AsyncIterator[WorkflowEvent]:
        async for event in self._engine.stream(
            workflow_id=self._parsed["id"],
            workflow_name=self._parsed["name"],
            description=self._parsed["description"],
            definition=self._parsed["definition"],
            arguments=arguments,
        ):
            yield event


def extract_skill_parameters(row: dict[str, Any]) -> dict[str, Any]:
    parsed = _parse_json_definition(row)
    params = parsed.get("parameters")
    if isinstance(params, dict) and params:
        return params
    return {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Input message."}
        },
        "required": ["message"],
        "additionalProperties": False,
    }


def get_skill_engine() -> SkillWorkflowEngine:
    return SkillWorkflowEngine()


def _parse_definition(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{WORKFLOW_ID_PREFIX}{row['id']}",
        "name": str(row.get("name", row.get("id", ""))),
        "description": str(row.get("description", "")),
        "definition": _parse_json_definition(row),
    }


def _parse_json_definition(row: dict[str, Any]) -> dict[str, Any]:
    defn = row.get("definition", {})
    if isinstance(defn, str):
        try:
            defn = json.loads(defn)
        except json.JSONDecodeError:
            defn = {}
    return defn if isinstance(defn, dict) else {}


def _read_workspace_file(relative_path: str) -> str:
    root = Path.cwd().resolve()
    target = (root / relative_path).resolve()
    if target == root or root not in target.parents:
        raise ValueError("skill_path must point to a file inside the workspace")
    if target.name != "SKILL.md":
        raise ValueError("skill_path must point to a SKILL.md file")
    return target.read_text(encoding="utf-8")


def _resolve_template(template: str, values: dict[str, Any]) -> str:
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        value: Any = values
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part, "")
            else:
                value = ""
                break
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return re.sub(r"\{([a-zA-Z_][\w.]*)\}", _replace, template)
