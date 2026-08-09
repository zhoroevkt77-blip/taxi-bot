# -*- coding: utf-8 -*-
"""
adapters/whatsapp_adapter.py
==============================
Green API webhook'тон келген JSON'ду core.messenger.IncomingMessage'ге
которот.

WhatsApp'та Telegram'дагыдай inline keyboard жок (Business план керек),
ошондуктан Keyboard'ду номерленген текст-меню кылып чыгарабыз —
Developer (акысыз) тарифте да иштейт:

    Багытты тандаңыз:
    1) Бишкекке барам
    2) Бишкектен кетем

Колдонуучу "1" деп жазат — биз аны route:to_bishkek action'га которобуз.
"""

import os
import requests
from flask import Flask, request, jsonify

from core.messenger import Messenger, IncomingMessage, make_uid
from core import logic

GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN")
GREEN_API_BASE = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE}"

app = Flask(__name__)

# Ар бир колдонуучунун азыркы номерленген менюсу
_PENDING_MENU = {}   # user_id -> {"1": "route:to_bishkek", ...}


class WhatsAppMessenger(Messenger):
    platform_name = "whatsapp"

    def send_text(self, user_id, text):
        phone = user_id.split(":", 1)[1]
        requests.post(
            f"{GREEN_API_BASE}/sendMessage/{GREEN_API_TOKEN}",
            json={"chatId": f"{phone}@c.us", "message": text},
            timeout=10)

    def send_buttons(self, user_id, text, keyboard):
        phone = user_id.split(":", 1)[1]
        flat = [b for row in keyboard.rows for b in row]

        if len(flat) <= 3:
            # Green API sendButtons (Business тарифте иштейт)
            buttons = [{"buttonId": str(i), "buttonText": {"displayText": b.text}}
                       for i, b in enumerate(flat)]
            _PENDING_MENU[user_id] = {str(i): b.action for i, b in enumerate(flat)}
            requests.post(
                f"{GREEN_API_BASE}/sendButtons/{GREEN_API_TOKEN}",
                json={"chatId": f"{phone}@c.us", "message": text,
                      "footer": "ТАКСИ роБОТ", "buttons": buttons},
                timeout=10)
        else:
            # Fallback: номерленген текст-меню — акысыз тарифте да иштейт
            lines = [text, ""]
            mapping = {}
            for i, b in enumerate(flat, start=1):
                lines.append(f"{i}) {b.text}")
                mapping[str(i)] = b.action
            _PENDING_MENU[user_id] = mapping
            self.send_text(user_id, "\n".join(lines))

    def ask_phone_contact(self, user_id, text):
        # WhatsApp'та контакт бөлүшүү баскычы жок — колдонуучу өзү жазат
        self.send_text(user_id, text + "\n\nНомериңизди жазыңыз (мис. 0700123456):")


messenger = WhatsAppMessenger()


@app.route("/webhook/whatsapp", methods=["POST"])
def webhook():
    payload = request.get_json(force=True, silent=True) or {}
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return jsonify({"ok": True})

    sender = payload["senderData"]["sender"].replace("@c.us", "")
    uid = make_uid("whatsapp", sender)
    body = payload.get("messageData", {})
    text = (body.get("textMessageData", {}).get("textMessage")
            or body.get("extendedTextMessageData", {}).get("text")
            or body.get("buttonRepliesData", {}).get("buttonId", ""))
    text = text.strip()

    mapping = _PENDING_MENU.get(uid)
    if mapping and text in mapping:
        msg = IncomingMessage(user_id=uid, platform="whatsapp",
                              is_button=True, button_action=mapping[text])
        _PENDING_MENU.pop(uid, None)
    else:
        msg = IncomingMessage(user_id=uid, platform="whatsapp", text=text)

    logic.handle_update(messenger, msg)
    return jsonify({"ok": True})


if __name__ == "__main__":
    from core.db import init_db
    init_db()
    app.run(port=5001)
