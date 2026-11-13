"""StockWise live/latest-available NSE/BSE quote service.

Yahoo Finance is a best-effort, potentially delayed data source, NOT an exchange
real-time feed. No fabricated prices; expose timestamp and source on every quote.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic
import math
import pandas as pd
import yfinance as yf

INDEX_SYMBOLS = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "BANK NIFTY": "^NSEBANK"}
_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_lock = Lock()
TTL_SECONDS = 30


def normalize_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol or len(symbol) > 32 or not all(c.isalnum() or c in ".^-&" for c in symbol):
        raise ValueError("Invalid market symbol")
    if symbol.startswith("^") or symbol.endswith((".NS", ".BO")):
        return symbol
    if symbol.isdigit():
        return symbol + ".BO"
    return symbol + ".NS"


def get_quote(symbol: str, *, interval: str = "1m") -> dict:
    symbol = normalize_symbol(symbol)
    if interval not in {"1m", "5m", "1d"}:
        raise ValueError("Unsupported interval")
    key = (symbol, interval)
    with _lock:
        hit = _cache.get(key)
        if hit and monotonic() - hit[0] < TTL_SECONDS:
            return {**hit[1], "cache_hit": True}
    period = "5d" if interval != "1d" else "10d"
    frame = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if frame is None or frame.empty:
        raise LookupError(f"No market data returned for {symbol}")
    frame = frame.dropna(subset=["Close"]).sort_index()
    if frame.empty:
        raise LookupError(f"No valid close returned for {symbol}")
    latest = frame.iloc[-1]
    close = float(latest["Close"])
    if not math.isfinite(close):
        raise LookupError("Non-finite price")
    # Daily previous close is a more meaningful baseline than previous minute.
    daily = yf.Ticker(symbol).history(period="10d", interval="1d", auto_adjust=False)
    previous = None
    if daily is not None and not daily.empty:
        closes = pd.to_numeric(daily["Close"], errors="coerce").dropna()
        if len(closes) >= 2:
            # If the last daily bar is today, use penultimate; otherwise use latest.
            latest_date = pd.Timestamp(frame.index[-1]).date()
            previous = float(closes.iloc[-2] if closes.index[-1].date() == latest_date else closes.iloc[-1])
    change = close - previous if previous and previous > 0 else None
    result = {
        "symbol": symbol, "price": close, "currency": "INR",
        "open": _finite(latest.get("Open")),
        "high": _finite(latest.get("High")),
        "low": _finite(latest.get("Low")),
        "volume": _finite(latest.get("Volume")),
        "previous_close": previous,
        "change": change,
        "change_percent": 100 * change / previous if change is not None else None,
        "quote_timestamp": pd.Timestamp(frame.index[-1]).isoformat(),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Yahoo Finance (unofficial; may be delayed)",
        "realtime_verified": False,
        "cache_hit": False,
    }
    with _lock:
        _cache[key] = (monotonic(), result)
    return result


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def get_indices() -> dict:
    result = {}
    for name, symbol in INDEX_SYMBOLS.items():
        try:
            result[name] = get_quote(symbol)
        except Exception as exc:
            result[name] = {"symbol": symbol, "error": str(exc)}
    return result


def register_live_routes(app):
    """Call register_live_routes(app) after constructing your existing FastAPI app."""
    from fastapi import HTTPException

    @app.get("/api/live/quote/{symbol}")
    def live_quote(symbol: str):
        try:
            return get_quote(symbol)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except (LookupError, Exception) as exc:
            raise HTTPException(status_code=503, detail=f"Quote unavailable: {exc}")

    @app.get("/api/live/indices")
    def live_indices():
        return get_indices()
