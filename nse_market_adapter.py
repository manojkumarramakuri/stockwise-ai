"""Official NSE MCP market-data adapter for StockWise AI.

Quotes are delayed/latest available, not tick-by-tick exchange streaming.
Keep NSE data out of ML training/redistribution unless usage terms permit.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

NSE_MCP_URL = os.getenv("NSE_MCP_URL", "https://mcp.nseindia.in/cmmkt/mcp")
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 60
_LOCK = asyncio.Lock()


async def _call(tool: str, arguments: dict) -> dict:
    key = json.dumps([tool, arguments], sort_keys=True)
    async with _LOCK:
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL:
            return {**cached[1], "cache_hit": True}

    async with streamablehttp_client(NSE_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments=arguments)
            if result.isError:
                details = "; ".join(str(getattr(x, "text", x)) for x in result.content)
                raise RuntimeError(details or "NSE tool reported an error")
            # Prefer structuredContent if supplied; otherwise decode text JSON.
            payload = result.structuredContent
            if payload is None:
                pieces = []
                for item in result.content:
                    value = getattr(item, "text", None)
                    if value is not None:
                        try:
                            pieces.append(json.loads(value))
                        except json.JSONDecodeError:
                            pieces.append(value)
                payload = pieces[0] if len(pieces) == 1 else pieces
            output = {
                "provider": "NSE official MCP",
                "tool": tool,
                "data": payload,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "realtime_verified": False,
                "note": "Latest available NSE MCP data; provider refresh may be approximately 1 minute or longer.",
                "cache_hit": False,
            }
            async with _LOCK:
                _CACHE[key] = (time.monotonic(), output)
            return output


async def discover_nse_tools() -> dict:
    async with streamablehttp_client(NSE_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return {
                "provider": "NSE official MCP",
                "url": NSE_MCP_URL,
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "tools": [
                    {"name": t.name, "description": (t.description or "")[:300],
                     "input_schema": t.inputSchema}
                    for t in result.tools
                ],
            }


def register_nse_routes(app):
    from fastapi import HTTPException

    async def safe_call(tool: str, args: dict):
        try:
            return await _call(tool, args)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"NSE service unavailable: {exc}")

    @app.get("/api/nse/tools")
    async def nse_tools():
        try:
            return await discover_nse_tools()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"NSE MCP unavailable: {exc}")

    @app.get("/api/nse/quote/{symbol}")
    async def nse_quote(symbol: str):
        symbol = symbol.strip().upper().removesuffix(".NS")
        if not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol):
            raise HTTPException(status_code=400, detail="Invalid NSE symbol")
        return await safe_call("cm_get_stock_quote", {"symbol": symbol})

    @app.get("/api/nse/index/{name}")
    async def nse_index(name: str):
        name = name.strip().upper()
        if not re.fullmatch(r"[A-Z0-9 &-]{2,64}", name):
            raise HTTPException(status_code=400, detail="Invalid index name")
        return await safe_call("cm_get_index_quote", {"indexName": name})

    @app.get("/api/nse/equities")
    async def nse_equities(limit: int = 20, prefix: str = ""):
        if not 1 <= limit <= 500 or not re.fullmatch(r"[A-Za-z0-9&-]{0,32}", prefix):
            raise HTTPException(status_code=400, detail="Invalid limit or prefix")
        return await safe_call("cm_get_equity_stocks", {
            "limit": limit, "symbolFilter": prefix.upper()
        })

    @app.get("/api/nse/movers")
    async def nse_movers(limit: int = 10, index: str = ""):
        if not 1 <= limit <= 50 or index not in ("", "NIFTY", "BANKNIFTY", "NIFTYNEXT50"):
            raise HTTPException(status_code=400, detail="Invalid limit or index")
        return await safe_call("nse_get_market_movers", {"indexName": index, "limit": limit})

    @app.get("/api/nse/status")
    async def nse_status():
        return await safe_call("cm_get_data_status", {})
