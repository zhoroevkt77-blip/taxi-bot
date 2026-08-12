# -*- coding: utf-8 -*-
"""
adapters/whatsapp_adapter.py
=============================
Green API аркылуу WhatsApp'ка туташат.

НЕГИЗГИ АЙЫРМА: WhatsApp'та ишенимдүү inline баскыч жок.
Ошондуктан clavatura номерленген текст менюга айланат:

    Тандаңыз:

    1 — 🚗 Айдоочумун
    2 — 🔍 Жүргүнчүмүн
    3 — 🆘 Жардам

Колдонуучу "2" деп жазса, биз аны core тааныган "menu:passenger"
кодуна которобуз. Акыркы меню ар бир колдонуучу боюнча эстелип турат.

Кабарлар polling менен алынат (receiveNotification/deleteNotification).
Webhook керек эмес — Railway'де ачык порт ачуунун кажети жок.
"""

import os
import time
import requests

from core.messenger import Messenger, IncomingMessage, make_uid
from core import logic

GREEN_ID = os.environ.get("GREEN_API_ID")
GREEN_TOKEN = os.environ.get("GREEN_API_TOKEN")
# Green API ар бир инстанцияга өз доменин берет: https://7107.api.greenapi.com
# Эгер GREEN_API_URL коюлбаса, idInstance'тин алгачкы 4 санынан курабыз.
_default_url = f"https://{str(GREEN_ID)[:4]}.api.greenapi.com" if GREEN_ID else ""
GREEN_URL = os.environ.get("GREEN_API_URL", _default_url)
BASE = f"{GREEN_URL}/waInstance{GREEN_ID}"

# Ар бир колдонуучунун акыркы менюсу: uid -> {"1": "menu:driver", ...}
LAST_MENU = {}


def _post(method, payload):
    """Green API'ге сурам жиберет."""
    url = f"{BASE}/{method}/{GREEN_TOKEN}"
    try:
        r = requests.post(url, json=payload, timeout=30)
        return r.json()
    except Exception as e:
        print("Green API POST катасы:", e)
        return None


def _get(method):
    url = f"{BASE}/{method}/{GREEN_TOKEN}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200 or not r.text.strip():
            return None
        return r.json()
    except Exception as e:
        print("Green API GET катасы:", e)
        return None


def _delete(receipt_id):
    url = f"{BASE}/deleteNotification/{GREEN_TOKEN}/{receipt_id}"
    try:
        requests.delete(url, timeout=30)
    except Exception as e:
        print("Green API DELETE катасы:", e)


def _chat_id(user_id):
    """'wa:996700123456' -> '996700123456@c.us'"""
    raw = user_id.split(":", 1)[1]
    return f"{raw}@c.us"


def _lang_of(user_id):
    """Колдонуучунун тилин базадан алат."""
    try:
        from core import db
        acc = db.get_or_create_account(user_id, "whatsapp")
        return acc.get("lang", "ky")
    except Exception:
        return "ky"


class WhatsAppMessenger(Messenger):
    platform_name = "whatsapp"

    def send_text(self, user_id, text):
        _post("sendMessage", {"chatId": _chat_id(user_id), "message": text})

    def send_buttons(self, user_id, text, keyboard):
        """Клавиатураны номерленген тизмеге айландырат."""
        lang = _lang_of(user_id)
        lines = [text, ""]
        mapping = {}
        n = 1
        for row in keyboard.rows:
            for b in row:
                lines.append(f"{n} — {b.text}")
                mapping[str(n)] = b.action
                n += 1
        # WhatsApp'та туруктуу меню жок — 0 дайыма башкы менюга кайтарат
        home = "0 — 🏠 Главное меню" if lang == "ru" else "0 — 🏠 Башкы меню"
        hint = ("👉 Напишите номер вашего выбора." if lang == "ru"
                else "👉 Тандооңуздун номерин жазыңыз.")
        lines.append(home)
        mapping["0"] = "menu:home"
        LAST_MENU[user_id] = mapping
        lines.append("")
        lines.append(hint)
        self.send_text(user_id, "\n".join(lines))

    def ask_phone_contact(self, user_id, text):
        """WhatsApp'та номер өзү белгилүү — сураштын кереги жок."""
        self.send_text(user_id, text)

    def publish_to_channel(self, text):
        """WhatsApp тарабында канал жок — азырынча эч нерсе кылбайт."""
        return None


messenger = WhatsAppMessenger()


def _handle(body):
    """Бир webhook кабарын иштетет."""
    if body.get("typeWebhook") != "incomingMessageReceived":
        return

    sender = body.get("senderData", {}).get("chatId", "")
    if not sender.endswith("@c.us"):
        return   # группалар азырынча эске алынбайт

    phone = sender.replace("@c.us", "")
    uid = make_uid("whatsapp", phone)

    md = body.get("messageData", {})
    tmsg = md.get("typeMessage")

    if tmsg == "textMessage":
        text = md.get("textMessageData", {}).get("textMessage", "")
    elif tmsg == "extendedTextMessage":
        text = md.get("extendedTextMessageData", {}).get("text", "")
    else:
        return   # сүрөт, аудио ж.б. — азырынча эске алынбайт

    text = (text or "").strip()
    if not text:
        return

    # Телефонду автоматтык ырастап коёбуз (WhatsApp'та ал белгилүү)
    _ensure_phone(uid, phone)

    # Номер басылдыбы? Ошондо аны баскычка айландырабыз
    mapping = LAST_MENU.get(uid, {})
    if text in mapping:
        msg = IncomingMessage(user_id=uid, platform="whatsapp",
                              is_button=True, button_action=mapping[text])
    else:
        msg = IncomingMessage(user_id=uid, platform="whatsapp", text=text)

    try:
        logic.handle_update(messenger, msg)
    except Exception as e:
        print("Логика катасы:", e)


def _ensure_phone(uid, phone):
    """WhatsApp колдонуучусунун номерин бир жолу базага жазат."""
    try:
        from core import db
        acc = db.get_or_create_account(uid, "whatsapp")
        if not acc.get("verified_phone"):
            existing = db.find_account_by_phone(phone)
            if existing and existing["account_id"] != acc["account_id"]:
                # Telegram'дагы аккаунт менен бириктирүү
                db.link_second_platform(existing["account_id"], uid, "whatsapp")
            else:
                db.update_account(acc["account_id"], verified_phone=phone)
    except Exception as e:
        print("Телефон ырастоо катасы:", e)


def _check_settings():
    """Башталышта Green API'дин абалын текшерип, логго жазат."""
    st = _get("getSettings")
    if not st:
        print("⚠️ Green API жооп бербей жатат — ID/TOKEN туурабы?")
        return
    incoming = st.get("incomingWebhook")
    hook_url = st.get("webhookUrl") or ""
    print(f"ℹ️ Green API жөндөөлөрү: incomingWebhook = {incoming}")
    print(f"ℹ️ webhookUrl = '{hook_url}'")
    if incoming != "yes":
        print("⚠️ КАБАРЛАР ӨЧҮК! Console'до 'Получать уведомления о входящих "
              "сообщениях' жөндөөсүн күйгүзүңүз.")
    if hook_url.strip():
        print("⚠️ webhookUrl коюлган! Кабарлар кезекке түшпөйт. "
              "Console'до webhookUrl'ди бош калтырыңыз.")

    state = _get("getStateInstance")
    if state:
        print(f"ℹ️ Инстанциянын абалы: {state.get('stateInstance')}")


def run():
    """Green API'ден кабарларды үзгүлтүксүз алып турат."""
    if not GREEN_ID or not GREEN_TOKEN:
        print("⚠️ GREEN_API_ID же GREEN_API_TOKEN коюлган эмес — WhatsApp өчүк.")
        return

    from core.db import init_db
    init_db()
    print(f"✅ WhatsApp адаптери башталды. BASE = {BASE}")
    _check_settings()

    while True:
        try:
            note = _get("receiveNotification")
            if not note:
                time.sleep(1)
                continue
            receipt = note.get("receiptId")
            body = note.get("body", {})
            print(f"📩 WhatsApp кабары: {body.get('typeWebhook')}")
            try:
                _handle(body)
            finally:
                if receipt:
                    _delete(receipt)
        except Exception as e:
            print("WhatsApp цикл катасы:", e)
            time.sleep(5)


if __name__ == "__main__":
    run()

