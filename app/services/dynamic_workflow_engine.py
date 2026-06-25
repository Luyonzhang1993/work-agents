"""Dynamic workflow engine — executes declarative workflow definitions.

A definition is a JSON document with:
  - parameters: input schema (optional)
  - steps: list of nodes (llm_call, mcp_tool, pass_through)
  - edges: list of {"from": "...", "to": "..."} defining the graph

Each step is executed as a LangGraph node. The state dict is shared
across steps so later steps can reference outputs of earlier ones via
{step_id} template placeholders in prompts.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
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
from app.services.mcp_registry import MCPRegistry, get_mcp_registry
from app.services.observability import get_observability_client
from app.services.openai_client import build_openai_client

logger = logging.getLogger(__name__)

_STEP_TYPE_LABELS: dict[str, str] = {
    "llm_call": "LLM调用",
    "mcp_tool": "MCP工具",
    "pass_through": "数据处理",
}


def _split_stream_text(text: str, chunk_size: int = 40) -> list[str]:
    parts = re.split(r"(?<=[。！？\n.!?])\s*", text)
    chunks: list[str] = []
    for part in parts:
        if not part:
            continue
        for i in range(0, len(part), chunk_size):
            chunks.append(part[i : i + chunk_size])
    return chunks if chunks else [text]


def _resolve_template(template: str, state: dict[str, Any]) -> str:
    """Replace {key} placeholders with state values."""
    # Support nested keys like {step1.result.field}
    def _replace(m: re.Match) -> str:
        key = m.group(1)
        value = state
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


class DynamicWorkflowEngine:
    """Execute a declarative workflow definition."""

    def __init__(
        self,
        llm_client: AsyncOpenAI | None = None,
        mcp_registry: MCPRegistry | None = None,
    ) -> None:
        self.settings = get_settings()
        self.llm_client = llm_client
        self.mcp_registry = mcp_registry or get_mcp_registry()
        self.observability = get_observability_client()

    def definition_to_steps(
        self,
        workflow_id: str,
        name: str,
        description: str,
        definition: dict[str, Any],
    ) -> WorkflowDefinitionResponse:
        """Build a WorkflowDefinitionResponse from a declarative definition."""
        steps_def = definition.get("steps") or []
        steps = [
            WorkflowStepDefinition(id="start", name="开始", type="start"),
        ]
        for s in steps_def:
            sid = s.get("id", "")
            sname = s.get("name", sid)
            stype = s.get("type", "llm_call")
            steps.append(
                WorkflowStepDefinition(
                    id=sid,
                    name=sname,
                    type=_STEP_TYPE_LABELS.get(stype, stype),
                    tool=f"dynamic:{stype}",
                )
            )
        steps.append(WorkflowStepDefinition(id="end", name="结束", type="end"))
        return WorkflowDefinitionResponse(
            id=workflow_id,
            name=name,
            description=description,
            steps=steps,
        )

    async def run(
        self,
        workflow_id: str,
        workflow_name: str,
        definition: dict[str, Any],
        arguments: dict[str, Any],
    ) -> WorkflowRunResponse:
        """Execute synchronously, returning the final result."""
        step_results: list[WorkflowStepResult] = []
        final_state: dict[str, Any] = {}
        async for event in self.stream(
            workflow_id, workflow_name, definition, arguments
        ):
            if event.type == "workflow.step.completed":
                sid = str(event.data.get("step_id", ""))
                sname = str(event.data.get("name", ""))
                output = event.data.get("output", {})
                step_results.append(
                    WorkflowStepResult(
                        id=sid,
                        name=sname,
                        status="completed",
                        output=output if isinstance(output, dict) else {"value": output},
                    )
                )
                if isinstance(output, dict):
                    final_state.update(output)
            elif event.type == "workflow.failed":
                step_results.append(
                    WorkflowStepResult(
                        id="runtime",
                        name="执行失败",
                        status="failed",
                        output={"error": event.data.get("error", "")},
                    )
                )
                return WorkflowRunResponse(
                    workflow_id=workflow_id,
                    status="failed",
                    steps=step_results,
                    report="",
                    error={"error": event.data.get("error", "")},
                )

        report = str(final_state.get("_report", ""))
        return WorkflowRunResponse(
            workflow_id=workflow_id,
            status="completed",
            steps=step_results,
            report=report,
        )

    async def stream(
        self,
        workflow_id: str,
        workflow_name: str,
        definition: dict[str, Any],
        arguments: dict[str, Any],
    ) -> AsyncIterator[WorkflowEvent]:
        """Execute and yield streaming events."""
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

        steps: list[dict[str, Any]] = definition.get("steps") or []
        edges: list[dict[str, str]] = definition.get("edges") or []

        # If no edges defined, create a linear chain
        if not edges:
            prev = "start"
            for i, s in enumerate(steps):
                sid = s.get("id", f"step_{i}")
                edges.append({"from": prev, "to": sid})
                prev = sid
            edges.append({"from": prev, "to": "end"})

        # Build adjacency
        successors: dict[str, list[str]] = {}
        for e in edges:
            f = e["from"]
            t = e["to"]
            successors.setdefault(f, []).append(t)

        # Step lookup
        step_map: dict[str, dict[str, Any]] = {s["id"]: s for s in steps if s.get("id")}

        # Initial state = arguments
        state: dict[str, Any] = dict(arguments)

        # Topological execution via BFS
        queue: list[str] = successors.get("start", [])
        visited: set[str] = set()

        while queue:
            node_id = queue.pop(0)
            if node_id == "end":
                continue
            if node_id in visited:
                continue
            visited.add(node_id)

            step = step_map.get(node_id)
            if step is None:
                logger.warning("Unknown step '%s' in graph", node_id)
                continue

            step_name = step.get("name", node_id)
            step_type = step.get("type", "llm_call")

            yield WorkflowEvent(
                type="workflow.step.started",
                data={
                    "step_id": node_id,
                    "name": step_name,
                    "message": f"正在执行: {step_name}",
                    "sequence": sequence,
                },
            )
            sequence += 1

            try:
                output = await self._execute_step(step, state)
            except Exception as exc:
                yield WorkflowEvent(
                    type="workflow.failed",
                    data={
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                        "step_id": node_id,
                        "sequence": sequence,
                    },
                )
                return

            state[node_id] = output
            yield WorkflowEvent(
                type="workflow.step.completed",
                data={
                    "step_id": node_id,
                    "name": step_name,
                    "output": {node_id: output},
                    "sequence": sequence,
                },
            )
            sequence += 1

            # Enqueue successors
            for succ in successors.get(node_id, []):
                if succ not in visited and succ not in queue:
                    queue.append(succ)

        # Gather final report from the last step or a designated _report key
        report_key = definition.get("report_from", "")
        if report_key and report_key in state:
            report = str(state[report_key])
        else:
            # Collect all text outputs
            parts = []
            for k, v in state.items():
                if isinstance(v, str) and k not in arguments:
                    parts.append(v)
            report = "\n\n".join(parts) if parts else json.dumps(state, ensure_ascii=False, indent=2)

        state["_report"] = report

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
                "state": state,
                "sequence": sequence,
            },
        )

    async def _execute_step(
        self,
        step: dict[str, Any],
        state: dict[str, Any],
    ) -> Any:
        step_type = step.get("type", "llm_call")

        if step_type == "llm_call":
            return await self._execute_llm_call(step, state)
        elif step_type == "mcp_tool":
            return await self._execute_mcp_tool(step, state)
        elif step_type == "pass_through":
            return self._execute_pass_through(step, state)
        else:
            raise ValueError(f"Unknown step type: {step_type}")

    async def _execute_llm_call(
        self,
        step: dict[str, Any],
        state: dict[str, Any],
    ) -> str:
        system_prompt = _resolve_template(step.get("system_prompt", ""), state)
        user_prompt = _resolve_template(step.get("user_prompt", step.get("prompt", "")), state)
        temperature = float(step.get("temperature", self.settings.llm_temperature))

        client = self._client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await client.chat.completions.create(
            model=self.settings.openai_model,
            messages=messages,
            temperature=temperature,
            timeout=120,
        )

        return response.choices[0].message.content or ""

    async def _execute_mcp_tool(
        self,
        step: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = step.get("tool_name", "")
        if not tool_name:
            raise ValueError("mcp_tool step requires 'tool_name'")

        # Resolve arguments from state
        raw_args = step.get("arguments") or {}
        args = {}
        for k, v in raw_args.items():
            if isinstance(v, str):
                args[k] = _resolve_template(v, state)
            else:
                args[k] = v

        tool_id = step.get("tool_id", f"mcp:{tool_name}")
        if ":" not in tool_id:
            tool_id = f"mcp:arithmetic:{tool_name}"

        return await self.mcp_registry.call_tool(tool_id, args)

    def _execute_pass_through(
        self,
        step: dict[str, Any],
        state: dict[str, Any],
    ) -> Any:
        """Return a value from state, optionally transformed."""
        source = step.get("source", "")
        if source and source in state:
            return state[source]
        return step.get("value", {})

    def _client(self) -> AsyncOpenAI:
        if self.llm_client is None:
            self.llm_client = build_openai_client(self.settings)
        return self.llm_client


def get_dynamic_engine() -> DynamicWorkflowEngine:
    return DynamicWorkflowEngine()
