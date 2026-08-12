# -*- coding: utf-8 -*-
"""
core/logic.py — БИР МЭЭ (толук визард)
=======================================
Referral, wizard кадамдары, меню, издөө — баары ушул жерде, БИР ЖОЛУ.
Telegram да, WhatsApp да ушул файлды колдонот.
"""
import os
import re
from datetime import datetime, timedelta
from core import db, posts, admin
from core.messenger import Keyboard, Button
from core.geo import REGIONS, DISTRICTS, DISTRICT_OBLASTS
from core.texts import (render, WELCOME, GUIDE, DRIVER_WARNING,
                        REQUIRED_REFERRALS, VIP_PRICE,
                        PAYMENT_REQUISITES, VIP_REFERRAL_STEP,
                        GATE_BONUS_DAYS, REFERRAL_BONUS_DAYS,
                        PASSENGER_FIRST_BONUS, PASSENGER_NEXT_BONUS,
                        PAYMENT_AMOUNT, PAYMENT_HOURS)

SESSIONS = {}
_SEARCH_CACHE = {}
BOT_USERNAME = "taxirobot_bot"
WA_BOT_NUMBER = os.environ.get("WA_BOT_NUMBER", "996227155603")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/taxirobotbot")

REGION_LIST = list(REGIONS.keys())

DRIVER_STEPS = ["name", "car", "date", "time", "seats", "price", "comment", "phone"]
PASSENGER_STEPS = ["name", "date", "time", "people", "baggage", "comment", "phone"]

STEP_FIELD = {
    "name": "name", "car": "car", "date": "date_text", "time": "time_text",
    "seats": "seats", "price": "price", "people": "people_count",
    "baggage": "baggage", "comment": "comment", "phone": "phone",
}


def steps_of(role):
    return DRIVER_STEPS if role == "driver" else PASSENGER_STEPS


def referral_link(account_id, platform):
    if platform == "telegram":
        return f"https://t.me/{BOT_USERNAME}?start=ref{account_id}"
    # WhatsApp: чат ачылып, кабар талаасына REF коду даяр турат
    return f"https://wa.me/{WA_BOT_NUMBER}?text=REF{account_id}"


def _share_link(link):
    """Telegram'дын контакт тандоо терезесин ачуучу шилтеме."""
    return ("https://t.me/share/url?url=" + link +
            "&text=" + "ТАКСИ роБОТ — Бишкекке такси табуунун эң оңой жолу!")


def _invite_block(account, platform):
    """Ар бир платформа үчүн ылайыктуу чакыруу блогун кайтарат."""
    link = referral_link(account["account_id"], platform)
    if platform == "telegram":
        share = _share_link(link)
        return (f"👇 <a href=\"{share}\">Досторуңузга жиберүү</a>\n\n"
                f"Же шилтемени көчүрүп алыңыз:\n<code>{link}</code>")
    # WhatsApp'та HTML жок — түз шилтеме
    return f"👇 Досторуңузга ушул шилтемени жибериңиз:\n{link}"


def _now():
    return datetime.now()


def has_access(account):
    """Айдоочунун акысыз мөөнөтү бүтө элекпи?"""
    until = account.get("access_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(str(until)) > _now()
    except (ValueError, TypeError):
        return False


def grant_days(account_id, days):
    """Аккаунтка N күн кошот. Мөөнөт бүтө элек болсо — үстүнө кошот."""
    acc = db.get_account(account_id)
    base = _now()
    until = acc.get("access_until") if acc else None
    if until:
        try:
            cur = datetime.fromisoformat(str(until))
            if cur > base:
                base = cur
        except (ValueError, TypeError):
            pass
    new_until = base + timedelta(days=days)
    db.update_account(account_id, access_until=new_until.isoformat())
    return new_until


def days_left(account):
    """Канча күн калганын кайтарат (бүтсө 0)."""
    until = account.get("access_until")
    if not until:
        return 0
    try:
        delta = datetime.fromisoformat(str(until)) - _now()
        return max(0, delta.days)
    except (ValueError, TypeError):
        return 0


def _say(messenger, msg, account, text, keyboard=None):
    lang = account.get("lang", "ky") if account else "ky"
    out = render(text, lang, messenger.platform_name)
    if keyboard:
        if lang != "ky":
            for row in keyboard.rows:
                for b in row:
                    b.text = render(b.text, lang, messenger.platform_name)
        messenger.send_buttons(msg.user_id, out, keyboard)
    elif hasattr(messenger, "send_prompt"):
        # Меню жок кабар — платформа кааласа "0 — башкы меню" эскертүүсүн кошот
        messenger.send_prompt(msg.user_id, out)
    else:
        messenger.send_text(msg.user_id, out)


# ============ КЛАВИАТУРАЛАР ============

def main_menu_kb(platform="telegram"):
    # WhatsApp'та "канал" деген сөз чаташтырбаш үчүн так жазабыз
    channel_label = ("📢 Каналыбыз" if platform == "telegram"
                     else "📢 Telegram каналыбыз")
    return Keyboard.from_flat([
        Button("🚗 Айдоочумун", "menu:driver"),
        Button("🔍 Жүргүнчүмүн", "menu:passenger"),
        Button(channel_label, "menu:channel"),
        Button("🆘 Жардам", "menu:help"),
        Button("🌐 Тил / Язык", "menu:lang"),
    ])


def lang_kb():
    return Keyboard.from_flat([
        Button("🇰🇬 Кыргызча", "setlang:ky"),
        Button("🇷🇺 Русский", "setlang:ru"),
    ])


def driver_menu_kb():
    return Keyboard.from_flat([
        Button("📝 Пост жазам", "d_types"),
        Button("🔍 Жүргүнчүлөрдү издейм", "d_search"),
        Button("📄 Менин посторум", "d_my"),
        Button("⭐ VIP болуу", "d_vip"),
    ])


def passenger_menu_kb():
    return Keyboard.from_flat([
        Button("📝 Пост жазам", "p_types"),
        Button("🔍 Айдоочуларды издейм", "p_search"),
        Button("📄 Менин посторум", "p_my"),
    ])


def back_kb():
    return Keyboard.from_flat([Button("🔙 Артка", "wback")])


def regions_kb():
    return Keyboard.from_flat(
        [Button(r, f"preg:{i}") for i, r in enumerate(REGION_LIST)])


# ============ КИРҮҮ НУКТАСЫ ============

def handle_update(messenger, msg):
    account = db.get_or_create_account(msg.user_id, msg.platform)
    session = SESSIONS.get(msg.user_id)

    text = (msg.text or "").strip()
    if text == "/admin" and admin.handle_command(messenger, msg, account, _say):
        return
    if text.startswith("/start") or text in ("старт", "start"):
        SESSIONS.pop(msg.user_id, None)
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith("ref"):
            try:
                inviter_id = int(parts[1][3:])
                register_referral(messenger, account, inviter_id)
                account = db.get_account(account["account_id"])
            except ValueError:
                pass
        return _say(messenger, msg, account, WELCOME, main_menu_kb(msg.platform))

    # WhatsApp referral: колдонуучу "REF12" деген текст жиберет
    if re.fullmatch(r"(?i)ref\d+", text):
        SESSIONS.pop(msg.user_id, None)
        try:
            register_referral(messenger, account, int(text[3:]))
            account = db.get_account(account["account_id"])
        except ValueError:
            pass
        return _say(messenger, msg, account, WELCOME, main_menu_kb(msg.platform))
    if session:
        # "🏠 Башкы меню" визарддын ичинен да иштеши керек
        if msg.is_button and msg.button_action == "menu:home":
            SESSIONS.pop(msg.user_id, None)
            return _say(messenger, msg, account, WELCOME, main_menu_kb(msg.platform))
        if msg.is_button:
            return _wizard_button(messenger, msg, account, session)
        return _wizard_text(messenger, msg, account, session)

    if msg.is_button:
        if admin.handle_button(messenger, msg, account, _say):
            return
        return _menu_button(messenger, msg, account)

    if admin.handle_text(messenger, msg, account, _say):
        return

    if text.startswith("#"):
        return _hashtag(messenger, msg, account, text)

    _say(messenger, msg, account, "Түшүнбөй калдым 🙈 /start деп жазып көрүңүз.")


# ============ МЕНЮ ============

def _menu_button(messenger, msg, account):
    a = msg.button_action

    if a == "menu:home":
        SESSIONS.pop(msg.user_id, None)
        return _say(messenger, msg, account, WELCOME, main_menu_kb(msg.platform))
    if a == "menu:driver":
        return driver_entry(messenger, msg, account)
    if a == "menu:passenger":
        free = account.get("free_posts", 0) or 0
        if free <= 0:
            invite = _invite_block(account, msg.platform)
            _say(messenger, msg, account,
                 f"💡 Акысыз посттоңуз бүттү, бирок жаза бересиз!\n\n"
                 f"🎁 1 дос чакырсаңыз — дагы {PASSENGER_NEXT_BONUS} пост.\n\n"
                 f"{invite}")
        return _say(messenger, msg, account, "Тандаңыз:", passenger_menu_kb())
    if a == "menu:help":
        return _say(messenger, msg, account, GUIDE)
    if a == "menu:channel":
        return _say(messenger, msg, account,
            f"📢 <b>Биздин канал</b>\n\n"
            f"Айдоочулардын жарыялары каналга чыгып турат — "
            f"жазылып койсоңуз, эң жаңыларын биринчи болуп көрөсүз.\n\n"
            f"{CHANNEL_LINK}")
    if a == "menu:lang":
        return _say(messenger, msg, account,
                    "🌐 Тилди тандаңыз / Выберите язык:", lang_kb())
    if a.startswith("setlang:"):
        new_lang = a.split(":")[1]
        db.update_account(account["account_id"], lang=new_lang)
        account = db.get_account(account["account_id"])
        return _say(messenger, msg, account, WELCOME, main_menu_kb(msg.platform))
    if a == "d_types":
        return post_types(messenger, msg, account, "driver")
    if a == "p_types":
        return post_types(messenger, msg, account, "passenger")
    if a == "d_my":
        return show_my_posts(messenger, msg, account, "driver")
    if a == "p_my":
        return show_my_posts(messenger, msg, account, "passenger")
    if a == "d_vip":
        return show_vip(messenger, msg, account)
    if a in ("d_search", "p_search"):
        return search_menu(messenger, msg, account,
                           "passenger" if a == "d_search" else "driver")
    if a.startswith("del:"):
        return delete_post(messenger, msg, account, int(a.split(":")[1]))
    if a.startswith("sb:"):
        return search_bishkek(messenger, msg, account, a)
    if a.startswith("sr:"):
        return show_results(messenger, msg, account, a)
    if a.startswith("la:"):
        return local_all(messenger, msg, account, a)
    if a.startswith("lo:"):
        return local_oblast_from(messenger, msg, account, a)
    if a.startswith("lof:"):
        return local_oblast_to(messenger, msg, account, a)
    if a.startswith("lot:"):
        return local_oblast_results(messenger, msg, account, a)
    if a.startswith("lr:"):
        return local_results(messenger, msg, account, a)

    _say(messenger, msg, account, "Бул баскыч азырынча иштелип чыккан жок.")


def driver_entry(messenger, msg, account):
    invite = _invite_block(account, msg.platform)

    # 1-этап: гейт ачыла элек
    if (account["ref_count"] or 0) < REQUIRED_REFERRALS:
        return _say(messenger, msg, account,
            f"🚫 Жарыя берүү үчүн {REQUIRED_REFERRALS} дос чакырышыңыз керек.\n"
            f"Учурдагы прогресс: {account['ref_count'] or 0}/{REQUIRED_REFERRALS}\n\n"
            f"🎁 Ачылганда {GATE_BONUS_DAYS} күн акысыз жарыя бересиз!\n\n"
            f"{invite}")

    # 2-этап: гейт ачык, бирок мөөнөт бүткөн
    if not has_access(account):
        return _say(messenger, msg, account,
            f"⏳ Акысыз мөөнөтүңүз бүттү.\n\n"
            f"Улантуу үчүн:\n"
            f"🎁 {REQUIRED_REFERRALS} дос чакырыңыз — {REFERRAL_BONUS_DAYS} күн акысыз\n"
            f"💳 Же {PAYMENT_AMOUNT} төлөңүз — {PAYMENT_HOURS} саат\n\n"
            f"{PAYMENT_REQUISITES}\n\n"
            f"{invite}")

    # 3-этап: баары ачык
    left = days_left(account)
    _say(messenger, msg, account,
         f"✅ Акысыз мөөнөтүңүз: дагы {left} күн\n\nТандаңыз:", driver_menu_kb())


def show_vip(messenger, msg, account):
    invite = _invite_block(account, msg.platform)
    _say(messenger, msg, account,
        f"⭐ <b>VIP айдоочу</b>\n\n"
        f"VIP болсоңуз, жарыяңыз издөө тизмесинин эң үстүнөн чыгат!\n\n"
        f"💳 Баасы: {VIP_PRICE}\n{PAYMENT_REQUISITES}\n\n"
        f"🎁 Же {VIP_REFERRAL_STEP} дос чакырсаңыз — акысыз:\n\n"
        f"{invite}")


# ============ ЖАРЫЯ БЕРҮҮ ============

def post_types(messenger, msg, account, role):
    if not account.get("verified_phone"):
        SESSIONS[msg.user_id] = {"step": "await_phone", "role": role, "data": {}}
        lang = account.get("lang", "ky")
        messenger.ask_phone_contact(msg.user_id, render(
            "📱 Жарыя берүү үчүн бир жолу телефон номериңизди ырастооңуз керек.",
            lang, messenger.platform_name))
        return

    SESSIONS[msg.user_id] = {"step": "mode", "role": role, "data": {}}
    kb = Keyboard.from_flat([
        Button("Облустардын район/шаарларынан Бишкекке жана кайтуу", "mode:bishkek"),
        Button("Район/шаар аралык", "mode:local"),
    ])
    _say(messenger, msg, account, "Кайсы багытта жарыя бересиз?", kb)


def ask_route(messenger, msg, account, st):
    if st["data"].get("mode") == "local":
        st["step"] = "loreg"
        kb = Keyboard.from_flat(
            [Button(o, f"loreg:{i}") for i, o in enumerate(DISTRICT_OBLASTS)])
        _say(messenger, msg, account, "🗺 Кайсы облустан чыгасыз?", kb)
    else:
        st["step"] = "dir"
        kb = Keyboard.from_flat([
            Button("🚕 Бишкекке барам", "route:to_bishkek"),
            Button("🚕 Бишкектен кайтам", "route:from_bishkek"),
        ])
        _say(messenger, msg, account, "Багытты тандаңыз:", kb)


# ============ ВИЗАРД КАДАМДАРЫ ============

def ask_step(messenger, msg, account, st, step):
    st["step"] = step
    role = st["role"]

    if step == "date":
        kb = Keyboard(rows=[[Button("Бүгүн", "dq:0"), Button("Эртең", "dq:1")],
                            [Button("🔙 Артка", "wback")]])
        return _say(messenger, msg, account, "📅 Качан жолго чыгасыз?", kb)

    if step == "time":
        hours = ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00",
                 "12:00", "13:00", "14:00", "15:00", "16:00", "17:00",
                 "18:00", "19:00", "20:00", "21:00", "22:00", "23:00",
                 "00:00", "01:00", "02:00", "03:00", "04:00", "05:00"]
        rows = [[Button(h, f"tm:{h}") for h in hours[k:k + 4]]
                for k in range(0, len(hours), 4)]
        rows.append([Button("🔙 Артка", "wback")])
        return _say(messenger, msg, account,
            "⏰ Саат канчада жолго чыгасыз?\n\n"
            "<i>Башка убакыт болсо — жазып жибериңиз (мис. 05:30).</i>",
            Keyboard(rows=rows))

    if step == "price":
        kb = Keyboard.from_flat([Button("🤝 Келишим баада", "pr:deal"),
                                 Button("🔙 Артка", "wback")])
        return _say(messenger, msg, account,
            "💰 Жол киреси канча?\n\n"
            "<i>Сумманы жазыңыз (мис. 1200), же төмөнкү баскычты басыңыз.</i>", kb)

    if step == "seats":
        rows = [[Button(str(i), f"seat:{i}") for i in range(1, 5)],
                [Button(str(i), f"seat:{i}") for i in range(5, 8)],
                [Button("🔙 Артка", "wback")]]
        return _say(messenger, msg, account, "👥 Канча бош орун бар?",
                    Keyboard(rows=rows))

    if step == "people":
        rows = [[Button(str(i), f"ppl:{i}") for i in range(1, 5)],
                [Button("🔙 Артка", "wback")]]
        return _say(messenger, msg, account,
            "👥 Канча киши жолго чыгасыңар?\n\n"
            "<i>Салон болсо — Салон деп жазып жибериңиз.</i>", Keyboard(rows=rows))

    if step == "baggage":
        kb = Keyboard.from_flat([Button("🚫 Жок", "bg:no"),
                                 Button("🔙 Артка", "wback")])
        return _say(messenger, msg, account,
            "🎒 Багажыңыз барбы?\n\n"
            "<i>Жок болсо — төмөнкү баскычты басыңыз.\n"
            "Бар болсо — жазып жибериңиз (мис. 2 чемодан).</i>", kb)

    if step == "phone":
        ph = account.get("verified_phone")
        if ph:
            kb = Keyboard.from_flat([Button(f"📱 {ph}", "usephone"),
                                     Button("🔙 Артка", "wback")])
            return _say(messenger, msg, account,
                "📞 Байланыш номериңиз:\n\n"
                "Ырасталган номериңизди колдонсоңуз — төмөнкү баскычты басыңыз.\n"
                "Башка номер жазам десеңиз — башка номер жазып жибериңиз.", kb)
        return _say(messenger, msg, account, "📞 Мобилдик телефон номериңиз:", back_kb())

    prompts = {
        "name": "Атыңызды жазыңыз:",
        "car": "Машинаңыздын маркасы жана модели:",
        "comment": ("📝 Кошумча комментарий (жазбасаңыз, жок деп жазыңыз):"
                    if role == "driver" else "📝 Айдоочуларга эмне деп жазасыз?"),
    }
    _say(messenger, msg, account, prompts.get(step, ""), back_kb())


def next_step(messenger, msg, account, st, current):
    steps = steps_of(st["role"])
    i = steps.index(current)
    if i < len(steps) - 1:
        ask_step(messenger, msg, account, st, steps[i + 1])
    else:
        finish(messenger, msg, account, st)


def finish(messenger, msg, account, st):
    if st["role"] == "driver":
        st["step"] = "confirm"
        kb = Keyboard.from_flat([Button("✅ Түшүндүм, жарыялаймын", "confirm"),
                                 Button("🔙 Артка", "wback")])
        _say(messenger, msg, account, DRIVER_WARNING, kb)
    else:
        save(messenger, msg, account, st)


def hashtag(frm, to):
    def short(s):
        s = re.sub(r"\s*(облусу|шаары|району|\(Раззаков\))\s*", "", s or "")
        return re.sub(r"\s+", "_", s.strip())
    return f"#{short(frm)}_{short(to)}"


def channel_text(d, role, tag):
    """Каналга чыгуучу жарыянын тексти."""
    if role == "driver":
        return (
            f"🚖 <b>{d.get('from_city')} ➡️ {d.get('to_city')}</b>\n"
            f"🧍 Аты: {d.get('name')}\n"
            f"🚘 Унаа: {d.get('car')}\n"
            f"📅 {d.get('date_text')} · ⏰ {d.get('time_text')}\n"
            f"👥 Бош орун: {d.get('seats')}\n"
            f"💰 Баасы: {d.get('price')}\n"
            f"📝 {d.get('comment')}\n"
            f"📞 <code>{d.get('phone')}</code>\n\n{tag}"
        )
    return ""


def save(messenger, msg, account, st):
    d = st["data"]
    role = st["role"]
    post_id = posts.create_post(account["account_id"], role, d)
    SESSIONS.pop(msg.user_id, None)

    _say(messenger, msg, account,
         "✅ Жарыя чыкты! Платформада 24 саат турат, андан кийин автоматтык өчүрүлөт.")

    tag = hashtag(d.get("from_city"), d.get("to_city"))

    if role == "driver":
        # Каналга чыгарабыз — платформа өзү билет, core билбейт
        msg_id = messenger.publish_to_channel(channel_text(d, role, tag))
        if msg_id:
            posts.set_channel_msg(post_id, msg_id)
            _say(messenger, msg, account,
                 "📢 Жарыяңыз каналга да чыкты — жүргүнчүлөр аны ошол жерден көрө алат.")
    else:
        _say(messenger, msg, account,
             "🔒 Жүргүнчүнүн жарыясы каналга чыкпайт — аны айдоочулар платформада гана көрөт.")

    _say(messenger, msg, account,
        f"💡Хештегди басып, ошол багыттагы айдоочуларды издеп көрүңүз.\n\n{tag}")

    if role == "driver":
        _say(messenger, msg, account, "Тандаңыз:", driver_menu_kb())
    else:
        _say(messenger, msg, account, "Тандаңыз:", passenger_menu_kb())


# ============ БАСКЫЧТАР (визард ичинде) ============

def _wizard_button(messenger, msg, account, st):
    a = msg.button_action
    d = st["data"]

    if a == "wback":
        return wizard_back(messenger, msg, account, st)

    if a.startswith("mode:"):
        d["mode"] = a.split(":")[1]
        return ask_route(messenger, msg, account, st)

    if a.startswith("route:"):
        direction = a.split(":")[1]
        d["direction"] = direction
        st["step"] = "preg"
        if direction == "to_bishkek":
            d["to_city"] = "Бишкек"
            return _say(messenger, msg, account, "Кайсы облуска барасыз?", regions_kb())
        d["from_city"] = "Бишкек"
        return _say(messenger, msg, account,
                    "🗺 Барар жериңизди тандаңыз (облус):", regions_kb())

    if a.startswith("preg:"):
        region = REGION_LIST[int(a.split(":")[1])]
        d["_region"] = region
        st["step"] = "pcity"
        kb = Keyboard.from_flat(
            [Button(c, f"pcity:{i}") for i, c in enumerate(REGIONS[region])]
            + [Button("🔙 Артка", "wback")])
        return _say(messenger, msg, account,
                    f"📍 <b>{region}</b>\nШаар/район тандаңыз:", kb)

    if a.startswith("pcity:"):
        region = d.get("_region")
        city = REGIONS[region][int(a.split(":")[1])]
        if d.get("direction") == "to_bishkek":
            d["from_city"] = city
        else:
            d["to_city"] = city
        _say(messenger, msg, account,
             f"✅ Маршрут: {d.get('from_city')} ➡️ {d.get('to_city')}")
        return ask_step(messenger, msg, account, st, steps_of(st["role"])[0])

    if a.startswith("loreg:"):
        oblast = DISTRICT_OBLASTS[int(a.split(":")[1])]
        d["_oblast"] = oblast
        st["step"] = "lofrom"
        kb = Keyboard.from_flat(
            [Button(c, f"lofrom:{i}") for i, c in enumerate(DISTRICTS[oblast])]
            + [Button("🔙 Артка", "wback")])
        return _say(messenger, msg, account,
                    f"📍 <b>{oblast}</b>\nКайсы райондон/шаардан чыгасыз?", kb)

    if a.startswith("lofrom:"):
        oblast = d["_oblast"]
        d["from_city"] = DISTRICTS[oblast][int(a.split(":")[1])]
        st["step"] = "lotoreg"
        kb = Keyboard.from_flat(
            [Button(o, f"lotoreg:{i}") for i, o in enumerate(DISTRICT_OBLASTS)]
            + [Button("🔙 Артка", "wback")])
        return _say(messenger, msg, account,
            f"📍 Чыгуу: <b>{d['from_city']}</b>\n🗺 Кайсы облуска барасыз?", kb)

    if a.startswith("lotoreg:"):
        oblast = DISTRICT_OBLASTS[int(a.split(":")[1])]
        d["_to_oblast"] = oblast
        st["step"] = "loto"
        btns = [Button(c, f"loto:{i}") for i, c in enumerate(DISTRICTS[oblast])
                if c != d.get("from_city")]
        btns.append(Button("🔙 Артка", "wback"))
        return _say(messenger, msg, account,
                    f"📍 <b>{oblast}</b>\nКайсы районго/шаарга барасыз?",
                    Keyboard.from_flat(btns))

    if a.startswith("loto:"):
        oblast = d["_to_oblast"]
        d["to_city"] = DISTRICTS[oblast][int(a.split(":")[1])]
        _say(messenger, msg, account,
             f"✅ Маршрут: {d['from_city']} ➡️ {d['to_city']}")
        return ask_step(messenger, msg, account, st, steps_of(st["role"])[0])

    if a.startswith("dq:"):
        d["date_text"] = ["Бүгүн", "Эртең"][int(a.split(":")[1])]
        return next_step(messenger, msg, account, st, "date")

    if a.startswith("tm:"):
        t = a.split(":", 1)[1]
        d["time_text"] = f"Саат {t}дө жолго чыгам"
        return next_step(messenger, msg, account, st, "time")

    if a == "pr:deal":
        d["price"] = "Келишим"
        return next_step(messenger, msg, account, st, "price")

    if a == "bg:no":
        d["baggage"] = "Жок"
        return next_step(messenger, msg, account, st, "baggage")

    if a.startswith("seat:"):
        d["seats"] = a.split(":")[1]
        return next_step(messenger, msg, account, st, "seats")

    if a.startswith("ppl:"):
        d["people_count"] = a.split(":")[1]
        return next_step(messenger, msg, account, st, "people")

    if a == "usephone":
        d["phone"] = account.get("verified_phone", "")
        return finish(messenger, msg, account, st)

    if a == "confirm":
        return save(messenger, msg, account, st)


def wizard_back(messenger, msg, account, st):
    step = st.get("step")
    steps = steps_of(st["role"])

    if step == "confirm":
        return ask_step(messenger, msg, account, st, steps[-1])
    if step in steps:
        i = steps.index(step)
        if i == 0:
            return ask_route(messenger, msg, account, st)
        return ask_step(messenger, msg, account, st, steps[i - 1])

    SESSIONS.pop(msg.user_id, None)
    if st["role"] == "driver":
        _say(messenger, msg, account, "Тандаңыз:", driver_menu_kb())
    else:
        _say(messenger, msg, account, "Тандаңыз:", passenger_menu_kb())


def _wizard_text(messenger, msg, account, st):
    step = st.get("step")
    text = (msg.text or "").strip()

    if step == "await_phone":
        return verify_phone(messenger, msg, account, st, text)

    field = STEP_FIELD.get(step)
    if not field:
        return
    st["data"][field] = text
    next_step(messenger, msg, account, st, step)


def verify_phone(messenger, msg, account, st, raw):
    phone = normalize_phone(raw)
    if not phone:
        return _say(messenger, msg, account,
                    "⚠️ Телефон номери туура эмес. Кайра аракет кылыңыз.")
    existing = db.find_account_by_phone(phone)
    if existing and existing["account_id"] != account["account_id"]:
        db.link_second_platform(existing["account_id"], msg.user_id, msg.platform)
        account = existing
        _say(messenger, msg, account, "✅ Номериңиз мурдагы аккаунтуңузга байланды!")
    else:
        db.update_account(account["account_id"], verified_phone=phone)
        account = db.get_account(account["account_id"])
    _say(messenger, msg, account, f"✅ Номериңиз ырасталды: <b>{phone}</b>")
    return post_types(messenger, msg, account, st["role"])


def normalize_phone(raw):
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        return "996" + digits[1:]
    if digits.startswith("996") and len(digits) == 12:
        return digits
    return None


# ============ МЕНИН ПОСТОРУМ ============

def post_card(p):
    vip = " ⭐" if p.get("is_vip") else ""
    role_tag = "🚗 <b>АЙДООЧУ</b>" if p["role"] == "driver" else "🧳 <b>ЖҮРГҮНЧҮ</b>"
    lines = [role_tag,
             f"<b>{p['from_city']} ➡️ {p['to_city']}</b>{vip}",
             f"🧍 Аты: {p['name']}"]
    if p["role"] == "driver":
        lines += [f"🚘 Унаа: {p['car']}", f"👥 Бош орун: {p['seats']}",
                  f"💰 Баасы: {p['price']}"]
    else:
        lines += [f"👥 Адам саны: {p['people_count']}", f"🎒 Багаж: {p['baggage']}"]
    lines += [f"📅 {p['date_text']} · ⏰ {p['time_text']}", f"📞 {p['phone']}"]
    if p.get("comment"):
        lines.append(f"📝 {p['comment']}")
    return "\n".join(lines)


def show_my_posts(messenger, msg, account, role):
    rows = posts.my_posts(account["account_id"], role)
    if not rows:
        return _say(messenger, msg, account, "❌ Сиздин учурда активдүү жарыяңыз жок.")
    _say(messenger, msg, account, "📄 <b>Сиздин активдүү посттор</b>")
    for p in rows:
        kb = Keyboard.from_flat([Button("❌ Өчүрүү", f"del:{p['id']}")])
        _say(messenger, msg, account, post_card(p), kb)


def delete_post(messenger, msg, account, post_id):
    ok = posts.deactivate_post(post_id, account["account_id"])
    _say(messenger, msg, account,
         "🗑 Жарыя өчүрүлдү." if ok else "❌ Жарыя табылган жок.")


# ============ ИЗДӨӨ ============

def search_menu(messenger, msg, account, target_role):
    kb = Keyboard.from_flat([
        Button("➡️ Бишкекке бараткандар", f"sb:to:{target_role}"),
        Button("⬅️ Бишкектен кайткандар", f"sb:from:{target_role}"),
        Button("🗺 Район аралык — баары", f"la:{target_role}"),
        Button("🗺 Район аралык — облус боюнча", f"lo:{target_role}"),
    ])
    _say(messenger, msg, account, "Багытты тандаңыз:", kb)


def local_all(messenger, msg, account, action):
    """🗺 Район аралык — бардык маршруттар."""
    role = action.split(":")[1]
    rows = [r for r in posts.local_route_counts() if r["role"] == role]
    if not rows:
        return _say(messenger, msg, account, "❌ Бул багыт боюнча жарыя азырынча жок.")
    btns = []
    pairs = []
    for i, r in enumerate(rows):
        btns.append(Button(f"{r['from_city']} ➡️ {r['to_city']} · {r['n']} жарыя",
                           f"lr:{role}:{i}"))
        pairs.append((r["from_city"], r["to_city"]))
    _SEARCH_CACHE[msg.user_id] = pairs
    _say(messenger, msg, account, "📋 <b>Жазылган посттор</b>",
         Keyboard.from_flat(btns))


def local_oblast_from(messenger, msg, account, action):
    """1-кадам: чыгуу облусу."""
    role = action.split(":")[1]
    kb = Keyboard.from_flat(
        [Button(o, f"lof:{role}:{i}") for i, o in enumerate(DISTRICT_OBLASTS)])
    _say(messenger, msg, account, "🗺 Кайсы облустан чыккандарды издейсиз?", kb)


def local_oblast_to(messenger, msg, account, action):
    """2-кадам: баруу облусу."""
    _, role, idx = action.split(":")
    kb = Keyboard.from_flat(
        [Button(o, f"lot:{role}:{idx}:{i}") for i, o in enumerate(DISTRICT_OBLASTS)])
    frm = DISTRICT_OBLASTS[int(idx)]
    _say(messenger, msg, account,
         f"📍 Чыгуу: <b>{frm}</b>\n🗺 Кайсы облуска баргандарды издейсиз?", kb)


def local_oblast_results(messenger, msg, account, action):
    """3-кадам: эки облустун ортосундагы маршруттар."""
    _, role, i_from, i_to = action.split(":")
    ob_from = DISTRICT_OBLASTS[int(i_from)]
    ob_to = DISTRICT_OBLASTS[int(i_to)]
    rows = posts.local_routes_by_oblast(
        DISTRICTS[ob_from], DISTRICTS[ob_to], role)
    if not rows:
        return _say(messenger, msg, account, "❌ Бул багыт боюнча жарыя азырынча жок.")
    btns = []
    pairs = []
    for i, r in enumerate(rows):
        btns.append(Button(f"{r['from_city']} ➡️ {r['to_city']} · {r['n']} жарыя",
                           f"lr:{role}:{i}"))
        pairs.append((r["from_city"], r["to_city"]))
    _SEARCH_CACHE[msg.user_id] = pairs
    _say(messenger, msg, account,
         f"📋 <b>{ob_from} ➡️ {ob_to}</b>", Keyboard.from_flat(btns))


def local_results(messenger, msg, account, action):
    """Тандалган маршруттун жарыялары."""
    _, role, idx = action.split(":")
    pairs = _SEARCH_CACHE.get(msg.user_id, [])
    if int(idx) >= len(pairs):
        return _say(messenger, msg, account, "❌ Кайра издеп көрүңүз.")
    frm, to = pairs[int(idx)]
    rows = posts.search_posts(role, from_city=frm, to_city=to)
    if not rows:
        return _say(messenger, msg, account, "❌ Бул багыт боюнча жарыя табылган жок.")
    for p in rows:
        _say(messenger, msg, account,
             post_card(p) + f"\n\n📞 Байланыш: <code>{p['phone']}</code>")


def search_bishkek(messenger, msg, account, action):
    _, direction, role = action.split(":")
    to_bishkek = direction == "to"
    rows = posts.route_counts(role, to_bishkek)
    if not rows:
        return _say(messenger, msg, account, "❌ Бул багыт боюнча жарыя азырынча жок.")
    btns = []
    for i, r in enumerate(rows):
        if to_bishkek:
            label = f"{r['k']} ➡️ Бишкек · {r['n']} жарыя"
        else:
            label = f"Бишкек ➡️ {r['k']} · {r['n']} жарыя"
        btns.append(Button(label, f"sr:{role}:{direction}:{i}"))
    _SEARCH_CACHE[msg.user_id] = [r["k"] for r in rows]
    _say(messenger, msg, account, "📋 <b>Жазылган посттор</b>",
         Keyboard.from_flat(btns))


def show_results(messenger, msg, account, action):
    _, role, direction, idx = action.split(":")
    cities = _SEARCH_CACHE.get(msg.user_id, [])
    if int(idx) >= len(cities):
        return _say(messenger, msg, account, "❌ Кайра издеп көрүңүз.")
    city = cities[int(idx)]
    if direction == "to":
        rows = posts.search_posts(role, from_city=city, to_city="Бишкек")
    else:
        rows = posts.search_posts(role, from_city="Бишкек", to_city=city)
    if not rows:
        return _say(messenger, msg, account, "❌ Бул багыт боюнча жарыя табылган жок.")
    for p in rows:
        _say(messenger, msg, account,
             post_card(p) + f"\n\n📞 Байланыш: <code>{p['phone']}</code>")


def _hashtag(messenger, msg, account, text):
    """#Ош_Бишкек → ошол багыттагы жарыялар, ролго бөлүнүп."""
    parts = text[1:].split("_")
    if len(parts) < 2:
        return _say(messenger, msg, account, "❓ Бул хештегди тааныган жокмун.")
    frm, to = parts[0], "_".join(parts[1:])
    rows = posts.search_by_hashtag(frm, to)
    _say(messenger, msg, account, f"🔎 Издөө: <b>{text}</b>")
    if not rows:
        return _say(messenger, msg, account, "❌ Бул багытта азырынча жарыя жок.")

    drivers = [p for p in rows if p["role"] == "driver"]
    passengers = [p for p in rows if p["role"] == "passenger"]

    if drivers:
        _say(messenger, msg, account,
             f"🚗 <b>Айдоочулар</b> ({len(drivers)})")
        for p in drivers:
            _say(messenger, msg, account,
                 post_card(p) + f"\n\n📞 Байланыш: <code>{p['phone']}</code>")

    if passengers:
        _say(messenger, msg, account,
             f"🧳 <b>Жүргүнчүлөр</b> ({len(passengers)})")
        for p in passengers:
            _say(messenger, msg, account,
                 post_card(p) + f"\n\n📞 Байланыш: <code>{p['phone']}</code>")


def register_referral(messenger, newbie, inviter_id):
    if inviter_id == newbie["account_id"]:
        return
    if newbie.get("referred_by"):
        return
    inviter = db.get_account(inviter_id)
    if not inviter:
        return

    db.update_account(newbie["account_id"], referred_by=inviter_id)
    new_count = (inviter["ref_count"] or 0) + 1
    granted = inviter.get("gate_bonus", 0) or 0   # канча жолу бонус берилди

    # ---- Жүргүнчү бонусу: ар бир дос ----
    old_free = inviter.get("free_posts", 0) or 0
    add_posts = PASSENGER_FIRST_BONUS if new_count == 1 else PASSENGER_NEXT_BONUS
    db.update_account(inviter_id, ref_count=new_count,
                      free_posts=old_free + add_posts)

    pid = db.platform_id_of(inviter_id)
    if not pid:
        return

    def tell(text):
        try:
            messenger.send_text(pid, text)
        except Exception:
            pass

    tell(f"✅ Жаңы дос кошулду! Жалпы: {new_count} дос.\n"
         f"🧳 Жүргүнчү катары +{add_posts} акысыз пост.")

    # ---- Айдоочу бонусу: ар 3 дос сайын ----
    earned = new_count // REQUIRED_REFERRALS      # канча бонус татыктуу
    if earned > granted:
        days = GATE_BONUS_DAYS if granted == 0 else REFERRAL_BONUS_DAYS
        grant_days(inviter_id, days)
        db.update_account(inviter_id, gate_bonus=earned)
        if granted == 0:
            tell(f"🎉 Куттуктайбыз! Платформа толук ачылды!\n"
                 f"🎁 {days} күн акысыз жарыя бере аласыз.")
        else:
            tell(f"🎁 Дагы {days} күн акысыз кошулду!")


