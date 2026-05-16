"""
CommodityPulse Alerts — app.py
================================
Streamlit dashboard.
Displays live signal status, price charts with indicators,
RSI gauges, and a signal history log for all 4 commodities.

Run locally:
  streamlit run app.py

Deploy on Streamlit Cloud or AWS:
  streamlit run app.py --server.port 8501 --server.address 0.0.0.0
"""

import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from engine import ASSETS, fetch_ohlcv, build_indicators, evaluate_signal

# ──────────────────────────────────────────────────────────────────────────────
#  PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title = "CommodityPulse Alerts",
    page_icon  = "📡",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
#  GLOBAL CSS
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600;700&display=swap');

/* Base */
:root {
  --navy:      #0f172a;
  --panel:     #1e293b;
  --panel2:    #273549;
  --border:    #334155;
  --bull:      #10b981;
  --bull-bg:   rgba(16,185,129,.12);
  --bear:      #ef4444;
  --bear-bg:   rgba(239,68,68,.12);
  --hold:      #64748b;
  --hold-bg:   rgba(100,116,139,.12);
  --amber:     #f59e0b;
  --blue:      #3b82f6;
  --text:      #e2e8f0;
  --muted:     #94a3b8;
  --mono:      'JetBrains Mono', monospace;
  --sans:      'Inter', sans-serif;
}

html, body, .stApp { background: var(--navy) !important; color: var(--text) !important; font-family: var(--sans); }
#MainMenu, footer, header { visibility: hidden !important; }
.block-container { padding: 1rem 2rem 2rem !important; max-width: 100% !important; }

/* Sidebar */
section[data-testid="stSidebar"] { background: var(--panel) !important; border-right: 1px solid var(--border); }
section[data-testid="stSidebar"] * { color: var(--text) !important; }
section[data-testid="stSidebar"] label { font-family: var(--mono) !important; font-size: 10px !important;
  text-transform: uppercase; letter-spacing: 1.5px; color: var(--muted) !important; }

/* Top bar */
.topbar {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 24px;
  margin-bottom: 20px;
  display: flex; align-items: center; justify-content: space-between;
}
.topbar-title {
  font-family: var(--mono); font-size: 22px; font-weight: 700;
  background: linear-gradient(90deg, #60a5fa, #34d399);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  letter-spacing: -0.5px;
}
.topbar-sub { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 4px; }
.topbar-time { font-family: var(--mono); font-size: 12px; color: var(--amber);
  background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.3);
  border-radius: 6px; padding: 6px 14px; }

/* Signal card */
.sig-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 12px;
  position: relative;
  overflow: hidden;
  transition: transform .15s;
}
.sig-card:hover { transform: translateY(-2px); }
.sig-card-bull { border-left: 4px solid var(--bull) !important; }
.sig-card-bear { border-left: 4px solid var(--bear) !important; }
.sig-card-hold { border-left: 4px solid var(--hold) !important; }

.sig-asset { font-family: var(--mono); font-size: 13px; font-weight: 700;
  color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
.sig-price { font-family: var(--mono); font-size: 26px; font-weight: 700;
  color: var(--text); line-height: 1; margin: 6px 0; }
.sig-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 20px;
  font-family: var(--mono); font-size: 11px; font-weight: 700; letter-spacing: .5px;
}
.sig-badge-bull { background: var(--bull-bg); color: var(--bull); border: 1px solid rgba(16,185,129,.35); }
.sig-badge-bear { background: var(--bear-bg); color: var(--bear); border: 1px solid rgba(239,68,68,.35);  }
.sig-badge-hold { background: var(--hold-bg); color: var(--hold); border: 1px solid rgba(100,116,139,.3); }

.sig-meta { font-family: var(--mono); font-size: 11px; color: var(--muted);
  margin-top: 8px; display: flex; gap: 16px; flex-wrap: wrap; }
.sig-sl  { font-family: var(--mono); font-size: 11px; color: var(--amber); margin-top: 6px; }

/* RSI gauge */
.rsi-track { background: var(--border); border-radius: 4px; height: 6px;
  position: relative; margin: 4px 0 8px; overflow: visible; }
.rsi-fill  { height: 100%; border-radius: 4px; transition: width .4s ease; }
.rsi-bull  { background: linear-gradient(90deg, #10b981, #34d399); }
.rsi-bear  { background: linear-gradient(90deg, #ef4444, #f87171); }
.rsi-neut  { background: linear-gradient(90deg, #64748b, #94a3b8); }
.rsi-label { font-family: var(--mono); font-size: 10px; color: var(--muted);
  display: flex; justify-content: space-between; }

/* Section header */
.sec-hdr { font-family: var(--mono); font-size: 10px; color: var(--muted);
  text-transform: uppercase; letter-spacing: 2px; margin: 18px 0 10px;
  padding-bottom: 6px; border-bottom: 1px solid var(--border); }

/* Signal history table */
.hist-row {
  display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr;
  gap: 8px; padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-family: var(--mono); font-size: 11px;
}
.hist-hdr { background: var(--panel2); color: var(--muted);
  font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; border-radius: 6px 6px 0 0; }

/* Metric strip */
.metric-strip {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 16px;
  display: flex; gap: 24px; flex-wrap: wrap;
  font-family: var(--mono); font-size: 11px; margin-bottom: 14px;
}
.metric-item { display: flex; flex-direction: column; gap: 2px; }
.metric-lbl  { font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
.metric-val  { font-size: 15px; font-weight: 700; color: var(--text); }
.metric-bull { color: var(--bull) !important; }
.metric-bear { color: var(--bear) !important; }
.metric-amb  { color: var(--amber) !important; }

/* Plotly container */
.chart-container { background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 4px; margin-bottom: 16px; overflow: hidden; }

/* Disclaimer */
.disclaimer { background: rgba(239,68,68,.07); border: 1px solid rgba(239,68,68,.2);
  border-radius: 8px; padding: 12px 16px; margin-top: 20px;
  font-family: var(--mono); font-size: 10px; color: rgba(239,68,68,.8); text-align: center; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--navy); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SESSION STATE
# ──────────────────────────────────────────────────────────────────────────────

if "signal_history" not in st.session_state:
    st.session_state.signal_history = []   # list of dicts
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {name: None for name in ASSETS}


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _badge(signal: str) -> str:
    if signal == "BULLISH":
        return '<span class="sig-badge sig-badge-bull">▲ BULLISH</span>'
    if signal == "BEARISH":
        return '<span class="sig-badge sig-badge-bear">▼ BEARISH</span>'
    return '<span class="sig-badge sig-badge-hold">⏸ HOLD</span>'


def _card_cls(signal: str) -> str:
    return {"BULLISH": "sig-card-bull", "BEARISH": "sig-card-bear"}.get(signal, "sig-card-hold")


def _rsi_bar(rsi: float) -> str:
    pct   = min(max(rsi, 0), 100)
    cls   = "rsi-bull" if rsi > 55 else "rsi-bear" if rsi < 45 else "rsi-neut"
    color = "#10b981" if rsi > 55 else "#ef4444" if rsi < 45 else "#64748b"
    zone  = "BULL ZONE" if rsi > 55 else "BEAR ZONE" if rsi < 45 else "NEUTRAL"
    return f"""
    <div class="rsi-label"><span>RSI {rsi:.1f}</span><span>{zone}</span></div>
    <div class="rsi-track">
      <div class="rsi-fill {cls}" style="width:{pct}%"></div>
    </div>
    <div class="rsi-label"><span>0</span><span style="color:{color}">●</span><span>100</span></div>
    """


def _build_chart(df: pd.DataFrame, asset_name: str, result: dict) -> go.Figure:
    """
    Build a two-panel Plotly chart:
      Top:    Candlestick + EMA-9/21/200 lines + SL annotation
      Bottom: RSI with overbought/oversold bands
    """
    display = df.tail(80).copy()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.03,
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x     = display.index,
        open  = display["open"],
        high  = display["high"],
        low   = display["low"],
        close = display["close"],
        name  = asset_name,
        increasing_line_color  = "#10b981",
        decreasing_line_color  = "#ef4444",
        increasing_fillcolor   = "rgba(16,185,129,.6)",
        decreasing_fillcolor   = "rgba(239,68,68,.6)",
        showlegend = False,
    ), row=1, col=1)

    # EMAs
    for col, color, width, name in [
        ("ema_9",   "#60a5fa", 1.2, "EMA 9"),
        ("ema_21",  "#f59e0b", 1.2, "EMA 21"),
        ("ema_200", "#a78bfa", 1.6, "EMA 200"),
    ]:
        if col in display.columns:
            fig.add_trace(go.Scatter(
                x    = display.index,
                y    = display[col],
                name = name,
                line = dict(color=color, width=width),
                mode = "lines",
            ), row=1, col=1)

    # Stop-loss line
    sl = result.get("sl", 0)
    if sl and sl > 0:
        sl_color = "#10b981" if result.get("signal") == "BULLISH" else "#ef4444"
        fig.add_hline(
            y          = sl,
            line_dash  = "dot",
            line_color = sl_color,
            line_width = 1.2,
            annotation_text  = f"SL {sl:,.2f}",
            annotation_font  = dict(color=sl_color, size=10),
            annotation_position = "right",
            row=1, col=1,
        )

    # RSI panel
    if "rsi" in display.columns:
        rsi_color = display["rsi"].apply(
            lambda v: "#10b981" if v > 55 else "#ef4444" if v < 45 else "#94a3b8"
        )
        fig.add_trace(go.Scatter(
            x    = display.index,
            y    = display["rsi"],
            name = "RSI 14",
            line = dict(color="#60a5fa", width=1.5),
            mode = "lines",
            fill = "tozeroy",
            fillcolor = "rgba(96,165,250,.08)",
        ), row=2, col=1)

        for level, color, label in [(70, "rgba(239,68,68,.35)", "OB 70"),
                                    (55, "rgba(16,185,129,.25)", "Bull 55"),
                                    (45, "rgba(239,68,68,.25)", "Bear 45"),
                                    (30, "rgba(16,185,129,.35)", "OS 30")]:
            fig.add_hline(
                y=level, line_dash="dot", line_color=color, line_width=1,
                annotation_text=label,
                annotation_font=dict(color=color, size=9),
                annotation_position="right",
                row=2, col=1,
            )

    # Layout
    sig    = result.get("signal", "HOLD")
    t_col  = "#10b981" if sig == "BULLISH" else "#ef4444" if sig == "BEARISH" else "#64748b"

    fig.update_layout(
        title       = dict(
            text      = f"{asset_name}  ·  15-min  ·  <span style='color:{t_col}'>{sig}</span>",
            font      = dict(family="JetBrains Mono", size=14, color="#e2e8f0"),
            x         = 0.01,
        ),
        paper_bgcolor = "#1e293b",
        plot_bgcolor  = "#1e293b",
        font          = dict(family="JetBrains Mono", size=11, color="#94a3b8"),
        margin        = dict(l=10, r=10, t=44, b=10),
        height        = 460,
        legend        = dict(
            orientation = "h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=10), bgcolor="rgba(0,0,0,0)",
        ),
        xaxis_rangeslider_visible = False,
        xaxis2 = dict(showgrid=False, zeroline=False),
        yaxis  = dict(
            gridcolor="#273549", zeroline=False, tickfont=dict(size=10),
            title=dict(text="Price", font=dict(size=10)),
        ),
        yaxis2 = dict(
            gridcolor="#273549", zeroline=False,
            range=[0, 100], tickfont=dict(size=10),
            title=dict(text="RSI", font=dict(size=10)),
        ),
        xaxis=dict(gridcolor="#273549", zeroline=False),
    )

    return fig


def _update_history(asset_name: str, signal: str, result: dict):
    """Append a new entry to signal_history in session state."""
    st.session_state.signal_history.append({
        "time":   datetime.utcnow().strftime("%d-%b %H:%M"),
        "asset":  asset_name,
        "signal": signal,
        "price":  result.get("price", 0),
        "rsi":    result.get("rsi", 0),
        "sl":     result.get("sl", 0),
    })
    # Keep last 50 entries
    st.session_state.signal_history = st.session_state.signal_history[-50:]


# ──────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="padding:20px 4px 8px">
      <div style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;
                  background:linear-gradient(90deg,#60a5fa,#34d399);
                  -webkit-background-clip:text;-webkit-text-fill-color:transparent">
        📡 CommodityPulse
      </div>
      <div style="font-size:10px;color:#64748b;letter-spacing:2px;margin-top:4px;
                  font-family:'JetBrains Mono',monospace">SIGNAL ENGINE · v1.0</div>
    </div>
    <div style="height:1px;background:#334155;margin:8px 0 16px"></div>
    """, unsafe_allow_html=True)

    st.markdown("**⚙️ Settings**")
    auto_refresh = st.toggle("Auto Refresh", value=True)
    refresh_sec  = st.slider("Refresh interval (s)", 30, 300, 60, 15)

    st.markdown('<div style="height:1px;background:#334155;margin:16px 0"></div>',
                unsafe_allow_html=True)
    st.markdown("**📊 Signal Filter**")
    show_hold    = st.checkbox("Show HOLD assets", value=True)
    show_bull    = st.checkbox("Show BULLISH", value=True)
    show_bear    = st.checkbox("Show BEARISH", value=True)

    st.markdown('<div style="height:1px;background:#334155;margin:16px 0"></div>',
                unsafe_allow_html=True)
    st.markdown("**📋 Assets**")
    selected_assets = st.multiselect(
        "Monitor",
        options=list(ASSETS.keys()),
        default=list(ASSETS.keys()),
        label_visibility="collapsed",
    )

    st.markdown('<div style="height:1px;background:#334155;margin:16px 0"></div>',
                unsafe_allow_html=True)
    manual_refresh = st.button("🔄 Refresh Now", use_container_width=True)

    st.markdown("""
    <div style="margin-top:20px;font-family:'JetBrains Mono',monospace;
                font-size:9px;color:#475569;line-height:1.8">
      <div>Data: Yahoo Finance</div>
      <div>Interval: 15-min candles</div>
      <div>Engine: EMA 9 / 21 / 200</div>
      <div>RSI window: 14 periods</div>
      <div>ATR SL mult: 1.5×</div>
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  TOP BAR
# ──────────────────────────────────────────────────────────────────────────────

now_str = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC")
st.markdown(f"""
<div class="topbar">
  <div>
    <div class="topbar-title">📡 CommodityPulse Alerts</div>
    <div class="topbar-sub">
      Multi-Asset Signal Engine · 15-min · EMA 9/21/200 + RSI Confluence · Signal-Only
    </div>
  </div>
  <div class="topbar-time">🕐 {now_str}</div>
</div>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN DATA FETCH LOOP
# ──────────────────────────────────────────────────────────────────────────────

with st.spinner("Fetching live commodity data…"):
    all_results: dict = {}
    all_dfs:     dict = {}

    for asset_name, meta in ASSETS.items():
        if asset_name not in selected_assets:
            continue
        ticker = meta["ticker"]
        df = fetch_ohlcv(ticker)
        if df is None:
            all_results[asset_name] = {"signal": "HOLD", "error": True}
            continue
        df = build_indicators(df)
        result = evaluate_signal(df)
        all_results[asset_name] = result
        all_dfs[asset_name]     = df

        # Update history if signal changed
        current = result.get("signal", "HOLD")
        if (current != "HOLD" and
                current != st.session_state.last_signals.get(asset_name)):
            _update_history(asset_name, current, result)
            st.session_state.last_signals[asset_name] = current
        elif current == "HOLD":
            st.session_state.last_signals[asset_name] = "HOLD"


# ──────────────────────────────────────────────────────────────────────────────
#  SUMMARY STRIP
# ──────────────────────────────────────────────────────────────────────────────

bull_count = sum(1 for r in all_results.values() if r.get("signal") == "BULLISH")
bear_count = sum(1 for r in all_results.values() if r.get("signal") == "BEARISH")
hold_count = sum(1 for r in all_results.values() if r.get("signal") == "HOLD")

sentiment = "BULLISH" if bull_count > bear_count else "BEARISH" if bear_count > bull_count else "MIXED"
sent_color = "metric-bull" if sentiment == "BULLISH" else "metric-bear" if sentiment == "BEARISH" else "metric-amb"

st.markdown(f"""
<div class="metric-strip">
  <div class="metric-item">
    <div class="metric-lbl">Market Sentiment</div>
    <div class="metric-val {sent_color}">{sentiment}</div>
  </div>
  <div class="metric-item">
    <div class="metric-lbl">Bullish Signals</div>
    <div class="metric-val metric-bull">{bull_count}</div>
  </div>
  <div class="metric-item">
    <div class="metric-lbl">Bearish Signals</div>
    <div class="metric-val metric-bear">{bear_count}</div>
  </div>
  <div class="metric-item">
    <div class="metric-lbl">Neutral / Hold</div>
    <div class="metric-val" style="color:#64748b">{hold_count}</div>
  </div>
  <div class="metric-item">
    <div class="metric-lbl">Assets Monitored</div>
    <div class="metric-val">{len(selected_assets)}</div>
  </div>
  <div class="metric-item">
    <div class="metric-lbl">Last Update</div>
    <div class="metric-val metric-amb">{datetime.utcnow().strftime('%H:%M:%S')}</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SIGNAL CARDS  (2-column grid)
# ──────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="sec-hdr">📊 LIVE SIGNAL STATUS</div>', unsafe_allow_html=True)

asset_items = [
    (name, all_results.get(name, {}), all_dfs.get(name))
    for name in selected_assets
]

# Filter by sidebar checkboxes
def _sig_visible(sig):
    if sig == "BULLISH" and not show_bull: return False
    if sig == "BEARISH" and not show_bear: return False
    if sig == "HOLD"    and not show_hold: return False
    return True

visible = [(n, r, d) for n, r, d in asset_items if _sig_visible(r.get("signal", "HOLD"))]

col_pairs = [visible[i:i+2] for i in range(0, len(visible), 2)]

for pair in col_pairs:
    cols = st.columns(2)
    for col_idx, (asset_name, result, df) in enumerate(pair):
        meta   = ASSETS[asset_name]
        emoji  = meta["emoji"]
        ticker = meta["ticker"]
        dp     = meta["dp"]
        curr   = meta["curr"]
        signal = result.get("signal", "HOLD")
        price  = result.get("price", 0)
        rsi    = result.get("rsi", 0)
        trend  = result.get("trend", "N/A")
        sl     = result.get("sl", 0)
        atr    = result.get("atr", 0)
        ema9   = result.get("ema_9", 0)
        ema21  = result.get("ema_21", 0)
        ema200 = result.get("ema_200", 0)
        error  = result.get("error", False)

        card_cls  = _card_cls(signal)
        badge_html = _badge(signal)

        sl_html = ""
        if sl and sl > 0:
            sl_html = f'<div class="sig-sl">📐 Suggested SL: {curr}{sl:,.{dp}f}  <span style="opacity:.6">(1.5 × ATR)</span></div>'

        err_html = '<div style="color:#ef4444;font-size:11px;margin-top:8px">⚠️ Data unavailable this cycle</div>' if error else ""

        with cols[col_idx]:
            st.markdown(f"""
            <div class="sig-card {card_cls}">
              <div class="sig-asset">{emoji} {asset_name} · {ticker}</div>
              <div class="sig-price">{curr}{price:,.{dp}f}</div>
              {badge_html}
              {_rsi_bar(rsi)}
              <div class="sig-meta">
                <span>Trend: <b style="color:{'#10b981' if trend=='BULLISH' else '#ef4444' if trend=='BEARISH' else '#64748b'}">{trend}</b></span>
                <span>EMA9: {curr}{ema9:,.{dp}f}</span>
                <span>EMA21: {curr}{ema21:,.{dp}f}</span>
                <span>EMA200: {curr}{ema200:,.{dp}f}</span>
                <span>ATR: {curr}{atr:,.{dp}f}</span>
              </div>
              {sl_html}
              {err_html}
            </div>
            """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  PRICE CHARTS (one per asset, expandable)
# ──────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="sec-hdr">📈 PRICE CHARTS WITH INDICATORS</div>', unsafe_allow_html=True)

for asset_name, result, df in visible:
    if df is None:
        continue
    meta  = ASSETS[asset_name]
    emoji = meta["emoji"]

    with st.expander(f"{emoji}  {asset_name}  —  Click to expand chart", expanded=True):
        fig = _build_chart(df, asset_name, result)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

        # Indicator strip below chart
        price  = result.get("price",   0)
        rsi    = result.get("rsi",     0)
        atr    = result.get("atr",     0)
        ema9   = result.get("ema_9",   0)
        ema21  = result.get("ema_21",  0)
        ema200 = result.get("ema_200", 0)
        dp     = meta["dp"]
        curr   = meta["curr"]

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Close",    f"{curr}{price:,.{dp}f}")
        c2.metric("RSI 14",   f"{rsi:.1f}")
        c3.metric("ATR 14",   f"{curr}{atr:,.{dp}f}")
        c4.metric("EMA 9",    f"{curr}{ema9:,.{dp}f}")
        c5.metric("EMA 21",   f"{curr}{ema21:,.{dp}f}")
        c6.metric("EMA 200",  f"{curr}{ema200:,.{dp}f}")


# ──────────────────────────────────────────────────────────────────────────────
#  SIGNAL HISTORY TABLE
# ──────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="sec-hdr">📋 SIGNAL HISTORY (this session)</div>', unsafe_allow_html=True)

history = st.session_state.signal_history
if not history:
    st.markdown(
        '<div style="font-family:JetBrains Mono,monospace;font-size:12px;'
        'color:#475569;padding:20px;text-align:center;">'
        'No signals fired yet this session. Waiting for EMA + RSI confluence…'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown("""
    <div class="hist-row hist-hdr">
      <span>Asset</span><span>Time (UTC)</span>
      <span>Signal</span><span>Price</span><span>Sugg. SL</span>
    </div>
    """, unsafe_allow_html=True)

    for entry in reversed(history):
        sig   = entry["signal"]
        s_col = "#10b981" if sig == "BULLISH" else "#ef4444"
        icon  = "▲" if sig == "BULLISH" else "▼"
        a_meta = ASSETS.get(entry["asset"], {})
        dp     = a_meta.get("dp", 2)
        curr   = a_meta.get("curr", "$")

        st.markdown(f"""
        <div class="hist-row" style="background:rgba(30,41,59,.5)">
          <span>{a_meta.get('emoji','📊')} {entry['asset']}</span>
          <span style="color:#64748b">{entry['time']}</span>
          <span style="color:{s_col};font-weight:700">{icon} {sig}</span>
          <span>{curr}{entry['price']:,.{dp}f}</span>
          <span style="color:#f59e0b">{curr}{entry['sl']:,.{dp}f}</span>
        </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  DISCLAIMER
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="disclaimer">
  ⚠️ CommodityPulse is a SIGNAL-ONLY tool. It does not place trades or manage money.
  All signals are algorithmic and for informational purposes only.
  Commodity trading carries substantial risk. Consult a financial advisor before trading.
</div>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  AUTO REFRESH
# ──────────────────────────────────────────────────────────────────────────────

if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()
elif manual_refresh:
    st.rerun()
