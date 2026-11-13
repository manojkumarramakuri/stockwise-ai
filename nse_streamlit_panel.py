"""Official NSE market panel for the StockWise Streamlit dashboard.

Uses the existing FastAPI NSE MCP adapter. Refreshing the UI does not imply
exchange tick streaming; NSE MCP equity data may refresh about once a minute.
"""
from __future__ import annotations

import requests
import streamlit as st

API = "http://127.0.0.1:8000"

def _read(path: str):
    response = requests.get(f"{API}{path}", timeout=15)
    response.raise_for_status()
    return response.json()

def _metric(col, label: str, path: str, kind: str):
    with col:
        try:
            envelope = _read(path)
            payload = envelope.get("data") or {}
            data = payload.get(kind) or {}
            if not isinstance(data, dict) or not data:
                st.metric(label, "Unavailable")
                st.caption("NSE returned no quote")
                return
            price = data.get("lastTradedPrice") if kind == "stock" else data.get("last")
            change = data.get("perChange") if kind == "stock" else data.get("percChange")
            if price is None:
                st.metric(label, "Unavailable")
                return
            st.metric(label, f"{float(price):,.2f}", f"{float(change):+.2f}%" if change is not None else None)
            timestamp = data.get("latestTimestamp") if kind == "stock" else (payload.get("nseTimestamp") or data.get("timeVal"))
            st.caption(f"NSE MCP · Quote: {timestamp or 'time unavailable'}")
        except (requests.RequestException, ValueError, TypeError) as exc:
            st.metric(label, "Unavailable")
            st.caption(f"Provider error: {str(exc)[:90]}")

@st.fragment(run_every="15s")
def official_nse_market_panel():
    st.subheader("NSE Market Monitor")
    st.caption("Official NSE MCP · Latest available quotes, not tick-by-tick streaming")
    cols = st.columns(4)
    _metric(cols[0], "NIFTY 50", "/api/nse/index/NIFTY%2050", "index")
    _metric(cols[1], "NIFTY BANK", "/api/nse/index/NIFTY%20BANK", "index")
    _metric(cols[2], "RELIANCE", "/api/nse/quote/RELIANCE", "stock")
    _metric(cols[3], "HDFC BANK", "/api/nse/quote/HDFCBANK", "stock")
