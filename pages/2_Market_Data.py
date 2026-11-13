"""StockWise AI — integrated market-data explorer.

Reads the existing normalized SQLite database directly, so this page works
without requiring a separate FastAPI process. Missing feeds are shown honestly.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Market Data | StockWise AI", page_icon="📊", layout="wide")

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("STOCKWISE_MARKET_DB", str(ROOT / "data" / "stockwise_market.db")))

st.markdown("""
<style>
.block-container{padding-top:1.2rem;max-width:1500px}
div[data-testid="stMetric"]{background:rgba(116,83,190,.08);border:1px solid rgba(116,83,190,.2);padding:12px;border-radius:12px}
</style>
""", unsafe_allow_html=True)

def connect():
    if not DB_PATH.exists():
        return None
    con = sqlite3.connect(str(DB_PATH), timeout=15)
    con.row_factory = sqlite3.Row
    return con

def exists(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

def count(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if exists(con, table) else 0

def records(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]

st.title("Market Data")
st.caption("Mutual funds · Futures & Options · IPOs | Official-source data stored in your StockWise database")

con = connect()
if con is None:
    st.warning(f"Market database not found at {DB_PATH}. Your stock dashboard remains available. Run the existing market-data ingestion script to create/populate this database.")
    st.stop()

tables = ["mf_schemes", "mf_nav", "fno_files", "fno_rows", "ipo_records"]
counts = {t: count(con, t) for t in tables}
cols = st.columns(5)
for col, label, key in zip(cols, ["MF schemes", "NAV records", "F&O files", "F&O rows", "IPO source rows"], tables):
    col.metric(label, f"{counts[key]:,}")

if exists(con, "source_status"):
    with st.expander("Source health and ingestion history"):
        st.dataframe(pd.DataFrame(records(con, "SELECT source,status,records,message,updated_at FROM source_status ORDER BY source")), use_container_width=True, hide_index=True)

mf_tab, fno_tab, ipo_tab = st.tabs(["Mutual Funds", "Futures & Options", "IPOs"])

with mf_tab:
    st.subheader("Mutual fund scheme explorer")
    if not exists(con, "mf_schemes"):
        st.info("Mutual-fund scheme data has not been imported yet.")
    else:
        a,b,c = st.columns([2,1,1])
        q = a.text_input("Search scheme / code / fund house", key="mf_q")
        cat = b.text_input("Category contains", key="mf_cat")
        house = c.text_input("Fund house contains", key="mf_house")
        size = st.selectbox("Rows per page", [25,50,100,200], index=1)
        page = st.number_input("Page", min_value=1, value=1, step=1, key="mf_page")
        clauses=[]; params=[]
        if q.strip():
            clauses.append("(scheme_name LIKE ? OR scheme_code LIKE ? OR fund_house LIKE ?)")
            params += [f"%{q.strip()}%"]*3
        if cat.strip():
            clauses.append("scheme_category LIKE ?"); params.append(f"%{cat.strip()}%")
        if house.strip():
            clauses.append("fund_house LIKE ?"); params.append(f"%{house.strip()}%")
        where = " WHERE "+" AND ".join(clauses) if clauses else ""
        total = con.execute("SELECT COUNT(*) FROM mf_schemes"+where, params).fetchone()[0]
        rows = records(con, "SELECT scheme_code,scheme_name,fund_house,scheme_type,scheme_category,isin_growth,isin_dividend FROM mf_schemes"+where+" ORDER BY scheme_name LIMIT ? OFFSET ?", tuple(params)+(size,(page-1)*size))
        st.caption(f"{total:,} matching schemes")
        if rows:
            for row in rows:
                nav = con.execute("SELECT nav,nav_date,source FROM mf_nav WHERE scheme_code=? ORDER BY nav_date DESC LIMIT 1",(row["scheme_code"],)).fetchone() if exists(con,"mf_nav") else None
                row["Latest NAV"] = nav["nav"] if nav else None
                row["NAV date"] = nav["nav_date"] if nav else None
                row["NAV source"] = nav["source"] if nav else None
            df=pd.DataFrame(rows).rename(columns={"scheme_code":"Scheme code","scheme_name":"Scheme","fund_house":"Fund house","scheme_type":"Type","scheme_category":"Category","isin_growth":"ISIN growth","isin_dividend":"ISIN dividend"})
            st.dataframe(df,use_container_width=True,hide_index=True)
            choices={f'{r["scheme_name"]} ({r["scheme_code"]})':str(r["scheme_code"]) for r in rows}
            selected=st.selectbox("Inspect NAV history",["Choose scheme"]+list(choices))
            if selected!="Choose scheme" and exists(con,"mf_nav"):
                hist=records(con,"SELECT nav_date,nav,source FROM mf_nav WHERE scheme_code=? ORDER BY nav_date",(choices[selected],))
                if hist:
                    h=pd.DataFrame(hist); h["nav_date"]=pd.to_datetime(h["nav_date"],errors="coerce"); h=h.dropna(subset=["nav_date"]).set_index("nav_date")
                    st.line_chart(h["nav"]); st.dataframe(h.reset_index(),use_container_width=True,hide_index=True)
                else: st.info("No historical NAV imported for this scheme.")
        else: st.info("No schemes match these filters.")
        st.caption("Mutual-fund NAV is end-of-day valuation, not an intraday traded price. Always display the NAV date.")

with fno_tab:
    st.subheader("Exchange derivatives reports")
    st.caption("Only imported report rows are shown; no synthetic contracts are generated.")
    if not exists(con,"fno_rows") or counts["fno_rows"]==0:
        st.info("No verified F&O report rows have been imported yet. Import official NSE derivatives reports to populate this section.")
    else:
        segment=st.text_input("Segment filter",key="fno_filter")
        sql="SELECT filename,segment,row_number,payload,imported_at FROM fno_rows"
        args=()
        if segment.strip(): sql+=" WHERE segment LIKE ?"; args=(f"%{segment.strip()}%",)
        sql+=" ORDER BY imported_at DESC LIMIT 500"
        rows=records(con,sql,args)
        for r in rows:
            try:r["payload"]=json.loads(r["payload"])
            except (ValueError,TypeError):pass
        st.dataframe(pd.json_normalize(rows),use_container_width=True,hide_index=True)

with ipo_tab:
    st.subheader("IPO source records")
    st.caption("Captured source-table records are not automatically equivalent to verified, currently open IPO issues.")
    if not exists(con,"ipo_records") or counts["ipo_records"]==0:
        st.info("No IPO source records imported yet.")
    else:
        source=st.selectbox("Source filter",["All","SEBI","NSE","BSE"])
        sql="SELECT source,source_url,table_number,row_number,payload,captured_at FROM ipo_records"
        args=()
        if source!="All": sql+=" WHERE source LIKE ?"; args=(f"%{source}%",)
        sql+=" ORDER BY captured_at DESC LIMIT 500"
        rows=records(con,sql,args)
        for r in rows:
            try:r["payload"]=json.loads(r["payload"])
            except (ValueError,TypeError):pass
        st.dataframe(pd.json_normalize(rows),use_container_width=True,hide_index=True)
        st.warning("Verify issue name, dates, price band and status against the linked official source before labelling any record as an active IPO.")
con.close()
