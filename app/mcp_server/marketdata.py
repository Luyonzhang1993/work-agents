import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from typing import Any, Callable


JSONRPC_VERSION = "2.0"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
YAHOO_SUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
USER_AGENT = "work-agents/0.1 local marketdata mcp"
SYMBOL_PROPERTY = {"type": "string", "description": "Ticker symbol, such as AMD."}
COUNT_PROPERTY = {"type": "integer", "description": "Maximum news count, default 5."}
RANGE_5D_PROPERTY = {"type": "string", "description": "Chart range, default 5d."}
RANGE_1MO_PROPERTY = {"type": "string", "description": "Chart range, default 1mo."}
INTERVAL_1D_PROPERTY = {
    "type": "string",
    "description": "Chart interval, default 1d.",
}


def company_profile(symbol: str) -> dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    quote = quote_snapshot(normalized_symbol)
    search = _safe_get_json(
        YAHOO_SEARCH_URL,
        {
            "q": normalized_symbol,
            "quotesCount": 1,
            "newsCount": 0,
        },
    )
    summary = _safe_summary(normalized_symbol, "assetProfile,price")
    quote_result = (search.get("quotes") or [{}])[0]
    profile = summary.get("assetProfile", {})
    price = summary.get("price", {})
    return {
        "symbol": normalized_symbol,
        "company_name": _raw_value(price.get("longName"))
        or quote_result.get("longname")
        or quote_result.get("shortname")
        or quote.get("short_name"),
        "exchange": _raw_value(price.get("exchangeName"))
        or quote_result.get("exchDisp")
        or quote.get("exchange"),
        "industry": profile.get("industry"),
        "sector": profile.get("sector"),
        "website": profile.get("website"),
        "business_summary": profile.get("longBusinessSummary"),
        "quote": quote,
        "data_sources": ["Yahoo Finance chart/search/quoteSummary"],
        "caveats": _source_caveats(summary, search),
    }


def quote_snapshot(
    symbol: str,
    range: str = "5d",
    interval: str = "1d",
) -> dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    chart = _chart(normalized_symbol, range, interval)
    meta = chart.get("meta", {})
    prices = _prices_from_chart(chart)
    latest = prices[-1] if prices else {}
    previous = prices[-2] if len(prices) >= 2 else {}
    latest_close = latest.get("close")
    previous_close = previous.get("close") or meta.get("chartPreviousClose")
    change = (
        latest_close - previous_close
        if isinstance(latest_close, (int, float))
        and isinstance(previous_close, (int, float))
        else None
    )
    change_percent = (
        change / previous_close * 100
        if isinstance(change, (int, float))
        and isinstance(previous_close, (int, float))
        and previous_close
        else None
    )
    return {
        "symbol": normalized_symbol,
        "short_name": meta.get("shortName"),
        "exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
        "currency": meta.get("currency"),
        "timezone": meta.get("timezone"),
        "regular_market_price": meta.get("regularMarketPrice"),
        "previous_close": previous_close,
        "latest_close": latest_close,
        "change": change,
        "change_percent": change_percent,
        "latest_bar": latest,
        "data_sources": ["Yahoo Finance chart"],
        "caveats": [
            "Yahoo Finance public chart data is best-effort and may be delayed.",
        ],
    }


def price_history(
    symbol: str,
    range: str = "1mo",
    interval: str = "1d",
) -> dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    chart = _chart(normalized_symbol, range, interval)
    prices = _prices_from_chart(chart)
    closes = [
        item["close"]
        for item in prices
        if isinstance(item.get("close"), (int, float))
    ]
    return {
        "symbol": normalized_symbol,
        "range": range,
        "interval": interval,
        "prices": prices,
        "summary": {
            "count": len(closes),
            "min_close": min(closes) if closes else None,
            "max_close": max(closes) if closes else None,
            "first_close": closes[0] if closes else None,
            "last_close": closes[-1] if closes else None,
        },
        "data_sources": ["Yahoo Finance chart"],
        "caveats": [
            "Historical bars are retrieved from Yahoo Finance public endpoints.",
        ],
    }


def financial_summary(symbol: str) -> dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    modules = "financialData,defaultKeyStatistics,summaryDetail,price"
    summary = _safe_summary(normalized_symbol, modules)
    financial_data = summary.get("financialData", {})
    key_stats = summary.get("defaultKeyStatistics", {})
    details = summary.get("summaryDetail", {})
    price = summary.get("price", {})
    quote = quote_snapshot(normalized_symbol)
    return {
        "symbol": normalized_symbol,
        "currency": _raw_value(price.get("currency")) or quote.get("currency"),
        "market_cap": _raw_value(price.get("marketCap"))
        or _raw_value(details.get("marketCap")),
        "revenue": _raw_value(financial_data.get("totalRevenue")),
        "gross_margin": _raw_value(financial_data.get("grossMargins")),
        "operating_margin": _raw_value(financial_data.get("operatingMargins")),
        "profit_margin": _raw_value(financial_data.get("profitMargins")),
        "free_cashflow": _raw_value(financial_data.get("freeCashflow")),
        "total_cash": _raw_value(financial_data.get("totalCash")),
        "total_debt": _raw_value(financial_data.get("totalDebt")),
        "trailing_eps": _raw_value(key_stats.get("trailingEps")),
        "forward_eps": _raw_value(key_stats.get("forwardEps")),
        "trailing_pe": _raw_value(details.get("trailingPE")),
        "forward_pe": _raw_value(details.get("forwardPE")),
        "quote": quote,
        "data_sources": ["Yahoo Finance quoteSummary/chart"],
        "caveats": _source_caveats(summary),
    }


def company_news(symbol: str, count: int = 5) -> dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    data = _safe_get_json(
        YAHOO_SEARCH_URL,
        {
            "q": normalized_symbol,
            "quotesCount": 1,
            "newsCount": max(0, min(int(count), 10)),
        },
    )
    news_items = []
    for item in data.get("news") or []:
        provider_publish_time = item.get("providerPublishTime")
        published_at = None
        if isinstance(provider_publish_time, int):
            published_at = dt.datetime.fromtimestamp(
                provider_publish_time,
                tz=dt.timezone.utc,
            ).isoformat()
        news_items.append(
            {
                "title": item.get("title"),
                "publisher": item.get("publisher"),
                "link": item.get("link"),
                "published_at": published_at,
                "type": item.get("type"),
            }
        )
    return {
        "symbol": normalized_symbol,
        "news_items": news_items,
        "data_sources": ["Yahoo Finance search"],
        "caveats": _source_caveats(data),
    }


def _chart(symbol: str, range: str, interval: str) -> dict[str, Any]:
    data = _get_json(
        YAHOO_CHART_URL.format(symbol=urllib.parse.quote(symbol)),
        {
            "range": range,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
        },
    )
    error = data.get("chart", {}).get("error")
    if error:
        raise ValueError(error.get("description") or "Yahoo chart request failed")
    result = data.get("chart", {}).get("result") or []
    if not result:
        raise ValueError(f"No chart data returned for symbol: {symbol}")
    return result[0]


def _prices_from_chart(chart: dict[str, Any]) -> list[dict[str, Any]]:
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    prices = []
    for index, timestamp in enumerate(timestamps):
        prices.append(
            {
                "timestamp": timestamp,
                "date": dt.datetime.fromtimestamp(
                    int(timestamp),
                    tz=dt.timezone.utc,
                ).date().isoformat(),
                "open": _at(opens, index),
                "high": _at(highs, index),
                "low": _at(lows, index),
                "close": _at(closes, index),
                "volume": _at(volumes, index),
            }
        )
    return prices


def _safe_summary(symbol: str, modules: str) -> dict[str, Any]:
    data = _safe_get_json(
        YAHOO_SUMMARY_URL.format(symbol=urllib.parse.quote(symbol)),
        {"modules": modules},
    )
    result = data.get("quoteSummary", {}).get("result") or []
    if not result:
        return {
            "status": "unavailable",
            "reason": "Yahoo quoteSummary returned no data.",
        }
    return result[0]


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        return _get_json(url, params)
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason": str(exc),
            "url": url,
        }


def _source_caveats(*payloads: dict[str, Any]) -> list[str]:
    caveats = [
        "Market data comes from Yahoo Finance public endpoints and may be delayed.",
    ]
    for payload in payloads:
        if payload.get("status") == "unavailable":
            caveats.append(
                str(payload.get("reason") or "A data source was unavailable.")
            )
    return caveats


def _raw_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "raw" in value:
            return value["raw"]
        if "fmt" in value:
            return value["fmt"]
    return value


def _at(values: list[Any], index: int) -> Any:
    return values[index] if index < len(values) else None


def _normalize_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


TOOLS = [
    tool_schema(
        "company_profile",
        "Get company profile, exchange, sector, industry, website, and quote context.",
        {"symbol": SYMBOL_PROPERTY},
        ["symbol"],
    ),
    tool_schema(
        "quote_snapshot",
        "Get latest quote and recent price change from Yahoo Finance chart data.",
        {
            "symbol": SYMBOL_PROPERTY,
            "range": RANGE_5D_PROPERTY,
            "interval": INTERVAL_1D_PROPERTY,
        },
        ["symbol"],
    ),
    tool_schema(
        "price_history",
        "Get historical OHLCV bars and a close-price summary.",
        {
            "symbol": SYMBOL_PROPERTY,
            "range": RANGE_1MO_PROPERTY,
            "interval": INTERVAL_1D_PROPERTY,
        },
        ["symbol"],
    ),
    tool_schema(
        "financial_summary",
        "Get financial summary fields from Yahoo Finance quoteSummary data.",
        {"symbol": SYMBOL_PROPERTY},
        ["symbol"],
    ),
    tool_schema(
        "company_news",
        "Get recent Yahoo Finance news for a ticker symbol.",
        {
            "symbol": SYMBOL_PROPERTY,
            "count": COUNT_PROPERTY,
        },
        ["symbol"],
    ),
]


OPERATIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "company_profile": company_profile,
    "quote_snapshot": quote_snapshot,
    "price_history": price_history,
    "financial_summary": financial_summary,
    "company_news": company_news,
}


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
                "serverInfo": {"name": "marketdata-mcp", "version": "0.1.0"},
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
            output = operation(**arguments)
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
