"""FastAPI router for the StockWise normalized market-data database."""
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/market-data", tags=["Market data"])
DB = Path(os.getenv("STOCKWISE_MARKET_DB", "data/stockwise_market.db"))

def db():
    if not DB.exists():
        raise HTTPException(status_code=503, detail=f"Market database not found: {DB}")
    c=sqlite3.connect(str(DB),timeout=15); c.row_factory=sqlite3.Row; return c

def has(c,t):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() is not None

def rows(c,sql,args=()):
    return [dict(x) for x in c.execute(sql,args).fetchall()]

@router.get("/status")
def status():
    with db() as c:
        names=("mf_schemes","mf_nav","fno_files","fno_rows","ipo_records")
        counts={n:(c.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0] if has(c,n) else 0) for n in names}
        sources=rows(c,"SELECT source,status,records,message,updated_at FROM source_status ORDER BY source") if has(c,"source_status") else []
        return {"counts":counts,"sources":sources}

@router.get("/mutual-funds")
def mutual_funds(q:str=Query("",max_length=120),limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    with db() as c:
        if not has(c,"mf_schemes"): return {"total":0,"items":[]}
        where=" WHERE scheme_name LIKE ? OR scheme_code LIKE ?" if q.strip() else ""
        args=(f"%{q.strip()}%",f"%{q.strip()}%") if where else ()
        total=c.execute("SELECT COUNT(*) FROM mf_schemes"+where,args).fetchone()[0]
        items=rows(c,"SELECT scheme_code,scheme_name,fund_house,scheme_type,scheme_category FROM mf_schemes"+where+" ORDER BY scheme_name LIMIT ? OFFSET ?",args+(limit,offset))
        for x in items:
            n=c.execute("SELECT nav,nav_date,source FROM mf_nav WHERE scheme_code=? ORDER BY nav_date DESC LIMIT 1",(x["scheme_code"],)).fetchone() if has(c,"mf_nav") else None
            x["latest_nav"]=dict(n) if n else None
        return {"total":total,"items":items}

@router.get("/mutual-funds/{scheme_code}/nav")
def nav_history(scheme_code:str,limit:int=Query(365,ge=1,le=5000)):
    with db() as c:
        if not has(c,"mf_nav"): return {"items":[]}
        return {"items":rows(c,"SELECT nav_date,nav,source FROM mf_nav WHERE scheme_code=? ORDER BY nav_date DESC LIMIT ?",(scheme_code,limit))}

@router.get("/fno")
def fno(limit:int=Query(100,ge=1,le=500)):
    with db() as c:
        if not has(c,"fno_rows"): return {"total":0,"items":[]}
        total=c.execute("SELECT COUNT(*) FROM fno_rows").fetchone()[0]
        items=rows(c,"SELECT filename,segment,row_number,payload,imported_at FROM fno_rows ORDER BY imported_at DESC LIMIT ?",(limit,))
        for x in items:
            try:x["payload"]=json.loads(x["payload"])
            except (ValueError,TypeError):pass
        return {"total":total,"items":items}

@router.get("/ipos")
def ipos(limit:int=Query(100,ge=1,le=500)):
    with db() as c:
        if not has(c,"ipo_records"): return {"total":0,"items":[]}
        total=c.execute("SELECT COUNT(*) FROM ipo_records").fetchone()[0]
        items=rows(c,"SELECT source,source_url,table_number,row_number,payload,captured_at FROM ipo_records ORDER BY captured_at DESC LIMIT ?",(limit,))
        for x in items:
            try:x["payload"]=json.loads(x["payload"])
            except (ValueError,TypeError):pass
        return {"total":total,"items":items}
