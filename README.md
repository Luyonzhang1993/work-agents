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

## API

- `GET /` - service status
- `GET /health` - health check
- `POST /api/chat` - model-plan local function tools and MCP tools, then fall back to plain LLM chat
- `GET /api/mcp/tools` - list registered MCP tools
- `POST /api/mcp/call` - call a registered MCP tool through stdio

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

When `use_tools` is `true`, `/api/chat` first asks the model to produce a JSON
tool plan from the local function tools and MCP tools catalog. The catalog uses
unique IDs such as `function:get_current_time` and `mcp:arithmetic:add`, so
multiple MCP services can expose tools without name collisions. If one or more
tools are planned, it executes them in order and can feed the previous result
into the next tool, then asks the model to summarize the tool results. If the
model plans no tools, it sends only the message history to the LLM without a
tools schema.

MCP stdio example:

```bash
curl -X POST http://127.0.0.1:8001/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"name":"mcp:arithmetic:multiply","arguments":{"left":6,"right":7}}'
```

## Architecture

```text
app/
  api/routes/       HTTP route handlers
  core/             configuration and shared app setup
  schemas/          request and response models
  services/         OpenAI client and LLM orchestration
  mcp_server/       local stdio MCP server modules
  tools/            function calling registry and handlers
```

Add new function calling tools in `app/tools/registry.py`, then expose them through
`ToolDefinition`.

MCP services are registered in `app/services/mcp_registry.py`. The arithmetic
MCP server lives in `app/mcp_server/arithmetic.py` and exposes `add`, `subtract`,
`multiply`, and `divide` over stdio. These MCP tools are also available to
`/api/chat`; addition uses `mcp:arithmetic:add` instead of a local function
calling tool.
