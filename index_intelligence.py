"""Unified PhonePe Share.Market-inspired index detail view for StockWise AI."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from options_chain import render_options_chain

INDEXES = {
    "NIFTY 50": ("^NSEI", "NSE", "nifty50.json"),
    "BSE SENSEX": ("^BSESN", "BSE", "sensex.json"),
    "BANK NIFTY": ("^NSEBANK", "NSE", "banknifty.json"),
}

@st.cache_data(ttl=300, show_spinner=False)
def index_history(symbol, period="1y"):
    try:
        df = yf.Ticker(symbol).history(period=period, auto_adjust=False)
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def render_index_details():
    st.markdown("""<style>
    .sw-index-title{font-size:2rem;font-weight:750;color:#B9664E}
    div[data-testid="stMetric"]{border:1px solid #A5AD9166;border-radius:14px;padding:12px}
    </style>""", unsafe_allow_html=True)
    names = list(INDEXES)
    chosen = st.query_params.get("sw_index", names[0])
    if chosen not in INDEXES:
        chosen = names[0]
    c1, c2 = st.columns([1,5])
    with c1:
        if st.button("← Back", key="sw_index_back"):
            st.query_params.pop("sw_index", None)
            st.rerun()
    with c2:
        st.markdown('<div class="sw-index-title">Index Intelligence</div>', unsafe_allow_html=True)
    name = st.selectbox("Index", names, index=names.index(chosen), key="sw_index_selector")
    if name != chosen:
        st.query_params["sw_index"] = name
        st.rerun()
    symbol, exchange, filename = INDEXES[name]
    st.subheader(name)
    st.caption(f"{exchange} · Latest available daily market data; not an intraday quote")
    hist = index_history(symbol)
    if not hist.empty and "Close" in hist:
        close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        if len(close):
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) > 1 else None
            change = ((last / prev - 1) * 100) if prev else None
            st.metric("Latest close", f"{last:,.2f}", f"{change:+.2f}%" if change is not None else None)
            st.caption(f"Session date: {close.index[-1].date()}")
    else:
        st.warning("Index history is unavailable from Yahoo Finance.")
    tab_names = ["Overview", "Charts", "Stocks", "Technicals", "F&O", "Predictions", "AI Summary"]
    tabs = st.tabs(tab_names)
    with tabs[0]:
        st.subheader("Overview")
        if not hist.empty:
            st.line_chart(hist["Close"])
            st.caption("Historical daily closes; not live streaming data.")
        else:
            st.info("Overview data unavailable.")
    with tabs[1]:
        st.subheader("Charts")
        if not hist.empty:
            fig = go.Figure(go.Candlestick(x=hist.index,open=hist["Open"],high=hist["High"],low=hist["Low"],close=hist["Close"]))
            fig.update_layout(height=480, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chart data unavailable.")
    with tabs[2]:
        st.subheader("Constituent Stocks")
        st.info("Index constituents and official index weights require a maintained NSE/BSE constituent dataset. No holdings are invented.")
    with tabs[3]:
        st.subheader("Technicals")
        if not hist.empty and len(hist) >= 30:
            close = hist["Close"].astype(float)
            delta = close.diff()
            gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss.replace(0, float("nan"))
            rsi = 100 - 100 / (1 + rs)
            macd = close.ewm(span=12,adjust=False).mean() - close.ewm(span=26,adjust=False).mean()
            a,b,c = st.columns(3)
            a.metric("RSI (14)", f"{rsi.iloc[-1]:.1f}" if pd.notna(rsi.iloc[-1]) else "—")
            b.metric("MACD (12,26)", f"{macd.iloc[-1]:.2f}")
            c.metric("SMA 20", f"{close.rolling(20).mean().iloc[-1]:,.2f}")
            st.line_chart(pd.DataFrame({"Close":close,"SMA20":close.rolling(20).mean(),"SMA50":close.rolling(50).mean()}))
        else:
            st.info("Not enough historical data to calculate technical indicators.")
    with tabs[4]:
        st.subheader(f"{name} · F&O")
        path = Path("data/options_chain") / filename
        snapshot = None
        if path.exists():
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                st.error(f"Could not load options snapshot: {exc}")
        if isinstance(snapshot, dict):
            expiries = snapshot.get("expiries")
            if isinstance(expiries, dict) and expiries:
                expiry = st.selectbox("Expiry", list(expiries), key=f"sw_expiry_{filename}")
                records = expiries[expiry]
            else:
                expiry = snapshot.get("expiry")
                records = snapshot.get("records")
            render_options_chain(records=records,spot=snapshot.get("spot"),instrument=name,expiry=expiry,quote_time=snapshot.get("quote_time"))
        else:
            render_options_chain(instrument=name)
        st.caption("NSE index and BSE SENSEX contracts require exchange-compatible data. The absence of a snapshot is not zero OI.")
    with tabs[5]:
        st.subheader("Predictions")
        st.info("Index-specific validated forecasts are not yet connected. Stock-level model predictions must not be represented as index predictions.")
    with tabs[6]:
        st.subheader("AI Summary")
        if not hist.empty and len(hist) >= 21:
            close = hist["Close"].astype(float)
            ret = (close.iloc[-1]/close.iloc[-21]-1)*100
            st.write(f"20-session historical change: {ret:+.2f}%. This is descriptive, not a trading signal.")
        else:
            st.info("Insufficient historical data for a market summary.")
