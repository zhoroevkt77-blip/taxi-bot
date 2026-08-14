# -*- coding: utf-8 -*-
"""
core/channel.py
===============
Telegram каналына жарыялоо — платформадан көз каранды эмес.

Эмне үчүн core'до?
    Мурда бул telegram_adapter'де турчу. Ошондуктан WhatsApp'тан жазылган
    айдоочунун жарыясы каналга чыкпай калчу. Эми ким жазса да — Telegram
    болобу, WhatsApp болобу — жарыя ошол эле каналга барат.

Бул модуль telebot'ту колдонбойт, түз Telegram Bot API'ге кайрылат.
Ошондуктан кошумча бот инстанциясы түзүлбөйт (Conflict коркунучу жок).
"""

import os
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")   # мис. @taxirobotbot же -1001234567890

API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""


def _markup(links):
    """[[(label, url), ...], ...] -> Telegram inline_keyboard"""
    if not links:
        return None
    rows = []
    for row in links:
        rows.append([{"text": label, "url": url} for label, url in row])
    return {"inline_keyboard": rows}


def publish(text, links=None):
    """Жарыяны каналга чыгарат. message_id кайтарат, болбосо None."""
    if not BOT_TOKEN or not CHANNEL_ID:
        print("ℹ️ Канал өчүк: BOT_TOKEN же CHANNEL_ID коюлган эмес.")
        return None

    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    markup = _markup(links)
    if markup:
        payload["reply_markup"] = markup

    try:
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=30)
        data = r.json()
        if not data.get("ok"):
            print("Каналга жарыялоо ишке ашкан жок:", data.get("description"))
            return None
        return data["result"]["message_id"]
    except Exception as e:
        print("Каналга жарыялоо катасы:", e)
        return None


def delete(message_id):
    """Каналдагы билдирүүнү өчүрөт (жарыянын мөөнөтү бүткөндө)."""
    if not BOT_TOKEN or not CHANNEL_ID or not message_id:
        return False
    try:
        r = requests.post(f"{API}/deleteMessage",
                          json={"chat_id": CHANNEL_ID, "message_id": message_id},
                          timeout=30)
        return bool(r.json().get("ok"))
    except Exception as e:
        print("Каналдан өчүрүү катасы:", e)
        return False
