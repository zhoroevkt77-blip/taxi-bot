# -*- coding: utf-8 -*-
"""
adapters/telegram_adapter.py
=============================
Бул файл БОЛГОНУ котормочу: Telegram update'терди
core.messenger.IncomingMessage'ге айландырат.
Эч бир бизнес-эреже бул жерде жазылбайт — баары core/logic.py'де.
"""

import os
import telebot
from telebot import types

from core.messenger import Messenger, Keyboard, IncomingMessage, make_uid
from core import logic

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


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


messenger = TelegramMessenger()


@bot.message_handler(commands=["start"])
def _start(m):
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", text="/start")
    logic.handle_update(messenger, msg)


@bot.message_handler(content_types=["contact"])
def _contact(m):
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", text=m.contact.phone_number)
    logic.handle_update(messenger, msg)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def _text(m):
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", text=m.text)
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
