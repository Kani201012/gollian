"""
CommodityPulse Alerts — commodity_pulse.py
==========================================
Background engine entry point.
Polls yfinance every 5 minutes, evaluates signals, sends Telegram alerts.

Run on AWS:
  nohup python3 commodity_pulse.py > commodity_pulse.log 2>&1 &

Environment variables required:
  TELEGRAM_BOT_TOKEN   — from @BotFather
  TELEGRAM_CHAT_ID     — your chat or group ID
"""

import os
import time
import logging
from datetime import datetime
from typing import Optional

import requests

from engine import ASSETS, fetch_ohlcv, build_indicators, evaluate_signal, format_alert

# ──────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(levelname)s | %(message)s",
    handlers= [
        logging.StreamHandler(),
        logging.FileHandler("commodity_pulse.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("CommodityPulse")

# ──────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID:   str = os.environ.get("TELEGRAM_CHAT_ID",   "")

# Poll every 5 minutes — fast enough to catch 15-min candle closes,
# slow enough to stay within yfinance rate limits.
POLL_INTERVAL_SECONDS: int = 300


# ──────────────────────────────────────────────────────────────────────────────
#  TELEGRAM SENDER
# ──────────────────────────────────────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    """
    POST a message to Telegram. Returns True on success.
    Falls back to stdout when credentials are not configured.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — printing to stdout.")
        print("\n" + "=" * 50)
        print(message)
        print("=" * 50 + "\n")
        return False

    url     = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.ok:
            logger.info("✅ Telegram alert sent.")
            return True
        logger.error(f"Telegram API error {resp.status_code}: {resp.text[:120]}")
        return False
    except requests.RequestException as exc:
        logger.error(f"Telegram send failed (network): {exc}")
        return False


def send_startup_ping():
    """Send one confirmation message on engine boot."""
    now_utc = datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")
    asset_lines = "\n".join(
        f"  {meta['emoji']} {name} ({meta['ticker']})"
        for name, meta in ASSETS.items()
    )
    send_telegram(
        f"🚀 <b>CommodityPulse Alerts — ENGINE STARTED</b>\n"
        f"{'─' * 32}\n"
        f"Monitoring:\n{asset_lines}\n"
        f"{'─' * 32}\n"
        f"⏱ Interval: 15-min candles\n"
        f"🔁 Poll: every {POLL_INTERVAL_SECONDS // 60} minutes\n"
        f"🧠 Logic: EMA 9/21/200 + RSI confluence\n"
        f"🛡 Anti-spam: signal-change alerts only\n"
        f"🕐 Started: {now_utc}"
    )


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN ENGINE LOOP
# ──────────────────────────────────────────────────────────────────────────────

def run_engine():
    """
    Infinite polling loop.

    Per-asset state machine:
      last_signal[name] ∈ { None, "HOLD", "BULLISH", "BEARISH" }

    Alert fires only when:
      current_signal not in ("HOLD", last_signal[name])
    """
    logger.info("=" * 60)
    logger.info("  CommodityPulse Alerts — Engine Starting")
    logger.info(f"  Telegram : {'configured ✅' if TELEGRAM_BOT_TOKEN else 'NOT configured ⚠️'}")
    logger.info("=" * 60)

    last_signal: dict[str, Optional[str]] = {name: None for name in ASSETS}
    send_startup_ping()

    cycle = 0
    while True:
        cycle += 1
        logger.info(
            f"── Cycle {cycle} | {datetime.utcnow().strftime('%H:%M:%S UTC')} "
            "─────────────────────────"
        )

        for asset_name, meta in ASSETS.items():
            ticker = meta["ticker"]
            emoji  = meta["emoji"]

            # 1 — Fetch
            df = fetch_ohlcv(ticker)
            if df is None:
                logger.warning(f"{asset_name}: no data this cycle — skipping.")
                continue

            # 2 — Indicators
            try:
                df = build_indicators(df)
            except Exception as exc:
                logger.error(f"{asset_name}: indicator error — {exc}")
                continue

            # 3 — Signal
            try:
                result = evaluate_signal(df)
            except Exception as exc:
                logger.error(f"{asset_name}: signal error — {exc}")
                continue

            current = result.get("signal", "HOLD")

            logger.info(
                f"{emoji} {asset_name:<12} | {current:<8} "
                f"| price={result.get('price', 0):>10,.3f} "
                f"| RSI={result.get('rsi', 0):>5.1f} "
                f"| {result.get('trend', 'N/A')}"
            )

            # 4 — Anti-spam gate
            if current == "HOLD":
                last_signal[asset_name] = "HOLD"
                continue

            if current == last_signal[asset_name]:
                logger.debug(f"{asset_name}: unchanged ({current}) — suppressed.")
                continue

            # 5 — Fire alert
            logger.info(f"🚨 NEW SIGNAL {asset_name}: {current} (was {last_signal[asset_name]})")
            send_telegram(format_alert(asset_name, result))
            last_signal[asset_name] = current
            time.sleep(1)  # rate-limit guard between consecutive asset alerts

        logger.info(f"── Cycle {cycle} done. Sleeping {POLL_INTERVAL_SECONDS}s ──\n")
        time.sleep(POLL_INTERVAL_SECONDS)


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run_engine()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — engine stopped.")
    except Exception as exc:
        logger.critical(f"Unhandled exception: {exc}", exc_info=True)
        raise
