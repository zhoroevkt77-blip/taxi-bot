# -*- coding: utf-8 -*-
"""
core/logic.py
=============
БУЛ — "БИР МЭЭ". Referral эрежелери, wizard кадамдары, меню
логикасы — баары ушул жерде, БИР ЖОЛУ жазылат.

Эки адаптер тең handle_update() функциясын чакырат.
Жаңы функцияны кошкондо экөөнү тең кайра жазуунун ордуна
БУЛ ФАЙЛГА бир жолу кошосуң.
"""

from core import db
from core.messenger import Messenger, Keyboard, Button, IncomingMessage
from core.texts import render, WELCOME, REQUIRED_REFERRALS

# Визарддын учурдагы кадамы (эки платформа үчүн тең ортоктош)
SESSIONS = {}   # platform_id -> {"step": ..., "data": {...}, "role": ...}

BOT_USERNAME = "tap_taxi_bot"


def referral_link(account_id, platform):
    if platform == "telegram":
        return f"https://t.me/{BOT_USERNAME}?start=ref{account_id}"
    return f"wa.me/?text=REF{account_id}"


def _say(messenger, msg, account, text, keyboard=None):
    lang = account.get("lang", "ky") if account else "ky"
    rendered = render(text, lang, messenger.platform_name)
    if keyboard:
        messenger.send_buttons(msg.user_id, rendered, keyboard)
    else:
        messenger.send_text(msg.user_id, rendered)


def main_menu_kb():
    return Keyboard.from_flat([
        Button("🚗 Айдоочумун", "menu:driver"),
        Button("🔍 Жүргүнчүмүн", "menu:passenger"),
        Button("🆘 Жардам", "menu:help"),
    ])


def driver_menu_kb():
    return Keyboard.from_flat([
        Button("📝 Жарыя берем", "d_types"),
        Button("🔍 Жүргүнчүлөрдү издейм", "d_search"),
        Button("📄 Менин жарыяларым", "d_my"),
        Button("⭐ VIP болуу", "d_vip"),
    ])


def handle_update(messenger, msg):
    """Эки адаптер тең ушул бир функцияны чакырат."""
    account = db.get_or_create_account(msg.user_id, msg.platform)
    session = SESSIONS.get(msg.user_id)

    if session and not msg.is_button:
        return _handle_wizard_text(messenger, msg, account, session)
    if session and msg.is_button:
        return _handle_wizard_button(messenger, msg, account, session)
    if msg.is_button:
        return _handle_menu_button(messenger, msg, account)

    text = msg.text.strip()
    if text in ("/start", "старт", "start"):
        return cmd_start(messenger, msg, account)
    if text.startswith("#"):
        return search_by_hashtag(messenger, msg, account, text)

    _say(messenger, msg, account, "Түшүнбөй калдым 🙈 /start деп жазып көрүңүз.")


def cmd_start(messenger, msg, account):
    _say(messenger, msg, account, WELCOME, keyboard=main_menu_kb())


def _handle_menu_button(messenger, msg, account):
    action = msg.button_action
    if action == "menu:driver":
        return driver_entry(messenger, msg, account)
    if action == "menu:passenger":
        return passenger_entry(messenger, msg, account)
    if action == "d_types":
        return post_types(messenger, msg, account, role="driver")
    if action == "p_types":
        return post_types(messenger, msg, account, role="passenger")
    if action.startswith("route:"):
        return route_pick(messenger, msg, account, action.split(":")[1])
    _say(messenger, msg, account, "Бул баскыч азырынча иштелип чыккан жок.")


def driver_entry(messenger, msg, account):
    if account["ref_count"] < REQUIRED_REFERRALS:
        link = referral_link(account["account_id"], msg.platform)
        _say(messenger, msg, account,
             f"🚫 Жарыя берүү үчүн {REQUIRED_REFERRALS} дос чакырышыңыз керек.\n"
             f"Учурдагы прогресс: {account['ref_count']}/{REQUIRED_REFERRALS}\n\n"
             f"👇 Жеке шилтемеңиз:\n{link}")
        return
    _say(messenger, msg, account, "Тандаңыз:", keyboard=driver_menu_kb())


def passenger_entry(messenger, msg, account):
    kb = Keyboard.from_flat([
        Button("📝 Жарыя берем", "p_types"),
        Button("🔍 Айдоочуларды издейм", "p_search"),
        Button("📄 Менин жарыяларым", "p_my"),
    ])
    note = ""
    if account["free_posts"] > 0:
        note = f"\n🎁 Акысыз жарыялар: {account['free_posts']}"
    _say(messenger, msg, account, f"Тандаңыз:{note}", keyboard=kb)


def post_types(messenger, msg, account, role):
    if not account.get("verified_phone"):
        SESSIONS[msg.user_id] = {"step": "await_phone", "role": role, "data": {}}
        lang = account.get("lang", "ky")
        messenger.ask_phone_contact(
            msg.user_id,
            render("📱 Жарыя берүү үчүн бир жолу телефон номериңизди ырастооңуз керек.",
                   lang, messenger.platform_name))
        return

    SESSIONS[msg.user_id] = {"step": "route", "role": role, "data": {}}
    kb = Keyboard.from_flat([
        Button("🚕 Бишкекке барам", "route:to_bishkek"),
        Button("🚕 Бишкектен кетем", "route:from_bishkek"),
    ])
    _say(messenger, msg, account, "Багытты тандаңыз:", keyboard=kb)


def route_pick(messenger, msg, account, direction):
    session = SESSIONS.get(msg.user_id)
    if not session:
        return
    session["data"]["direction"] = direction
    session["step"] = "region"
    _say(messenger, msg, account, "🗺 Кайсы облуска барасыз? (аталышын жазыңыз)")


def _handle_wizard_text(messenger, msg, account, session):
    step = session["step"]
    if step == "await_phone":
        return _verify_phone(messenger, msg, account, session, msg.text)
    if step == "region":
        session["data"]["region"] = msg.text.strip()
        _say(messenger, msg, account,
             f"✅ Маршрут сакталды: {session['data']}\n\n"
             f"(Калган кадамдар ушул схема боюнча уланат: аты, күнү, баасы...)")
        SESSIONS.pop(msg.user_id, None)


def _handle_wizard_button(messenger, msg, account, session):
    if msg.button_action.startswith("route:"):
        return route_pick(messenger, msg, account, msg.button_action.split(":")[1])


def _verify_phone(messenger, msg, account, session, raw_phone):
    phone = normalize_phone(raw_phone)
    if not phone:
        _say(messenger, msg, account, "⚠️ Телефон номери туура эмес. Кайра аракет кылыңыз.")
        return
    existing = db.find_account_by_phone(phone)
    if existing and existing["account_id"] != account["account_id"]:
        db.link_second_platform(existing["account_id"], msg.user_id, msg.platform)
        _say(messenger, msg, account, "✅ Номериңиз мурдагы аккаунтуңузга байланды!")
    else:
        db.update_account(account["account_id"], verified_phone=phone)
    session["step"] = "route"
    _say(messenger, msg, account, "✅ Ырасталды! Эми жарыя бере аласыз.")


def normalize_phone(raw):
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        return "996" + digits[1:]
    if digits.startswith("996") and len(digits) == 12:
        return digits
    return None


def search_by_hashtag(messenger, msg, account, text):
    _say(messenger, msg, account, f"🔎 «{text}» боюнча издөө (толук логика кийин кошулат).")
