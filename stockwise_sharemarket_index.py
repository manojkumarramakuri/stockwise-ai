"""Share.Market-inspired dark index detail, reusing StockWise index analytics."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

def _members(name):
    paths = {
        "NIFTY 50": ["data/ind_nifty50list.csv", "data/indices/nifty50.csv"],
        "BANK NIFTY": ["data/ind_niftybanklist.csv", "data/indices/banknifty.csv"],
        "BSE SENSEX": ["data/sensex_constituents.csv", "data/indices/sensex.csv"],
    }
    path = next((Path(p) for p in paths[name] if Path(p).is_file()), None)
    if path is None:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        col = next((c for c in df if c.lower().strip() in ("symbol","ticker","security code","security_code")), None)
        if col is None:
            return pd.DataFrame()
        suffix = ".BO" if name == "BSE SENSEX" else ".NS"
        df["Ticker"] = df[col].astype(str).str.strip().map(lambda v: v if v.endswith((".NS",".BO")) else v + suffix)
        namecol = next((c for c in df if c.lower().strip() in ("company name","company","name","security name")), None)
        df["Company"] = df[namecol].astype(str) if namecol else df[col].astype(str)
        return df.drop_duplicates("Ticker")
    except (OSError, ValueError, KeyError):
        return pd.DataFrame()

def _stock_rows(df, key):
    if df.empty:
        st.info("No verified constituent quotes available.")
        return
    for i, (_, r) in enumerate(df.iterrows()):
        change = float(r["Change %"])
        color = "#58c894" if change >= 0 else "#e36c77"
        bg = "#10291d" if change >= 0 else "#30191e"
        price = float(r["Price"])
        symbol = str(r["Ticker"]).split(".")[0]
        left, right = st.columns([3, 1.4], vertical_alignment="center")
        with left:
        if st.button(f"{str(r['Company'])} · {symbol}", key=f'sw_open_{key}_{i}', use_container_width=True):
            ticker=str(r['Ticker'])
            st.session_state['sw_selected_stock']=ticker
            st.session_state['selected_stock']=ticker
            st.query_params['sw_symbol']=ticker
            st.query_params['sw_view']='detail'
            st.rerun()
        st.markdown(f'<div class="sw-stock-symbol">{_esc(symbol)}</div>',unsafe_allow_html=True)
        with right:
            st.markdown(f'<div class="sw-stock-price" style="background:{bg};color:{color}">₹{price:,.2f}</div><div class="sw-stock-change" style="color:{color}">{change:+.2f}%</div>', unsafe_allow_html=True)
        st.markdown('<div class="sw-stock-divider"></div>', unsafe_allow_html=True)

def _esc(s):
    import html
    return html.escape(s, quote=True)

def _breadth(name, constituent_quotes):
    members = _members(name)
    if members.empty:
        st.warning("Constituent membership CSV not found. Install a current exchange list to enable breadth and movers.")
        return
    quotes = constituent_quotes(tuple(members["Ticker"].tolist()))
    if quotes.empty:
        st.warning("Latest constituent prices unavailable; no simulated prices are displayed.")
        return
    df = members[["Ticker","Company"]].merge(quotes, on="Ticker", how="left")
    valid = df.dropna(subset=["Price","Change %"]).copy()
    if valid.empty:
        st.warning("No verified price changes returned.")
        return
    advances = int((valid["Change %"] > 0).sum())
    declines = int((valid["Change %"] < 0).sum())
    unchanged = int((valid["Change %"] == 0).sum())
    total = len(valid)
    st.markdown("### Advances & Declines")
    green = advances / total * 100
    neutral = unchanged / total * 100
    st.markdown(f'<div class="sw-breadth"><span style="width:{green:.3f}%;background:#50aa78"></span><span style="width:{neutral:.3f}%;background:#777"></span><span style="flex:1;background:#ad4b55"></span></div>',unsafe_allow_html=True)
    a,b=st.columns(2)
    a.markdown(f'<span style="color:#58c894">Advances: {advances}</span>',unsafe_allow_html=True)
    b.markdown(f'<div style="text-align:right;color:#e36c77">Declines: {declines}</div>',unsafe_allow_html=True)
    choice=st.radio("Market movers",["Gainers","Losers"],horizontal=True,label_visibility="collapsed",key=f"sw_movers_{name}")
    ordered=valid.sort_values("Change %",ascending=(choice=="Losers"))
    if choice=="Gainers":
        ordered=ordered[ordered["Change %"]>0]
    else:
        ordered=ordered[ordered["Change %"]<0]
    _stock_rows(ordered.head(12),name)
    sessions=", ".join(sorted(valid["Session"].dropna().astype(str).unique())) if "Session" in valid else "unknown"
    st.caption(f"Verified quotes: {total}/{len(members)} constituents · Session(s): {sessions} · Yahoo Finance; data may be delayed.")
    if total < len(members):
        st.caption("Breadth is calculated from available quotes only, not the full index.")

def render():
    from index_intelligence import INDEXES,index_history,show_range_chart,show_constituents,show_index_predictions
    from index_intelligence import constituent_quotes
    from options_chain import render_options_chain
    import json
    st.markdown("""<style>
    /* Keep the host application theme */
    .block-container{max-width:1120px;padding-top:1.1rem}
    .sw-index-head{font-size:1.65rem;font-weight:750;color:#17233b}
    .sw-index-price{font-size:1.3rem;font-weight:700}
    .sw-stock-name{font-size:1.03rem;font-weight:650;color:#17233b}
    .sw-stock-symbol{font-size:.85rem;color:#737985;margin-top:4px}
    .sw-stock-price{font-size:1.12rem;font-weight:700;text-align:right;border-radius:7px;padding:4px 9px}
    .sw-stock-change{text-align:right;font-size:.86rem;margin-top:4px}
    .sw-stock-divider{border-bottom:1px solid #e2e5e9;margin:10px 0 16px}
    .sw-breadth{display:flex;height:8px;border-radius:20px;overflow:hidden;margin:20px 0}
    div[data-testid="stTabs"] button{color:#657080}
    div[data-testid="stTabs"] button[aria-selected="true"]{color:#315bcb!important}
    div[data-testid="stMetric"]{background:#fff;border:1px solid #e0e5eb}
    </style>""",unsafe_allow_html=True)
    names=list(INDEXES)
    selected=st.query_params.get("sw_index",names[0])
    if selected not in INDEXES:
        selected=names[0]
    back,selector=st.columns([1,4],vertical_alignment="center")
    with back:
        if st.button("← Back",key="sw_dark_index_back"):
            st.query_params.pop("sw_index",None)
            st.rerun()
    with selector:
        name=st.selectbox("Index",names,index=names.index(selected),label_visibility="collapsed",key="sw_dark_index_choice")
        if name!=selected:
            st.query_params["sw_index"]=name
            st.rerun()
    symbol,exchange,filename=INDEXES[name]
    hist=index_history(symbol)
    st.markdown(f'<div class="sw-index-head">{_esc(name.title())}</div>',unsafe_allow_html=True)
    if not hist.empty and "Close" in hist:
        close=pd.to_numeric(hist["Close"],errors="coerce").dropna()
        if len(close)>1 and float(close.iloc[-2])!=0:
            last=float(close.iloc[-1]);delta=last-float(close.iloc[-2]);pct=delta/float(close.iloc[-2])*100
            color="#58c894" if delta>=0 else "#e36c77"
            st.markdown(f'<div class="sw-index-price" style="color:{color}">{last:,.2f} &nbsp; <span style="font-size:1rem;font-weight:400">{delta:+,.2f} ({pct:+.2f}%)</span></div>',unsafe_allow_html=True)
            st.caption(f"{exchange} · Latest available session: {close.index[-1].date()} · Not a live tick")
    else:
        st.warning("Index price currently unavailable.")
    tabs=st.tabs(["Overview","Charts","Stocks","Technicals","F&O","Predictions","AI Summary"])
    with tabs[0]:
        show_range_chart(symbol, 'sw_overview_range')
        st.markdown('### Open & Close')
        if not hist.empty and {'Open','High','Low','Close'}.issubset(hist.columns):
            daily=hist.dropna(subset=['Open','High','Low','Close'])
            if not daily.empty:
                last=daily.iloc[-1]
                prev=float(daily['Close'].iloc[-2]) if len(daily)>1 else None
                a,b,c=st.columns(3)
                a.metric('Open', f"{float(last['Open']):,.2f}")
                b.metric('Close', f"{float(last['Close']):,.2f}")
                c.metric('Previous Close', f'{prev:,.2f}' if prev is not None else '—')
                d,e=st.columns(2)
                d.metric('Day High', f"{float(last['High']):,.2f}")
                e.metric('Day Low', f"{float(last['Low']):,.2f}")
                st.caption(f'Latest OHLC session: {daily.index[-1].date()}')
        else:
            st.info('OHLC data unavailable')
        _breadth(name,constituent_quotes)
    with tabs[1]:
        show_range_chart(symbol,"sw_dark_chart_range")
    with tabs[2]:
        show_constituents(name)
    with tabs[3]:
        if not hist.empty and len(hist)>=50:
            close=hist["Close"].astype(float)
            delta=close.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
            loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
            rs=gain/loss.replace(0,float("nan"));rsi=100-100/(1+rs)
            ema12=close.ewm(span=12,adjust=False).mean();ema26=close.ewm(span=26,adjust=False).mean()
            macd=ema12-ema26; signal=macd.ewm(span=9,adjust=False).mean()
            cols=st.columns(4)
            for col,(label,val) in zip(cols,[("RSI 14",rsi.iloc[-1]),("MACD",macd.iloc[-1]),("MACD Signal",signal.iloc[-1]),("SMA 20",close.rolling(20).mean().iloc[-1])]):
                col.metric(label,f"{val:,.2f}" if pd.notna(val) else "—")
            fig=go.Figure()
            for label,values in [("Close",close),("SMA 20",close.rolling(20).mean()),("SMA 50",close.rolling(50).mean())]:
                fig.add_trace(go.Scatter(x=values.index,y=values,name=label))
            fig.update_layout(template="plotly_white",paper_bgcolor="#fff",plot_bgcolor="#fff",height=400)
            st.plotly_chart(fig,use_container_width=True)
        else:
            st.info("Insufficient price history for indicators.")
    with tabs[4]:
        path=Path("data/options_chain")/filename
        snapshot=None
        if path.is_file():
            try: snapshot=json.loads(path.read_text(encoding="utf-8"))
            except (OSError,ValueError): st.warning("Invalid options snapshot.")
        if isinstance(snapshot,dict):
            expiries=snapshot.get("expiries")
            if isinstance(expiries,dict) and expiries:
                expiry=st.selectbox("Expiry",list(expiries),key=f"sw_dark_expiry_{filename}")
                records=expiries[expiry]
            else:
                expiry=snapshot.get("expiry");records=snapshot.get("records")
            render_options_chain(records=records,spot=snapshot.get("spot"),instrument=name,expiry=expiry,quote_time=snapshot.get("quote_time"))
        else:
            render_options_chain(instrument=name)
    with tabs[5]:
        show_index_predictions(symbol)
    with tabs[6]:
        if not hist.empty and len(hist)>=21:
            close=hist["Close"].astype(float)
            st.write(f"20-session historical change: {(close.iloc[-1]/close.iloc[-21]-1)*100:+.2f}%. Historical observation, not a trading recommendation.")
        else:
            st.info("Insufficient history for summary.")
