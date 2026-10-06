"""Telegram alerts. Silent no-op when not configured; never logs the bot token."""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)


def send(text: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.info("Telegram not configured; skipping message")
        return False
    try:  # the URL contains the token, so only the exception type is logged
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text[:4000]}, timeout=15)
        if not r.ok:
            log.warning("Telegram returned HTTP %s", r.status_code)
        return r.ok
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegram send failed: %s", type(exc).__name__)
        return False
