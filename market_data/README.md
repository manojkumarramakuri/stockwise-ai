# StockWise AI market-data API integration

This is an additive integration for the existing SQLite market-data database. It does not replace the stock dashboard, prediction pipeline, or existing ingestion script.

## Add the router to FastAPI

In `api/main.py`, after the existing FastAPI app is created, add:

```python
from market_data.normalized_api import router as market_data_router
app.include_router(market_data_router)
```

Keep the existing `app` object and all current routes unchanged.

## Routes

| Route | Purpose |
|---|---|
| `GET /api/market-data/status` | Counts for MF, F&O and IPO tables plus per-source status |
| `GET /api/market-data/sources` | Ingestion status and error messages |
| `GET /api/market-data/mutual-funds?q=&category=&fund_house=&limit=&offset=` | Search/filter scheme master and attach each scheme's latest imported NAV |
| `GET /api/market-data/mutual-funds/{scheme_code}/nav?limit=365` | Imported NAV history for one scheme |
| `GET /api/market-data/fno?segment=&limit=&offset=` | Imported F&O report rows |
| `GET /api/market-data/ipos?source=&limit=&offset=` | Captured IPO source-table rows |

The database defaults to `data/stockwise_market.db`. Override it with `STOCKWISE_MARKET_DB` if your deployment stores it elsewhere.

## Current feed coverage recorded by the project

- MF scheme master: 38,052 schemes imported from MFapi.
- AMFI latest NAV file: 14,455 scheme NAV records.
- Historical NAV table: 17,703 rows in total; this is not complete historical coverage for every scheme.
- F&O: no verified report rows imported yet. The API returns an explicit empty-state message rather than fabricated contracts.
- IPO: 18 captured source-table rows (14 SEBI + 4 NSE in the last run); these are not yet normalized, verified issue records.

## Validate

After adding the router and restarting FastAPI:

```bash
curl -s http://127.0.0.1:8000/api/market-data/status
curl -s 'http://127.0.0.1:8000/api/market-data/mutual-funds?q=hdfc&limit=5'
curl -s 'http://127.0.0.1:8000/api/market-data/ipos?limit=5'
```

Do not label imported NAV as live intraday pricing. Display its NAV date and source. Do not display raw captured IPO HTML rows as verified IPO listings.
