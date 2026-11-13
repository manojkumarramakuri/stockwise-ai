# StockWise AI — market data integration

## What is included
- Streamlit page `pages/2_Market_Data.py` reads the existing SQLite market database directly. It does not require a separate API process.
- Mutual Funds: searchable scheme master, latest imported NAV, NAV history chart.
- F&O: displays imported report rows; shows an honest empty state if no official report has been imported.
- IPO: displays captured source records with a warning that raw captures are not verified active IPO issues.
- `market_data/normalized_api.py` provides optional FastAPI endpoints under `/api/market-data`.

## Database
Default: `data/stockwise_market.db`. Override with `STOCKWISE_MARKET_DB`.
Expected tables: `mf_schemes`, `mf_nav`, `fno_files`, `fno_rows`, `ipo_records`, `source_status`.

## FastAPI integration (optional)
After creating the existing FastAPI app in `api/main.py`:
```python
from market_data.normalized_api import router as market_data_router
app.include_router(market_data_router)
```

## Run
From repository root:
```bash
streamlit run app.py
```
Streamlit discovers the page under `pages/` automatically. Install Streamlit, pandas, and plotly from the existing requirements file.
