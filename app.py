"""
CommodityPulse Alerts — app.py  v1.1
======================================
Streamlit dashboard.

FIX v1.1: Signal cards were rendering raw HTML source instead of styled
content. Root cause: _rsi_bar() and _badge() returned HTML strings that
were embedded inside nested f-strings — Python's f-string parser
corrupted the inner quotes and curly braces before Streamlit could
render them. Fix: every card is now built via plain string concatenation
(+) with NO nested f-strings, NO function calls inside f-string braces.
All interpolation is done before the HTML string is opened.

Run locally:
  streamlit run app.py

Run on AWS / Streamlit Cloud:
  streamlit run app.py --server.port 8501 --server.address 0.0.0.0
"""

import time
from datetime import datetime, timezone

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from engine import ASSETS, fetch_ohlcv, build_indicators, evaluate_signal

# ─────────────────────────────────────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CommodityPulse Alerts",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@300;400;600;700&display=swap');

:root {
  --navy:     #0f172a;
  --panel:    #1e293b;
  --panel2:   #273549;
  --border:   #334155;
  --bull:     #10b981;
  --bull-bg:  rgba(16,185,129,.13);
  --bear:     #ef4444;
  --bear-bg:  rgba(239,68,68,.13);
  --hold:     #64748b;
  --hold-bg:  rgba(100,116,139,.13);
  --amber:    #f59e0b;
  --blue:     #3b82f6;
  --text:     #e2e8f0;
  --muted:    #94a3b8;
  --mono:     'JetBrains Mono', monospace;
  --sans:     'Inter', sans-serif;
}

html, body, .stApp { background: var(--navy) !important; color: var(--text) !important; }
#MainMenu, footer, header { visibility: hidden !important; }
.block-container { padding: 1rem 2rem 2rem !important; max-width: 100% !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
  background: var(--panel) !important;
  border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] * { color: var(--text) !important; }
section[data-testid="stSidebar"] label {
  font-family: var(--mono) !important; font-size: 10px !important;
  text-transform: uppercase; letter-spacing: 1.5px; color: var(--muted) !important;
}
section[data-testid="stSidebar"] .stButton > button {
  background: rgba(59,130,246,.15) !important;
  border: 1px solid rgba(59,130,246,.35) !important;
  color: #93c5fd !important; font-family: var(--mono) !important;
  font-size: 11px !important; border-radius: 8px !important;
}

/* Top bar */
.topbar {
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
  border: 1px solid var(--border); border-radius: 12px;
  padding: 18px 24px; margin-bottom: 20px;
  display: flex; align-items: center; justify-content: space-between;
}
.topbar-title {
  font-family: var(--mono); font-size: 22px; font-weight: 700;
  background: linear-gradient(90deg, #60a5fa, #34d399);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.topbar-sub { font-size: 11px; color: var(--muted); margin-top: 4px; font-family: var(--mono); }
.topbar-time {
  font-family: var(--mono); font-size: 12px; color: var(--amber);
  background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.3);
  border-radius: 6px; padding: 6px 14px;
}

/* Summary strip */
.metric-strip {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 20px;
  display: flex; gap: 28px; flex-wrap: wrap;
  font-family: var(--mono); margin-bottom: 16px;
}
.metric-item { display: flex; flex-direction: column; gap: 3px; }
.metric-lbl  { font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
.metric-val  { font-size: 16px; font-weight: 700; color: var(--text); }
.c-bull { color: var(--bull) !important; }
.c-bear { color: var(--bear) !important; }
.c-amb  { color: var(--amber) !important; }
.c-mute { color: var(--muted) !important; }

/* Signal card */
.sig-card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 22px; margin-bottom: 14px;
  transition: transform .15s, box-shadow .15s;
}
.sig-card:hover { transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,.35); }
.card-bull { border-left: 4px solid var(--bull) !important; }
.card-bear { border-left: 4px solid var(--bear) !important; }
.card-hold { border-left: 4px solid var(--hold) !important; }

.card-header {
  display: flex; align-items: flex-start;
  justify-content: space-between; margin-bottom: 8px;
}
.card-asset {
  font-family: var(--mono); font-size: 12px; font-weight: 700;
  color: var(--muted); text-transform: uppercase; letter-spacing: 1.2px;
}
.card-ticker {
  font-family: var(--mono); font-size: 10px; color: var(--hold);
  background: var(--hold-bg); border-radius: 4px; padding: 2px 7px;
}
.card-price {
  font-family: var(--mono); font-size: 30px; font-weight: 700;
  color: var(--text); line-height: 1; margin: 4px 0 12px; letter-spacing: -1px;
}

/* Signal badge */
.badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 13px; border-radius: 20px;
  font-family: var(--mono); font-size: 11px; font-weight: 700;
  letter-spacing: .5px; margin-bottom: 14px;
}
.badge-bull { background: var(--bull-bg); color: var(--bull); border: 1px solid rgba(16,185,129,.4); }
.badge-bear { background: var(--bear-bg); color: var(--bear); border: 1px solid rgba(239,68,68,.4); }
.badge-hold { background: var(--hold-bg); color: var(--hold); border: 1px solid rgba(100,116,139,.3); }

/* RSI bar */
.rsi-labels {
  display: flex; justify-content: space-between;
  font-family: var(--mono); font-size: 10px; color: var(--muted);
  margin-bottom: 4px;
}
.rsi-track {
  background: var(--border); border-radius: 4px; height: 7px;
  margin-bottom: 2px; overflow: hidden;
}
.rsi-fill-bull { background: linear-gradient(90deg,#059669,#10b981); height: 100%; border-radius: 4px; }
.rsi-fill-bear { background: linear-gradient(90deg,#dc2626,#ef4444); height: 100%; border-radius: 4px; }
.rsi-fill-neut { background: linear-gradient(90deg,#475569,#64748b); height: 100%; border-radius: 4px; }
.rsi-ends {
  display: flex; justify-content: space-between;
  font-family: var(--mono); font-size: 9px; color: #475569; margin-bottom: 10px;
}

/* Indicator chips */
.ind-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
.ind-chip {
  background: var(--panel2); border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 10px;
  font-family: var(--mono); font-size: 10px; color: var(--muted);
}
.ind-chip span { color: var(--text); font-weight: 700; }

/* Trend label */
.trend-bull { color: var(--bull); font-weight: 700; }
.trend-bear { color: var(--bear); font-weight: 700; }
.trend-neut { color: var(--muted); font-weight: 700; }

/* Stop-loss row */
.sl-row { margin-top: 10px; font-family: var(--mono); font-size: 11px; color: var(--amber); }
.sl-note { opacity: .6; font-size: 10px; }

/* Error */
.card-err { color: var(--bear); font-size: 11px; margin-top: 8px; font-family: var(--mono); }

/* Section header */
.sec-hdr {
  font-family: var(--mono); font-size: 10px; color: var(--muted);
  text-transform: uppercase; letter-spacing: 2px;
  margin: 20px 0 12px; padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

/* Chart wrapper */
.chart-wrap {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; overflow: hidden; margin-bottom: 8px;
}

/* History table */
.hist-grid {
  display: grid; grid-template-columns: 2fr 1.2fr 1.2fr 1.2fr 1.2fr;
  gap: 4px; padding: 9px 14px;
  border-bottom: 1px solid var(--border);
  font-family: var(--mono); font-size: 11px;
}
.hist-hdr {
  background: var(--panel2); border-radius: 8px 8px 0 0;
  color: var(--muted); font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase;
}
.hist-body { background: rgba(30,41,59,.5); }
.hist-body:hover { background: var(--panel2); }

/* Disclaimer */
.disclaimer {
  background: rgba(239,68,68,.07); border: 1px solid rgba(239,68,68,.2);
  border-radius: 8px; padding: 12px 18px; margin-top: 24px;
  font-family: var(--mono); font-size: 10px; color: rgba(239,68,68,.75);
  text-align: center;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

if "signal_history" not in st.session_state:
    st.session_state.signal_history = []
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {name: None for name in ASSETS}


# ─────────────────────────────────────────────────────────────────────────────
#  HTML BUILDER FUNCTIONS
#  All HTML is assembled with plain string concatenation (+).
#  No function calls or expressions inside f-string braces.
#  All values are pre-computed into local variables before any string is built.
# ─────────────────────────────────────────────────────────────────────────────

def _badge_html(signal: str) -> str:
    """Standalone badge div — no f-string used."""
    if signal == "BULLISH":
        return '<div class="badge badge-bull">&#9650; BULLISH</div>'
    if signal == "BEARISH":
        return '<div class="badge badge-bear">&#9660; BEARISH</div>'
    return '<div class="badge badge-hold">&#9646; HOLD</div>'


def _rsi_html(rsi: float) -> str:
    """RSI bar — all values pre-computed, then joined with +."""
    pct_val  = min(max(rsi, 0.0), 100.0)
    pct_str  = str(round(pct_val, 1))
    rsi_str  = str(round(rsi, 1))

    if rsi > 55:
        fill_cls = "rsi-fill-bull"
        zone     = "BULL ZONE"
        zone_col = "#10b981"
    elif rsi < 45:
        fill_cls = "rsi-fill-bear"
        zone     = "BEAR ZONE"
        zone_col = "#ef4444"
    else:
        fill_cls = "rsi-fill-neut"
        zone     = "NEUTRAL"
        zone_col = "#64748b"

    return (
        '<div class="rsi-labels">'
        '<span>RSI ' + rsi_str + '</span>'
        '<span style="color:' + zone_col + ';">' + zone + '</span>'
        '</div>'
        '<div class="rsi-track">'
        '<div class="' + fill_cls + '" style="width:' + pct_str + '%;"></div>'
        '</div>'
        '<div class="rsi-ends"><span>0</span><span>100</span></div>'
    )


def _trend_html(trend: str) -> str:
    """Coloured trend span."""
    if trend == "BULLISH":
        return '<span class="trend-bull">BULLISH &#8593;</span>'
    if trend == "BEARISH":
        return '<span class="trend-bear">BEARISH &#8595;</span>'
    return '<span class="trend-neut">NEUTRAL</span>'


def _card_html(asset_name: str, result: dict) -> str:
    """
    Build the complete signal card HTML.
    Every value is extracted to a local variable first.
    The HTML string is assembled entirely with + concatenation.
    No function call or conditional expression appears inside {}.
    """
    meta   = ASSETS.get(asset_name, {})
    emoji  = meta.get("emoji", "")
    ticker = meta.get("ticker", asset_name)
    curr   = meta.get("curr", "$")
    dp     = meta.get("dp", 2)
    dp_fmt = ",." + str(dp) + "f"

    signal = result.get("signal", "HOLD")
    price  = float(result.get("price",   0))
    rsi    = float(result.get("rsi",     0))
    trend  = str(result.get("trend",     "NEUTRAL"))
    sl     = float(result.get("sl",      0))
    atr    = float(result.get("atr",     0))
    ema9   = float(result.get("ema_9",   0))
    ema21  = float(result.get("ema_21",  0))
    ema200 = float(result.get("ema_200", 0))
    error  = bool(result.get("error",    False))

    # Pre-compute every string that will appear in HTML
    if signal == "BULLISH":
        card_cls = "card-bull"
    elif signal == "BEARISH":
        card_cls = "card-bear"
    else:
        card_cls = "card-hold"

    price_s  = curr + format(price,  dp_fmt)
    ema9_s   = curr + format(ema9,   dp_fmt)
    ema21_s  = curr + format(ema21,  dp_fmt)
    ema200_s = curr + format(ema200, dp_fmt)
    atr_s    = curr + format(atr,    dp_fmt)

    badge_h  = _badge_html(signal)
    rsi_h    = _rsi_html(rsi)
    trend_h  = _trend_html(trend)

    # Stop-loss section
    sl_section = ""
    if sl > 0.0:
        sl_s = curr + format(sl, dp_fmt)
        sl_section = (
            '<div class="sl-row">'
            '&#128208; Suggested SL: ' + sl_s +
            ' <span class="sl-note">(1.5 x ATR from entry)</span>'
            '</div>'
        )

    # Error notice
    err_section = ""
    if error:
        err_section = (
            '<div class="card-err">'
            '&#9888; Data unavailable this cycle &#8212; retrying on next refresh'
            '</div>'
        )

    # Assemble final HTML with + only
    return (
        '<div class="sig-card ' + card_cls + '">'

        '<div class="card-header">'
        '<div class="card-asset">' + emoji + ' ' + asset_name + '</div>'
        '<div class="card-ticker">' + ticker + '</div>'
        '</div>'

        '<div class="card-price">' + price_s + '</div>'

        + badge_h +
        rsi_h +

        '<div class="ind-row">'
        '<div class="ind-chip">Trend: ' + trend_h + '</div>'
        '<div class="ind-chip">EMA9 <span>' + ema9_s + '</span></div>'
        '<div class="ind-chip">EMA21 <span>' + ema21_s + '</span></div>'
        '<div class="ind-chip">EMA200 <span>' + ema200_s + '</span></div>'
        '<div class="ind-chip">ATR <span>' + atr_s + '</span></div>'
        '</div>'

        + sl_section
        + err_section +

        '</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
#  HISTORY HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _record_history(asset_name: str, signal: str, result: dict):
    st.session_state.signal_history.append({
        "time":   datetime.utcnow().strftime("%d-%b %H:%M"),
        "asset":  asset_name,
        "signal": signal,
        "price":  result.get("price", 0),
        "rsi":    result.get("rsi",   0),
        "sl":     result.get("sl",    0),
    })
    st.session_state.signal_history = st.session_state.signal_history[-50:]


# ─────────────────────────────────────────────────────────────────────────────
#  CHART BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_chart(df, asset_name: str, result: dict) -> go.Figure:
    display = df.tail(80).copy()
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.72, 0.28], vertical_spacing=0.03,
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=display.index,
        open=display["open"], high=display["high"],
        low=display["low"],   close=display["close"],
        name=asset_name,
        increasing_line_color="#10b981", decreasing_line_color="#ef4444",
        increasing_fillcolor="rgba(16,185,129,.55)",
        decreasing_fillcolor="rgba(239,68,68,.55)",
        showlegend=False,
    ), row=1, col=1)

    # EMA lines
    for col_name, color, width, leg_name in [
        ("ema_9",   "#60a5fa", 1.2, "EMA 9"),
        ("ema_21",  "#f59e0b", 1.2, "EMA 21"),
        ("ema_200", "#a78bfa", 1.8, "EMA 200"),
    ]:
        if col_name in display.columns:
            fig.add_trace(go.Scatter(
                x=display.index, y=display[col_name],
                name=leg_name, mode="lines",
                line=dict(color=color, width=width),
            ), row=1, col=1)

    # Stop-loss dashed line
    sl = float(result.get("sl", 0))
    sig = result.get("signal", "HOLD")
    if sl > 0:
        sl_col  = "#10b981" if sig == "BULLISH" else "#ef4444"
        sl_text = "SL " + str(round(sl, 2))
        fig.add_hline(
            y=sl, line_dash="dot", line_color=sl_col, line_width=1.2,
            annotation_text=sl_text,
            annotation_font=dict(color=sl_col, size=10),
            annotation_position="right", row=1, col=1,
        )

    # RSI panel
    if "rsi" in display.columns:
        fig.add_trace(go.Scatter(
            x=display.index, y=display["rsi"],
            name="RSI 14", mode="lines",
            line=dict(color="#60a5fa", width=1.4),
            fill="tozeroy", fillcolor="rgba(96,165,250,.07)",
        ), row=2, col=1)
        for level, color, label in [
            (70, "rgba(239,68,68,.4)",  "OB 70"),
            (55, "rgba(16,185,129,.3)", "55"),
            (45, "rgba(239,68,68,.3)",  "45"),
            (30, "rgba(16,185,129,.4)", "OS 30"),
        ]:
            fig.add_hline(
                y=level, line_dash="dot", line_color=color, line_width=1,
                annotation_text=label,
                annotation_font=dict(color=color, size=9),
                annotation_position="right", row=2, col=1,
            )

    t_col = "#10b981" if sig == "BULLISH" else "#ef4444" if sig == "BEARISH" else "#64748b"
    title_text = asset_name + "  \u00b7  15-min  \u00b7  " + sig

    fig.update_layout(
        title=dict(
            text=title_text,
            font=dict(family="JetBrains Mono", size=14, color=t_col),
            x=0.01,
        ),
        paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
        font=dict(family="JetBrains Mono", size=11, color="#94a3b8"),
        margin=dict(l=10, r=10, t=44, b=10),
        height=460,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=10), bgcolor="rgba(0,0,0,0)",
        ),
        xaxis_rangeslider_visible=False,
        yaxis=dict(
            gridcolor="#273549", zeroline=False, tickfont=dict(size=10),
            title=dict(text="Price", font=dict(size=10)),
        ),
        yaxis2=dict(
            gridcolor="#273549", zeroline=False, range=[0, 100],
            tickfont=dict(size=10),
            title=dict(text="RSI", font=dict(size=10)),
        ),
        xaxis=dict(gridcolor="#273549",  zeroline=False),
        xaxis2=dict(gridcolor="#273549", zeroline=False, showgrid=False),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="padding:20px 4px 10px;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;
                  background:linear-gradient(90deg,#60a5fa,#34d399);
                  -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
        &#128225; CommodityPulse
      </div>
      <div style="font-size:10px;color:#64748b;letter-spacing:2px;margin-top:4px;
                  font-family:'JetBrains Mono',monospace;">SIGNAL ENGINE &middot; v1.1</div>
    </div>
    <div style="height:1px;background:#334155;margin:6px 0 14px;"></div>
    """, unsafe_allow_html=True)

    st.markdown("**&#9881; Settings**")
    auto_refresh = st.toggle("Auto Refresh", value=True)
    refresh_sec  = st.slider("Refresh interval (s)", 30, 300, 60, 15)

    st.markdown(
        '<div style="height:1px;background:#334155;margin:14px 0;"></div>',
        unsafe_allow_html=True,
    )
    st.markdown("**&#128202; Signal Filter**")
    show_bull = st.checkbox("Show BULLISH",    value=True)
    show_bear = st.checkbox("Show BEARISH",    value=True)
    show_hold = st.checkbox("Show HOLD assets", value=True)

    st.markdown(
        '<div style="height:1px;background:#334155;margin:14px 0;"></div>',
        unsafe_allow_html=True,
    )
    st.markdown("**&#128203; Assets**")
    selected_assets = st.multiselect(
        "Monitor",
        options=list(ASSETS.keys()),
        default=list(ASSETS.keys()),
        label_visibility="collapsed",
    )

    st.markdown(
        '<div style="height:1px;background:#334155;margin:14px 0;"></div>',
        unsafe_allow_html=True,
    )
    manual_refresh = st.button("&#128260; Refresh Now", use_container_width=True)

    st.markdown("""
    <div style="margin-top:18px;font-family:'JetBrains Mono',monospace;
                font-size:9px;color:#475569;line-height:2.1;">
      <div>Data: Yahoo Finance</div>
      <div>Interval: 15-min candles</div>
      <div>Engine: EMA 9 / 21 / 200</div>
      <div>RSI window: 14 periods</div>
      <div>ATR SL mult: 1.5x</div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  TOP BAR
# ─────────────────────────────────────────────────────────────────────────────

now_str = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC")

st.markdown(
    '<div class="topbar">'
    '<div>'
    '<div class="topbar-title">&#128225; CommodityPulse Alerts</div>'
    '<div class="topbar-sub">Multi-Asset Signal Engine &middot; 15-min &middot; '
    'EMA 9/21/200 + RSI Confluence &middot; Signal-Only</div>'
    '</div>'
    '<div class="topbar-time">&#128336; ' + now_str + '</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
#  DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Fetching live commodity data…"):
    all_results: dict = {}
    all_dfs:     dict = {}

    for asset_name, meta in ASSETS.items():
        if asset_name not in selected_assets:
            continue
        df = fetch_ohlcv(meta["ticker"])
        if df is None:
            all_results[asset_name] = {"signal": "HOLD", "error": True}
            continue
        df = build_indicators(df)
        result = evaluate_signal(df)
        all_results[asset_name] = result
        all_dfs[asset_name]     = df

        current = result.get("signal", "HOLD")
        prev    = st.session_state.last_signals.get(asset_name)
        if current != "HOLD" and current != prev:
            _record_history(asset_name, current, result)
        st.session_state.last_signals[asset_name] = current


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY STRIP
# ─────────────────────────────────────────────────────────────────────────────

bull_n = sum(1 for r in all_results.values() if r.get("signal") == "BULLISH")
bear_n = sum(1 for r in all_results.values() if r.get("signal") == "BEARISH")
hold_n = sum(1 for r in all_results.values() if r.get("signal") == "HOLD")

if bull_n > bear_n:
    sentiment = "BULLISH"
    sent_cls  = "c-bull"
elif bear_n > bull_n:
    sentiment = "BEARISH"
    sent_cls  = "c-bear"
else:
    sentiment = "MIXED"
    sent_cls  = "c-amb"

upd_time = datetime.utcnow().strftime("%H:%M:%S")

st.markdown(
    '<div class="metric-strip">'
    '<div class="metric-item"><div class="metric-lbl">Market Sentiment</div>'
    '<div class="metric-val ' + sent_cls + '">' + sentiment + '</div></div>'
    '<div class="metric-item"><div class="metric-lbl">Bullish Signals</div>'
    '<div class="metric-val c-bull">' + str(bull_n) + '</div></div>'
    '<div class="metric-item"><div class="metric-lbl">Bearish Signals</div>'
    '<div class="metric-val c-bear">' + str(bear_n) + '</div></div>'
    '<div class="metric-item"><div class="metric-lbl">Neutral / Hold</div>'
    '<div class="metric-val c-mute">' + str(hold_n) + '</div></div>'
    '<div class="metric-item"><div class="metric-lbl">Assets Monitored</div>'
    '<div class="metric-val">' + str(len(selected_assets)) + '</div></div>'
    '<div class="metric-item"><div class="metric-lbl">Last Update</div>'
    '<div class="metric-val c-amb">' + upd_time + '</div></div>'
    '</div>',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL CARDS — 2-column grid
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="sec-hdr">&#128202; LIVE SIGNAL STATUS</div>', unsafe_allow_html=True)


def _is_visible(sig: str) -> bool:
    if sig == "BULLISH" and not show_bull:
        return False
    if sig == "BEARISH" and not show_bear:
        return False
    if sig == "HOLD" and not show_hold:
        return False
    return True


visible = [
    (name, all_results.get(name, {}), all_dfs.get(name))
    for name in selected_assets
    if _is_visible(all_results.get(name, {}).get("signal", "HOLD"))
]

if not visible:
    st.info("No assets match the current filter. Adjust the Signal Filter in the sidebar.")

for i in range(0, len(visible), 2):
    pair = visible[i: i + 2]
    cols = st.columns(2)
    for col_idx, (asset_name, result, _df) in enumerate(pair):
        with cols[col_idx]:
            # _card_html uses only + concatenation — guaranteed no nested f-strings
            st.markdown(_card_html(asset_name, result), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  PRICE CHARTS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="sec-hdr">&#128200; PRICE CHARTS WITH INDICATORS</div>', unsafe_allow_html=True)

for asset_name, result, df in visible:
    if df is None:
        continue
    meta  = ASSETS[asset_name]
    emoji = meta["emoji"]
    dp    = meta["dp"]
    curr  = meta["curr"]
    dp_fmt = ",." + str(dp) + "f"

    with st.expander(emoji + "  " + asset_name + "  \u2014  click to expand", expanded=True):
        fig = _build_chart(df, asset_name, result)
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

        price  = float(result.get("price",   0))
        rsi    = float(result.get("rsi",     0))
        atr    = float(result.get("atr",     0))
        ema9   = float(result.get("ema_9",   0))
        ema21  = float(result.get("ema_21",  0))
        ema200 = float(result.get("ema_200", 0))

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Close",   curr + format(price,  dp_fmt))
        c2.metric("RSI 14",  str(round(rsi,   1)))
        c3.metric("ATR 14",  curr + format(atr,    dp_fmt))
        c4.metric("EMA 9",   curr + format(ema9,   dp_fmt))
        c5.metric("EMA 21",  curr + format(ema21,  dp_fmt))
        c6.metric("EMA 200", curr + format(ema200, dp_fmt))


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL HISTORY
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="sec-hdr">&#128203; SIGNAL HISTORY (this session)</div>', unsafe_allow_html=True)

history = st.session_state.signal_history
if not history:
    st.markdown(
        '<div style="font-family:JetBrains Mono,monospace;font-size:12px;'
        'color:#475569;padding:24px;text-align:center;">'
        'No high-conviction signals fired yet this session. Monitoring all assets&#8230;'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="hist-grid hist-hdr">'
        '<span>Asset</span><span>Time (UTC)</span>'
        '<span>Signal</span><span>Price</span><span>Sugg. SL</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    for entry in reversed(history):
        sig    = entry["signal"]
        s_col  = "#10b981" if sig == "BULLISH" else "#ef4444"
        icon   = "&#9650;" if sig == "BULLISH" else "&#9660;"
        a_meta = ASSETS.get(entry["asset"], {})
        e_dp   = a_meta.get("dp", 2)
        e_curr = a_meta.get("curr", "$")
        e_emj  = a_meta.get("emoji", "")
        e_dp_fmt = ",." + str(e_dp) + "f"

        price_s = e_curr + format(float(entry["price"]), e_dp_fmt)
        sl_s    = e_curr + format(float(entry["sl"]),    e_dp_fmt)

        st.markdown(
            '<div class="hist-grid hist-body">'
            '<span>' + e_emj + ' ' + entry["asset"] + '</span>'
            '<span style="color:#64748b;">' + entry["time"] + '</span>'
            '<span style="color:' + s_col + ';font-weight:700;">' + icon + ' ' + sig + '</span>'
            '<span>' + price_s + '</span>'
            '<span style="color:#f59e0b;">' + sl_s + '</span>'
            '</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  DISCLAIMER
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    '<div class="disclaimer">'
    '&#9888; CommodityPulse is a SIGNAL-ONLY tool. It does not place trades or manage money. '
    'All signals are algorithmic and for informational purposes only. '
    'Commodity trading carries substantial risk. Consult a financial advisor before trading.'
    '</div>',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
#  AUTO REFRESH
# ─────────────────────────────────────────────────────────────────────────────

if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()
elif manual_refresh:
    st.rerun()
