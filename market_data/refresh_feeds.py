#!/usr/bin/env python3
"""Refresh StockWise public market-data feeds.

Sources:
- AMFI NAVAll.txt: official daily NAV snapshot.
- MFAPI scheme master: scheme metadata (historical NAV is fetched on demand separately).
- NSE UDiFF FO bhavcopy archive: official end-of-day derivatives contracts.

This script never fabricates rows. Failed sources are recorded in source_status.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.getenv("STOCKWISE_MARKET_DB", str(ROOT / "data" / "stockwise_market.db")))
RAW = ROOT / "data" / "market_raw"
RAW.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
})

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(DB,timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS source_status(
        source TEXT PRIMARY KEY,status TEXT,records INTEGER DEFAULT 0,
        message TEXT,updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS mf_schemes(
        scheme_code TEXT PRIMARY KEY,scheme_name TEXT,fund_house TEXT,
        scheme_type TEXT,scheme_category TEXT,isin_growth TEXT,isin_dividend TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS mf_nav(
        scheme_code TEXT,nav_date TEXT,nav REAL,source TEXT,
        PRIMARY KEY(scheme_code,nav_date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS fno_files(
        filename TEXT PRIMARY KEY,segment TEXT,trade_date TEXT,source_url TEXT,imported_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fno_rows(
        filename TEXT,segment TEXT,row_number INTEGER,payload TEXT,imported_at TEXT,
        PRIMARY KEY(filename,row_number))""")
    c.commit()
    return c

def status(c,source,state,n,message=""):
    c.execute("INSERT INTO source_status(source,status,records,message,updated_at) VALUES(?,?,?,?,?) "
              "ON CONFLICT(source) DO UPDATE SET status=excluded.status,records=excluded.records,"
              "message=excluded.message,updated_at=excluded.updated_at",
              (source,state,int(n),str(message)[:1500],datetime.now().isoformat(timespec="seconds")))
    c.commit()

def get(url,**kwargs):
    r=SESSION.get(url,timeout=60,**kwargs); r.raise_for_status(); return r

def ingest_mf(c):
    source="AMFI latest NAV"
    try:
        raw=get("https://www.amfiindia.com/spages/NAVAll.txt").content
        (RAW/"NAVAll.txt").write_bytes(raw)
        parsed=[]
        for line in raw.decode("utf-8-sig",errors="replace").splitlines():
            p=line.split(";")
            if len(p)<6 or not p[0].strip().isdigit(): continue
            try:
                parsed.append((p[0].strip(),datetime.strptime(p[5].strip(),"%d-%b-%Y").date().isoformat(),
                               float(p[4].strip()),"AMFI NAVAll.txt"))
            except (ValueError,IndexError): continue
        c.executemany("INSERT OR REPLACE INTO mf_nav(scheme_code,nav_date,nav,source) VALUES(?,?,?,?)",parsed)
        status(c,source,"SUCCESS",len(parsed),"Official AMFI latest NAV snapshot")
    except Exception as e: status(c,source,"FAILED",0,repr(e))

def ingest_scheme_master(c):
    source="MFAPI scheme master"
    try:
        data=get("https://api.mfapi.in/mf").json()
        parsed=[]
        for x in data:
            code=str(x.get("schemeCode","")).strip()
            name=str(x.get("schemeName","")).strip()
            if code and name:
                parsed.append((code,name,None,None,None,None,None))
        c.executemany("INSERT OR IGNORE INTO mf_schemes(scheme_code,scheme_name,fund_house,scheme_type,scheme_category,isin_growth,isin_dividend) VALUES(?,?,?,?,?,?,?)",parsed)
        status(c,source,"SUCCESS",len(parsed),"MFAPI scheme master; category metadata may be unavailable")
    except Exception as e: status(c,source,"FAILED",0,repr(e))

def find_nse_fo_zip():
    # NSE archive naming convention for the UDiFF final derivatives bhavcopy.
    # Retry recent calendar dates because weekends and exchange holidays have no file.
    errors=[]
    for days_back in range(0,11):
        d=date.today()-timedelta(days=days_back)
        ds=d.strftime("%Y%m%d")
        filename=f"BhavCopy_NSE_FO_0_0_0_{ds}_F_0000.csv.zip"
        url=f"https://nsearchives.nseindia.com/content/fo/{filename}"
        try:
            r=get(url,headers={"Accept":"application/zip,application/octet-stream,*/*"})
            if len(r.content)<1000 or not r.content[:2]==b"PK": continue
            return filename,url,r.content,d.isoformat()
        except Exception as e: errors.append(f"{ds}: {str(e)[:160]}")
    raise RuntimeError("No recent NSE UDiFF FO bhavcopy archive found. "+" | ".join(errors[-3:]))

def ingest_fno(c):
    source="NSE F&O UDiFF bhavcopy"
    try:
        filename,url,blob,trade_date=find_nse_fo_zip()
        (RAW/filename).write_bytes(blob)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            csv_names=[n for n in z.namelist() if n.lower().endswith(".csv")]
            if not csv_names: raise RuntimeError("NSE ZIP contained no CSV file")
            member=csv_names[0]
            text=z.read(member).decode("utf-8-sig",errors="replace")
        reader=csv.DictReader(io.StringIO(text))
        rows=[]
        for i,row in enumerate(reader,1):
            clean={str(k).strip(): (v.strip() if isinstance(v,str) else v) for k,v in row.items() if k}
            rows.append((filename,"FO",i,json.dumps(clean,ensure_ascii=False),""))
        now=datetime.now().isoformat(timespec="seconds")
        c.execute("INSERT OR REPLACE INTO fno_files(filename,segment,trade_date,source_url,imported_at) VALUES(?,?,?,?,?)",
                  (filename,"FO",trade_date,url,now))
        c.executemany("INSERT OR REPLACE INTO fno_rows(filename,segment,row_number,payload,imported_at) VALUES(?,?,?,?,?)",
                      [(a,b,n,p,now) for a,b,n,p,_ in rows])
        status(c,source,"SUCCESS",len(rows),f"Trade date {trade_date}; {member}; official NSE archive")
    except Exception as e: status(c,source,"FAILED",0,repr(e))

def main():
    c=connect()
    try:
        ingest_scheme_master(c)
        ingest_mf(c)
        ingest_fno(c)
        print(json.dumps({r[0]:{"status":r[1],"records":r[2],"message":r[3]}
                          for r in c.execute("SELECT source,status,records,message FROM source_status")},indent=2))
    finally:c.close()

if __name__=="__main__": main()
