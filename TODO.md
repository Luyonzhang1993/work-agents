# TODO

This roadmap tracks the work needed to evolve `work-agents` into a locally
persistent, dynamically orchestrated workflow/agent runtime.

## North Star

- [ ] Build a workflow platform where new workflows can be registered,
      selected, executed, streamed, persisted, resumed, and inspected without
      hard-coding dispatch logic in chat.
- [ ] Use workflow engine capabilities, especially LangGraph state graphs,
      streaming, checkpointing, interrupts, retries, subgraphs, and memory.
- [ ] Persist conversations, runs, workflow events, checkpoints, and long-term
      agent memory on the local machine first.
- [ ] Let agents learn over time in a Hermes-like way: remember useful facts,
      user preferences, prior workflow outcomes, tool behavior, and reusable
      strategies while keeping the memory inspectable and correctable.

## Phase 1: Workflow Registry And Runtime Boundary

- [x] Add a workflow registry so `/api/chat` does not hard-code individual
      workflow IDs.
- [x] Register the finance report workflow.
- [x] Register the LangGraph travel planner workflow.
- [ ] Define a shared workflow runtime interface:
      `definition()`, `run()`, `stream()`, `resume()`, and `cancel()`.
- [ ] Move workflow-specific argument normalization into each workflow adapter
      or schema instead of central service code.
- [ ] Add workflow metadata fields:
      `version`, `engine`, `capabilities`, `enabled`, `owner`, and `risk_level`.
- [ ] Add a registry endpoint:
      `GET /api/workflows` to list all registered workflows.
- [ ] Make individual workflow endpoints use the registry where practical,
      instead of depending directly on concrete workflow services.

## Phase 2: Unified Run Model

- [ ] Introduce `run_id` for every workflow/chat execution.
- [ ] Add a `RunOrchestrator` layer that owns lifecycle transitions:
      `pending`, `running`, `waiting_for_input`, `completed`, `failed`,
      `cancelled`.
- [ ] Split `/api/chat` into:
      create run, route workflow/direct LLM, execute run, summarize result.
- [ ] Return run metadata from chat responses:
      `run_id`, `workflow_id`, `status`, and final assistant message.
- [ ] Add cancel support:
      `POST /api/runs/{run_id}/cancel`.
- [ ] Add resume support:
      `POST /api/runs/{run_id}/resume`.

## Phase 3: Structured Event Streaming

- [ ] Define one public event protocol for chat and workflow execution:
      `run.started`, `workflow.step.started`, `workflow.step.completed`,
      `tool.call.started`, `tool.call.completed`, `assistant.message.delta`,
      `run.completed`, `run.failed`, and `heartbeat`.
- [ ] Add `GET /api/runs/{run_id}/stream` using SSE.
- [ ] Keep WebSocket for bidirectional control later, but use SSE first for
      ChatGPT-style streaming output.
- [ ] Map LangGraph stream modes to public events:
      `updates -> workflow.step.completed`,
      `custom -> workflow.step.started/status`,
      `messages -> assistant.message.delta`.
- [ ] Add heartbeats for long-running workflow steps.
- [ ] Add client reconnect support using event sequence numbers.

## Phase 4: Local Persistence

- [ ] Choose the first local database:
      SQLite is the preferred default for this project.
- [ ] Add tables for:
      `conversations`, `messages`, `runs`, `run_steps`, `run_events`,
      `workflow_checkpoints`, `agent_memories`, and `memory_events`.
- [ ] Persist every run event before or while streaming it to the client.
- [ ] Persist final assistant messages and workflow reports.
- [ ] Add APIs to inspect persisted state:
      `GET /api/conversations/{id}`,
      `GET /api/runs/{run_id}`,
      `GET /api/runs/{run_id}/events`.
- [ ] Add a local data directory convention, for example:
      `.local/work-agents.sqlite3`.
- [ ] Add backup/export guidance for local persistence files.

## Phase 5: LangGraph Production Features

- [ ] Add LangGraph checkpointer support for graph-backed workflows.
- [ ] Map application `run_id` and `conversation_id` to LangGraph `thread_id`.
- [ ] Persist checkpoints locally so workflows can resume after process restart.
- [ ] Add interrupt nodes for human approval and missing information.
- [ ] Add retry policies for unstable LLM/tool/API nodes.
- [ ] Add timeout policies for slow external calls.
- [ ] Add subgraph conventions for reusable workflow modules.
- [ ] Add time-travel/debug tools to replay or fork from a prior checkpoint.
- [ ] Add a way to render workflow graphs as Mermaid text or PNG for debugging.

## Phase 6: Tool And Permission Model

- [ ] Create a tool registry capability model:
      `read_only`, `external_network`, `writes_local_file`, `writes_database`,
      `sends_message`, `high_risk`.
- [ ] Require human approval before high-risk tool calls.
- [ ] Add per-workflow allowed tools.
- [ ] Add per-run tool call records.
- [ ] Add tool result compaction and redaction rules.
- [ ] Add tool error normalization so workflows can recover consistently.

## Phase 7: Long-Term Learning Agent Memory

- [ ] Separate short-term memory from long-term memory:
      conversation state belongs in run/conversation storage; durable learned
      facts belong in `agent_memories`.
- [ ] Define memory record types:
      `user_preference`, `project_fact`, `workflow_lesson`, `tool_lesson`,
      `domain_note`, `correction`, and `rejected_memory`.
- [ ] Add memory metadata:
      `source_run_id`, `confidence`, `scope`, `created_at`, `updated_at`,
      `last_used_at`, `expires_at`, and `status`.
- [ ] Add a memory write policy:
      the agent proposes memories; the system stores only validated or
      user-approved memories.
- [ ] Add a memory retrieval policy:
      fetch only memories relevant to the current user, project, workflow, and
      task.
- [ ] Add memory correction and deletion APIs.
- [ ] Add a memory inspection UI/API before allowing autonomous learning to
      affect workflow behavior.
- [ ] Add periodic memory consolidation:
      summarize repeated successful patterns and retire stale or contradicted
      memories.

## Phase 8: Observability And Evaluation

- [ ] Add structured logs for run lifecycle, workflow steps, tool calls, and
      memory reads/writes.
- [ ] Add timing metrics per workflow step.
- [ ] Add failure categories:
      routing_failed, workflow_failed, tool_failed, llm_failed, validation_failed.
- [ ] Add deterministic tests for workflow routing.
- [ ] Add tests for registry dispatch.
- [ ] Add tests for LangGraph branch selection.
- [ ] Add tests for event stream ordering.
- [ ] Add tests for persistence recovery.
- [ ] Add sample evaluation cases for travel planning and finance reporting.

## Phase 9: Frontend-Ready Experience

- [ ] Design a run view model:
      current status, visible steps, assistant message, artifacts, sources,
      and errors.
- [ ] Make workflow steps progressively render from event stream data.
- [ ] Render tool calls and workflow outputs separately from final assistant
      text.
- [ ] Support refresh/reconnect by replaying persisted `run_events`.
- [ ] Show human approval prompts when a workflow is interrupted.
- [ ] Add a workflow graph view using Mermaid output.

## Near-Term Next Actions

- [ ] Add `GET /api/workflows` backed by `WorkflowRegistry.catalog()`.
- [ ] Add `WorkflowRuntime` protocol/interface and adapt both existing
      workflows to it.
- [ ] Add SQLite dependency and a local persistence module.
- [ ] Add `runs` and `run_events` tables first; do not start with the full
      memory system.
- [ ] Add a unified `/api/runs/{run_id}/stream` endpoint.
- [ ] Update LangGraph travel planner to persist and replay its events.
- [ ] Add local long-term memory only after run/event persistence is stable.

# TODO 中文版

这份路线图用于推动 `work-agents` 演进成一个支持本机持久化、动态编排
workflow、并具备长期学习能力的 agent/workflow runtime。

## 北极星目标

- [ ] 构建一个 workflow 平台，让新 workflow 可以注册、选择、执行、流式输出、
      持久化、恢复和检查，避免在 chat 层硬编码分发逻辑。
- [ ] 使用 workflow engine 能力，尤其是 LangGraph 的状态图、流式输出、
      checkpoint、interrupt、retry、subgraph 和 memory。
- [ ] 优先在本机持久化 conversations、runs、workflow events、checkpoints 和
      长期 agent memory。
- [ ] 让 agent 像 Hermes 一样长期学习：记住有用事实、用户偏好、历史 workflow
      结果、工具行为和可复用策略，同时保持记忆可检查、可修正。

## 阶段 1：Workflow Registry 和 Runtime 边界

- [x] 增加 workflow registry，让 `/api/chat` 不再硬编码具体 workflow ID。
- [x] 注册金融报告 workflow。
- [x] 注册 LangGraph 旅行规划 workflow。
- [ ] 定义统一的 workflow runtime 接口：
      `definition()`、`run()`、`stream()`、`resume()`、`cancel()`。
- [ ] 将 workflow 参数归一化移动到各自 workflow adapter 或 schema 中。
- [ ] 增加 workflow 元数据：
      `version`、`engine`、`capabilities`、`enabled`、`owner`、`risk_level`。
- [ ] 增加 registry 列表接口：
      `GET /api/workflows`。
- [ ] 尽量让单个 workflow endpoint 也通过 registry 调用，而不是直接依赖具体服务。

## 阶段 2：统一 Run Model

- [ ] 为每次 workflow/chat 执行引入 `run_id`。
- [ ] 增加 `RunOrchestrator` 层，管理生命周期状态：
      `pending`、`running`、`waiting_for_input`、`completed`、`failed`、
      `cancelled`。
- [ ] 拆分 `/api/chat` 流程：
      创建 run、路由 workflow/direct LLM、执行 run、汇总结果。
- [ ] chat response 返回 run 元信息：
      `run_id`、`workflow_id`、`status`、最终 assistant message。
- [ ] 增加取消能力：
      `POST /api/runs/{run_id}/cancel`。
- [ ] 增加恢复能力：
      `POST /api/runs/{run_id}/resume`。

## 阶段 3：结构化事件流

- [ ] 定义统一的公开事件协议：
      `run.started`、`workflow.step.started`、`workflow.step.completed`、
      `tool.call.started`、`tool.call.completed`、`assistant.message.delta`、
      `run.completed`、`run.failed`、`heartbeat`。
- [ ] 增加 SSE 接口：
      `GET /api/runs/{run_id}/stream`。
- [ ] 普通 ChatGPT 风格输出优先使用 SSE，WebSocket 保留给后续双向控制。
- [ ] 将 LangGraph stream mode 映射成公开事件：
      `updates -> workflow.step.completed`，
      `custom -> workflow.step.started/status`，
      `messages -> assistant.message.delta`。
- [ ] 为长时间运行的 workflow step 增加 heartbeat。
- [ ] 使用 event sequence number 支持客户端断线重连。

## 阶段 4：本机持久化

- [ ] 选择第一版本机数据库：本项目优先使用 SQLite。
- [ ] 增加数据表：
      `conversations`、`messages`、`runs`、`run_steps`、`run_events`、
      `workflow_checkpoints`、`agent_memories`、`memory_events`。
- [ ] 每个 run event 在推给客户端前或同时写入本机存储。
- [ ] 持久化最终 assistant message 和 workflow report。
- [ ] 增加状态检查 API：
      `GET /api/conversations/{id}`、
      `GET /api/runs/{run_id}`、
      `GET /api/runs/{run_id}/events`。
- [ ] 约定本机数据目录，例如：
      `.local/work-agents.sqlite3`。
- [ ] 增加本机持久化文件的备份和导出说明。

## 阶段 5：LangGraph 生产级能力

- [ ] 为基于 graph 的 workflow 增加 LangGraph checkpointer。
- [ ] 将应用层 `run_id`、`conversation_id` 映射到 LangGraph `thread_id`。
- [ ] 本机持久化 checkpoints，让 workflow 在进程重启后可以恢复。
- [ ] 增加 interrupt 节点，用于人工审批和参数补全。
- [ ] 为不稳定的 LLM/tool/API 节点增加 retry policy。
- [ ] 为慢外部调用增加 timeout policy。
- [ ] 建立 subgraph 约定，用于复用 workflow 模块。
- [ ] 增加 time-travel/debug 工具，支持从历史 checkpoint 回放或分叉。
- [ ] 增加 workflow 图渲染能力，输出 Mermaid 文本或 PNG。

## 阶段 6：工具和权限模型

- [ ] 建立 tool registry capability 模型：
      `read_only`、`external_network`、`writes_local_file`、`writes_database`、
      `sends_message`、`high_risk`。
- [ ] 高风险 tool call 需要人工确认。
- [ ] 增加每个 workflow 允许使用的工具清单。
- [ ] 记录每次 run 的 tool call。
- [ ] 增加 tool result 压缩和脱敏规则。
- [ ] 统一 tool error 格式，让 workflow 可以一致地恢复。

## 阶段 7：长期学习 Agent Memory

- [ ] 区分短期记忆和长期记忆：
      conversation state 存在 run/conversation storage；长期事实存在
      `agent_memories`。
- [ ] 定义 memory 类型：
      `user_preference`、`project_fact`、`workflow_lesson`、`tool_lesson`、
      `domain_note`、`correction`、`rejected_memory`。
- [ ] 增加 memory 元数据：
      `source_run_id`、`confidence`、`scope`、`created_at`、`updated_at`、
      `last_used_at`、`expires_at`、`status`。
- [ ] 增加 memory 写入策略：
      agent 提议 memory，系统只存储通过验证或用户批准的 memory。
- [ ] 增加 memory 检索策略：
      只检索和当前用户、项目、workflow、任务相关的 memory。
- [ ] 增加 memory 修正和删除 API。
- [ ] 在让长期学习影响 workflow 行为前，先增加 memory 检查 UI/API。
- [ ] 增加周期性 memory consolidation：
      总结反复成功的模式，淘汰过期或被推翻的 memory。

## 阶段 8：可观测性和评估

- [ ] 为 run lifecycle、workflow steps、tool calls、memory reads/writes 增加
      结构化日志。
- [ ] 增加每个 workflow step 的耗时指标。
- [ ] 增加失败分类：
      `routing_failed`、`workflow_failed`、`tool_failed`、`llm_failed`、
      `validation_failed`。
- [ ] 增加 workflow routing 的确定性测试。
- [ ] 增加 registry dispatch 测试。
- [ ] 增加 LangGraph 分支选择测试。
- [ ] 增加 event stream 顺序测试。
- [ ] 增加持久化恢复测试。
- [ ] 为旅行规划和金融报告增加样例评估集。

## 阶段 9：面向前端的体验

- [ ] 设计 run view model：
      当前状态、可见步骤、assistant message、artifacts、sources、errors。
- [ ] 让 workflow steps 基于 event stream 渐进式渲染。
- [ ] 将 tool calls、workflow outputs 和最终 assistant 文本分开展示。
- [ ] 通过回放已持久化的 `run_events` 支持刷新和重连。
- [ ] workflow 被 interrupt 时展示人工确认提示。
- [ ] 增加基于 Mermaid 的 workflow 图展示。

## 近期下一步

- [ ] 增加由 `WorkflowRegistry.catalog()` 驱动的 `GET /api/workflows`。
- [ ] 增加 `WorkflowRuntime` protocol/interface，并适配当前两个 workflow。
- [ ] 增加 SQLite 依赖和本机持久化模块。
- [ ] 先落地 `runs` 和 `run_events` 表，不要一开始就做完整 memory 系统。
- [ ] 增加统一的 `/api/runs/{run_id}/stream` endpoint。
- [ ] 让 LangGraph 旅行规划 workflow 可以持久化和回放事件。
- [ ] 等 run/event persistence 稳定后，再加入本机长期 memory。
