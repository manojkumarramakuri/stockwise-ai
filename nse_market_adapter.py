"""Opt-in NSE MCP discovery for StockWise AI.

This module deliberately does NOT guess NSE tool names or scrape NSE web pages.
NSE market data may be delayed and subject to redistribution/training restrictions.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

NSE_MCP_URL = os.getenv("NSE_MCP_URL", "https://mcp.nseindia.in/cmmkt/mcp")


async def discover_nse_tools() -> dict:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        raise RuntimeError("Install the optional dependency: pip install 'mcp>=1.0'") from exc

    async with streamablehttp_client(NSE_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return {
                "provider": "NSE official MCP",
                "url": NSE_MCP_URL,
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": "Discovery only; no quote streaming or model-training permission implied.",
                "tools": [
                    {
                        "name": tool.name,
                        "description": (tool.description or "")[:300],
                        "input_schema": tool.inputSchema,
                    }
                    for tool in tools.tools
                ],
            }


def register_nse_routes(app):
    from fastapi import HTTPException

    @app.get("/api/nse/tools")
    async def nse_tools():
        try:
            return await discover_nse_tools()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"NSE MCP unavailable: {exc}")
