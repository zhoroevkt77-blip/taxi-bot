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

СҮРӨТ ЖӨНҮНДӨ (v3):
    Айдоочу унаасынын сүрөтүн кошсо, жарыя каналга sendPhoto менен
    чыгат — текст сүрөттүн астындагы кол жазуу (caption) болот.
    Ошондо жаңыртуу да башкача: editMessageText эмес,
    editMessageCaption колдонулат. Экөөнү аралаштырса Telegram ката
    берет, ошондуктан edit() өзү туурасын тандайт.

    Caption'дын чеги — 1024 белги. Жарыянын тексти андан кыска,
    бирок ар бир жолу кыркып коёбуз: чектен ашса Telegram такыр
    жарыялабай коёт.
"""

import os
import requests

CHANNEL_VERSION = "v3-photo"
print(f"📢 core/channel.py жүктөлдү. Версия = {CHANNEL_VERSION}")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")   # мис. @taxirobotbot же -1001234567890

API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

CAPTION_LIMIT = 1024


def _markup(links):
    """[[(label, url), ...], ...] -> Telegram inline_keyboard"""
    if not links:
        return None
    rows = []
    for row in links:
        rows.append([{"text": label, "url": url} for label, url in row])
    return {"inline_keyboard": rows}


def _cap(text):
    """Кол жазууну Telegram'дын чегине батырат."""
    text = text or ""
    if len(text) <= CAPTION_LIMIT:
        return text
    return text[:CAPTION_LIMIT - 1] + "…"


def publish(text, links=None, photo=None):
    """Жарыяны каналга чыгарат. message_id кайтарат, болбосо None.

    photo берилсе — sendPhoto, текст кол жазуу болуп кетет.
    photo — Telegram file_id же ачык URL (WhatsApp'тан келген).
    """
    if not BOT_TOKEN or not CHANNEL_ID:
        print("ℹ️ Канал өчүк: BOT_TOKEN же CHANNEL_ID коюлган эмес.")
        return None

    markup = _markup(links)

    if photo:
        payload = {
            "chat_id": CHANNEL_ID,
            "photo": photo,
            "caption": _cap(text),
            "parse_mode": "HTML",
        }
        if markup:
            payload["reply_markup"] = markup
        method = "sendPhoto"
    else:
        payload = {
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if markup:
            payload["reply_markup"] = markup
        method = "sendMessage"

    try:
        r = requests.post(f"{API}/{method}", json=payload, timeout=40)
        data = r.json()
        if not data.get("ok"):
            desc = data.get("description")
            print(f"Каналга жарыялоо ишке ашкан жок ({method}):", desc)
            # Сүрөт жарабай калса, жок дегенде текст чыксын
            if photo:
                print("↩️ Сүрөтсүз кайра аракет кылабыз.")
                return publish(text, links, photo=None)
            return None
        return data["result"]["message_id"]
    except Exception as e:
        print("Каналга жарыялоо катасы:", e)
        return None


def edit(message_id, text, links=None, has_photo=False):
    """Каналдагы билдирүүнү жаңыртат.

    Айдоочу бош орундун санын же убакытты өзгөрткөндө колдонулат —
    каналдагы жарыя да ошол замат жаңырат, эски маалымат калбайт.

    has_photo=True болсо editMessageCaption колдонулат: сүрөттүү
    билдирүүнүн «тексти» жок, кол жазуусу гана бар.

    МААНИЛҮҮ: Telegram баскычтарды өзү сактабайт. links берилбесе,
    алар жоголуп калат. Ошондуктан чакырган жерде contact_links()
    менен аларды кайра куруп берүү керек.
    """
    if not BOT_TOKEN or not CHANNEL_ID or not message_id:
        return False

    markup = _markup(links)

    if has_photo:
        payload = {
            "chat_id": CHANNEL_ID,
            "message_id": message_id,
            "caption": _cap(text),
            "parse_mode": "HTML",
        }
        method = "editMessageCaption"
    else:
        payload = {
            "chat_id": CHANNEL_ID,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        method = "editMessageText"

    if markup:
        payload["reply_markup"] = markup

    try:
        r = requests.post(f"{API}/{method}", json=payload, timeout=30)
        data = r.json()
        if not data.get("ok"):
            desc = str(data.get("description", ""))
            # Текст такыр өзгөрбөсө Telegram ката берет — бул ката эмес
            if "message is not modified" in desc:
                return True
            print(f"Каналды жаңыртуу ишке ашкан жок ({method}):", desc)
            return False
        return True
    except Exception as e:
        print("Каналды жаңыртуу катасы:", e)
        return False


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


def file_url(file_id):
    """Telegram file_id'ден жүктөп алуучу түз шилтеме курат.

    Сайтка сүрөт көрсөтүү үчүн керек: браузер Telegram'дын file_id'син
    түшүнбөйт. Шилтеме ~1 саат жашайт, ошондуктан ар бир жолу кайра
    сурайбыз (web/app.py аны кештейт).
    """
    if not BOT_TOKEN or not file_id:
        return None
    try:
        r = requests.get(f"{API}/getFile", params={"file_id": file_id},
                         timeout=20)
        data = r.json()
        if not data.get("ok"):
            print("getFile ишке ашкан жок:", data.get("description"))
            return None
        path = data["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}"
    except Exception as e:
        print("getFile катасы:", e)
        return None
