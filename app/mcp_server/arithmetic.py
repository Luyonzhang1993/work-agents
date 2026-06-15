import json
import sys
from typing import Any, Callable


JSONRPC_VERSION = "2.0"


def add(left: float, right: float) -> dict[str, float]:
    return {"left": left, "right": right, "result": left + right}


def subtract(left: float, right: float) -> dict[str, float]:
    return {"left": left, "right": right, "result": left - right}


def multiply(left: float, right: float) -> dict[str, float]:
    return {"left": left, "right": right, "result": left * right}


def divide(left: float, right: float) -> dict[str, float]:
    if right == 0:
        raise ValueError("right must not be zero")
    return {"left": left, "right": right, "result": left / right}


OPERATIONS: dict[str, Callable[[float, float], dict[str, float]]] = {
    "add": add,
    "subtract": subtract,
    "multiply": multiply,
    "divide": divide,
}


def tool_schema(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "left": {"type": "number", "description": "The left operand."},
                "right": {"type": "number", "description": "The right operand."},
            },
            "required": ["left", "right"],
            "additionalProperties": False,
        },
    }


TOOLS = [
    tool_schema("add", "Add two numbers."),
    tool_schema("subtract", "Subtract the right number from the left number."),
    tool_schema("multiply", "Multiply two numbers."),
    tool_schema("divide", "Divide the left number by the right number."),
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
                "serverInfo": {"name": "arithmetic-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return result_response(request_id, {"tools": TOOLS})

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        operation = OPERATIONS.get(name)
        if operation is None:
            return error_response(request_id, -32602, f"Unknown tool: {name}")

        try:
            output = operation(float(arguments["left"]), float(arguments["right"]))
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
