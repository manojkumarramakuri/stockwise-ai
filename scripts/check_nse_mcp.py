"""Discover official NSE market tools without scraping the NSE website.

Run:
  pip install 'mcp>=1.0'
  python scripts/check_nse_mcp.py

The NSE CM Market service is delayed 1-3 minutes, not a tick feed.
Read NSE usage terms before republishing or training models on its data.
"""
from __future__ import annotations
import asyncio
import json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVERS = {
    "cm-market": "https://mcp.nseindia.in/cmmkt/mcp",
    "bhavcopy": "https://mcp.nseindia.in/bhavcopy/cm/mcp",
}

async def inspect(name: str, url: str):
    print(f"\n=== Official NSE {name}: {url} ===")
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                for tool in result.tools:
                    print(json.dumps({
                        "name": tool.name,
                        "description": (tool.description or "")[:160],
                        "inputSchema": tool.inputSchema,
                    }, ensure_ascii=False))
                print(f"Discovered {len(result.tools)} tools.")
    except Exception as exc:
        print(f"Connection failed: {type(exc).__name__}: {exc}")

async def main():
    for name, url in SERVERS.items():
        await inspect(name, url)

if __name__ == "__main__":
    asyncio.run(main())
