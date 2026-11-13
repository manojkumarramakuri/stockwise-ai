"""NSE index overview and reusable stock quote helpers for StockWise AI.

No fixed stock tickers on the home page. Quote freshness is always disclosed.
"""
from __future__ import annotations

import requests
import streamlit as st

API = "http://127.0.0.1:8000"

def nse_quote(symbol: str) -> dict:
    """Fetch the latest available NSE quote for the selected stock."""
    symbol = symbol.strip().upper().removesuffix(".NS")
    if not symbol or symbol.endswith(".BO"):
        return {}
    response = requests.get(f"{API}/api/nse/quote/{symbol}", timeout=15)
    response.raise_for_status()
    envelope = response.json()
    stock = (envelope.get("data") or {}).get("stock") or {}
    if not stock or stock.get("lastTradedPrice") is None:
        return {}
    return {
        "symbol": stock.get("symbol", symbol),
        "price": stock["lastTradedPrice"],
        "change_pct": stock.get("perChange"),
        "volume": stock.get("volume"),
        "timestamp": stock.get("latestTimestamp"),
        "source": "NSE official MCP",
        "retrieved_at_utc": envelope.get("retrieved_at_utc"),
    }

def selected_stock_quote(symbol: str):
    """Call inside a stock detail view after selecting a ticker."""
    try:
        quote = nse_quote(symbol)
        if not quote:
            st.info("No NSE quote available for this symbol. Historical charts remain available.")
            return
        delta = quote["change_pct"]
        st.metric(
            f"{quote['symbol']} · NSE",
            f"₹{float(quote['price']):,.2f}",
            f"{float(delta):+.2f}%" if delta is not None else None,
        )
        st.caption(f"Latest available NSE quote: {quote['timestamp'] or 'timestamp unavailable'}")
    except (requests.RequestException, ValueError, TypeError) as exc:
        st.warning(f"NSE quote unavailable: {str(exc)[:120]}")

def _index_metric(col, label: str, name: str):
    with col:
        try:
            response = requests.get(f"{API}/api/nse/index/{requests.utils.quote(name)}", timeout=15)
            response.raise_for_status()
            envelope = response.json()
            payload = envelope.get("data") or {}
            data = payload.get("index") or {}
            price = data.get("last")
            if price is None:
                st.metric(label, "Unavailable")
                return
            change = data.get("percChange")
            st.metric(label, f"{float(price):,.2f}", f"{float(change):+.2f}%" if change is not None else None)
            st.caption(f"NSE · {payload.get('nseTimestamp') or data.get('timeVal') or 'time unavailable'}")
        except (requests.RequestException, ValueError, TypeError) as exc:
            st.metric(label, "Unavailable")
            st.caption(f"NSE unavailable: {str(exc)[:80]}")

@st.fragment(run_every="30s")
def official_nse_market_panel():
    st.subheader("Market indices")
    st.caption("Official NSE MCP · Latest available quotes; not tick-by-tick streaming")
    cols = st.columns(2)
    _index_metric(cols[0], "NIFTY 50", "NIFTY 50")
    _index_metric(cols[1], "NIFTY BANK", "NIFTY BANK")
