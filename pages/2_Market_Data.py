"""StockWise AI — Mutual Funds, F&O and IPO data page.

Streamlit auto-discovers this file when saved under pages/.
Requires the FastAPI market-data router documented in market_data/README.md.
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Market Data | StockWise AI", page_icon="📊", layout="wide")

API_BASE = os.getenv("STOCKWISE_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_ROOT = f"{API_BASE}/api/market-data"

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; max-width: 1450px;}
    div[data-testid="stMetric"] {background:#f7f5ff;border:1px solid #e7e1ff;
      padding:14px;border-radius:12px;}
    .muted {color:#777}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Market Data")
st.caption("Mutual funds · Futures & Options · IPOs — sourced from the connected market-data database")


def api_get(path: str, params: dict[str, Any] | None = None) -> dict:
    try:
        response = requests.get(f"{API_ROOT}/{path.lstrip('/')}", params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(
            f"Market-data API is not reachable at {API_BASE}. "
            "Confirm the FastAPI router is included in api/main.py and the API is running. "
            f"Details: {exc}"
        )
        st.stop()


def show_source_status() -> None:
    status = api_get("status")
    counts = status.get("counts", {})
    cols = st.columns(5)
    metrics = [
        ("MF schemes", counts.get("mf_schemes", 0)),
        ("NAV rows", counts.get("mf_nav", 0)),
        ("F&O files", counts.get("fno_files", 0)),
        ("F&O rows", counts.get("fno_rows", 0)),
        ("IPO source rows", counts.get("ipo_records", 0)),
    ]
    for col, (label, value) in zip(cols, metrics):
        col.metric(label, f"{value:,}")
    sources = status.get("sources", [])
    if sources:
        with st.expander("Data source health and last ingestion", expanded=False):
            st.dataframe(pd.DataFrame(sources), use_container_width=True, hide_index=True)


show_source_status()
tab_mf, tab_fno, tab_ipo = st.tabs(["Mutual Funds", "Futures & Options", "IPOs"])

with tab_mf:
    st.subheader("Explore mutual funds")
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("Search scheme or scheme code", placeholder="e.g. HDFC, SBI, 120503")
    category = c2.text_input("Category contains", placeholder="e.g. equity")
    fund_house = c3.text_input("Fund house contains", placeholder="e.g. ICICI")
    page_size = st.selectbox("Rows per page", [25, 50, 100, 200], index=1, key="mf_page_size")
    page = st.number_input("Page", min_value=1, value=1, step=1, key="mf_page")
    data = api_get("mutual-funds", {
        "q": query, "category": category, "fund_house": fund_house,
        "limit": page_size, "offset": (page - 1) * page_size,
    })
    st.caption(f'{data.get("total", 0):,} matching schemes')
    items = data.get("items", [])
    if items:
        frame = pd.DataFrame(items)
        frame["Latest NAV"] = frame["latest_nav"].apply(
            lambda x: x.get("nav") if isinstance(x, dict) else None
        )
        frame["NAV date"] = frame["latest_nav"].apply(
            lambda x: x.get("nav_date") if isinstance(x, dict) else None
        )
        frame["scheme_code"] = frame["scheme_code"].astype(str)
        visible = frame.rename(columns={
            "scheme_code": "Scheme code", "scheme_name": "Scheme",
            "fund_house": "Fund house", "scheme_type": "Type",
            "scheme_category": "Category", "isin_growth": "ISIN growth",
            "isin_dividend": "ISIN dividend",
        })
        cols = [c for c in ["Scheme code", "Scheme", "Fund house", "Type",
                            "Category", "Latest NAV", "NAV date"] if c in visible]
        st.dataframe(visible[cols], use_container_width=True, hide_index=True)
        codes = {f'{x["scheme_name"]} ({x["scheme_code"]})': str(x["scheme_code"]) for x in items}
        selected = st.selectbox("View imported NAV history", ["Select a scheme"] + list(codes))
        if selected != "Select a scheme":
            history = api_get(f'mutual-funds/{codes[selected]}/nav', {"limit": 1000})
            nav_rows = history.get("items", [])
            if nav_rows:
                hist = pd.DataFrame(nav_rows)
                hist["nav_date"] = pd.to_datetime(hist["nav_date"], errors="coerce")
                hist = hist.dropna(subset=["nav_date"]).sort_values("nav_date")
                st.line_chart(hist.set_index("nav_date")["nav"])
                st.dataframe(hist, use_container_width=True, hide_index=True)
            else:
                st.info("No NAV history has been imported for this scheme yet.")
    else:
        st.info("No schemes match these filters. Clear a filter or check the source status above.")
    st.caption("NAV is mutual-fund end-of-day NAV, not an intraday traded price. The date is shown with each value.")

with tab_fno:
    st.subheader("Futures & Options reports")
    st.caption("Only imported source rows are displayed. Empty data is not replaced with sample contracts.")
    segment = st.text_input("Filter report segment", placeholder="Optional segment filter", key="fno_segment")
    fno = api_get("fno", {"segment": segment, "limit": 200, "offset": 0})
    st.metric("Imported report rows", f'{fno.get("total", 0):,}')
    if fno.get("items"):
        fno_frame = pd.json_normalize(fno["items"])
        st.dataframe(fno_frame, use_container_width=True, hide_index=True)
    else:
        st.info(fno.get("message") or "No F&O report rows are currently available.")
        st.markdown(
            "The NSE report downloader still needs a verified downloadable report endpoint. "
            "This page will populate automatically when real report files are imported."
        )

with tab_ipo:
    st.subheader("IPO source data")
    source = st.selectbox("Source", ["All sources", "SEBI", "NSE", "BSE"])
    ipo = api_get("ipos", {
        "source": "" if source == "All sources" else source,
        "limit": 200, "offset": 0,
    })
    st.metric("Captured source rows", f'{ipo.get("total", 0):,}')
    if ipo.get("items"):
        ipo_frame = pd.json_normalize(ipo["items"])
        st.dataframe(ipo_frame, use_container_width=True, hide_index=True)
        st.warning(
            "These are captured exchange/regulator source-table rows. They are not yet "
            "normalized and verified IPO issue listings; confirm issue name, dates, price band "
            "and status against the linked official source before presenting them as active IPOs."
        )
    else:
        st.info(ipo.get("message") or "No IPO source rows have been imported.")
