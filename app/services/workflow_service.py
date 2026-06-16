import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowStepDefinition,
    WorkflowStepResult,
)
from app.services.openai_client import build_openai_client


FINANCE_REPORT_WORKFLOW_ID = "finance_company_report"


FINANCE_REPORT_STEPS = [
    WorkflowStepDefinition(id="start", name="开始", type="start"),
    WorkflowStepDefinition(
        id="get_company_info",
        name="获取公司信息",
        type="llm",
        tool="llm:get_company_info",
    ),
    WorkflowStepDefinition(
        id="get_company_news",
        name="获取新闻",
        type="llm",
        tool="llm:get_company_news",
    ),
    WorkflowStepDefinition(
        id="get_financial_data",
        name="获取财务数据",
        type="llm",
        tool="llm:get_financial_data",
    ),
    WorkflowStepDefinition(
        id="generate_report",
        name="生成报告",
        type="llm",
        tool="llm:generate_report",
    ),
    WorkflowStepDefinition(id="end", name="结束", type="end"),
]


class WorkflowService:
    def __init__(self, llm_client: AsyncOpenAI | None = None) -> None:
        self.settings = get_settings()
        self.llm_client = llm_client

    def finance_report_definition(self) -> WorkflowDefinitionResponse:
        return WorkflowDefinitionResponse(
            id=FINANCE_REPORT_WORKFLOW_ID,
            name="金融公司报告工作流",
            description=(
                "按公司信息、新闻、财务数据的顺序让 LLM "
                "获取和整理信息，并由 LLM 生成最终报告。"
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

        parallel_results = await self._run_parallel_llm_steps(
            step_results,
            [
                (
                    "get_company_info",
                    "获取公司信息",
                    lambda: self._get_company_info(symbol),
                ),
                (
                    "get_company_news",
                    "获取新闻",
                    lambda: self._get_company_news(symbol),
                ),
                (
                    "get_financial_data",
                    "获取财务数据",
                    lambda: self._get_financial_data(symbol),
                ),
            ],
        )
        if parallel_results is None:
            return self._failed_response(step_results)

        company_info = parallel_results["get_company_info"]
        company_news = parallel_results["get_company_news"]
        financial_data = parallel_results["get_financial_data"]

        report_result = await self._run_llm_step(
            step_results,
            step_id="generate_report",
            name="生成报告",
            operation=lambda: self._generate_report(
                symbol,
                company_info,
                company_news,
                financial_data,
            ),
        )
        if report_result is None:
            return self._failed_response(step_results)

        step_results.append(self._step_result("end", "结束", {"symbol": symbol}))

        return WorkflowRunResponse(
            workflow_id=FINANCE_REPORT_WORKFLOW_ID,
            status="completed",
            steps=step_results,
            report=str(report_result.get("report", "")),
        )

    async def _get_company_info(self, symbol: str) -> dict[str, Any]:
        return await self._complete_json(
            system_prompt=(
                "You are a finance research assistant. Return only valid JSON. "
                "Do not fabricate precise facts; if uncertain, use null and add "
                "a short caveat."
            ),
            user_prompt=(
                f"获取股票代码 {symbol} 对应公司的基础信息。"
                "返回字段：symbol, company_name, exchange, industry, sector, "
                "headquarters, website, business_summary, caveats。"
            ),
        )

    async def _get_company_news(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        return await self._complete_json(
            system_prompt=(
                "You are a finance news analyst. Return only valid JSON. "
                "Do not invent source URLs or exact timestamps. If you cannot "
                "verify freshness, say so in caveats."
            ),
            user_prompt=(
                f"基于公司代码 {symbol}，"
                "独立整理重要新闻或市场动态。"
                "返回字段：symbol, news_items, sentiment, key_themes, caveats。\n"
            ),
        )

    async def _get_financial_data(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        return await self._complete_json(
            system_prompt=(
                "You are a finance fundamentals analyst. Return only valid JSON. "
                "Do not fabricate exact financial numbers; if data is unavailable "
                "or stale, use null and explain in caveats."
            ),
            user_prompt=(
                f"基于公司代码 {symbol}，"
                "独立整理可用于报告的财务数据和指标。"
                "返回字段：symbol, period, currency, revenue, gross_margin, "
                "operating_income, net_income, eps, cash_flow, balance_sheet, "
                "financial_highlights, caveats。"
            ),
        )

    async def _generate_report(
        self,
        symbol: str,
        company_info: dict[str, Any],
        company_news: dict[str, Any],
        financial_data: dict[str, Any],
    ) -> dict[str, Any]:
        report = await self._complete_text(
            system_prompt=(
                "You are an equity research report writer. Generate the final "
                "report directly from the workflow node outputs. Do not use a "
                "fixed template; choose the structure that best explains the "
                "company, news context, financial picture, risks, and caveats."
            ),
            user_prompt=(
                f"请为 {symbol} 生成一份中文金融分析报告。\n"
                f"公司信息：{json.dumps(company_info, ensure_ascii=False)}\n"
                f"新闻信息：{json.dumps(company_news, ensure_ascii=False)}\n"
                f"财务数据：{json.dumps(financial_data, ensure_ascii=False)}"
            ),
        )
        return {"report": report}

    async def _run_parallel_llm_steps(
        self,
        step_results: list[WorkflowStepResult],
        steps: list[tuple[str, str, Callable[[], Awaitable[dict[str, Any]]]]],
    ) -> dict[str, dict[str, Any]] | None:
        outputs = await asyncio.gather(
            *(operation() for _, _, operation in steps),
            return_exceptions=True,
        )

        completed_outputs: dict[str, dict[str, Any]] = {}
        has_failure = False
        for (step_id, name, _), output in zip(steps, outputs):
            if isinstance(output, Exception):
                has_failure = True
                step_results.append(
                    self._step_result(
                        step_id,
                        name,
                        {
                            "error": str(output),
                            "error_type": output.__class__.__name__,
                        },
                        status="failed",
                    )
                )
                continue

            completed_outputs[step_id] = output
            step_results.append(self._step_result(step_id, name, output))

        return None if has_failure else completed_outputs

    async def _run_llm_step(
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
