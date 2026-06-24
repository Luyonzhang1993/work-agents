# work-agents

FastAPI + Uvicorn project skeleton for OpenAI-compatible LLM calls and function
calling. Defaults to local Ollama on `127.0.0.1:11434` with `qwen3:8b`.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
ollama run qwen3:8b
make dev
```

The app runs at `http://127.0.0.1:8001` by default.

You can override the defaults in `.env`:

```bash
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=qwen3:8b
PORT=8001
RELOAD=false
```

Local MCP services such as arithmetic and marketdata are registered by default.
The marketdata MCP server uses Yahoo Finance public endpoints for quote,
history, financial summary, and news context.

## API

- `GET /` - service status
- `GET /health` - health check
- `POST /api/chat` - route to a workflow or fall back to direct LLM chat
- `WS /api/ws/chat` - chat over WebSocket with structured lifecycle events
- `GET /api/mcp/tools` - list registered MCP tools
- `POST /api/mcp/call` - call a registered MCP tool through stdio
- `GET /api/workflows/finance-report` - get the finance report workflow definition
- `POST /api/workflows/finance-report/run` - run the LLM-driven finance report workflow
- `GET /api/workflows/travel-planner` - get the LangGraph travel demo workflow definition
- `POST /api/workflows/travel-planner/run` - run the LangGraph travel demo workflow
- `POST /api/workflows/travel-planner/stream` - stream LangGraph workflow events as SSE

Example:

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"请帮我计算 12.5 加 7.5","use_tools":true}'
```

Chained tool example:

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"计算10 + 20， 用结果再除以5告诉我最终答案","use_tools":true}'
```

When `use_tools` is `true`, `/api/chat` first asks a lightweight LLM router to
choose one workflow using function calling, such as
`workflow:finance_company_report` or `workflow:langgraph_travel_planner`, or
return no tool call. The router only enumerates workflow-level routing tools,
not lower-level function tools or MCP tools, so adding more low-level
capabilities does not slow the first routing step. If a workflow is selected,
the workflow owns all subsequent tool/MCP/LLM orchestration, and `/api/chat`
only asks the LLM to summarize the final workflow result. If no workflow
matches, `/api/chat` falls back to direct LLM invocation.
Workflow routing metadata and execution adapters are centralized in the workflow
registry, so chat dispatch does not hard-code individual workflow IDs.

MCP stdio example:

```bash
curl -X POST http://127.0.0.1:8001/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"name":"mcp:arithmetic:multiply","arguments":{"left":6,"right":7}}'
```

Marketdata MCP example:

```bash
curl -X POST http://127.0.0.1:8001/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"name":"mcp:marketdata:quote_snapshot","arguments":{"symbol":"AMD"}}'
```

Finance report workflow example:

```bash
curl -X POST http://127.0.0.1:8001/api/workflows/finance-report/run \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AMD"}'
```

LangGraph travel planner workflow example:

```bash
curl -X POST http://127.0.0.1:8001/api/workflows/travel-planner/run \
  -H "Content-Type: application/json" \
  -d '{"destination":"杭州","duration_days":3,"budget_level":"comfort","traveler_type":"couple","interests":["local_food","culture","city_walk"]}'
```

LangGraph travel planner streaming example:

```bash
curl -N -X POST http://127.0.0.1:8001/api/workflows/travel-planner/stream \
  -H "Content-Type: application/json" \
  -d '{"destination":"京都","duration_days":4,"budget_level":"premium","traveler_type":"family","interests":["culture","local_food","nature"]}'
```

LLM-planned workflow example:

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"请运行 AMD 金融报告 workflow，并告诉我结果","use_tools":true}'
```

LLM-routed travel workflow example:

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我规划一个杭州 3 天情侣旅行，预算舒适，想吃本地美食和逛文化街区","use_tools":true}'
```

WebSocket chat example:

```bash
wscat -c ws://127.0.0.1:8001/api/ws/chat
```

Send:

```json
{"message":"请运行 AMD 金融报告 workflow，并告诉我结果","use_tools":true}
```

The server responds with structured events:

```json
{"type":"ready","data":{"message":"Send a chat request JSON payload with message, history, and use_tools fields."}}
{"type":"accepted","data":{"use_tools":true,"history_count":0}}
{"type":"responding","data":{"message":"Routing through workflow or direct LLM invocation."}}
{"type":"completed","data":{"message":"...","model":"...","tool_calls":[]}}
```

## Architecture

```text
app/
  api/routes/       HTTP route handlers
  core/             configuration and shared app setup
  schemas/          request and response models
  services/         OpenAI client, workflow routing, and orchestration
  mcp_server/       local stdio MCP server modules
  tools/            function calling registry and handlers
```

Add new user-facing capabilities as workflows first. Keep lower-level function
tools in `app/tools/registry.py` and MCP services in `app/services/mcp_registry.py`
behind workflows when they are part of a larger process.

MCP services are registered in `app/services/mcp_registry.py`. The arithmetic
MCP server lives in `app/mcp_server/arithmetic.py` and exposes `add`, `subtract`,
`multiply`, and `divide` over stdio. Financial market data is provided by the
local `app/mcp_server/marketdata.py` MCP server and registered as `marketdata`.
It uses Yahoo Finance public endpoints for quote, history, financial summary,
and news context. MCP tools remain available through `/api/mcp/*`, and workflows
can use them internally when needed.

The finance report workflow is defined in `app/services/workflow_service.py` and
now runs as a LangGraph `StateGraph`: start, fan out to get company info, news,
and financial data in parallel, join those research nodes, then generate the
final report. Each business node is implemented by LLM calls; the final report
is also generated by the LLM from prior node outputs rather than a local
template.
Inside the workflow, finance LLM nodes receive local marketdata MCP results as
evidence. The workflow calls the required marketdata tools directly instead of
asking the LLM to discover external market data meta-tools.

`/api/chat` exposes the finance workflow to the lightweight LLM router as
`workflow:finance_company_report`. When a workflow result has `status: failed`,
the LLM summarization step receives the failed step and error context so it can
explain why the workflow did not complete and suggest the next action.

The LangGraph travel planner demo is defined in
`app/services/langgraph_travel_workflow.py`. It is intentionally separate from
the fixed finance workflow so you can compare a hand-written orchestration flow
with a workflow runtime. The demo builds a `StateGraph`, routes to one of three
budget branches, passes state through planning and risk-check nodes, and exposes
the run as structured SSE events such as `workflow.step.started`,
`workflow.step.completed`, and `assistant.message.delta`. `/api/chat` also
exposes it to the same workflow router as `workflow:langgraph_travel_planner`.

# 中文说明

`work-agents` 是一个基于 FastAPI + Uvicorn 的 OpenAI-compatible LLM 服务，
支持 function calling、MCP 工具调用、workflow 路由，以及 LangGraph workflow
demo。默认使用本机 Ollama：

```text
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=qwen3:8b
```

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
ollama run qwen3:8b
make dev
```

服务默认运行在：

```text
http://127.0.0.1:8001
```

可以通过 `.env` 覆盖配置：

```bash
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=qwen3:8b
PORT=8001
RELOAD=false
```

本地 MCP 服务会默认注册，例如 arithmetic 和 marketdata。marketdata MCP 使用
Yahoo Finance 公开接口提供行情、历史价格、财务摘要和新闻上下文。

## 主要 API

- `GET /` - 服务状态
- `GET /health` - 健康检查
- `POST /api/chat` - 路由到 workflow，或回退到直接 LLM 对话
- `WS /api/ws/chat` - WebSocket chat，返回结构化生命周期事件
- `GET /api/mcp/tools` - 查看已注册 MCP 工具
- `POST /api/mcp/call` - 调用 MCP 工具
- `GET /api/workflows/finance-report` - 查看金融报告 workflow 定义
- `POST /api/workflows/finance-report/run` - 执行金融报告 workflow
- `GET /api/workflows/travel-planner` - 查看 LangGraph 旅行规划 workflow 定义
- `POST /api/workflows/travel-planner/run` - 执行 LangGraph 旅行规划 workflow
- `POST /api/workflows/travel-planner/stream` - 以 SSE 流式输出 LangGraph 事件

## Chat 示例

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"请帮我计算 12.5 加 7.5","use_tools":true}'
```

链式工具调用示例：

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"计算10 + 20， 用结果再除以5告诉我最终答案","use_tools":true}'
```

当 `use_tools` 为 `true` 时，`/api/chat` 会先通过轻量 LLM router 判断是否
应该调用 workflow。当前可路由的 workflow 包括：

```text
workflow:finance_company_report
workflow:langgraph_travel_planner
```

router 只暴露 workflow 级别的 routing tools，不直接枚举底层 function tools 或
MCP tools。这样新增底层能力时，不会拖慢第一步路由。如果选中了 workflow，
后续 MCP、工具、LLM 编排都由 workflow 自己负责；`/api/chat` 只负责汇总最终结果。

workflow 路由元数据和执行 adapter 集中在 `app/services/workflow_registry.py`，
chat 分发层不再硬编码具体 workflow ID。

## Workflow 示例

金融报告 workflow：

```bash
curl -X POST http://127.0.0.1:8001/api/workflows/finance-report/run \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AMD"}'
```

LangGraph 旅行规划 workflow：

```bash
curl -X POST http://127.0.0.1:8001/api/workflows/travel-planner/run \
  -H "Content-Type: application/json" \
  -d '{"destination":"杭州","duration_days":3,"budget_level":"comfort","traveler_type":"couple","interests":["local_food","culture","city_walk"]}'
```

LangGraph 旅行规划 SSE 流式输出：

```bash
curl -N -X POST http://127.0.0.1:8001/api/workflows/travel-planner/stream \
  -H "Content-Type: application/json" \
  -d '{"destination":"京都","duration_days":4,"budget_level":"premium","traveler_type":"family","interests":["culture","local_food","nature"]}'
```

通过 `/api/chat` 触发金融报告 workflow：

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"请运行 AMD 金融报告 workflow，并告诉我结果","use_tools":true}'
```

通过 `/api/chat` 触发旅行规划 workflow：

```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我规划一个杭州 3 天情侣旅行，预算舒适，想吃本地美食和逛文化街区","use_tools":true}'
```

## WebSocket 示例

```bash
wscat -c ws://127.0.0.1:8001/api/ws/chat
```

发送：

```json
{"message":"请运行 AMD 金融报告 workflow，并告诉我结果","use_tools":true}
```

服务端返回结构化事件：

```json
{"type":"ready","data":{"message":"Send a chat request JSON payload with message, history, and use_tools fields."}}
{"type":"accepted","data":{"use_tools":true,"history_count":0}}
{"type":"responding","data":{"message":"Routing through workflow or direct LLM invocation."}}
{"type":"completed","data":{"message":"...","model":"...","tool_calls":[]}}
```

## 项目结构

```text
app/
  api/routes/       HTTP 路由
  core/             配置和应用启动
  schemas/          请求和响应模型
  services/         OpenAI client、workflow 路由、编排和 registry
  mcp_server/       本地 stdio MCP server
  tools/            function calling 工具注册和处理
```

新增用户能力时，优先抽象成 workflow。底层 function tools 放在
`app/tools/registry.py`，MCP 服务放在 `app/services/mcp_registry.py`，
当它们属于更大的业务流程时，由 workflow 统一编排。

## 当前 Workflow

金融报告 workflow 定义在 `app/services/workflow_service.py`，现在也使用
LangGraph `StateGraph`。流程为：

```text
start -> get_company_info / get_company_news / get_financial_data -> generate_report -> end
```

公司信息、新闻、财务数据三个节点通过 LangGraph fan-out/fan-in 并行执行；最终报告
由 LLM 基于前面节点输出生成。金融节点会直接调用本地 marketdata MCP 获取证据，
不再依赖外部 market data meta-tools。

LangGraph 旅行规划 workflow 定义在
`app/services/langgraph_travel_workflow.py`。它用于对比手写 orchestration 和
workflow runtime，当前能力包括：

```text
StateGraph
条件分支
节点状态事件
SSE 流式输出
assistant.message.delta
```

它会根据预算走 `budget_options`、`comfort_options` 或 `premium_options` 分支，
再生成每日行程、检查风险、汇总最终方案。

## 迭代路线

详细路线图见 [TODO.md](./TODO.md)。目标是把项目继续演进成：

```text
动态 workflow registry
统一 run model
结构化事件流
本机 SQLite 持久化
LangGraph checkpoint / interrupt / retry / subgraph
长期 agent memory
前端可恢复的 ChatGPT-like workflow 展示
```
