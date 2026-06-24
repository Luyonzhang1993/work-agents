import json
from typing import Any, TypedDict

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowStepDefinition,
    WorkflowStepResult,
)
from app.services.mcp_registry import MCPRegistry, get_mcp_registry
from app.services.openai_client import build_openai_client


FINANCE_REPORT_WORKFLOW_ID = "finance_company_report"
MAX_MCP_RESULT_CHARS = 4000


MARKETDATA_MCP_TOOLS = {
    "company_profile": "mcp:marketdata:company_profile",
    "quote_snapshot": "mcp:marketdata:quote_snapshot",
    "price_history": "mcp:marketdata:price_history",
    "financial_summary": "mcp:marketdata:financial_summary",
    "company_news": "mcp:marketdata:company_news",
}


FINANCE_REPORT_STEPS = [
    WorkflowStepDefinition(id="start", name="开始", type="start"),
    WorkflowStepDefinition(
        id="get_company_info",
        name="获取公司信息",
        type="langgraph_node",
        tool="langgraph:get_company_info",
    ),
    WorkflowStepDefinition(
        id="get_company_news",
        name="获取新闻",
        type="langgraph_node",
        tool="langgraph:get_company_news",
    ),
    WorkflowStepDefinition(
        id="get_financial_data",
        name="获取财务数据",
        type="langgraph_node",
        tool="langgraph:get_financial_data",
    ),
    WorkflowStepDefinition(
        id="generate_report",
        name="生成报告",
        type="langgraph_node",
        tool="langgraph:generate_report",
    ),
    WorkflowStepDefinition(id="end", name="结束", type="end"),
]


PUBLIC_FINANCE_STEP_NAMES = {step.id: step.name for step in FINANCE_REPORT_STEPS}


class FinanceReportWorkflowState(TypedDict, total=False):
    symbol: str
    company_info: dict[str, Any]
    company_news: dict[str, Any]
    financial_data: dict[str, Any]
    company_info_error: dict[str, Any]
    company_news_error: dict[str, Any]
    financial_data_error: dict[str, Any]
    research_failed: bool
    report: str
    report_error: dict[str, Any]


class WorkflowService:
    def __init__(
        self,
        llm_client: AsyncOpenAI | None = None,
        mcp_registry: MCPRegistry | None = None,
    ) -> None:
        self.settings = get_settings()
        self.llm_client = llm_client
        self.mcp_registry = mcp_registry or get_mcp_registry()

    def finance_report_definition(self) -> WorkflowDefinitionResponse:
        return WorkflowDefinitionResponse(
            id=FINANCE_REPORT_WORKFLOW_ID,
            name="金融公司报告工作流",
            description=(
                "使用 LangGraph 并行执行公司信息、新闻、财务数据节点，"
                "再由 LLM 基于节点输出生成最终报告。"
            ),
            steps=FINANCE_REPORT_STEPS,
        )

    async def run_finance_report(
        self,
        request: WorkflowRunRequest,
    ) -> WorkflowRunResponse:
        symbol = request.symbol.upper()
        step_results: list[WorkflowStepResult] = []
        final_state: FinanceReportWorkflowState = {}

        try:
            async for chunk in self._compile_finance_report_graph().astream(
                {"symbol": symbol},
                stream_mode="updates",
            ):
                if not isinstance(chunk, dict):
                    continue
                for node_id, output in chunk.items():
                    if isinstance(output, dict):
                        final_state.update(output)
                    self._append_finance_step_result(step_results, node_id, output)
        except Exception as exc:
            step_results.append(
                self._step_result(
                    "langgraph_runtime",
                    "LangGraph runtime",
                    {
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    },
                    status="failed",
                )
            )
            return self._failed_response(step_results)

        if self._has_finance_failure(step_results):
            return self._failed_response(step_results)

        step_results.append(self._step_result("end", "结束", {"symbol": symbol}))

        return WorkflowRunResponse(
            workflow_id=FINANCE_REPORT_WORKFLOW_ID,
            status="completed",
            steps=step_results,
            report=str(final_state.get("report", "")),
        )

    def _compile_finance_report_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError(
                "LangGraph is not installed. Run `make install` or install "
                "`langgraph>=0.2.60` before using the finance report workflow."
            ) from exc

        graph = StateGraph(FinanceReportWorkflowState)
        graph.add_node("start", self._finance_start_node)
        graph.add_node("get_company_info", self._company_info_node)
        graph.add_node("get_company_news", self._company_news_node)
        graph.add_node("get_financial_data", self._financial_data_node)
        graph.add_node("check_research", self._check_research_node)
        graph.add_node("generate_report", self._generate_report_node)

        graph.add_edge(START, "start")
        graph.add_edge("start", "get_company_info")
        graph.add_edge("start", "get_company_news")
        graph.add_edge("start", "get_financial_data")
        graph.add_edge(
            ["get_company_info", "get_company_news", "get_financial_data"],
            "check_research",
        )
        graph.add_conditional_edges(
            "check_research",
            self._route_after_research,
            {
                "generate_report": "generate_report",
                "end": END,
            },
        )
        graph.add_edge("generate_report", END)
        return graph.compile()

    async def _finance_start_node(
        self,
        state: FinanceReportWorkflowState,
    ) -> dict[str, Any]:
        return {"symbol": state["symbol"]}

    async def _company_info_node(
        self,
        state: FinanceReportWorkflowState,
    ) -> dict[str, Any]:
        try:
            return {"company_info": await self._get_company_info(state["symbol"])}
        except Exception as exc:
            return {"company_info_error": self._node_error(exc)}

    async def _company_news_node(
        self,
        state: FinanceReportWorkflowState,
    ) -> dict[str, Any]:
        try:
            return {"company_news": await self._get_company_news(state["symbol"])}
        except Exception as exc:
            return {"company_news_error": self._node_error(exc)}

    async def _financial_data_node(
        self,
        state: FinanceReportWorkflowState,
    ) -> dict[str, Any]:
        try:
            return {"financial_data": await self._get_financial_data(state["symbol"])}
        except Exception as exc:
            return {"financial_data_error": self._node_error(exc)}

    async def _check_research_node(
        self,
        state: FinanceReportWorkflowState,
    ) -> dict[str, Any]:
        return {
            "research_failed": any(
                key in state
                for key in (
                    "company_info_error",
                    "company_news_error",
                    "financial_data_error",
                )
            )
        }

    async def _generate_report_node(
        self,
        state: FinanceReportWorkflowState,
    ) -> dict[str, Any]:
        try:
            return await self._generate_report(
                state["symbol"],
                state["company_info"],
                state["company_news"],
                state["financial_data"],
            )
        except Exception as exc:
            return {"report_error": self._node_error(exc)}

    def _route_after_research(self, state: FinanceReportWorkflowState) -> str:
        if state.get("research_failed"):
            return "end"
        return "generate_report"

    async def _get_company_info(self, symbol: str) -> dict[str, Any]:
        return await self._complete_json_with_marketdata(
            symbol=symbol,
            tool_names=["company_profile", "quote_snapshot"],
            system_prompt=(
                "You are a finance research assistant. Return only valid JSON. "
                "Do not fabricate precise facts; if uncertain, use null and add "
                "a short caveat. Prefer the provided market data MCP context "
                "when available."
            ),
            user_prompt=(
                f"获取股票代码 {symbol} 对应公司的基础信息。"
                "返回字段：symbol, company_name, exchange, industry, sector, "
                "headquarters, website, business_summary, data_sources, caveats。"
            ),
        )

    async def _get_company_news(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        return await self._complete_json_with_marketdata(
            symbol=symbol,
            tool_names=["company_news", "quote_snapshot"],
            system_prompt=(
                "You are a finance news analyst. Return only valid JSON. "
                "Do not invent source URLs or exact timestamps. If you cannot "
                "verify freshness, say so in caveats. Prefer the provided "
                "market data MCP context when available."
            ),
            user_prompt=(
                f"基于公司代码 {symbol}，"
                "独立整理重要新闻或市场动态。"
                "返回字段：symbol, news_items, sentiment, key_themes, "
                "data_sources, caveats。\n"
            ),
        )

    async def _get_financial_data(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        return await self._complete_json_with_marketdata(
            symbol=symbol,
            tool_names=["financial_summary", "price_history", "quote_snapshot"],
            system_prompt=(
                "You are a finance fundamentals analyst. Return only valid JSON. "
                "Do not fabricate exact financial numbers; if data is unavailable "
                "or stale, use null and explain in caveats. Prefer the provided "
                "market data MCP context when available."
            ),
            user_prompt=(
                f"基于公司代码 {symbol}，"
                "独立整理可用于报告的财务数据和指标。"
                "返回字段：symbol, period, currency, revenue, gross_margin, "
                "operating_income, net_income, eps, cash_flow, balance_sheet, "
                "financial_highlights, data_sources, caveats。"
            ),
        )

    async def _generate_report(
        self,
        symbol: str,
        company_info: dict[str, Any],
        company_news: dict[str, Any],
        financial_data: dict[str, Any],
    ) -> dict[str, Any]:
        report = await self._complete_text_with_marketdata(
            symbol=symbol,
            tool_names=[
                "company_profile",
                "financial_summary",
                "company_news",
                "price_history",
            ],
            system_prompt=(
                "You are an equity research report writer. Generate the final "
                "report directly from the workflow node outputs. Do not use a "
                "fixed template; choose the structure that best explains the "
                "company, news context, financial picture, risks, and caveats. "
                "Use the provided market data MCP context when it helps verify "
                "or enrich the report."
            ),
            user_prompt=(
                f"请为 {symbol} 生成一份中文金融分析报告。\n"
                f"公司信息：{json.dumps(company_info, ensure_ascii=False)}\n"
                f"新闻信息：{json.dumps(company_news, ensure_ascii=False)}\n"
                f"财务数据：{json.dumps(financial_data, ensure_ascii=False)}"
            ),
        )
        return {"report": report}

    async def _complete_json_with_marketdata(
        self,
        symbol: str,
        tool_names: list[str],
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        mcp_context = await self._marketdata_mcp_context(symbol, tool_names)
        return await self._complete_json(
            system_prompt=self._with_marketdata_system_prompt(system_prompt),
            user_prompt=self._with_marketdata_user_prompt(user_prompt, mcp_context),
        )

    async def _complete_text_with_marketdata(
        self,
        symbol: str,
        tool_names: list[str],
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        mcp_context = await self._marketdata_mcp_context(symbol, tool_names)
        return await self._complete_text(
            system_prompt=self._with_marketdata_system_prompt(system_prompt),
            user_prompt=self._with_marketdata_user_prompt(user_prompt, mcp_context),
        )

    async def _marketdata_mcp_context(
        self,
        symbol: str,
        tool_names: list[str],
    ) -> list[dict[str, Any]]:
        if "marketdata" not in self.mcp_registry.services:
            return [
                {
                    "status": "skipped",
                    "reason": "Marketdata MCP service is not configured.",
                }
            ]

        evidence: list[dict[str, Any]] = []
        for tool_name in tool_names:
            evidence.append(
                await self._call_marketdata_tool(
                    tool_name,
                    self._marketdata_tool_arguments(symbol, tool_name),
                )
            )
        return evidence

    def _marketdata_tool_arguments(
        self,
        symbol: str,
        tool_name: str,
    ) -> dict[str, Any]:
        if tool_name == "company_news":
            return {"symbol": symbol, "count": 5}
        if tool_name == "price_history":
            return {"symbol": symbol, "range": "1mo", "interval": "1d"}
        if tool_name == "quote_snapshot":
            return {"symbol": symbol, "range": "5d", "interval": "1d"}
        return {"symbol": symbol}

    async def _call_marketdata_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        tool_id = MARKETDATA_MCP_TOOLS.get(tool_name)
        if tool_id is None:
            return {"tool": tool_name, "error": "Unknown marketdata MCP tool."}

        try:
            result = await self.mcp_registry.call_tool(tool_id, arguments)
            return {
                "tool_name": tool_name,
                "tool": tool_id,
                "arguments": arguments,
                "result": self._compact_mcp_result(
                    self._extract_mcp_text_result(result)
                ),
            }
        except Exception as exc:
            return {
                "tool_name": tool_name,
                "tool": tool_id,
                "arguments": arguments,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            }

    def _extract_mcp_text_result(self, result: dict[str, Any]) -> dict[str, Any]:
        content = result.get("content") or []
        if not content:
            return result
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if not isinstance(text, str):
            return result
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
        return parsed if isinstance(parsed, dict) else {}

    def _compact_mcp_result(self, result: dict[str, Any]) -> dict[str, Any]:
        compacted = json.dumps(result, ensure_ascii=False)
        if len(compacted) <= MAX_MCP_RESULT_CHARS:
            return result
        return {
            "truncated": True,
            "preview": compacted[:MAX_MCP_RESULT_CHARS],
        }

    def _with_marketdata_system_prompt(self, system_prompt: str) -> str:
        return (
            f"{system_prompt} Use the provided market data MCP results as "
            "evidence when relevant. If tool results are missing, failed, or "
            "insufficient, say so in caveats instead of fabricating."
        )

    def _with_marketdata_user_prompt(
        self,
        user_prompt: str,
        mcp_context: list[dict[str, Any]],
    ) -> str:
        return (
            f"{user_prompt}\n\n"
            "Market data MCP results available to this node:\n"
            f"{json.dumps(mcp_context, ensure_ascii=False)}"
        )

    def _append_finance_step_result(
        self,
        step_results: list[WorkflowStepResult],
        node_id: str,
        output: Any,
    ) -> None:
        if not isinstance(output, dict):
            output = {"value": output}

        if node_id == "start":
            step_results.append(
                self._step_result(
                    "start",
                    PUBLIC_FINANCE_STEP_NAMES["start"],
                    {"symbol": output.get("symbol")},
                )
            )
            return

        if node_id == "get_company_info":
            self._append_finance_research_step(
                step_results,
                "get_company_info",
                output,
                "company_info",
                "company_info_error",
            )
            return

        if node_id == "get_company_news":
            self._append_finance_research_step(
                step_results,
                "get_company_news",
                output,
                "company_news",
                "company_news_error",
            )
            return

        if node_id == "get_financial_data":
            self._append_finance_research_step(
                step_results,
                "get_financial_data",
                output,
                "financial_data",
                "financial_data_error",
            )
            return

        if node_id == "generate_report":
            if "report_error" in output:
                step_results.append(
                    self._step_result(
                        "generate_report",
                        PUBLIC_FINANCE_STEP_NAMES["generate_report"],
                        output["report_error"],
                        status="failed",
                    )
                )
            else:
                step_results.append(
                    self._step_result(
                        "generate_report",
                        PUBLIC_FINANCE_STEP_NAMES["generate_report"],
                        {"report": output.get("report", "")},
                    )
                )

    def _append_finance_research_step(
        self,
        step_results: list[WorkflowStepResult],
        step_id: str,
        output: dict[str, Any],
        success_key: str,
        error_key: str,
    ) -> None:
        if error_key in output:
            step_results.append(
                self._step_result(
                    step_id,
                    PUBLIC_FINANCE_STEP_NAMES[step_id],
                    output[error_key],
                    status="failed",
                )
            )
            return

        step_results.append(
            self._step_result(
                step_id,
                PUBLIC_FINANCE_STEP_NAMES[step_id],
                output.get(success_key, {}),
            )
        )

    def _node_error(self, exc: Exception) -> dict[str, Any]:
        return {
            "error": str(exc),
            "error_type": exc.__class__.__name__,
        }

    def _has_finance_failure(self, step_results: list[WorkflowStepResult]) -> bool:
        return any(step.status == "failed" for step in step_results)

    def _failed_response(
        self,
        step_results: list[WorkflowStepResult],
    ) -> WorkflowRunResponse:
        failed_step = next(
            (step for step in step_results if step.status == "failed"),
            None,
        )
        error = None
        if failed_step is not None:
            error = {
                "step_id": failed_step.id,
                "step_name": failed_step.name,
                **failed_step.output,
            }

        return WorkflowRunResponse(
            workflow_id=FINANCE_REPORT_WORKFLOW_ID,
            status="failed",
            steps=step_results,
            report="",
            error=error,
        )

    async def _complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        content = await self._complete_text(system_prompt, user_prompt, temperature=0)
        return self._loads_json_object(content)

    async def _complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        client = self._client()
        response = await client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=(
                self.settings.llm_temperature
                if temperature is None
                else temperature
            ),
            timeout=60,
        )
        return response.choices[0].message.content or ""

    def _client(self) -> AsyncOpenAI:
        if self.llm_client is None:
            self.llm_client = build_openai_client(self.settings)
        return self.llm_client

    def _loads_json_object(self, content: str) -> dict[str, Any]:
        cleaned_content = content.strip()
        if cleaned_content.startswith("```"):
            cleaned_content = cleaned_content.strip("`")
            if cleaned_content.lower().startswith("json"):
                cleaned_content = cleaned_content[4:]
            cleaned_content = cleaned_content.strip()

        try:
            data = json.loads(cleaned_content)
        except json.JSONDecodeError:
            data = self._first_json_object(cleaned_content)

        if not isinstance(data, dict):
            raise ValueError("LLM response did not contain a JSON object")
        return data

    def _first_json_object(self, content: str) -> dict[str, Any] | None:
        start = content.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(content)):
            character = content[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue

            if character == '"':
                in_string = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(content[start : index + 1])
                    except json.JSONDecodeError:
                        return None
                    return data if isinstance(data, dict) else None
        return None

    def _step_result(
        self,
        step_id: str,
        name: str,
        output: dict[str, Any],
        status: str = "completed",
    ) -> WorkflowStepResult:
        return WorkflowStepResult(
            id=step_id,
            name=name,
            status=status,
            output=output,
        )


def get_workflow_service() -> WorkflowService:
    return WorkflowService()
