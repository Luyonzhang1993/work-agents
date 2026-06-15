import asyncio
import json
import subprocess
import sys
from itertools import count
from typing import Any, Optional


class MCPError(RuntimeError):
    pass


class MCPStdioClient:
    def __init__(self, module: str, timeout: float = 10) -> None:
        self.module = module
        self.timeout = timeout
        self._request_ids = count(1)

    async def list_tools(self) -> list[dict[str, Any]]:
        async with _MCPProcess(self.module, self.timeout) as process:
            await process.initialize(next(self._request_ids))
            response = await process.request(next(self._request_ids), "tools/list")
            return response.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with _MCPProcess(self.module, self.timeout) as process:
            await process.initialize(next(self._request_ids))
            response = await process.request(
                next(self._request_ids),
                "tools/call",
                {"name": name, "arguments": arguments},
            )
            return response


class _MCPProcess:
    def __init__(self, module: str, timeout: float) -> None:
        self.module = module
        self.timeout = timeout
        self.process: Optional[asyncio.subprocess.Process] = None

    async def __aenter__(self) -> "_MCPProcess":
        try:
            self.process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    self.module,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                ),
                timeout=self.timeout,
            )
        except Exception as exc:
            raise MCPError(f"Failed to start MCP process: {self.module}") from exc
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.process is None:
            return
        if self.process.stdin:
            self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=1)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()

    async def initialize(self, request_id: int) -> None:
        await asyncio.wait_for(
            self.request(
                request_id,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "work-agents", "version": "0.1.0"},
                },
            ),
            timeout=self.timeout,
        )
        await self.notify("notifications/initialized")

    async def request(
        self,
        request_id: int,
        method: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        try:
            await asyncio.wait_for(
                self.write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": method,
                        "params": params or {},
                    }
                ),
                timeout=self.timeout,
            )
            response = await asyncio.wait_for(
                self.read_message(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError as exc:
            raise MCPError(f"MCP request timed out: {method}") from exc
        if "error" in response:
            error = response["error"]
            raise MCPError(error.get("message", "MCP request failed"))
        return response.get("result", {})

    async def notify(
        self,
        method: str,
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        await self.write_message(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
        )

    async def write_message(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise MCPError("MCP process is not running")
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        self.process.stdin.write(
            f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        )
        await self.process.stdin.drain()

    async def read_message(self) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise MCPError("MCP process is not running")

        headers: dict[str, str] = {}
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise MCPError("MCP process closed stdout")
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("ascii").partition(":")
            headers[key.lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise MCPError("MCP response did not include a body")
        body = await self.process.stdout.readexactly(content_length)
        return json.loads(body.decode("utf-8"))


def get_arithmetic_mcp_client() -> MCPStdioClient:
    return MCPStdioClient("app.mcp_server.arithmetic")
