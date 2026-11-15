"""Five-factor CRISP summary for StockWise AI. No fabricated fundamental scores."""
from __future__ import annotations
import html
import math
import pandas as pd
import streamlit as st

FACTORS = ("Momentum", "Value", "Quality", "Stability", "Sentiment")

def _valid(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None

def _pick(data, *keys):
    if data is None:
        return None
    for key in keys:
        if isinstance(data, dict) and key in data:
            value = _valid(data[key])
            if value is not None:
                return value
    return None

def _score(value):
    value = _valid(value)
    if value is None:
        return None
    # The caller must provide a 1–5 factor score; do not rescale unknown score systems.
    if 1 <= value <= 5:
        return int(round(value))
    return None

def _momentum(history):
    """Fallback momentum from 20-session return; no cross-universe claim."""
    if history is None or not isinstance(history, pd.DataFrame) or "Close" not in history:
        return None
    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if len(close) < 21 or close.iloc[-21] <= 0:
        return None
    change = (close.iloc[-1] / close.iloc[-21] - 1) * 100
    if change <= -10: return 1
    if change <= -3: return 2
    if change < 3: return 3
    if change < 10: return 4
    return 5

def _stability(history):
    """Fallback volatility score from daily close-to-close changes."""
    if history is None or not isinstance(history, pd.DataFrame) or "Close" not in history:
        return None
    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if len(close) < 61:
        return None
    returns = close.pct_change().dropna().tail(60)
    if len(returns) < 40:
        return None
    vol = float(returns.std() * (252 ** .5) * 100)
    if vol < 15: return 5
    if vol < 25: return 4
    if vol < 35: return 3
    if vol < 50: return 2
    return 1

DESCRIPTIONS = {
    "Momentum": {
        1: "Recent price momentum is strongly negative.",
        2: "Recent price momentum is weak.",
        3: "Recent price momentum is broadly neutral.",
        4: "Recent price momentum is positive.",
        5: "Recent price momentum is strongly positive.",
    },
    "Value": {
        1: "Valuation metrics suggest an expensive stock.",
        2: "Valuation metrics suggest a relatively high valuation.",
        3: "Valuation metrics indicate a neutral valuation.",
        4: "Valuation metrics suggest an attractive valuation.",
        5: "Valuation metrics suggest a highly attractive valuation.",
    },
    "Quality": {
        1: "Fundamental quality indicators are weak.",
        2: "Fundamental quality indicators are below average.",
        3: "Fundamental quality indicators are mixed.",
        4: "Fundamental quality indicators are strong.",
        5: "Fundamental quality indicators are very strong.",
    },
    "Stability": {
        1: "Historical price volatility is very high.",
        2: "Historical price volatility is elevated.",
        3: "Historical price volatility is moderate.",
        4: "Historical price volatility is relatively low.",
        5: "Historical price volatility is very low.",
    },
    "Sentiment": {
        1: "Available sentiment indicators are strongly negative.",
        2: "Available sentiment indicators are negative.",
        3: "Available sentiment indicators are neutral.",
        4: "Available sentiment indicators are positive.",
        5: "Available sentiment indicators are strongly positive.",
    },
}

def render_five_factor_summary(stock_name, factor_scores=None, history=None):
    """Render a reference-style card under the existing CRISP radar.

    factor_scores: dict with 1–5 scores under factor names. The optional
    history is used only to estimate missing Momentum and Stability scores.
    Value, Quality and Sentiment require real supplied inputs.
    """
    supplied = factor_scores or {}
    scores = {name: _score(_pick(supplied, name, name.lower())) for name in FACTORS}
    estimated = set()
    if scores["Momentum"] is None:
        scores["Momentum"] = _momentum(history)
        if scores["Momentum"] is not None: estimated.add("Momentum")
    if scores["Stability"] is None:
        scores["Stability"] = _stability(history)
        if scores["Stability"] is not None: estimated.add("Stability")

    strengths = [name.lower() for name in FACTORS if scores[name] is not None and scores[name] >= 4]
    concerns = [name.lower() for name in FACTORS if scores[name] is not None and scores[name] <= 2]
    summary = ("Strengths: " + ", ".join(strengths) + ". " if strengths else "")
    summary += ("Watch-outs: " + ", ".join(concerns) + ". " if concerns else "")
    if not summary:
        summary = "Insufficient verified factor data to produce a stock summary."
    if any(scores[name] is None for name in FACTORS):
        summary += " Some factors are unavailable pending reliable data."

    st.markdown("""<style>
    .sw-five-card{background:#151719;border:1px solid #34373a;border-radius:18px;
      overflow:hidden;color:#f5f5f5;margin:14px 0 24px;font-family:inherit}
    .sw-five-head{padding:24px 28px;background:#1c1e20}
    .sw-five-title{font-size:25px;font-weight:750;line-height:1.35;color:#fff}
    .sw-five-summary{font-size:17px;color:#aaaeb3;line-height:1.6;margin-top:12px}
    .sw-five-row{display:flex;gap:22px;align-items:center;padding:20px 28px;
      border-top:1px dashed #383b3e}
    .sw-five-score{width:76px;min-width:76px;height:76px;display:flex;
      align-items:center;justify-content:center;border-radius:10px;font-size:28px;
      font-weight:700}
    .sw-five-score small{font-size:15px;font-weight:400}
    .sw-five-name{font-size:22px;font-weight:750;color:#fff}
    .sw-five-desc{font-size:16px;color:#aaaeb3;line-height:1.5;margin-top:6px}
    @media(max-width:600px){.sw-five-head{padding:18px}.sw-five-row{padding:16px;gap:14px}
      .sw-five-score{width:62px;min-width:62px;height:62px;font-size:24px}
      .sw-five-name{font-size:19px}.sw-five-desc{font-size:14px}}
    </style>""", unsafe_allow_html=True)

    rows = []
    for name in FACTORS:
        value = scores[name]
        if value is None:
            fg, bg, label = "#aeb2b8", "#292c30", "N/A"
            desc = "Not available: reliable factor inputs have not been supplied."
        else:
            fg, bg = (("#e06b72", "#49191d") if value <= 2 else
                      ("#eba66c", "#43230e") if value == 3 else
                      ("#31c48d", "#09291c"))
            label = f"{value}<small>/5</small>"
            desc = DESCRIPTIONS[name][value]
            if name in estimated:
                desc += " Estimated from historical prices."
        rows.append(
            '<div class="sw-five-row"><div class="sw-five-score" '
            f'style="color:{fg};background:{bg}">{label}</div>'
            '<div><div class="sw-five-name">' + html.escape(name) + '</div>'
            '<div class="sw-five-desc">' + html.escape(desc) + '</div></div></div>'
        )
    markup = (
        '<div class="sw-five-card"><div class="sw-five-head">'
        '<div class="sw-five-title">' + html.escape(str(stock_name)) + ' summarised</div>'
        '<div class="sw-five-summary">' + html.escape(summary) + '</div></div>'
        + ''.join(rows) + '</div>'
    )
    st.markdown(markup, unsafe_allow_html=True)
    return scores
