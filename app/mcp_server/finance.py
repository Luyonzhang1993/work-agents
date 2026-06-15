import json
import sys
from typing import Any, Callable


JSONRPC_VERSION = "2.0"


def get_company_info(symbol: str = "AMD") -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "companyName": "Advanced Micro Devices, Inc.",
        "exchange": "NASDAQ",
        "industry": "Semiconductors",
        "sector": "Technology",
        "headquarters": "Santa Clara, California, United States",
        "ceo": "Lisa Su",
        "website": "https://www.amd.com",
        "description": (
            "Mock company profile for workflow validation. AMD designs CPUs, GPUs, "
            "adaptive SoCs, and data center accelerators."
        ),
    }


def get_company_news(symbol: str = "AMD") -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "news": [
            {
                "title": "AMD unveils mock AI accelerator roadmap",
                "source": "Workflow Finance Wire",
                "publishedAt": "2026-06-15T09:30:00Z",
                "summary": "Synthetic news item for validating downstream workflows.",
                "url": "https://example.com/amd-ai-roadmap",
            },
            {
                "title": "Analysts highlight simulated data center demand for AMD",
                "source": "Example Markets",
                "publishedAt": "2026-06-14T16:00:00Z",
                "summary": "Mock analyst commentary about data center revenue momentum.",
                "url": "https://example.com/amd-data-center-demand",
            },
            {
                "title": "AMD shares move in pretend premarket trading",
                "source": "Demo Market News",
                "publishedAt": "2026-06-13T12:15:00Z",
                "summary": "Fake market movement headline used only for workflow testing.",
                "url": "https://example.com/amd-premarket",
            },
        ],
    }


def get_financial_data(symbol: str = "AMD") -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "currency": "USD",
        "period": "FY2025",
        "revenue": 25785000000,
        "grossProfit": 12892000000,
        "operatingIncome": 2364000000,
        "netIncome": 1854000000,
        "epsDiluted": 1.13,
        "freeCashFlow": 2410000000,
        "cashAndEquivalents": 5820000000,
        "totalDebt": 3120000000,
        "note": "Mock financial data for workflow validation only.",
    }


TOOLS_BY_NAME: dict[str, Callable[[str], dict[str, Any]]] = {
    "get_company_info": get_company_info,
    "get_company_news": get_company_news,
    "get_financial_data": get_financial_data,
}


def tool_schema(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol. Defaults to AMD.",
                    "default": "AMD",
                }
            },
            "additionalProperties": False,
        },
    }


TOOLS = [
    tool_schema("get_company_info", "Return mock company profile data."),
    tool_schema("get_company_news", "Return mock company news items."),
    tool_schema("get_financial_data", "Return mock company financial data."),
]


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("ascii").partition(":")
        headers[key.lower()] = value.strip()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    body = sys.stdin.buffer.read(content_length)
    return json.loads(body.decode("utf-8"))


def write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def result_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if request_id is None:
        return None

    if method == "initialize":
        return result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "finance-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return result_response(request_id, {"tools": TOOLS})

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        tool = TOOLS_BY_NAME.get(name)
        if tool is None:
            return error_response(request_id, -32602, f"Unknown tool: {name}")

        try:
            output = tool(str(arguments.get("symbol") or "AMD"))
        except Exception as exc:
            return error_response(request_id, -32000, str(exc))

        return result_response(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(output, ensure_ascii=False),
                    }
                ],
                "isError": False,
            },
        )

    return error_response(request_id, -32601, f"Unknown method: {method}")


def main() -> None:
    while True:
        request = read_message()
        if request is None:
            break
        response = handle_request(request)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    main()
