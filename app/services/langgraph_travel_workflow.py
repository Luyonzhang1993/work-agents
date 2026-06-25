import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any, TypedDict

from app.schemas.workflow import (
    TravelWorkflowRunRequest,
    WorkflowDefinitionResponse,
    WorkflowEvent,
    WorkflowRunResponse,
    WorkflowStepDefinition,
    WorkflowStepResult,
)
from app.services.observability import get_observability_client

TRAVEL_PLANNER_WORKFLOW_ID = "langgraph_travel_planner"


TRAVEL_PLANNER_STEPS = [
    WorkflowStepDefinition(id="start", name="开始", type="start"),
    WorkflowStepDefinition(
        id="collect_preferences",
        name="整理偏好",
        type="langgraph_node",
        tool="langgraph:collect_preferences",
    ),
    WorkflowStepDefinition(
        id="budget_options",
        name="预算优先方案",
        type="langgraph_branch",
        tool="langgraph:budget_options",
    ),
    WorkflowStepDefinition(
        id="comfort_options",
        name="舒适均衡方案",
        type="langgraph_branch",
        tool="langgraph:comfort_options",
    ),
    WorkflowStepDefinition(
        id="premium_options",
        name="高品质方案",
        type="langgraph_branch",
        tool="langgraph:premium_options",
    ),
    WorkflowStepDefinition(
        id="build_day_plan",
        name="生成每日行程",
        type="langgraph_node",
        tool="langgraph:build_day_plan",
    ),
    WorkflowStepDefinition(
        id="risk_check",
        name="检查节奏和风险",
        type="langgraph_node",
        tool="langgraph:risk_check",
    ),
    WorkflowStepDefinition(
        id="synthesize",
        name="汇总最终方案",
        type="langgraph_node",
        tool="langgraph:synthesize",
    ),
    WorkflowStepDefinition(id="end", name="结束", type="end"),
]


STEP_NAMES = {step.id: step.name for step in TRAVEL_PLANNER_STEPS}


class TravelWorkflowState(TypedDict, total=False):
    destination: str
    duration_days: int
    budget_level: str
    traveler_type: str
    interests: list[str]
    preferences: dict[str, Any]
    branch: str
    budget_strategy: dict[str, Any]
    itinerary: list[dict[str, Any]]
    risk_notes: list[str]
    report: str


class LangGraphTravelWorkflowService:
    def __init__(self) -> None:
        self.observability = get_observability_client()

    def definition(self) -> WorkflowDefinitionResponse:
        return WorkflowDefinitionResponse(
            id=TRAVEL_PLANNER_WORKFLOW_ID,
            name="LangGraph 旅行规划工作流",
            description=(
                "用 LangGraph StateGraph 演示状态传递、条件分支、节点事件和"
                "最终答案流式输出。该 demo 使用本地模拟数据，不依赖外部旅游 API。"
            ),
            steps=TRAVEL_PLANNER_STEPS,
        )

    async def run(
        self,
        request: TravelWorkflowRunRequest,
    ) -> WorkflowRunResponse:
        with self.observability.start_span(
            "workflow.langgraph_travel_planner.run",
            input=request.model_dump(),
            metadata={"workflow_id": TRAVEL_PLANNER_WORKFLOW_ID},
        ) as observation:
            try:
                response = await self._run(request)
                observation.update(output=response.model_dump())
                return response
            except Exception as exc:
                observation.record_exception(exc)
                raise

    async def _run(
        self,
        request: TravelWorkflowRunRequest,
    ) -> WorkflowRunResponse:
        steps: list[WorkflowStepResult] = [
            self._step_result(
                "start",
                {
                    "destination": request.destination,
                    "duration_days": request.duration_days,
                    "budget_level": request.budget_level,
                },
            )
        ]
        final_state: TravelWorkflowState | None = None
        try:
            async for event in self.stream(request):
                if event.type == "workflow.step.completed":
                    steps.append(
                        self._step_result(
                            str(event.data["step_id"]),
                            event.data.get("output", {}),
                        )
                    )
                elif event.type == "workflow.completed":
                    final_state = event.data.get("state", {})
        except Exception as exc:
            steps.append(
                self._step_result(
                    "langgraph_runtime",
                    {
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    },
                    status="failed",
                )
            )
            return WorkflowRunResponse(
                workflow_id=TRAVEL_PLANNER_WORKFLOW_ID,
                status="failed",
                steps=steps,
                report="",
                error={
                    "step_id": "langgraph_runtime",
                    "step_name": "LangGraph runtime",
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
            )

        steps.append(self._step_result("end", {"destination": request.destination}))
        return WorkflowRunResponse(
            workflow_id=TRAVEL_PLANNER_WORKFLOW_ID,
            status="completed",
            steps=steps,
            report=(final_state or {}).get("report", ""),
        )

    async def stream(
        self,
        request: TravelWorkflowRunRequest,
    ) -> AsyncIterator[WorkflowEvent]:
        with self.observability.start_span(
            "workflow.langgraph_travel_planner.stream",
            input=request.model_dump(),
            metadata={"workflow_id": TRAVEL_PLANNER_WORKFLOW_ID},
        ) as observation:
            try:
                async for event in self._stream(request):
                    if event.type == "workflow.completed":
                        observation.update(output=event.data)
                    yield event
            except Exception as exc:
                observation.record_exception(exc)
                raise

    async def _stream(
        self,
        request: TravelWorkflowRunRequest,
    ) -> AsyncIterator[WorkflowEvent]:
        graph = self._compile_graph()
        state: TravelWorkflowState = {
            "destination": request.destination.strip(),
            "duration_days": request.duration_days,
            "budget_level": request.budget_level,
            "traveler_type": request.traveler_type.strip(),
            "interests": request.interests,
        }
        final_state: TravelWorkflowState = {}
        sequence = 0

        yield self._event(
            "workflow.started",
            sequence,
            {
                "workflow_id": TRAVEL_PLANNER_WORKFLOW_ID,
                "input": state,
            },
        )
        sequence += 1

        async for mode, chunk in self._astream_graph(graph, state):
            if mode == "custom":
                yield self._event(
                    str(chunk.get("type", "workflow.event")),
                    sequence,
                    chunk.get("data", {}),
                )
                sequence += 1
                continue

            if mode != "updates" or not isinstance(chunk, dict):
                continue

            for node_id, output in chunk.items():
                if not isinstance(output, dict):
                    output = {"value": output}
                final_state.update(output)
                yield self._event(
                    "workflow.step.completed",
                    sequence,
                    {
                        "step_id": node_id,
                        "name": STEP_NAMES.get(node_id, node_id),
                        "output": output,
                    },
                )
                sequence += 1

        report = final_state.get("report", "")
        for token in self._split_stream_text(report):
            yield self._event(
                "assistant.message.delta",
                sequence,
                {"content": token},
            )
            sequence += 1
            await asyncio.sleep(0.015)

        yield self._event(
            "assistant.message.completed",
            sequence,
            {"content": report},
        )
        sequence += 1
        yield self._event(
            "workflow.completed",
            sequence,
            {
                "workflow_id": TRAVEL_PLANNER_WORKFLOW_ID,
                "state": final_state,
            },
        )

    def _compile_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError(
                "LangGraph is not installed. Run `make install` or install "
                "`langgraph>=0.2.60` before using the travel planner demo."
            ) from exc

        graph = StateGraph(TravelWorkflowState)
        graph.add_node("collect_preferences", self._collect_preferences)
        graph.add_node("budget_options", self._budget_options)
        graph.add_node("comfort_options", self._comfort_options)
        graph.add_node("premium_options", self._premium_options)
        graph.add_node("build_day_plan", self._build_day_plan)
        graph.add_node("risk_check", self._risk_check)
        graph.add_node("synthesize", self._synthesize)

        graph.add_edge(START, "collect_preferences")
        graph.add_conditional_edges(
            "collect_preferences",
            self._route_budget,
            {
                "budget": "budget_options",
                "comfort": "comfort_options",
                "premium": "premium_options",
            },
        )
        graph.add_edge("budget_options", "build_day_plan")
        graph.add_edge("comfort_options", "build_day_plan")
        graph.add_edge("premium_options", "build_day_plan")
        graph.add_edge("build_day_plan", "risk_check")
        graph.add_edge("risk_check", "synthesize")
        graph.add_edge("synthesize", END)
        return graph.compile()

    async def _astream_graph(
        self,
        graph: Any,
        state: TravelWorkflowState,
    ) -> AsyncIterator[tuple[str, Any]]:
        async for item in graph.astream(
            state,
            stream_mode=["custom", "updates"],
        ):
            if isinstance(item, tuple) and len(item) == 2:
                yield item
            else:
                yield "updates", item

    async def _collect_preferences(
        self,
        state: TravelWorkflowState,
    ) -> dict[str, Any]:
        self._write_custom(
            "workflow.step.started",
            "collect_preferences",
            "整理偏好",
            "正在把用户输入归一化成 workflow state。",
        )
        interests = state.get("interests") or ["city_walk", "local_food"]
        preferences = {
            "destination": state["destination"],
            "days": state["duration_days"],
            "traveler_type": state["traveler_type"],
            "interests": interests,
            "pace": "relaxed" if state["duration_days"] <= 3 else "balanced",
        }
        return {"preferences": preferences}

    async def _budget_options(self, state: TravelWorkflowState) -> dict[str, Any]:
        self._write_custom(
            "workflow.step.started",
            "budget_options",
            "预算优先方案",
            "预算分支被选中，优先考虑公共交通和高性价比住宿。",
        )
        return {
            "branch": "budget",
            "budget_strategy": {
                "lodging": "地铁沿线经济型酒店或民宿",
                "transport": "公共交通 + 步行",
                "dining": "本地小店、市场、轻量正餐",
            },
        }

    async def _comfort_options(self, state: TravelWorkflowState) -> dict[str, Any]:
        self._write_custom(
            "workflow.step.started",
            "comfort_options",
            "舒适均衡方案",
            "舒适分支被选中，平衡体验、交通时间和预算。",
        )
        return {
            "branch": "comfort",
            "budget_strategy": {
                "lodging": "核心区域四星或精品酒店",
                "transport": "公共交通为主，晚间或跨区使用网约车",
                "dining": "特色餐厅 + 咖啡馆 + 少量排队名店",
            },
        }

    async def _premium_options(self, state: TravelWorkflowState) -> dict[str, Any]:
        self._write_custom(
            "workflow.step.started",
            "premium_options",
            "高品质方案",
            "高品质分支被选中，优先减少排队和路上消耗。",
        )
        return {
            "branch": "premium",
            "budget_strategy": {
                "lodging": "景观酒店或高端度假酒店",
                "transport": "专车/包车 + 少量步行",
                "dining": "预约制餐厅、主厨菜单或私房体验",
            },
        }

    async def _build_day_plan(self, state: TravelWorkflowState) -> dict[str, Any]:
        self._write_custom(
            "workflow.step.started",
            "build_day_plan",
            "生成每日行程",
            "正在根据预算分支和兴趣生成 day-by-day itinerary。",
        )
        interests = state.get("preferences", {}).get("interests", [])
        itinerary = [
            {
                "day": day,
                "morning": self._pick_activity(day, interests, "morning"),
                "afternoon": self._pick_activity(day, interests, "afternoon"),
                "evening": self._pick_activity(day, interests, "evening"),
            }
            for day in range(1, state["duration_days"] + 1)
        ]
        return {"itinerary": itinerary}

    async def _risk_check(self, state: TravelWorkflowState) -> dict[str, Any]:
        self._write_custom(
            "workflow.step.started",
            "risk_check",
            "检查节奏和风险",
            "正在检查行程密度、天气缓冲和预约风险。",
        )
        notes = [
            "每天保留至少 1 个可替换时段，避免天气或排队影响整天体验。",
            "热门餐厅和展馆建议提前预约。",
        ]
        if state["duration_days"] <= 2:
            notes.append("天数较短，建议少换住宿区域，把路线集中在 1-2 个片区。")
        if state.get("branch") == "budget":
            notes.append("预算优先方案需要额外关注末班车时间。")
        return {"risk_notes": notes}

    async def _synthesize(self, state: TravelWorkflowState) -> dict[str, Any]:
        self._write_custom(
            "workflow.step.started",
            "synthesize",
            "汇总最终方案",
            "正在把各节点 state 汇总成可展示的最终回答。",
        )
        preferences = state["preferences"]
        strategy = state["budget_strategy"]
        itinerary_lines = []
        for item in state["itinerary"]:
            itinerary_lines.append(
                f"Day {item['day']}: 上午 {item['morning']}；"
                f"下午 {item['afternoon']}；晚上 {item['evening']}。"
            )
        report = (
            f"{preferences['destination']} {preferences['days']} 天旅行规划\n\n"
            f"适合人群：{preferences['traveler_type']}\n"
            f"节奏：{preferences['pace']}\n"
            f"预算策略：住宿选择 {strategy['lodging']}，交通采用 "
            f"{strategy['transport']}，餐饮建议 {strategy['dining']}。\n\n"
            "每日安排：\n"
            + "\n".join(itinerary_lines)
            + "\n\n注意事项：\n"
            + "\n".join(f"- {note}" for note in state["risk_notes"])
        )
        return {"report": report}

    def _route_budget(self, state: TravelWorkflowState) -> str:
        budget_level = state.get("budget_level", "comfort")
        if budget_level in {"budget", "premium"}:
            return budget_level
        return "comfort"

    def _write_custom(
        self,
        event_type: str,
        step_id: str,
        name: str,
        message: str,
    ) -> None:
        try:
            from langgraph.config import get_stream_writer
        except ImportError:
            return

        writer = get_stream_writer()
        writer(
            {
                "type": event_type,
                "data": {
                    "step_id": step_id,
                    "name": name,
                    "message": message,
                },
            }
        )

    def _pick_activity(self, day: int, interests: list[str], slot: str) -> str:
        fallback = {
            "morning": "城市经典地标和轻量步行",
            "afternoon": "博物馆、街区或在地体验",
            "evening": "夜景、夜市或特色餐厅",
        }
        activity_map = {
            "local_food": {
                "morning": "本地早餐和市场闲逛",
                "afternoon": "老街小吃和咖啡休息",
                "evening": "特色餐厅或夜市",
            },
            "culture": {
                "morning": "博物馆或历史街区",
                "afternoon": "展览、书店或非遗体验",
                "evening": "剧场、演出或文化夜游",
            },
            "nature": {
                "morning": "公园、湖边或山景路线",
                "afternoon": "轻徒步或自然景观",
                "evening": "安静河岸散步",
            },
            "city_walk": {
                "morning": "核心街区 city walk",
                "afternoon": "特色社区和独立小店",
                "evening": "城市夜景路线",
            },
        }
        if not interests:
            return fallback[slot]
        interest = interests[(day - 1) % len(interests)]
        return activity_map.get(interest, fallback).get(slot, fallback[slot])

    def _split_stream_text(self, text: str) -> list[str]:
        # Split by sentence boundaries first, then chunk by size
        parts = re.split(r"(?<=[。！？\n.!?])\s*", text)
        chunks: list[str] = []
        for part in parts:
            if not part:
                continue
            for i in range(0, len(part), 40):
                chunks.append(part[i : i + 40])
        return chunks if chunks else [text]

    def _event(
        self,
        event_type: str,
        sequence: int,
        data: dict[str, Any],
    ) -> WorkflowEvent:
        return WorkflowEvent(
            type=event_type,
            data={
                "sequence": sequence,
                **data,
            },
        )

    def failed_event(self, exc: Exception) -> WorkflowEvent:
        return self._event(
            "workflow.failed",
            -1,
            {
                "workflow_id": TRAVEL_PLANNER_WORKFLOW_ID,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            },
        )

    def _step_result(
        self,
        step_id: str,
        output: dict[str, Any],
        status: str = "completed",
    ) -> WorkflowStepResult:
        return WorkflowStepResult(
            id=step_id,
            name=STEP_NAMES.get(step_id, step_id),
            status=status,
            output=output,
        )


def event_to_sse(event: WorkflowEvent) -> str:
    payload = json.dumps(event.model_dump(), ensure_ascii=False)
    return f"event: {event.type}\ndata: {payload}\n\n"


def get_langgraph_travel_workflow_service() -> LangGraphTravelWorkflowService:
    return LangGraphTravelWorkflowService()
