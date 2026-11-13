"""Read-only API routes for StockWise AI's normalized market-data SQLite database.

Add to api/main.py:
    from market_data.normalized_api import router as market_data_router
    app.include_router(market_data_router)

The router reads the existing data/stockwise_market.db created by market_data/ingest.py.
It never fabricates missing F&O or IPO rows; source_status exposes feed coverage.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/market-data", tags=["Market data"])

DB_PATH = Path(os.getenv("STOCKWISE_MARKET_DB", "data/stockwise_market.db"))


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Market database not found: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


@router.get("/status")
def market_data_status() -> dict:
    """Counts and latest source status for MF, F&O and IPO feeds."""
    with _connect() as conn:
        counts = {}
        for table in ("mf_schemes", "mf_nav", "fno_files", "fno_rows", "ipo_records"):
            counts[table] = (
                conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if _table_exists(conn, table) else 0
            )
        statuses = _rows(
            conn,
            "SELECT source, status, records, message, updated_at "
            "FROM source_status ORDER BY source"
        ) if _table_exists(conn, "source_status") else []
        return {"database": str(DB_PATH), "counts": counts, "sources": statuses}


@router.get("/sources")
def source_status() -> dict:
    with _connect() as conn:
        if not _table_exists(conn, "source_status"):
            return {"sources": []}
        return {"sources": _rows(
            conn,
            "SELECT source, status, records, message, updated_at "
            "FROM source_status ORDER BY source"
        )}


@router.get("/mutual-funds")
def mutual_funds(
    q: str = Query("", max_length=120),
    category: str = Query("", max_length=80),
    fund_house: str = Query("", max_length=120),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    clauses, params = [], []
    if q.strip():
        clauses.append("(scheme_name LIKE ? OR scheme_code LIKE ?)")
        term = f"%{q.strip()}%"
        params.extend((term, term))
    if category.strip():
        clauses.append("scheme_category LIKE ?")
        params.append(f"%{category.strip()}%")
    if fund_house.strip():
        clauses.append("fund_house LIKE ?")
        params.append(f"%{fund_house.strip()}%")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect() as conn:
        if not _table_exists(conn, "mf_schemes"):
            return {"total": 0, "items": [], "limit": limit, "offset": offset}
        total = conn.execute("SELECT COUNT(*) FROM mf_schemes" + where, params).fetchone()[0]
        items = _rows(
            conn,
            "SELECT scheme_code, scheme_name, isin_growth, isin_dividend, "
            "fund_house, scheme_type, scheme_category "
            "FROM mf_schemes" + where +
            " ORDER BY scheme_name LIMIT ? OFFSET ?",
            tuple(params) + (limit, offset),
        )
        # Attach the latest NAV without requiring historical data for every scheme.
        for item in items:
            latest = conn.execute(
                "SELECT nav, nav_date, source FROM mf_nav "
                "WHERE scheme_code=? ORDER BY nav_date DESC LIMIT 1",
                (item["scheme_code"],),
            ).fetchone() if _table_exists(conn, "mf_nav") else None
            item["latest_nav"] = dict(latest) if latest else None
        return {"total": total, "items": items, "limit": limit, "offset": offset}


@router.get("/mutual-funds/{scheme_code}/nav")
def mutual_fund_nav(
    scheme_code: str,
    limit: int = Query(365, ge=1, le=5000),
) -> dict:
    with _connect() as conn:
        if not _table_exists(conn, "mf_nav"):
            return {"scheme_code": scheme_code, "items": []}
        items = _rows(
            conn,
            "SELECT scheme_code, nav_date, nav, source FROM mf_nav "
            "WHERE scheme_code=? ORDER BY nav_date DESC LIMIT ?",
            (scheme_code, limit),
        )
        return {"scheme_code": scheme_code, "items": items, "count": len(items)}


@router.get("/fno")
def derivatives_data(
    segment: str = Query("", max_length=40),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Returns only imported F&O rows. Empty means no source file has been imported."""
    with _connect() as conn:
        if not _table_exists(conn, "fno_rows"):
            return {"total": 0, "items": [], "message": "No F&O table is available yet."}
        where = " WHERE segment LIKE ?" if segment.strip() else ""
        params: tuple[Any, ...] = (f"%{segment.strip()}%",) if segment.strip() else ()
        total = conn.execute("SELECT COUNT(*) FROM fno_rows" + where, params).fetchone()[0]
        rows = _rows(
            conn,
            "SELECT filename, segment, row_number, payload, imported_at "
            "FROM fno_rows" + where +
            " ORDER BY imported_at DESC, filename, row_number LIMIT ? OFFSET ?",
            params + (limit, offset),
        )
        for row in rows:
            # Payload remains raw source data; clients can render columns by report type.
            import json
            try:
                row["payload"] = json.loads(row["payload"])
            except (TypeError, ValueError):
                pass
        return {
            "total": total, "items": rows, "limit": limit, "offset": offset,
            "message": None if total else "No verified NSE F&O report rows imported yet.",
        }


@router.get("/ipos")
def ipo_records(
    source: str = Query("", max_length=80),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Returns captured IPO source records without presenting raw HTML as verified issues."""
    with _connect() as conn:
        if not _table_exists(conn, "ipo_records"):
            return {"total": 0, "items": [], "message": "No IPO records table is available."}
        where = " WHERE source LIKE ?" if source.strip() else ""
        params: tuple[Any, ...] = (f"%{source.strip()}%",) if source.strip() else ()
        total = conn.execute("SELECT COUNT(*) FROM ipo_records" + where, params).fetchone()[0]
        rows = _rows(
            conn,
            "SELECT source, source_url, table_number, row_number, payload, captured_at "
            "FROM ipo_records" + where +
            " ORDER BY captured_at DESC, source, table_number, row_number LIMIT ? OFFSET ?",
            params + (limit, offset),
        )
        import json
        for row in rows:
            try:
                row["payload"] = json.loads(row["payload"])
            except (TypeError, ValueError):
                pass
        return {
            "total": total, "items": rows, "limit": limit, "offset": offset,
            "message": (
                "These are captured source-table rows, not yet normalized/verified IPO issue records."
                if total else "No IPO source rows imported."
            ),
        }
