import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowStepDefinition,
    WorkflowStepResult,
)
from app.services.mcp_registry import MCPRegistry, get_mcp_registry


FINANCE_REPORT_WORKFLOW_ID = "finance_company_report"


FINANCE_REPORT_STEPS = [
    WorkflowStepDefinition(id="start", name="开始", type="start"),
    WorkflowStepDefinition(
        id="get_company_info",
        name="获取公司信息",
        type="tool",
        tool="mcp:finance:get_company_info",
    ),
    WorkflowStepDefinition(
        id="get_company_news",
        name="获取新闻",
        type="tool",
        tool="mcp:finance:get_company_news",
    ),
    WorkflowStepDefinition(
        id="get_financial_data",
        name="获取财务数据",
        type="tool",
        tool="mcp:finance:get_financial_data",
    ),
    WorkflowStepDefinition(id="generate_report", name="生成报告", type="task"),
    WorkflowStepDefinition(id="end", name="结束", type="end"),
]


class WorkflowService:
    def __init__(self, mcp_registry: MCPRegistry | None = None) -> None:
        self.mcp_registry = mcp_registry or get_mcp_registry()

    def finance_report_definition(self) -> WorkflowDefinitionResponse:
        return WorkflowDefinitionResponse(
            id=FINANCE_REPORT_WORKFLOW_ID,
            name="金融公司报告工作流",
            description=(
                "按公司信息、新闻、财务数据的顺序获取数据，"
                "并生成一份报告。"
            ),
            steps=FINANCE_REPORT_STEPS,
        )

    async def run_finance_report(
        self,
        request: WorkflowRunRequest,
    ) -> WorkflowRunResponse:
        symbol = request.symbol.upper()
        step_results = [
            self._step_result("start", "开始", {"symbol": symbol}),
        ]

        company_info = await self._run_tool_step(
            step_results,
            step_id="get_company_info",
            name="获取公司信息",
            operation=lambda: self._call_finance_tool(
                "mcp:finance:get_company_info",
                symbol,
            ),
        )
        if company_info is None:
            return self._failed_response(step_results)

        company_news = await self._run_tool_step(
            step_results,
            step_id="get_company_news",
            name="获取新闻",
            operation=lambda: self._call_finance_tool(
                "mcp:finance:get_company_news",
                symbol,
            ),
        )
        if company_news is None:
            return self._failed_response(step_results)

        financial_data = await self._run_tool_step(
            step_results,
            step_id="get_financial_data",
            name="获取财务数据",
            operation=lambda: self._call_finance_tool(
                "mcp:finance:get_financial_data",
                symbol,
            ),
        )
        if financial_data is None:
            return self._failed_response(step_results)

        report = self._generate_report(company_info, company_news, financial_data)
        step_results.append(
            self._step_result(
                "generate_report",
                "生成报告",
                {"report": report},
            )
        )
        step_results.append(self._step_result("end", "结束", {"symbol": symbol}))

        return WorkflowRunResponse(
            workflow_id=FINANCE_REPORT_WORKFLOW_ID,
            status="completed",
            steps=step_results,
            report=report,
        )

    async def _run_tool_step(
        self,
        step_results: list[WorkflowStepResult],
        step_id: str,
        name: str,
        operation: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        try:
            output = await operation()
        except Exception as exc:
            step_results.append(
                self._step_result(
                    step_id,
                    name,
                    {
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    },
                    status="failed",
                )
            )
            return None

        step_results.append(self._step_result(step_id, name, output))
        return output

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

    async def _call_finance_tool(self, tool_id: str, symbol: str) -> dict[str, Any]:
        result = await self.mcp_registry.call_tool(tool_id, {"symbol": symbol})
        return self._parse_mcp_text_result(result)

    def _parse_mcp_text_result(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("isError") is True:
            raise RuntimeError(str(result))

        content = result.get("content")
        if not isinstance(content, list) or not content:
            return result

        first_item = content[0]
        if not isinstance(first_item, dict):
            return result

        text = first_item.get("text")
        if not isinstance(text, str):
            return result

        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    def _generate_report(
        self,
        company_info: dict[str, Any],
        company_news: dict[str, Any],
        financial_data: dict[str, Any],
    ) -> str:
        news_items = company_news.get("news", [])
        top_news = news_items[0] if news_items else {}
        company_name = company_info.get(
            "companyName",
            company_info.get("symbol", "Unknown"),
        )

        return "\n".join(
            [
                f"# {company_name} 公司报告",
                "",
                "## 公司信息",
                f"- 股票代码：{company_info.get('symbol', 'N/A')}",
                f"- 行业：{company_info.get('industry', 'N/A')}",
                f"- CEO：{company_info.get('ceo', 'N/A')}",
                "",
                "## 最新新闻",
                f"- 头条：{top_news.get('title', 'N/A')}",
                f"- 来源：{top_news.get('source', 'N/A')}",
                "",
                "## 财务数据",
                f"- 报告期：{financial_data.get('period', 'N/A')}",
                f"- 营收：{financial_data.get('revenue', 'N/A')} "
                f"{financial_data.get('currency', '')}",
                f"- 净利润：{financial_data.get('netIncome', 'N/A')} "
                f"{financial_data.get('currency', '')}",
                "",
                (
                    "说明：当前报告基于 mock MCP 数据生成，"
                    "仅用于 workflow 验证。"
                ),
            ]
        )

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
