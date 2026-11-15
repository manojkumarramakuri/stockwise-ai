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

RANGES = {
    "1D": ("1d", "5m"), "5D": ("5d", "15m"),
    "1M": ("1mo", "1d"), "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"), "1Y": ("1y", "1d"),
    "5Y": ("5y", "1d"), "10Y": ("10y", "1d"),
    "MAX": ("max", "1d"),
}

@st.cache_data(ttl=300, show_spinner=False)
def range_history(symbol, period, interval):
    try:
        data = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        return data if data is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def show_range_chart(symbol, chart_key):
    # The selector belongs BELOW the chart, like the supplied Share.Market reference.
    selected = st.session_state.get(chart_key, "1D")
    if selected not in RANGES:
        selected = "1D"
    period, interval = RANGES[selected]
    # Use recent intraday history and isolate the last actual trading session.
    if selected == "1D":
        data = range_history(symbol, "5d", "5m")
        if not data.empty:
            local_dates = pd.to_datetime(data.index).tz_convert("Asia/Kolkata").date if data.index.tz is not None else pd.to_datetime(data.index).date
            data = data[local_dates == local_dates[-1]]
    else:
        data = range_history(symbol, period, interval)
    if data.empty or not {"Open", "High", "Low", "Close"}.issubset(data.columns):
        st.warning(f"{selected} chart unavailable from the current provider.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data.index, y=data["Close"], mode="lines", name="Close", line=dict(color="#315BCB", width=2)))
        fig.update_layout(height=420, xaxis_rangeslider_visible=False, margin=dict(l=8,r=8,t=15,b=8), template="plotly_white")
        st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_plot")
        latest = data.index[-1]
        st.caption(f"{selected} · {interval} interval · Latest available candle: {latest} · Yahoo Finance (may be delayed)")
        if selected == "1D":
            st.caption("Displays the latest available trading session, including when the market is closed.")
    st.radio("Chart period", list(RANGES), index=list(RANGES).index(selected), horizontal=True, key=chart_key)


def show_constituents(name):
    import csv
    files = {
        "NIFTY 50": ["data/ind_nifty50list.csv", "data/indices/nifty50.csv"],
        "BANK NIFTY": ["data/ind_niftybanklist.csv", "data/indices/banknifty.csv"],
        "BSE SENSEX": ["data/sensex_constituents.csv", "data/indices/sensex.csv"],
    }
    source = next((Path(p) for p in files[name] if Path(p).is_file()), None)
    if source is None:
        st.warning("Official constituent list not installed. Add the latest exchange constituent CSV to enable breadth, gainers, losers and stock prices.")
        return
    try:
        constituents = pd.read_csv(source)
    except Exception as exc:
        st.error(f"Could not read constituent list: {exc}")
        return
    col = next((c for c in constituents.columns if c.lower().strip() in ("symbol","ticker","security code","security_code")), None)
    if col is None:
        st.warning("Constituent CSV needs a Symbol or Ticker column.")
        return
    rows = constituents.copy()
    st.caption(f"Constituent file: {source} · {len(rows)} rows. Membership date and index weights depend on source.")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if st.button("Load latest constituent prices", key="sw_constituent_prices"):
        symbols = rows[col].dropna().astype(str).str.strip().tolist()
        if name != "BSE SENSEX":
            symbols = [x if x.endswith((".NS",".BO")) else x+".NS" for x in symbols]
        else:
            symbols = [x if x.endswith((".NS",".BO")) else x+".BO" for x in symbols]
        prices = []
        progress = st.progress(0)
        for i, symbol in enumerate(symbols):
            try:
                history = yf.Ticker(symbol).history(period="5d", interval="1d")
                close = history["Close"].dropna()
                if len(close) >= 2 and close.iloc[-2] > 0:
                    prices.append({"Symbol":symbol,"Price":float(close.iloc[-1]),"Change %":float((close.iloc[-1]/close.iloc[-2]-1)*100)})
            except Exception:
                pass
            progress.progress((i+1)/max(1,len(symbols)))
        progress.empty()
        if prices:
            result = pd.DataFrame(prices).sort_values("Change %", ascending=False)
            adv = int((result["Change %"] > 0).sum())
            dec = int((result["Change %"] < 0).sum())
            unchanged = int((result["Change %"] == 0).sum())
            st.write(f"Advances: {adv} · Declines: {dec} · Unchanged: {unchanged} · Quotes received: {len(result)}/{len(symbols)}")
            left,right = st.columns(2)
            with left:
                st.markdown("**Top Gainers**")
                st.dataframe(result.head(10), hide_index=True, use_container_width=True)
            with right:
                st.markdown("**Top Losers**")
                st.dataframe(result.tail(10).sort_values("Change %"), hide_index=True, use_container_width=True)
        else:
            st.warning("No valid constituent price changes returned.")

def show_index_predictions(symbol):
    st.caption("Experimental index forecast, trained on historical daily closes; not the StockWise stock-level production model.")
    if not st.button("Train and evaluate index forecast", key="sw_index_forecast"):
        st.info("Select the button to run a chronological backtest and estimate the next close.")
        return
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error
    history = index_history(symbol, "5y")
    if history.empty or len(history) < 220:
        st.warning("Insufficient index history for a chronological evaluation.")
        return
    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    features = pd.DataFrame(index=close.index)
    for lag in [1,2,3,5,10,20]:
        features[f"return_{lag}"] = close.pct_change(lag)
    features["volatility_10"] = close.pct_change().rolling(10).std()
    features["sma20_gap"] = close / close.rolling(20).mean() - 1
    features["target_return"] = close.shift(-1) / close - 1
    clean = features.replace([float("inf"),float("-inf")],float("nan")).dropna()
    if len(clean) < 150:
        st.warning("Not enough valid model samples.")
        return
    x = clean.drop(columns="target_return")
    y = clean["target_return"]
    split = int(len(clean)*0.8)
    model = RandomForestRegressor(n_estimators=120, max_depth=7, min_samples_leaf=5, random_state=42, n_jobs=-1)
    model.fit(x.iloc[:split], y.iloc[:split])
    test_pred = model.predict(x.iloc[split:])
    actual = close.loc[x.index[split:]].to_numpy() * (1+y.iloc[split:].to_numpy())
    predicted = close.loc[x.index[split:]].to_numpy() * (1+test_pred)
    mae = mean_absolute_error(actual, predicted)
    baseline = close.loc[x.index[split:]].to_numpy()
    baseline_mae = mean_absolute_error(actual, baseline)
    latest = features.drop(columns="target_return").replace([float("inf"),float("-inf")],float("nan")).dropna().iloc[[-1]]
    next_return = float(model.predict(latest)[0])
    estimate = float(close.iloc[-1]) * (1+next_return)
    a,b,c = st.columns(3)
    a.metric("Next-session estimate", f"{estimate:,.2f}")
    b.metric("Holdout MAE", f"{mae:,.2f}")
    c.metric("No-change baseline MAE", f"{baseline_mae:,.2f}")
    st.caption(f"Chronological 80/20 split · {len(clean)-split} test sessions · Experimental one-session regression. No guarantee of accuracy.")

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
        show_range_chart(symbol, "sw_overview_range")
        st.caption("Market breadth and gainers/losers are in Stocks, based on installed constituent lists.")
    with tabs[1]:
        st.subheader("Charts")
        show_range_chart(symbol, "sw_charts_range")
    with tabs[2]:
        st.subheader("Constituent Stocks · Advances & Declines")
        show_constituents(name)
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
        show_index_predictions(symbol)
    with tabs[6]:
        st.subheader("AI Summary")
        if not hist.empty and len(hist) >= 21:
            close = hist["Close"].astype(float)
            ret = (close.iloc[-1]/close.iloc[-21]-1)*100
            st.write(f"20-session historical change: {ret:+.2f}%. This is descriptive, not a trading signal.")
        else:
            st.info("Insufficient historical data for a market summary.")
