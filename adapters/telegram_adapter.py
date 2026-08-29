# -*- coding: utf-8 -*-
"""
adapters/telegram_adapter.py
=============================
Telegram update'терди core.messenger.IncomingMessage'ге айландырат.
Эч бир бизнес-эреже бул жерде жазылбайт — баары core/logic.py'де.

Башкы меню (Айдоочумун / Жүргүнчүмүн / Канал / Сайт / Жардам / Тил) —
Telegram'дын ылдыйкы reply-клавиатурасы. Ал ар дайым көрүнүп турат.
Колдонуучу аны басканда текст келет, биз аны core тааныган баскыч
кодуна которобуз.

ЭСКЕРТҮҮ: бул клавиатура core/logic.py'деги main_menu_kb() менен
ДАЛ КЕЛИШИ керек. Ал жерге жаңы баскыч кошсоңуз, бул жерге да
кошуңуз — болбосо ылдыйкы меню эски бойдон калат.

URL БАСКЫЧТАРЫ:
    Button'дун url талаасы толтурулса, ал inline URL баскычы болуп
    чыгат — басканда ботко кабар келбей, дароо ошол шилтеме ачылат.

CONFLICT КАТАСЫ (409):
    Telegram бир ботко бир гана getUpdates уруксат берет. Эки жерден
    сураса, экинчисине «Conflict: terminated by other getUpdates
    request» деген ката берет.

    Эки коргоо коюлган:
      1. _RUNNING белгиси — run() кокустан эки жолу чакырылса,
         экинчиси дароо чыгып кетет (whatsapp_adapter'деги сыяктуу).
      2. remove_webhook() — эгер мурда webhook коюлуп калган болсо,
         polling'ке өтөрдөн мурун аны алып салабыз.

    Эскертүү: деплой учурунда эски контейнер өчө элегинде жаңысы
    башталса, бул ката бир-эки жолу чыгып, өзү басылат — ал кадимки
    көрүнүш жана эч нерсени бузбайт.
"""

import os
import time
import threading
import telebot
from telebot import types

from core.messenger import Messenger, IncomingMessage, make_uid
from core import logic

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # мис. @kanal_aty же -1001234567890
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

TG_ADAPTER_VERSION = "v9-site-button"
print(f"📨 telegram_adapter жүктөлдү. Версия = {TG_ADAPTER_VERSION}, "
      f"PID={os.getpid()}")

# Ылдыйкы клавиатурадагы жазуу → core'дун ички коду
MAIN_MENU = {
    "🚗 Айдоочумун": "menu:driver",
    "🔍 Жүргүнчүмүн": "menu:passenger",
    "📢 Telegram каналыбыз": "menu:channel",
    "🌐 Сайт": "menu:site",
    "🆘 Жардам": "menu:help",
    "🌐 Тил / Язык": "menu:lang",
    # Орусча варианттары да ушул эле коддорго барат
    "🚗 Я водитель": "menu:driver",
    "🔍 Я пассажир": "menu:passenger",
    "📢 Наш Telegram-канал": "menu:channel",
    "🆘 Помощь": "menu:help",
}


def main_reply_kb(lang="ky"):
    """Ылдыйкы туруктуу меню.

    Тартиби core/logic.py'деги main_menu_kb() менен бирдей болушу керек.
    «🌐 Сайт» эки тилде тең бирдей жазылат — кыска жана түшүнүктүү.
    """
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang == "ru":
        kb.row("🚗 Я водитель", "🔍 Я пассажир")
        kb.row("📢 Наш Telegram-канал", "🌐 Сайт")
        kb.row("🆘 Помощь", "🌐 Тил / Язык")
    else:
        kb.row("🚗 Айдоочумун", "🔍 Жүргүнчүмүн")
        kb.row("📢 Telegram каналыбыз", "🌐 Сайт")
        kb.row("🆘 Жардам", "🌐 Тил / Язык")
    return kb


# Боттун өз аватары — /start'та салам катары чыгат.
# Башталышта бир жолу алынып, file_id эсте калат (кайра-кайра сурабайбыз).
BOT_PHOTO = None
BOT_TITLE = "<b>ТАКСИ роБОТ</b>"


def _load_bot_photo():
    """Боттун профилиндеги сүрөттүн file_id'син алат.

    Аватар коюлбаса же API уруксат бербесе — None калат,
    ошондо /start'та мурдагыдай 🚕 эмодзи чыгат.
    """
    global BOT_PHOTO
    try:
        me = bot.get_me()
        photos = bot.get_user_profile_photos(me.id, limit=1)
        if photos and photos.total_count and photos.photos:
            BOT_PHOTO = photos.photos[0][-1].file_id   # эң чоң өлчөмү
            print("🖼 Боттун аватары табылды — /start'та ошол чыгат.")
        else:
            print("ℹ️ Ботто аватар жок — /start'та 🚕 эмодзи чыгат.")
    except Exception as e:
        print("Аватарды алуу катасы:", e)


def _send_greeting(chat_id, lang):
    """/start'тагы салам: логотип + аталыш, же болбосо эмодзи."""
    kb = main_reply_kb(lang)
    if BOT_PHOTO:
        try:
            bot.send_photo(chat_id, BOT_PHOTO, caption=BOT_TITLE, reply_markup=kb)
            return
        except Exception as e:
            print("Логотип жиберүү катасы:", e)
    bot.send_message(chat_id, "🚕", reply_markup=kb)


def _lang_of(tg_user_id):
    """Колдонуучунун тилин базадан алат (клавиатура үчүн)."""
    try:
        from core import db
        acc = db.get_or_create_account(make_uid("telegram", tg_user_id), "telegram")
        return acc.get("lang", "ky")
    except Exception:
        return "ky"


class TelegramMessenger(Messenger):
    platform_name = "telegram"

    def send_text(self, user_id, text):
        chat_id = user_id.split(":", 1)[1]
        bot.send_message(chat_id, text)

    def send_buttons(self, user_id, text, keyboard):
        """Inline баскычтар. url коюлган баскыч түз шилтемени ачат."""
        chat_id = user_id.split(":", 1)[1]
        kb = types.InlineKeyboardMarkup()
        for row in keyboard.rows:
            btns = []
            for b in row:
                url = getattr(b, "url", None)
                if url:
                    btns.append(types.InlineKeyboardButton(b.text, url=url))
                else:
                    btns.append(types.InlineKeyboardButton(
                        b.text, callback_data=b.action))
            kb.row(*btns)
        bot.send_message(chat_id, text, reply_markup=kb)

    def ask_phone_contact(self, user_id, text):
        chat_id = user_id.split(":", 1)[1]
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton("📱 Номеримди бөлүшөм", request_contact=True))
        bot.send_message(chat_id, text, reply_markup=kb)

    def send_photo(self, user_id, photo, caption=""):
        """photo — Telegram file_id же ачык URL."""
        chat_id = user_id.split(":", 1)[1]
        bot.send_photo(chat_id, photo, caption=caption)

    def publish_to_channel(self, text, links=None):
        """Каналга жарыялоо эми core/channel.py'де — экөө тең колдонот."""
        from core import channel
        return channel.publish(text, links)


messenger = TelegramMessenger()


@bot.message_handler(commands=["start"])
def _start(m):
    # Башкы менюну ылдыйга орнотуп, логотип менен саламдашабыз
    _send_greeting(m.chat.id, _lang_of(m.from_user.id))
    # ВАЖНО: m.text'ти толук беребиз — "/start ref12" же "/start ht34"
    # деген параметрлер core'го жетиши керек.
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", text=(m.text or "/start"))
    logic.handle_update(messenger, msg)


@bot.message_handler(content_types=["contact"])
def _contact(m):
    # Контакт баскычын алып салып, башкы менюну кайтарабыз
    bot.send_message(m.chat.id, "✅ Рахмат!",
                     reply_markup=main_reply_kb(_lang_of(m.from_user.id)))
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", text=m.contact.phone_number)
    logic.handle_update(messenger, msg)


@bot.message_handler(content_types=["photo"])
def _photo(m):
    """Сүрөт келди — төлөм чеги болушу мүмкүн.

    Эң чоң өлчөмүн алабыз (m.photo[-1]) — админ так көрсүн.
    """
    file_id = m.photo[-1].file_id
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram", photo_id=file_id,
                          text=(m.caption or ""))
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
    # Тил алмашса — ылдыйкы клавиатураны да жаңыртабыз
    if c.data.startswith("setlang:"):
        new_lang = c.data.split(":")[1]
        _send_greeting(c.message.chat.id, new_lang)
    bot.answer_callback_query(c.id)


# Polling бир гана жолу башталышы үчүн коргоо
_RUNNING = False
_RUN_LOCK = threading.Lock()


def run():
    """Telegram'дан кабарларды үзгүлтүксүз алып турат.

    Бир процессте бир гана жолу иштейт — _RUNNING аны кепилдейт.
    """
    global _RUNNING

    print(f"🔵 TG run() чакырылды. PID={os.getpid()}, "
          f"thread={threading.current_thread().name}, _RUNNING={_RUNNING}")

    with _RUN_LOCK:
        if _RUNNING:
            print("⚠️ Telegram адаптери мурда башталган — экинчи жолу "
                  "иштетилбейт.")
            return
        if not BOT_TOKEN:
            print("⚠️ BOT_TOKEN коюлган эмес — Telegram өчүк.")
            return
        _RUNNING = True

    from core.db import init_db
    init_db()

    # Мурда webhook коюлуп калган болсо, аны алып салабыз — болбосо
    # Telegram polling'ке уруксат бербей, 409 ката берет.
    try:
        bot.remove_webhook()
        print("🧹 Эски webhook тазаланды (болсо).")
    except Exception as e:
        print("Webhook тазалоо катасы:", e)

    _load_bot_photo()
    print(f"✅ Telegram адаптери башталды. PID={os.getpid()}")

    # 409 (Conflict) же тармак катасы болсо — процессти өлтүрбөй, кайра аракет
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30,
                                 long_polling_timeout=30)
        except Exception as e:
            print("Telegram polling катасы:", e)
            time.sleep(15)


if __name__ == "__main__":
    run()

