# -*- coding: utf-8 -*-
"""
adapters/telegram_adapter.py
=============================
Telegram update'терди core.messenger.IncomingMessage'ге айландырат.
Эч бир бизнес-эреже бул жерде жазылбайт — баары core/logic.py'де.

Башкы меню (Айдоочумун / Жүргүнчүмүн / Жардам) — Telegram'дын ылдыйкы
reply-клавиатурасы. Ал ар дайым көрүнүп турат. Колдонуучу аны басканда
текст келет, биз аны core тааныган баскыч кодуна которобуз.
"""

import os
import telebot
from telebot import types

from core.messenger import Messenger, IncomingMessage, make_uid
from core import logic

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # мис. @kanal_aty же -1001234567890
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Ылдыйкы клавиатурадагы жазуу → core'дун ички коду
MAIN_MENU = {
    "🚗 Айдоочумун": "menu:driver",
    "🔍 Жүргүнчүмүн": "menu:passenger",
    "🆘 Жардам": "menu:help",
}


def main_reply_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🚗 Айдоочумун", "🔍 Жүргүнчүмүн")
    kb.row("🆘 Жардам")
    return kb


class TelegramMessenger(Messenger):
    platform_name = "telegram"

    def send_text(self, user_id, text):
        chat_id = user_id.split(":", 1)[1]
        bot.send_message(chat_id, text)

    def send_buttons(self, user_id, text, keyboard):
        chat_id = user_id.split(":", 1)[1]
        kb = types.InlineKeyboardMarkup()
        for row in keyboard.rows:
            kb.row(*[types.InlineKeyboardButton(b.text, callback_data=b.action)
                     for b in row])
        bot.send_message(chat_id, text, reply_markup=kb)

    def ask_phone_contact(self, user_id, text):
        chat_id = user_id.split(":", 1)[1]
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton("📱 Номеримди бөлүшөм", request_contact=True))
        bot.send_message(chat_id, text, reply_markup=kb)

    def publish_to_channel(self, text):
        """Жарыяны Telegram каналына чыгарат."""
        if not CHANNEL_ID:
            return None
        try:
            m = bot.send_message(CHANNEL_ID, text)
            return m.message_id
        except Exception as e:
            print("Каналга жарыялоо ишке ашкан жок:", e)
            return None
messenger = TelegramMessenger()


@bot.message_handler(commands=["start"])
def _start(m):
    # Башкы менюну ылдыйга орнотуп коёбуз
    bot.send_message(m.chat.id, "🚕", reply_markup=main_reply_kb())
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", text="/start")
    logic.handle_update(messenger, msg)


@bot.message_handler(content_types=["contact"])
def _contact(m):
    # Контакт баскычын алып салып, башкы менюну кайтарабыз
    bot.send_message(m.chat.id, "✅ Рахмат!", reply_markup=main_reply_kb())
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", text=m.contact.phone_number)
    logic.handle_update(messenger, msg)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def _text(m):
    uid = make_uid("telegram", m.from_user.id)
    action = MAIN_MENU.get(m.text)
    if action:
        # Ылдыйкы менюнун баскычы — аны core'го баскыч катары беребиз
        msg = IncomingMessage(user_id=uid, platform="telegram",
                              is_button=True, button_action=action)
    else:
        msg = IncomingMessage(user_id=uid, platform="telegram", text=m.text)
    logic.handle_update(messenger, msg)


@bot.callback_query_handler(func=lambda c: True)
def _callback(c):
    msg = IncomingMessage(user_id=make_uid("telegram", c.from_user.id),
                          platform="telegram", is_button=True, button_action=c.data)
    logic.handle_update(messenger, msg)
    bot.answer_callback_query(c.id)


def run():
    from core.db import init_db
    init_db()
    bot.infinity_polling()


if __name__ == "__main__":
    run()
