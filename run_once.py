"""
CommodityPulse — run_once.py
==============================
GitHub Actions entry point.

Runs ONE evaluation cycle across all 4 assets and exits.
The infinite polling loop in commodity_pulse.py is for the
Oracle/AWS VM. GitHub Actions jobs are ephemeral — they trigger
every 5 minutes via cron and run this file instead.

Environment variables:
  TELEGRAM_BOT_TOKEN  — Telegram bot token (GitHub Secret)
  TELEGRAM_CHAT_ID    — Target chat ID (GitHub Secret)
  DRY_RUN             — "true" to log signals without sending Telegram
"""

import os
import logging
import time
from datetime import datetime
from typing import Optional

import requests

from engine import ASSETS, fetch_ohlcv, build_indicators, evaluate_signal, format_alert

# ──────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("run_once.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("CommodityPulse.RunOnce")

# ──────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN: str  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID:   str  = os.environ.get("TELEGRAM_CHAT_ID",   "")
DRY_RUN:            bool = os.environ.get("DRY_RUN", "false").lower() == "true"


# ──────────────────────────────────────────────────────────────────────────────
#  TELEGRAM
# ──────────────────────────────────────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would send:\n{message}")
        return True
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — signal logged only.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.ok:
            logger.info("✅ Telegram alert sent.")
            return True
        logger.error(f"Telegram error {resp.status_code}: {resp.text[:120]}")
        return False
    except requests.RequestException as exc:
        logger.error(f"Telegram network error: {exc}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
#  STATE FILE  — persists last_signal across GitHub Actions runs via artifact
#  NOTE: Because GitHub Actions runners are stateless, we use a simple JSON
#  state file committed to the repo OR passed through artifacts.
#  For simplicity, this run_once always sends signals (no cross-run dedup).
#  If you want cross-run dedup, mount the state via GitHub Cache action.
# ──────────────────────────────────────────────────────────────────────────────

import json, pathlib

STATE_FILE = pathlib.Path("signal_state.json")

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {name: None for name in ASSETS}

def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as exc:
        logger.warning(f"Could not save state: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    now_utc = datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")
    mode    = "DRY RUN" if DRY_RUN else "LIVE"
    logger.info("=" * 60)
    logger.info(f"  CommodityPulse — Single Cycle [{mode}] | {now_utc}")
    logger.info("=" * 60)

    last_signal = load_state()
    alerts_sent = 0

    for asset_name, meta in ASSETS.items():
        ticker = meta["ticker"]
        emoji  = meta["emoji"]

        # 1 — Fetch
        df = fetch_ohlcv(ticker)
        if df is None:
            logger.warning(f"{asset_name}: no data — skipping.")
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

        # 4 — Anti-spam gate (cross-run via state file)
        if current == "HOLD":
            last_signal[asset_name] = "HOLD"
            continue

        if current == last_signal.get(asset_name):
            logger.info(f"{asset_name}: unchanged ({current}) — suppressed.")
            continue

        # 5 — Fire
        logger.info(f"🚨 NEW SIGNAL {asset_name}: {current}")
        send_telegram(format_alert(asset_name, result))
        last_signal[asset_name] = current
        alerts_sent += 1
        time.sleep(1)

    save_state(last_signal)
    logger.info(f"── Cycle complete. Alerts sent: {alerts_sent} ──\n")


if __name__ == "__main__":
    main()
