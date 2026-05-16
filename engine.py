"""
CommodityPulse — engine.py
===========================
Shared core module.
Imported by commodity_pulse.py (background engine)
and app.py (Streamlit dashboard).

Contains:
  - ASSETS configuration
  - fetch_ohlcv()
  - build_indicators()
  - evaluate_signal()
  - format_alert()

Neither entry point is here — this is a pure library module.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np
import yfinance as yf

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

logger = logging.getLogger("CommodityPulse.Engine")

# ──────────────────────────────────────────────────────────────────────────────
#  ASSET REGISTRY
# ──────────────────────────────────────────────────────────────────────────────

# { display_name: { ticker, emoji, currency, decimal_places } }
ASSETS: dict = {
    "CRUDE OIL": {"ticker": "CL=F", "emoji": "🛢️",  "curr": "$", "dp": 3},
    "NAT GAS":   {"ticker": "NG=F", "emoji": "🔥",  "curr": "$", "dp": 3},
    "GOLD":      {"ticker": "GC=F", "emoji": "🟡",  "curr": "$", "dp": 2},
    "SILVER":    {"ticker": "SI=F", "emoji": "⚪",  "curr": "$", "dp": 2},
}

# ──────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

RSI_BULL_MIN:      float = 55.0
RSI_BEAR_MAX:      float = 45.0
ATR_SL_MULT:       float = 1.5
MIN_ROWS:          int   = 220
YFINANCE_PERIOD:   str   = "15d"
YFINANCE_INTERVAL: str   = "15m"


# ──────────────────────────────────────────────────────────────────────────────
#  SAFE FLOAT
# ──────────────────────────────────────────────────────────────────────────────

def _sf(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────────────────────
#  DATA FETCHER
# ──────────────────────────────────────────────────────────────────────────────

def fetch_ohlcv(ticker: str, period: str = YFINANCE_PERIOD,
                interval: str = YFINANCE_INTERVAL) -> Optional[pd.DataFrame]:
    """
    Download OHLCV data from yfinance.
    Returns a cleaned DataFrame or None on any failure.
    The try-except ensures a network blip on one asset never crashes the caller.
    """
    try:
        raw = yf.download(
            tickers     = ticker,
            period      = period,
            interval    = interval,
            progress    = False,
            auto_adjust = True,
        )

        if raw is None or raw.empty:
            logger.warning(f"{ticker}: empty response from yfinance.")
            return None

        # Flatten MultiIndex columns (yfinance >= 0.2 bulk download)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [str(c[0]).lower() for c in raw.columns]
        else:
            raw.columns = [str(c).lower() for c in raw.columns]

        raw = raw.loc[:, ~raw.columns.duplicated()]
        raw.rename(columns={"adj close": "close", "adj_close": "close"}, inplace=True)

        required = {"open", "high", "low", "close", "volume"}
        missing  = required - set(raw.columns)
        if missing:
            logger.warning(f"{ticker}: missing columns {missing}.")
            return None

        for col in ["open", "high", "low", "close", "volume"]:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")

        raw.dropna(subset=["close"], inplace=True)
        raw.index = pd.to_datetime(raw.index)

        if len(raw) < MIN_ROWS:
            logger.warning(
                f"{ticker}: only {len(raw)} rows (need ≥ {MIN_ROWS}). "
                "200 EMA not warm yet."
            )
            return None

        return raw

    except Exception as exc:
        logger.error(f"{ticker}: fetch error — {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
#  INDICATOR BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute EMA-9, EMA-21, EMA-200, RSI-14, ATR-14 and attach to DataFrame.
    Returns the same DataFrame with indicator columns added.
    """
    cs = df["close"].squeeze()

    df["ema_9"]   = EMAIndicator(close=cs, window=9).ema_indicator()
    df["ema_21"]  = EMAIndicator(close=cs, window=21).ema_indicator()
    df["ema_200"] = EMAIndicator(close=cs, window=200).ema_indicator()
    df["rsi"]     = RSIIndicator(close=cs, window=14).rsi()

    try:
        df["atr"] = AverageTrueRange(
            high   = df["high"].squeeze(),
            low    = df["low"].squeeze(),
            close  = cs,
            window = 14,
        ).average_true_range()
    except Exception:
        df["atr"] = cs * 0.005   # fallback: 0.5% of price

    return df


# ──────────────────────────────────────────────────────────────────────────────
#  SIGNAL EVALUATOR
# ──────────────────────────────────────────────────────────────────────────────

def evaluate_signal(df: pd.DataFrame) -> dict:
    """
    HIGH-CONVICTION confluence signal on the last CLOSED candle (iloc[-2]).
    Crossover uses iloc[-2] vs iloc[-3].

    Returns dict with keys:
      signal, price, rsi, ema_9, ema_21, ema_200, atr, sl, trend
    """
    df = df.dropna(subset=["ema_9", "ema_21", "ema_200", "rsi"])
    if len(df) < 3:
        return {"signal": "HOLD"}

    lat = df.iloc[-2]
    prv = df.iloc[-3]

    price   = _sf(lat["close"])
    ema_9   = _sf(lat["ema_9"])
    ema_21  = _sf(lat["ema_21"])
    ema_200 = _sf(lat["ema_200"])
    rsi     = _sf(lat["rsi"])
    atr     = _sf(lat["atr"]) or price * 0.005

    prev_e9  = _sf(prv["ema_9"])
    prev_e21 = _sf(prv["ema_21"])

    trend      = "BULLISH" if price > ema_200 else "BEARISH" if price < ema_200 else "NEUTRAL"
    bull_cross = (prev_e9 <= prev_e21) and (ema_9 > ema_21)
    bear_cross = (prev_e9 >= prev_e21) and (ema_9 < ema_21)

    if price > ema_200 and bull_cross and rsi > RSI_BULL_MIN:
        signal = "BULLISH"
        sl     = round(price - ATR_SL_MULT * atr, 4)
    elif price < ema_200 and bear_cross and rsi < RSI_BEAR_MAX:
        signal = "BEARISH"
        sl     = round(price + ATR_SL_MULT * atr, 4)
    else:
        signal = "HOLD"
        sl     = 0.0

    return {
        "signal":  signal,
        "price":   round(price,   4),
        "rsi":     round(rsi,     1),
        "ema_9":   round(ema_9,   4),
        "ema_21":  round(ema_21,  4),
        "ema_200": round(ema_200, 4),
        "atr":     round(atr,     4),
        "sl":      sl,
        "trend":   trend,
    }


# ──────────────────────────────────────────────────────────────────────────────
#  TELEGRAM ALERT FORMATTER
# ──────────────────────────────────────────────────────────────────────────────

def format_alert(asset_name: str, result: dict) -> str:
    """
    Build the HTML-formatted Telegram alert string for a signal.
    """
    meta      = ASSETS.get(asset_name, {})
    emoji     = meta.get("emoji", "📊")
    ticker    = meta.get("ticker", asset_name)
    curr      = meta.get("curr", "$")
    dp        = meta.get("dp", 2)
    signal    = result["signal"]
    price     = result["price"]
    rsi       = result["rsi"]
    trend     = result["trend"]
    sl        = result["sl"]
    atr       = result["atr"]

    direction = "▲ BUY"  if signal == "BULLISH" else "▼ SELL"
    sig_icon  = "🟢" if signal == "BULLISH" else "🔴"

    if rsi > 70:
        rsi_label = "Overbought"
    elif rsi > 55:
        rsi_label = "Bull Zone"
    elif rsi < 30:
        rsi_label = "Oversold"
    elif rsi < 45:
        rsi_label = "Bear Zone"
    else:
        rsi_label = "Neutral"

    now_utc   = datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")
    price_str = f"{curr}{price:,.{dp}f}"
    sl_str    = f"{curr}{sl:,.{dp}f}"
    atr_str   = f"{curr}{atr:,.{dp}f}"

    return (
        f"{sig_icon} {emoji} <b>{asset_name} ({ticker})</b> — {direction} SIGNAL\n"
        f"{'─' * 32}\n"
        f"💰 <b>Price:</b> {price_str}\n"
        f"🔥 <b>RSI ({rsi}):</b> {rsi_label} | <b>Trend:</b> {trend}\n"
        f"📐 <b>Suggested SL:</b> {sl_str}  <i>(1.5 × ATR from entry)</i>\n"
        f"📏 <b>ATR (14):</b> {atr_str}\n"
        f"⏱ <b>Candle:</b> 15-min | {now_utc}\n"
        f"{'─' * 32}\n"
        f"<i>⚠️ Signal-only. Not financial advice. Do your own analysis.</i>"
    )
