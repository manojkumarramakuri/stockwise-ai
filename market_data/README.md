# StockWise AI — connected market data

## Included dashboard
The multipage Streamlit app discovers `pages/2_Market_Data.py` automatically. The page reads `data/stockwise_market.db` directly; it does not depend on a separate FastAPI process.

- **Mutual Funds:** scheme search, latest available NAV and imported NAV history.
- **F&O:** official NSE UDiFF derivatives bhavcopy rows.
- **IPOs:** captured NSE, BSE and SEBI source tables, clearly marked as source captures until normalized/verified.
- **Feed health:** counts and last ingestion result per source.

## Refresh official feeds
From the repository root:
```bash
python market_data/refresh_feeds.py
```
Or open **Market Data → Refresh official data feeds → Refresh market data now**.

The refresh job:
1. Imports the MFAPI scheme master.
2. Imports the latest AMFI `NAVAll.txt` snapshot.
3. Tries the most recent 11 calendar dates for NSE's official UDiFF F&O bhavcopy archive.
4. Captures HTML tables from official NSE, BSE and SEBI IPO pages.

Raw downloads are stored in `data/market_raw/`; normalized data is stored in `data/stockwise_market.db`. The database location can be overridden with `STOCKWISE_MARKET_DB`.

**Coverage caveats:** AMFI NAVAll is a latest snapshot, not complete historical NAV for every scheme. MFAPI historical NAV can be fetched scheme-by-scheme. IPO source tables are not automatically verified active IPO issues. NSE F&O data is end-of-day bhavcopy, not live options-chain quotes. If an exchange blocks a request or has no report for recent dates, the source status records the failure instead of inventing rows.

## Optional FastAPI integration
If this project has a FastAPI app, include the router after creating the app:
```python
from market_data.normalized_api import router as market_data_router
app.include_router(market_data_router)
```
Endpoints are under `/api/market-data`.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
