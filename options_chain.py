"""StockWise AI option-chain panel. Import and call render_options_chain() in Streamlit."""
from __future__ import annotations
import pandas as pd
import streamlit as st

REQUIRED = ["strike", "call_oi", "call_ltp", "put_ltp", "put_oi"]

def normalize_chain(records):
    """Accept provider-normalized records; never fabricate missing prices."""
    df = pd.DataFrame(records)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Missing option-chain fields: " + ", ".join(missing))
    for c in REQUIRED + [c for c in ("call_oi_change_pct", "put_oi_change_pct", "call_iv", "put_iv") if c in df]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["strike"]).sort_values("strike")

def render_options_chain(records=None, spot=None, instrument="NIFTY 50", expiry=None, quote_time=None):
    """Render screenshot-inspired calls/strike/puts layout; provider data is injected by caller."""
    st.markdown("""<style>
    .sw-oc-head{background:#B9664E;color:white;padding:13px 17px;border-radius:12px;font-weight:700}
    .sw-oc-note{color:#A5AD91;font-size:.85rem}
    </style>""", unsafe_allow_html=True)
    st.markdown(f'<div class="sw-oc-head">{instrument} · Options Chain</div>', unsafe_allow_html=True)
    st.caption(f"Expiry: {expiry or 'Not selected'} · Quote time: {quote_time or 'Unavailable'} · Source: external provider")
    if records is None:
        st.warning("Option-chain quotes unavailable. Connect a licensed NSE-compatible market-data provider; no sample quotes are displayed as live.")
        return
    try:
        df = normalize_chain(records)
    except ValueError as exc:
        st.error(str(exc))
        return
    if df.empty:
        st.info("No contracts returned for this expiry.")
        return
    atm = None
    if spot is not None:
        atm = float(df.loc[(df["strike"] - float(spot)).abs().idxmin(), "strike"])
        st.metric("Underlying spot", f"{float(spot):,.2f}")
    call_total = df["call_oi"].sum(min_count=1)
    put_total = df["put_oi"].sum(min_count=1)
    pcr = put_total / call_total if pd.notna(call_total) and call_total > 0 else None
    a,b,c = st.columns(3)
    a.metric("Put / Call OI", f"{pcr:.3f}" if pcr is not None else "N/A")
    b.metric("Call OI", f"{call_total:,.0f}" if pd.notna(call_total) else "N/A")
    c.metric("Put OI", f"{put_total:,.0f}" if pd.notna(put_total) else "N/A")
    view = df[REQUIRED + [col for col in ("call_oi_change_pct", "put_oi_change_pct") if col in df]].copy()
    view = view.rename(columns={"call_oi":"CALL OI","call_ltp":"CALL LTP","strike":"STRIKE","put_ltp":"PUT LTP","put_oi":"PUT OI","call_oi_change_pct":"CALL OI Δ%","put_oi_change_pct":"PUT OI Δ%"})
    cols = ["CALL OI", "CALL LTP"]
    if "CALL OI Δ%" in view: cols.append("CALL OI Δ%")
    cols += ["STRIKE", "PUT LTP", "PUT OI"]
    if "PUT OI Δ%" in view: cols.append("PUT OI Δ%")
    def style_row(row):
        if atm is not None and row["STRIKE"] == atm:
            return ["background-color:rgba(49,91,203,.20);font-weight:bold"] * len(row)
        return [""] * len(row)
    st.dataframe(view[cols].style.apply(style_row, axis=1).format(precision=2, na_rep="—"), use_container_width=True, hide_index=True, height=560)
    st.caption("OI and PCR reflect only contracts returned by the provider. No max-pain estimate is shown without complete expiry data.")
