from __future__ import annotations
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

st.set_page_config(page_title='StockWise AI', page_icon='📈', layout='wide', initial_sidebar_state='expanded')

# --------------------------- Styling ---------------------------
st.markdown('''
<style>
.block-container{padding-top:1.2rem;padding-bottom:2rem;max-width:none;width:100%;padding-left:2rem;padding-right:2rem}
[data-testid="stMetric"]{background:rgba(120,120,120,.08);padding:14px;border-radius:12px;border:1px solid rgba(128,128,128,.18)}
</style>
''', unsafe_allow_html=True)

st.title('📈 StockWise AI')
st.caption('Indian equity market dashboard • NSE & BSE • Technical analysis • CRISP insights • Machine-learning estimates')

@st.cache_data(ttl=300, show_spinner=False)
def get_index_snapshot(symbol: str):
    """Return the latest two available daily index closes; never synthesize missing quotes."""
    try:
        hist = yf.Ticker(symbol).history(period='5d', interval='1d', auto_adjust=True)
        if hist is None or hist.empty or 'Close' not in hist:
            return None
        close = pd.to_numeric(hist['Close'], errors='coerce').dropna()
        if close.empty:
            return None
        latest = float(close.iloc[-1])
        previous = float(close.iloc[-2]) if len(close) > 1 else latest
        change = (latest / previous - 1) * 100 if previous else 0.0
        return {'value': latest, 'change': change, 'date': close.index[-1].strftime('%d %b %Y')}
    except Exception:
        return None

st.subheader('Indian market indices')
index_specs = [
    ('NIFTY 50', '^NSEI'),
    ('BSE SENSEX', '^BSESN'),
    ('BANK NIFTY', '^NSEBANK'),
]
index_cols = st.columns(3)
for col, (label, symbol) in zip(index_cols, index_specs):
    snapshot = get_index_snapshot(symbol)
    if snapshot:
        col.metric(label, f"{snapshot['value']:,.2f}", f"{snapshot['change']:+.2f}%")
        col.caption(f"Latest available close: {snapshot['date']} · Yahoo Finance")
    else:
        col.metric(label, '—')
        col.caption('Index quote currently unavailable from provider')
st.divider()

# Curated searchable universe. Any valid NSE/BSE symbol can also be entered manually.
STOCKS = {
    'Reliance Industries': ('RELIANCE', '500325'),
    'Tata Consultancy Services': ('TCS', '532540'),
    'HDFC Bank': ('HDFCBANK', '500180'),
    'ICICI Bank': ('ICICIBANK', '532174'),
    'Infosys': ('INFY', '500209'),
    'State Bank of India': ('SBIN', '500112'),
    'Bharti Airtel': ('BHARTIARTL', '532454'),
    'ITC': ('ITC', '500875'),
    'Larsen & Toubro': ('LT', '500510'),
    'Tata Motors': ('TATAMOTORS', '500570'),
    'Tata Steel': ('TATASTEEL', '500470'),
    'Wipro': ('WIPRO', '507685'),
    'Axis Bank': ('AXISBANK', '532215'),
    'Kotak Mahindra Bank': ('KOTAKBANK', '500247'),
    'Maruti Suzuki': ('MARUTI', '532500'),
    'Mahindra & Mahindra': ('M&M', '500520'),
    'Hindustan Unilever': ('HINDUNILVR', '500696'),
    'Sun Pharma': ('SUNPHARMA', '524715'),
    'NTPC': ('NTPC', '532555'),
    'Power Grid': ('POWERGRID', '532898'),
    'Adani Enterprises': ('ADANIENT', '512599'),
    'Bajaj Finance': ('BAJFINANCE', '500034'),
    'Bajaj Finserv': ('BAJAJFINSV', '532978'),
    'Asian Paints': ('ASIANPAINT', '500820'),
    'Titan Company': ('TITAN', '500114'),
    'Zomato': ('ETERNAL', '543320'),
    'HCL Technologies': ('HCLTECH', '532281'),
    'Tech Mahindra': ('TECHM', '532755'),
    'ONGC': ('ONGC', '500312'),
    'Coal India': ('COALINDIA', '533278'),
}
PERIODS = {'1D': ('1d', '5m'), '3M': ('3mo', '1d'), '6M': ('6mo', '1d'), '1Y': ('1y', '1d'), '5Y': ('5y', '1wk'), 'MAX': ('max', '1mo')}

# --------------------------- Data functions ---------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    for c in ['Open','High','Low','Close','Volume']:
        if c not in df:
            df[c] = np.nan
    return df.dropna(subset=['Close'])

@st.cache_data(ttl=1800, show_spinner=False)
def get_info(symbol: str) -> dict:
    try:
        return yf.Ticker(symbol).info or {}
    except Exception:
        return {}

@st.cache_data(ttl=1800, show_spinner=False)
def get_shareholders(symbol: str):
    try:
        t = yf.Ticker(symbol)
        major = t.major_holders
        inst = t.institutional_holders
        mutual = t.mutualfund_holders
        return major, inst, mutual
    except Exception:
        return None, None, None

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    close, high, low, vol = d['Close'], d['High'], d['Low'], d['Volume'].fillna(0)
    d['SMA20'] = close.rolling(20).mean(); d['SMA50'] = close.rolling(50).mean(); d['SMA200'] = close.rolling(200).mean()
    d['EMA12'] = close.ewm(span=12, adjust=False).mean(); d['EMA26'] = close.ewm(span=26, adjust=False).mean()
    d['MACD'] = d['EMA12'] - d['EMA26']; d['MACD_signal'] = d['MACD'].ewm(span=9, adjust=False).mean()
    delta = close.diff(); gain = delta.clip(lower=0).rolling(14).mean(); loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan); d['RSI'] = 100 - (100/(1+rs)); d['RSI'] = d['RSI'].fillna(50)
    prev = close.shift(1)
    tr = pd.concat([(high-low), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    d['ATR'] = tr.rolling(14).mean()
    mf_mult = (((close-low) - (high-close)) / (high-low).replace(0, np.nan)).fillna(0)
    mf_vol = mf_mult * vol
    pos = mf_vol.clip(lower=0).rolling(14).sum(); neg = -mf_vol.clip(upper=0).rolling(14).sum()
    d['MFI'] = (100 - 100/(1 + pos/neg.replace(0,np.nan))).fillna(50)
    d['ROC'] = close.pct_change(12)*100
    up = high.diff(); down = -low.diff()
    plus_dm = up.where((up>down)&(up>0),0); minus_dm = down.where((down>up)&(down>0),0)
    atr = tr.rolling(14).mean().replace(0,np.nan)
    pdi = 100*plus_dm.rolling(14).mean()/atr; mdi = 100*minus_dm.rolling(14).mean()/atr
    d['ADX'] = (100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)).rolling(14).mean().fillna(0)
    return d

def money(v):
    try:
        v=float(v)
        if abs(v)>=1e12: return f'₹{v/1e12:.2f}T'
        if abs(v)>=1e9: return f'₹{v/1e7:.0f} Cr'
        if abs(v)>=1e7: return f'₹{v/1e7:.2f} Cr'
        return f'₹{v:,.2f}'
    except Exception: return '—'

def pct(v):
    try: return f'{float(v):+.2f}%'
    except Exception: return '—'

def score_crisp(df: pd.DataFrame):
    last=df.iloc[-1]; close=float(last['Close']); sma50=last.get('SMA50',np.nan); sma200=last.get('SMA200',np.nan)
    rsi=float(last.get('RSI',50)); roc=float(last.get('ROC',0) or 0); adx=float(last.get('ADX',0) or 0)
    momentum=int(np.clip(50 + (roc*2) + (10 if close>sma50 else -10),0,100)) if pd.notna(sma50) else int(np.clip(50+roc*2,0,100))
    stability=int(np.clip(100 - df['Close'].pct_change().tail(60).std()*100*5,0,100))
    quality=int(np.clip(50 + (15 if close>sma200 else -10 if pd.notna(sma200) else 0) + (10 if adx>20 else 0),0,100))
    sentiment=int(np.clip(50 + (rsi-50)*0.8 + np.clip(roc,-10,10),0,100))
    return {'Momentum':momentum,'Sentiment proxy':sentiment,'Stability':stability,'Trend quality':quality}

def ml_forecast(df: pd.DataFrame, horizon: int = 5):
    """Forecast a close price and a data-driven uncertainty band for a given bar horizon.

    A chronological holdout estimates forecast error; the reported range is a model
    uncertainty band, not a guaranteed high/low or a statistical certainty interval.
    """
    d = df[['Close', 'Volume']].copy()
    d['ret1'] = d['Close'].pct_change()
    d['ret5'] = d['Close'].pct_change(5)
    d['ret10'] = d['Close'].pct_change(10)
    d['ma5'] = d['Close'].rolling(5).mean()
    d['ma10'] = d['Close'].rolling(10).mean()
    d['ma20'] = d['Close'].rolling(20).mean()
    d['volatility'] = d['ret1'].rolling(10).std()
    d['volume_change'] = d['Volume'].pct_change().replace([np.inf, -np.inf], np.nan)
    features = ['Close', 'Volume', 'ret1', 'ret5', 'ret10', 'ma5', 'ma10', 'ma20', 'volatility', 'volume_change']
    d = d.replace([np.inf, -np.inf], np.nan).dropna()
    if len(d) < max(80, horizon + 50):
        return None

    X = d[features]
    # Learn the future percentage return instead of the raw price. This reduces
    # the tendency of tree models to regress toward the historical price level.
    y = d['Close'].shift(-horizon) / d['Close'] - 1.0
    valid = y.notna()
    X_all, y_all = X.loc[valid], y.loc[valid]
    if len(X_all) < 50:
        return None

    split = max(40, int(len(X_all) * 0.8))
    if split >= len(X_all):
        split = len(X_all) - max(10, int(len(X_all) * 0.2))
    if split < 30 or len(X_all) - split < 5:
        return None

    params = dict(n_estimators=220, max_depth=8, min_samples_leaf=2, random_state=42, n_jobs=-1)
    validation_model = RandomForestRegressor(**params)
    validation_model.fit(X_all.iloc[:split], y_all.iloc[:split])
    validation_pred = validation_model.predict(X_all.iloc[split:])
    residuals = y_all.iloc[split:].to_numpy() - validation_pred
    mae_return = float(mean_absolute_error(y_all.iloc[split:], validation_pred))
    # Convert return errors to rupees at the current price for interpretable ranges.
    current = float(d['Close'].iloc[-1])
    error_band = (float(np.quantile(np.abs(residuals), 0.80)) if len(residuals) else mae_return) * current
    mae = mae_return * current
    recent_vol = float(d['ret1'].tail(20).std()) if len(d) > 2 else 0.0
    vol_floor = abs(current) * max(0.0, recent_vol) * np.sqrt(max(1, horizon))
    band = max(error_band, vol_floor, mae * 0.5 if np.isfinite(mae) else 0.0)

    final_model = RandomForestRegressor(**params).fit(X_all, y_all)
    predicted_return = float(final_model.predict(X.iloc[[-1]])[0])
    prediction = max(0.0, current * (1.0 + predicted_return))
    return {
        'prediction': prediction,
        'low': max(0.0, prediction - band),
        'high': prediction + band,
        'mae': mae,
        'horizon': int(horizon),
        'current': current,
        'change_pct': (prediction / current - 1.0) * 100 if current else np.nan,
        'band_pct': (band / current) * 100 if current else np.nan,
        'model': final_model,
    }

# --------------------------- Sidebar ---------------------------
with st.sidebar:
    st.header('Market & stock')
    exchange=st.radio('Exchange', ['NSE','BSE'], horizontal=True, key='exchange_choice')
    stock_names=list(STOCKS.keys())
    chosen=st.selectbox('Choose a company', stock_names, index=0, key='company_choice')
    manual=st.text_input('Or enter any symbol', placeholder='e.g. INFY or 500325', key='unique_manual_symbol')
    symbol_map=STOCKS[chosen]
    default_symbol=symbol_map[0] if exchange=='NSE' else symbol_map[1]
    entered=manual.strip().upper()
    if entered:
        if entered.isdigit():
            ticker=entered+'.BO'
        elif entered.endswith(('.NS','.BO')):
            ticker=entered
        else:
            ticker=entered+('.NS' if exchange=='NSE' else '.BO')
    else:
        ticker=default_symbol+('.NS' if exchange=='NSE' else '.BO')
    period_label=st.select_slider('Historical range', options=list(PERIODS.keys()), value='1Y', key='range_slider')
    period, interval=PERIODS[period_label]
    show_sma=st.checkbox('Show SMA 20 / 50 / 200', True, key='show_sma')
    show_ema=st.checkbox('Show EMA 12 / 26', False, key='show_ema')
    st.caption('Quotes and company data are provided by Yahoo Finance and may be delayed or unavailable for some symbols.')

# For 1D, Yahoo's intraday history has a limited window; handle unavailable data clearly.
with st.spinner(f'Loading {ticker} market data…'):
    raw=get_history(ticker, period, interval)
if raw.empty and not manual.strip():
    # Exchange listing may be missing; try the opposite exchange for this curated company.
    fallback=symbol_map[0]+('.BO' if exchange=='NSE' else '.NS')
    raw=get_history(fallback, period, interval)
    if not raw.empty:
        ticker=fallback
if raw.empty:
    st.error(f'No price history returned for **{ticker}**. Check the symbol/exchange or try another historical range.')
    st.info('Examples: NSE `RELIANCE`, `INFY`, `TCS`; BSE numeric codes such as `500325` or tickers like `RELIANCE.BO`.')
    st.stop()

df=add_indicators(raw)
info=get_info(ticker)
latest=df.iloc[-1]; previous=df.iloc[-2] if len(df)>1 else latest
price=float(latest['Close']); change=(price/float(previous['Close'])-1)*100 if float(previous['Close']) else 0
company=info.get('longName') or info.get('shortName') or chosen
st.subheader(f'{company}  ·  {ticker}')
st.caption(f"{exchange} view • Latest available bar: {df.index[-1].strftime('%d %b %Y %H:%M') if period_label=='1D' else df.index[-1].strftime('%d %b %Y')}")

m1,m2,m3,m4,m5=st.columns(5)
m1.metric('Latest price', f'₹{price:,.2f}', pct(change))
m2.metric('Day / bar high', f"₹{float(latest['High']):,.2f}")
m3.metric('Day / bar low', f"₹{float(latest['Low']):,.2f}")
m4.metric('Volume', f"{float(latest['Volume']):,.0f}")
m5.metric('Market cap', money(info.get('marketCap')))

st.header('01. Overview')
st.markdown('### Price overview')
fig=go.Figure()
fig.add_trace(go.Candlestick(x=df.index,open=df.Open,high=df.High,low=df.Low,close=df.Close,name='Price'))
if show_sma:
    for col in ['SMA20','SMA50','SMA200']:
        fig.add_trace(go.Scatter(x=df.index,y=df[col],mode='lines',name=col,line={'width':1.4}))
if show_ema:
    for col in ['EMA12','EMA26']:
        fig.add_trace(go.Scatter(x=df.index,y=df[col],mode='lines',name=col,line={'width':1.3,'dash':'dot'}))
fig.update_layout(height=520,xaxis_rangeslider_visible=False,legend_orientation='h',legend_y=1.02,margin=dict(l=10,r=10,t=35,b=10),yaxis_title='Price (INR)')
st.plotly_chart(fig, width='stretch')
volfig=go.Figure(go.Bar(x=df.index,y=df.Volume,name='Volume'))
volfig.update_layout(height=220,margin=dict(l=10,r=10,t=25,b=10),yaxis_title='Volume')
st.plotly_chart(volfig,width='stretch')
st.markdown('### Market snapshot')
c1,c2,c3,c4=st.columns(4)
c1.metric('52-week high', f"₹{float(info.get('fiftyTwoWeekHigh',df.High.tail(252).max())):,.2f}")
c2.metric('52-week low', f"₹{float(info.get('fiftyTwoWeekLow',df.Low.tail(252).min())):,.2f}")
c3.metric('P/E ratio', f"{info.get('trailingPE',float('nan')):.2f}" if isinstance(info.get('trailingPE'),(int,float)) else '—')
c4.metric('Dividend yield', pct((info.get('dividendYield') or 0)*100) if info.get('dividendYield') is not None else '—')
st.markdown('### Recent price data')
st.dataframe(df[['Open','High','Low','Close','Volume']].tail(15).sort_index(ascending=False).style.format({'Open':'₹{:,.2f}','High':'₹{:,.2f}','Low':'₹{:,.2f}','Close':'₹{:,.2f}','Volume':'{:,.0f}'}),width='stretch')

st.divider()
st.header('02. Technical Indicators')
st.markdown('### Technical indicator dashboard')
indcols=st.columns(4)
for col,label,val in zip(indcols,['RSI (14)','MACD','MFI (14)','ADX (14)'],[latest.RSI,latest.MACD,latest.MFI,latest.ADX]):
    col.metric(label, f'{float(val):.2f}' if pd.notna(val) else '—')
fig=make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=.06,row_heights=[.55,.22,.23],subplot_titles=('Price + averages','RSI (14)','MACD'))
fig.add_trace(go.Scatter(x=df.index,y=df.Close,name='Close'),row=1,col=1)
for col in ['SMA20','SMA50','SMA200']:
    fig.add_trace(go.Scatter(x=df.index,y=df[col],name=col),row=1,col=1)
fig.add_trace(go.Scatter(x=df.index,y=df.RSI,name='RSI',line={'color':'#9467bd'}),row=2,col=1)
fig.add_hline(y=70,line_dash='dash',line_color='red',row=2,col=1); fig.add_hline(y=30,line_dash='dash',line_color='green',row=2,col=1)
fig.add_trace(go.Scatter(x=df.index,y=df.MACD,name='MACD'),row=3,col=1); fig.add_trace(go.Scatter(x=df.index,y=df.MACD_signal,name='Signal'),row=3,col=1)
fig.update_layout(height=800,showlegend=True,legend_orientation='h',margin=dict(l=10,r=10,t=55,b=10))
st.plotly_chart(fig,width='stretch')
indicator_table=pd.DataFrame({'Indicator':['SMA 20','SMA 50','SMA 200','EMA 12','EMA 26','RSI 14','MACD','MACD signal','MFI 14','ATR 14','ROC 12','ADX 14'],'Latest value':[latest.get(k,np.nan) for k in ['SMA20','SMA50','SMA200','EMA12','EMA26','RSI','MACD','MACD_signal','MFI','ATR','ROC','ADX']]})
st.dataframe(indicator_table.style.format({'Latest value':'{:.3f}'}),width='stretch',hide_index=True)
st.caption('Indicators are descriptive technical measures, not guaranteed trading signals.')

st.divider()
st.header('03. CRISP Analysis')
st.markdown('### CRISP analysis')
scores=score_crisp(df)
cols=st.columns(4)
for col,(name,score) in zip(cols,scores.items()): col.metric(name,f'{score}/100')
crispfig = go.Figure()
crisp_names = list(scores.keys())
crisp_values = list(scores.values())
crispfig.add_trace(go.Scatterpolar(
    r=crisp_values + [crisp_values[0]],
    theta=crisp_names + [crisp_names[0]],
    fill='toself',
    name='CRISP score',
    line=dict(width=2),
    hovertemplate='%{theta}: %{r}/100<extra></extra>'
))
crispfig.update_layout(
    title='CRISP market diagnostic — radar / spider chart',
    polar=dict(radialaxis=dict(visible=True, range=[0, 100], ticksuffix='/100')),
    showlegend=False, height=470,
    margin=dict(l=30, r=30, t=60, b=30)
)
st.plotly_chart(crispfig, width='stretch')
rsi=float(latest.RSI); roc=float(latest.ROC) if pd.notna(latest.ROC) else 0
trend='Bullish' if price>latest.SMA50 and latest.SMA50>latest.SMA200 else 'Bearish' if price<latest.SMA50 and latest.SMA50<latest.SMA200 else 'Mixed / neutral'
st.markdown('**C — Current trend:** '+trend)
st.markdown(f"**R — Relative strength:** RSI is {rsi:.1f}; {'overbought zone' if rsi>=70 else 'oversold zone' if rsi<=30 else 'middle range'}.")
st.markdown(f"**I — Impulse / momentum:** 12-period rate of change is {roc:+.2f}%.")
st.markdown(f"**S — Stability:** score {scores['Stability']}/100, based on recent return volatility.")
st.markdown(f"**P — Price trend quality:** score {scores['Trend quality']}/100 using long-term average and ADX context.")
st.caption('CRISP scores are an app-defined educational heuristic, not an official financial rating or investment advice.')

st.divider()
st.header('04. Company Profile')
st.markdown('### Company profile')
if info.get('longBusinessSummary'): st.write(info['longBusinessSummary'])
else: st.info('Company description is not available from the data provider for this ticker.')
profile_rows=[('Company',company),('Exchange ticker',ticker),('Sector',info.get('sector','—')),('Industry',info.get('industry','—')),('Website',info.get('website','—')),('Country',info.get('country','—')),('Employees',f"{info.get('fullTimeEmployees'):,}" if info.get('fullTimeEmployees') else '—'),('Market cap',money(info.get('marketCap'))),('Enterprise value',money(info.get('enterpriseValue'))),('Trailing P/E',info.get('trailingPE','—')),('Forward P/E',info.get('forwardPE','—')),('Price/book',info.get('priceToBook','—')),('Beta',info.get('beta','—')),('Dividend yield',pct((info.get('dividendYield') or 0)*100) if info.get('dividendYield') is not None else '—')]
st.dataframe(pd.DataFrame(profile_rows,columns=['Field','Value']),width='stretch',hide_index=True)
if info.get('website'):
    st.markdown(f"[Open company website]({info['website']})")

st.divider()
st.header('05. Shareholding Pattern')
st.markdown('### Shareholding pattern')
major,inst,mutual=get_shareholders(ticker)
if major is not None and not major.empty:
    st.markdown('**Major holders (provider data)**'); st.dataframe(major,width='stretch',hide_index=True)
holder_frames=[]
for frame,label in [(inst,'Institutional holders'),(mutual,'Mutual fund holders')]:
    if frame is not None and not frame.empty:
        st.markdown(f'**{label}**'); st.dataframe(frame,width='stretch',hide_index=True)
        # Use only reported percentage column; normalize for a readable distribution view.
        pct_col=next((c for c in frame.columns if 'pct' in str(c).lower() or 'percent' in str(c).lower()),None)
        name_col=next((c for c in frame.columns if str(c).lower() in ['holder','organization','name']),frame.columns[0])
        if pct_col:
            tmp=frame[[name_col,pct_col]].copy(); tmp.columns=['Holder','Percent']
            tmp['Percent']=pd.to_numeric(tmp.Percent.astype(str).str.replace('%','',regex=False),errors='coerce')
            tmp=tmp.dropna(subset=['Percent'])
            if not tmp.empty:
                tmp=tmp.groupby('Holder',as_index=False).Percent.sum().nlargest(8,'Percent')
                holder_frames.append(tmp)
if holder_frames:
    h=pd.concat(holder_frames,ignore_index=True).groupby('Holder',as_index=False).Percent.sum().nlargest(8,'Percent')
    total=h.Percent.sum()
    if total>0:
        h['Share %']=h.Percent/total*100
        # 100% stacked area requires at least two observations. Build a valid two-point 100% composition chart.
        fig=go.Figure()
        for _,r in h.iterrows():
            fig.add_trace(go.Scatter(x=['Reported holder mix','Reported holder mix + 2nd point'],y=[r['Share %'],r['Share %']],mode='lines',stackgroup='one',name=str(r.Holder),line={'width':0.5}))
        fig.update_layout(title='100% stacked area — normalized reported holder mix',yaxis=dict(title='Share of displayed holders (%)',range=[0,100],ticksuffix='%'),xaxis_title='',height=430,margin=dict(l=10,r=10,t=50,b=10),legend_orientation='h')
        st.plotly_chart(fig,width='stretch')
    else: st.info('Holder percentage values could not be normalized for a chart.')
else:
    st.info('Shareholder breakdown is not available for this symbol from Yahoo Finance. This does not mean the company has no shareholders.')
st.caption('Shareholder datasets can be incomplete, stale, or unavailable for Indian listings. A blank chart indicates missing provider data, not 0% ownership.')

st.divider()
st.header('06. ML Predictions')
st.markdown('### Multi-horizon price estimates and ranges')
st.warning('These are experimental model estimates, not reliable promises of future prices. The displayed low/high band is estimated from chronological validation errors and recent volatility; it is not a guaranteed trading range or a formal confidence interval.')

st.markdown('#### Forecast horizons')
forecast_specs = [
    ('Intraday · ~1 hour', 12, '5-minute bars'),
    ('Intraday · ~3 hours', 36, '5-minute bars'),
    ('Short term · 1 trading day', 1, 'daily bars'),
    ('Short term · 5 trading days', 5, 'daily bars'),
    ('Medium term · 20 trading days', 20, 'daily bars'),
    ('Long term · 60 trading days', 60, 'daily bars'),
]
st.caption('Intraday estimates use recent 5-minute candles; short/medium/long-term estimates use daily candles. Intraday data availability varies by ticker and provider.')

if st.button('Run all horizon predictions', key='run_all_ml_predictions', type='primary'):
    prediction_rows = []
    progress = st.progress(0, text='Preparing forecast models…')
    daily_raw = raw.copy()
    # If the selected chart range is too short for long horizons, request more daily history.
    with st.spinner('Training daily-horizon models…'):
        daily_history = daily_raw
        if len(daily_history) < 180:
            daily_history = get_history(ticker, '5y', '1d')
        daily_df = add_indicators(daily_history) if not daily_history.empty else pd.DataFrame()
        daily_specs = [
            ('Short term · 1 trading day', 1),
            ('Short term · 5 trading days', 5),
            ('Medium term · 20 trading days', 20),
            ('Long term · 60 trading days', 60),
        ]
        for i, (label, bars) in enumerate(daily_specs, start=1):
            result = ml_forecast(daily_df, bars) if not daily_df.empty else None
            if result:
                prediction_rows.append({
                    'Horizon': label, 'Bars': f'{bars} daily bars',
                    'Current price': result['current'], 'Model estimate': result['prediction'],
                    'Estimated low': result['low'], 'Estimated high': result['high'],
                    'Change vs current (%)': result['change_pct'], 'Test MAE (₹)': result['mae'],
                    'Range width (%)': 2 * result['band_pct']
                })
            progress.progress(i / 6, text=f'Completed {label}')

    with st.spinner('Fetching and training intraday models…'):
        intraday = get_history(ticker, '5d', '5m')
        if not intraday.empty:
            intraday_df = add_indicators(intraday)
            for j, (label, bars) in enumerate([('Intraday · ~1 hour', 12), ('Intraday · ~3 hours', 36)], start=5):
                result = ml_forecast(intraday_df, bars)
                if result:
                    prediction_rows.append({
                        'Horizon': label, 'Bars': f'{bars} five-minute bars',
                        'Current price': result['current'], 'Model estimate': result['prediction'],
                        'Estimated low': result['low'], 'Estimated high': result['high'],
                        'Change vs current (%)': result['change_pct'], 'Test MAE (₹)': result['mae'],
                        'Range width (%)': 2 * result['band_pct']
                    })
                progress.progress(j / 6, text=f'Completed {label}')
        else:
            st.info('Intraday 5-minute candles are unavailable for this symbol right now; daily forecasts are still shown.')

    progress.empty()
    if prediction_rows:
        pred_df = pd.DataFrame(prediction_rows)
        st.markdown('#### Prediction summary')
        st.dataframe(
            pred_df.style.format({
                'Current price': '₹{:,.2f}', 'Model estimate': '₹{:,.2f}',
                'Estimated low': '₹{:,.2f}', 'Estimated high': '₹{:,.2f}',
                'Change vs current (%)': '{:+.2f}%', 'Test MAE (₹)': '₹{:,.2f}',
                'Range width (%)': '{:.2f}%'
            }), width='stretch', hide_index=True
        )
        st.markdown('#### Estimated price ranges')
        range_fig = go.Figure()
        for _, row in pred_df.iterrows():
            range_fig.add_trace(go.Scatter(
                x=[row['Estimated low'], row['Estimated high']],
                y=[row['Horizon'], row['Horizon']], mode='lines+markers',
                line=dict(width=8), marker=dict(size=9), name=row['Horizon'],
                showlegend=False,
                hovertemplate='%{y}<br>Range edge: ₹%{x:,.2f}<extra></extra>'
            ))
            range_fig.add_trace(go.Scatter(
                x=[row['Model estimate']], y=[row['Horizon']], mode='markers',
                marker=dict(size=12, symbol='diamond'), name='Model estimate',
                showlegend=False,
                hovertemplate='Model estimate<br>₹%{x:,.2f}<extra></extra>'
            ))
        range_fig.add_vline(x=price, line_dash='dash', annotation_text=f'Current ₹{price:,.2f}')
        range_fig.update_layout(
            height=max(380, 65 * len(pred_df)), xaxis_title='Estimated price (INR)',
            yaxis_title='', margin=dict(l=10, r=20, t=45, b=10),
            title='Low–high model range (bars show range; diamond shows estimate)'
        )
        st.plotly_chart(range_fig, width='stretch')
        st.markdown('#### How to read these predictions')
        st.markdown("""- **Intraday:** roughly 1 hour and 3 hours ahead using 5-minute bars (12 and 36 bars). These are bar-based estimates and do not account for market closure or gaps.
- **Short term:** 1 and 5 trading days ahead.
- **Medium term:** 20 trading days ahead (about one trading month).
- **Long term:** 60 trading days ahead (about one trading quarter).
- **Estimated low/high:** a rough model uncertainty band based on held-out errors and recent volatility, not guaranteed support/resistance or a formal confidence interval.
- **Test MAE:** mean absolute error on a later chronological holdout; larger values indicate weaker historical forecast accuracy.""")
    else:
        st.error('The model could not produce enough reliable rows for the selected ticker. Try another symbol or rerun later when more history is available.')
else:
    st.info('Click **Run all horizon predictions** to calculate intraday, short-term, medium-term, and long-term estimates with low/high ranges and a historical test-error metric.')

st.divider()
st.caption('StockWise AI • Data may be delayed, incomplete, or unavailable. Not investment advice. Verify exchange filings and consult a qualified adviser before making financial decisions.')
