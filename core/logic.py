# -*- coding: utf-8 -*-
"""
core/logic.py — БИР МЭЭ (толук визард)
=======================================
Referral, wizard кадамдары, меню, издөө — баары ушул жерде, БИР ЖОЛУ.
Telegram да, WhatsApp да ушул файлды колдонот.

НАВИГАЦИЯ:
    Ар бир меню экраны NAV стегине жазылат. "🔙 Артка" басылганда
    стектен акыркысы алынып, мурунку экран кайра көрсөтүлөт.
    Визард (пост жазуу) өзүнүн wizard_back() логикасы менен иштейт.

    WhatsApp'та бул баскыч ар дайым 99 болуп чыгат (adapter аны бөлүп алат).

ТӨЛӨМ:
    Мөөнөтү бүткөн айдоочу «💳 Төлөдүм» басып, чектин скриншотун
    жиберет. Чек админге барат, ал ырастаса — мөөнөт автоматтык кошулат.
"""
import os
import re
from datetime import datetime, timedelta
from core import db, posts, admin, channel
from core.messenger import Keyboard, Button
from core.geo import REGIONS, DISTRICTS, DISTRICT_OBLASTS
from core.texts import (render, WELCOME, GUIDE, DRIVER_WARNING,
                        DRIVER_SAFETY,
                        REQUIRED_REFERRALS, VIP_PRICE,
                        PAYMENT_REQUISITES, VIP_REFERRAL_STEP,
                        GATE_BONUS_DAYS, REFERRAL_BONUS_DAYS,
                        PASSENGER_FIRST_BONUS, PASSENGER_NEXT_BONUS,
                        PAYMENT_AMOUNT, PAYMENT_HOURS, DRIVER_DAILY_LIMIT,
                        PASSENGER_POST_PRICE,
                        VIP_HOURS,
                        FAQ_INTRO, FAQ_POST, FAQ_FREE, FAQ_SEARCH,
                        FAQ_CONTACT, FAQ_SAFETY)

LOGIC_VERSION = "v27-test"
print(f"🧩 core/logic.py жүктөлдү. Версия = {LOGIC_VERSION}")

SESSIONS = {}
_SEARCH_CACHE = {}
PAY_WAIT = {}     # user_id -> "access" | "vip" (чек күтүлүүдө)
NAV = {}          # user_id -> [экран действиелери] — "Артка" үчүн тарых
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

# Тарыхка жазылуучу экрандар (баскыч коддорунун башы)
SCREEN_PREFIXES = (
    "menu:driver", "menu:passenger", "menu:help", "menu:channel", "menu:lang",
    "menu:faq", "faq:", "menu:guide", "menu:safety",
    "d_search", "p_search", "d_my", "p_my", "d_vip",
    "sb:", "sr:", "lo:", "lof:", "lot:", "lr:", "ht:",
)

BACK = Button("🔙 Артка", "wback")


def _back_btn():
    """Ар бир менюга жаңы объект керек — текст которулганда бузулбашы үчүн."""
    return Button("🔙 Артка", "wback")


def _is_screen(action):
    return action.startswith(SCREEN_PREFIXES)


def _nav_push(user_id, action):
    stack = NAV.setdefault(user_id, [])
    # Ошол эле экранды кайра-кайра жазбайбыз
    if not stack or stack[-1] != action:
        stack.append(action)
    if len(stack) > 30:
        del stack[:len(stack) - 30]


def steps_of(role):
    return DRIVER_STEPS if role == "driver" else PASSENGER_STEPS


def referral_link(account_id, platform):
    if platform == "telegram":
        return f"https://t.me/{BOT_USERNAME}?start=ref{account_id}"
    # WhatsApp: чат ачылып, кабар талаасына REF коду даяр турат
    return f"https://wa.me/{WA_BOT_NUMBER}?text=REF{account_id}"


def _share_link(link, lang="ky"):
    """Telegram'дын контакт тандоо терезесин ачуучу шилтеме."""
    text = ("ТАКСИ роБОТ — самый простой способ найти такси!" if lang == "ru"
            else "ТАКСИ роБОТ — Бишкекке такси табуунун эң оңой жолу!")
    return "https://t.me/share/url?url=" + link + "&text=" + text


def _invite_block(account, platform, lang="ky"):
    """Ар бир платформа үчүн ылайыктуу чакыруу блогун кайтарат."""
    link = referral_link(account["account_id"], platform)
    ru = lang == "ru"
    if platform == "telegram":
        share = _share_link(link, lang)
        if ru:
            return (f"👇 <a href=\"{share}\">Отправить друзьям</a>\n\n"
                    f"Или скопируйте ссылку:\n<code>{link}</code>")
        return (f"👇 <a href=\"{share}\">Досторуңузга жиберүү</a>\n\n"
                f"Же шилтемени көчүрүп алыңыз:\n<code>{link}</code>")
    # WhatsApp'та HTML жок — түз шилтеме
    if ru:
        return f"👇 Отправьте друзьям эту ссылку:\n{link}"
    return f"👇 Досторуңузга ушул шилтемени жибериңиз:\n{link}"


def _digits_only(phone):
    """Номерди эл аралык форматка келтирет: '0555112233' -> '996555112233'."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "996" + digits[1:]
    return digits


def contact_links(phone, post_id=None):
    """Каналдагы жарыянын астындагы баскычтар.

    Telegram inline баскычтары http/https/tg шилтемелерин гана кабыл алат,
    ошондуктан 'чалуу' үчүн түз шилтеме жок — экөө тең чатты ачат,
    андан кийин колдонуучу ошол жерден чала алат.

    Үчүнчү баскыч ботту ачып, ошол багыттагы бардык жарыяларды көрсөтөт.
    (Каналдагы текст хештегин басканда Telegram өзүнүн издөөсүн ачат,
     ботко жетпейт — ошондуктан баскыч керек.)

    Төртүнчү баскыч ботту ачып, дароо башкы менюну көрсөтөт.
    """
    d = _digits_only(phone)
    rows = []
    if len(d) >= 9:
        rows.append([
            ("💬 Telegram", f"https://t.me/+{d}"),
            ("📱 WhatsApp — жазуу же чалуу", f"https://wa.me/{d}"),
        ])
    if post_id:
        rows.append([
            ("🔍 Ушул багыттагы бардык жарыялар",
             f"https://t.me/{BOT_USERNAME}?start=ht{post_id}"),
        ])
    # Ботту ачып, башкы менюну көрсөтөт
    rows.append([
        ("🏠 Ботту ачуу", f"https://t.me/{BOT_USERNAME}?start=home"),
    ])
    return rows or None


def contact_lines(phone, lang="ky"):
    """Жарыя карточкасынын астындагы байланыш саптары.

    Бот ичинде (издөө натыйжаларында) баскыч эмес, басылуучу шилтеме
    колдонобуз — Telegram да, WhatsApp да аларды автоматтык таанып,
    басылуучу кылат.
    """
    d = _digits_only(phone)
    if len(d) < 9:
        return f"📞 Байланыш: <code>{phone}</code>"
    # Номерди '+' менен жазабыз — Telegram да, WhatsApp да аны автоматтык
    # таанып, басылуучу кылат: басканда дароо чалуу сунушу чыгат.
    if lang == "ru":
        return (f"📞 Позвонить: +{d}\n"
                f"💬 Telegram: https://t.me/+{d}\n"
                f"📱 WhatsApp (написать или позвонить): https://wa.me/{d}")
    return (f"📞 Чалуу: +{d}\n"
            f"💬 Telegram: https://t.me/+{d}\n"
            f"📱 WhatsApp (жазуу же чалуу): https://wa.me/{d}")


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


def grant_hours(account_id, hours):
    """Аккаунтка N саат кошот (төлөм ырасталганда)."""
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
    new_until = base + timedelta(hours=hours)
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


def L(ky, ru):
    """Эки тилдүү текст. _say аны өзү тандайт — сөз-сөз которулбайт."""
    return ("__L__", ky, ru)


def _say(messenger, msg, account, text, keyboard=None):
    lang = account.get("lang", "ky") if account else "ky"

    # Эки тилдүү текст болсо — даяр вариантты алабыз, котормо катмарын аттайбыз
    if isinstance(text, tuple) and len(text) == 3 and text[0] == "__L__":
        out = text[2] if lang == "ru" else text[1]
        if messenger.platform_name == "whatsapp":
            from core.texts import strip_html
            out = strip_html(out)
    else:
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


# ============ ТӨЛӨМ ============

PAY_KINDS = {
    "access": {
        "ky_title": "💳 <b>Жарыя берүү укугу</b>",
        "ru_title": "💳 <b>Право размещать объявления</b>",
        "amount": PAYMENT_AMOUNT,
        "ky_gives": f"{PAYMENT_HOURS} саат чектөөсүз жарыя",
        "ru_gives": f"{PAYMENT_HOURS} часа объявлений без ограничений",
    },
    "vip": {
        "ky_title": "⭐ <b>VIP айдоочу</b>",
        "ru_title": "⭐ <b>VIP-водитель</b>",
        "amount": VIP_PRICE,
        "ky_gives": f"{VIP_HOURS} саат тизменин эң үстүндө",
        "ru_gives": f"{VIP_HOURS} часа в самом верху списка",
    },
    "post": {
        "ky_title": "💳 <b>Жүргүнчүнүн жарыясы</b>",
        "ru_title": "💳 <b>Объявление пассажира</b>",
        "amount": PASSENGER_POST_PRICE,
        "ky_gives": "1 жарыя",
        "ru_gives": "1 объявление",
    },
}


def pay_btn(kind):
    """Ар бир жерге коюлуучу бирдей төлөм баскычы."""
    return Button("💳 Төлөдүм (чек жиберем)", f"pay:start:{kind}")


def start_payment(messenger, msg, account, kind):
    """«💳 Төлөдүм» басылды — реквизиттерди берип, чек күтөбүз."""
    info = PAY_KINDS.get(kind)
    if not info:
        return _say(messenger, msg, account, "❌ Төлөмдүн түрү белгисиз.", back_kb())

    PAY_WAIT[msg.user_id] = kind
    _say(messenger, msg, account, L(
        f"{info['ky_title']}\n\n"
        f"{PAYMENT_REQUISITES}\n\n"
        f"💰 Сумма: <b>{info['amount']}</b>\n"
        f"🎁 Берет: {info['ky_gives']}\n\n"
        f"📷 Төлөгөндөн кийин чектин скриншотун ушул жерге жибериңиз.\n"
        f"Админ текшергенден кийин автоматтык ачылат.",
        f"{info['ru_title']}\n\n"
        f"{PAYMENT_REQUISITES}\n\n"
        f"💰 Сумма: <b>{info['amount']}</b>\n"
        f"🎁 Даёт: {info['ru_gives']}\n\n"
        f"📷 После оплаты отправьте сюда скриншот чека.\n"
        f"После проверки доступ откроется автоматически."), back_kb())


def receive_receipt(messenger, msg, account, kind):
    """Колдонуучудан келген төлөм чегин админге жиберет."""
    ok = admin.notify_payment(account, msg.photo_id, msg.platform, kind)
    if ok:
        _say(messenger, msg, account, L(
            "✅ Чегиңиз админге жиберилди.\n\n"
            "Текшерилгенден кийин сизге кабар келет.",
            "✅ Ваш чек отправлен администратору.\n\n"
            "После проверки вы получите уведомление."))
    else:
        _say(messenger, msg, account, L(
            "⚠️ Чекти жиберүүдө ката кетти. Кайра аракет кылыңыз.",
            "⚠️ Ошибка при отправке чека. Попробуйте ещё раз."))


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
        _back_btn(),
    ])


def driver_menu_kb():
    return Keyboard.from_flat([
        Button("📝 Пост жазам", "d_types"),
        Button("🔍 Жүргүнчүлөрдү издейм", "d_search"),
        Button("📄 Менин посторум", "d_my"),
        Button("⭐ VIP болуу", "d_vip"),
        _back_btn(),
    ])


def passenger_menu_kb():
    return Keyboard.from_flat([
        Button("📝 Пост жазам", "p_types"),
        Button("🔍 Айдоочуларды издейм", "p_search"),
        Button("📄 Менин посторум", "p_my"),
        _back_btn(),
    ])


def back_kb():
    return Keyboard.from_flat([_back_btn()])


def regions_kb():
    return Keyboard.from_flat(
        [Button(r, f"preg:{i}") for i, r in enumerate(REGION_LIST)]
        + [_back_btn()])


# ============ КИРҮҮ НУКТАСЫ ============

def handle_update(messenger, msg):
    account = db.get_or_create_account(msg.user_id, msg.platform)
    session = SESSIONS.get(msg.user_id)

    # ---- Сүрөт келдиби? (төлөм чеги) ----
    if getattr(msg, "photo_id", None):
        kind = PAY_WAIT.pop(msg.user_id, None)
        if kind:
            return receive_receipt(messenger, msg, account, kind)
        return _say(messenger, msg, account, L(
            "📷 Сүрөт алдым, бирок азыр ал керек эмес.",
            "📷 Фото получено, но сейчас оно не требуется."))

    text = (msg.text or "").strip()
    if text == "/admin" and admin.handle_command(messenger, msg, account, _say):
        return
    if text.startswith("/start") or text in ("старт", "start"):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        PAY_WAIT.pop(msg.user_id, None)
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith("ref"):
            try:
                inviter_id = int(parts[1][3:])
                register_referral(messenger, account, inviter_id)
                account = db.get_account(account["account_id"])
            except ValueError:
                pass
        elif len(parts) > 1 and parts[1].startswith("ht"):
            # Каналдагы «🔍 Ушул багыттагы бардык жарыялар» баскычы
            try:
                return hashtag_search(messenger, msg, account, int(parts[1][2:]))
            except ValueError:
                pass
        elif len(parts) > 1 and parts[1].startswith("tag_"):
            frm, _, to = parts[1][4:].partition("_")
            if frm and to:
                return _show_hashtag_results(messenger, msg, account, f"#{frm}_{to}", frm, to)

        return _say(messenger, msg, account, WELCOME, main_menu_kb(msg.platform))

    # WhatsApp referral: колдонуучу "REF12" деген текст жиберет
    if re.fullmatch(r"(?i)ref\d+", text):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
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
            NAV.pop(msg.user_id, None)
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

    _say(messenger, msg, account, L(
        "Түшүнбөй калдым 🙈 /start деп жазып көрүңүз.",
        "Не понял 🙈 Попробуйте написать /start."))


# ============ МЕНЮ ============

def _menu_button(messenger, msg, account):
    """Навигация тарыхын жүргүзүп, экранды көрсөтөт."""
    a = msg.button_action

    if a == "menu:home":
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        PAY_WAIT.pop(msg.user_id, None)
        return _say(messenger, msg, account, WELCOME, main_menu_kb(msg.platform))

    if a == "wback":
        PAY_WAIT.pop(msg.user_id, None)
        stack = NAV.get(msg.user_id, [])
        if stack:
            stack.pop()                      # учурдагы экранды алып салабыз
        prev = stack[-1] if stack else None
        if not prev:
            NAV.pop(msg.user_id, None)
            return _say(messenger, msg, account, WELCOME,
                        main_menu_kb(msg.platform))
        return _dispatch(messenger, msg, account, prev)

    if _is_screen(a):
        _nav_push(msg.user_id, a)

    return _dispatch(messenger, msg, account, a)


def _dispatch(messenger, msg, account, a):
    """Баскычтын кодун тиешелүү экранга багыттайт."""
    if a == "menu:driver":
        return driver_entry(messenger, msg, account)
    if a == "menu:passenger":
        free = account.get("free_posts", 0) or 0
        if free <= 0:
            invite = _invite_block(account, msg.platform, "ky")
            invite_ru = _invite_block(account, msg.platform, "ru")
            return _say(messenger, msg, account, L(
                 f"💡 Акысыз жарыяңыз бүттү, бирок улантсаңыз болот!\n\n"
                 f"💳 Баасы: {PASSENGER_POST_PRICE}\n{PAYMENT_REQUISITES}\n\n"
                 f"🎁 Же 1 дос чакырсаңыз — дагы {PASSENGER_NEXT_BONUS} жарыя:\n\n"
                 f"{invite}",
                 f"💡 Бесплатные объявления закончились, но вы можете продолжить!\n\n"
                 f"💳 Стоимость: {PASSENGER_POST_PRICE}\n{PAYMENT_REQUISITES}\n\n"
                 f"🎁 Или пригласите 1 друга — ещё {PASSENGER_NEXT_BONUS} объявл.:\n\n"
                 f"{invite_ru}"),
                 Keyboard.from_flat([pay_btn("post"), _back_btn()]))
        return _say(messenger, msg, account, "Тандаңыз:", passenger_menu_kb())
    if a.startswith("pay:start:"):
        return start_payment(messenger, msg, account, a.split(":")[2])
    if a == "menu:help":
        return help_menu(messenger, msg, account)
    if a == "menu:guide":
        return _say(messenger, msg, account, GUIDE, back_kb())
    if a == "menu:safety":
        return _say(messenger, msg, account, DRIVER_SAFETY, back_kb())
    if a == "menu:faq":
        return faq_menu(messenger, msg, account)
    if a.startswith("faq:"):
        return faq_section(messenger, msg, account, a.split(":")[1])
    if a == "menu:channel":
        # Telegram'да URL баскычы — басканда дароо каналга өтөт.
        # WhatsApp'та мындай баскыч жок, ошондуктан шилтеме текст менен.
        if msg.platform == "telegram":
            kb = Keyboard.from_flat([
                Button("📢 Каналга өтүү", "noop", CHANNEL_LINK),
                _back_btn(),
            ])
            return _say(messenger, msg, account, L(
                "📢 <b>Биздин канал</b>\n\n"
                "Айдоочулардын жарыялары каналга чыгып турат — "
                "жазылып койсоңуз, эң жаңыларын биринчи болуп көрөсүз.",
                "📢 <b>Наш канал</b>\n\n"
                "Объявления водителей публикуются в канале — подпишитесь, "
                "и вы первыми увидите самые свежие."), kb)
        return _say(messenger, msg, account,
            f"📢 <b>Биздин канал</b>\n\n"
            f"Айдоочулардын жарыялары каналга чыгып турат — "
            f"жазылып койсоңуз, эң жаңыларын биринчи болуп көрөсүз.\n\n"
            f"{CHANNEL_LINK}", back_kb())
    if a == "menu:lang":
        return _say(messenger, msg, account,
                    "🌐 Тилди тандаңыз / Выберите язык:", lang_kb())
    if a.startswith("setlang:"):
        new_lang = a.split(":")[1]
        db.update_account(account["account_id"], lang=new_lang)
        account = db.get_account(account["account_id"])
        NAV.pop(msg.user_id, None)
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
    if a.startswith("lo:"):
        return local_oblast_from(messenger, msg, account, a)
    if a.startswith("lof:"):
        return local_oblast_to(messenger, msg, account, a)
    if a.startswith("lot:"):
        return local_oblast_results(messenger, msg, account, a)
    if a.startswith("lr:"):
        return local_results(messenger, msg, account, a)
    if a.startswith("ht:"):
        return hashtag_search(messenger, msg, account, int(a.split(":")[1]))

    _say(messenger, msg, account, "Бул баскыч азырынча иштелип чыккан жок.")


def hashtag_search(messenger, msg, account, post_id):
    """Жарыянын багыты боюнча издейт (хештег баскычы басылганда).

    Telegram'да билдирүүдөгү хештегди басканда, ал ботко жиберилбейт —
    Telegram өзүнүн издөөсүн ачат. Ошондуктан баскыч колдонобуз.
    """
    p = posts.get_post(post_id)
    if not p:
        return _say(messenger, msg, account, "❌ Жарыя табылган жок.", back_kb())
    tag = hashtag(p.get("from_city"), p.get("to_city"))
    _show_hashtag_results(messenger, msg, account, tag,
                          p.get("from_city"), p.get("to_city"))


def help_menu(messenger, msg, account):
    """🆘 Жардам — эки бөлүм: нускама жана суроо-жооптор."""
    kb = Keyboard.from_flat([
        Button("📖 Нускама", "menu:guide"),
        Button("❓ Көп берилүүчү суроолорго жооп", "menu:faq"),
        Button("🛡 Айдоочунун коопсуздугу", "menu:safety"),
        _back_btn(),
    ])
    _say(messenger, msg, account, L(
         "🆘 <b>Жардам</b>\n\nЭмне керек экенин тандаңыз:",
         "🆘 <b>Помощь</b>\n\nВыберите, что вам нужно:"), kb)


def faq_menu(messenger, msg, account):
    """Көп берилүүчү суроолордун бөлүмдөрү."""
    kb = Keyboard.from_flat([
        Button("📝 Жарыя жөнүндө", "faq:post"),
        Button("🎁 Акысыз мүмкүнчүлүк", "faq:free"),
        Button("🔍 Издөө", "faq:search"),
        Button("📞 Байланыш", "faq:contact"),
        Button("🛡 Коопсуздук", "faq:safety"),
        _back_btn(),
    ])
    _say(messenger, msg, account, FAQ_INTRO, kb)


FAQ_SECTIONS = {
    "post": FAQ_POST,
    "free": FAQ_FREE,
    "search": FAQ_SEARCH,
    "contact": FAQ_CONTACT,
    "safety": FAQ_SAFETY,
}


def faq_section(messenger, msg, account, key):
    """Тандалган бөлүмдүн суроо-жооптору."""
    text = FAQ_SECTIONS.get(key)
    if not text:
        return _say(messenger, msg, account, "❌ Бул бөлүм табылган жок.", back_kb())
    _say(messenger, msg, account, text, back_kb())


def driver_entry(messenger, msg, account):
    invite = _invite_block(account, msg.platform, "ky")
    invite_ru = _invite_block(account, msg.platform, "ru")

    # 1-этап: гейт ачыла элек
    if (account["ref_count"] or 0) < REQUIRED_REFERRALS:
        return _say(messenger, msg, account, L(
            f"🚫 Жарыя берүү үчүн {REQUIRED_REFERRALS} дос чакырышыңыз керек.\n"
            f"Учурдагы прогресс: {account['ref_count'] or 0}/{REQUIRED_REFERRALS}\n\n"
            f"🎁 Ачылганда {GATE_BONUS_DAYS} күн акысыз жарыя бересиз!\n\n"
            f"💳 Же {PAYMENT_AMOUNT} төлөп, {PAYMENT_HOURS} саатка дароо ачсаңыз болот.\n\n"
            f"{invite}",
            f"🚫 Чтобы оставить объявление, пригласите {REQUIRED_REFERRALS} друзей.\n"
            f"Текущий прогресс: {account['ref_count'] or 0}/{REQUIRED_REFERRALS}\n\n"
            f"🎁 После открытия вы получите {GATE_BONUS_DAYS} дней бесплатно!\n\n"
            f"💳 Или оплатите {PAYMENT_AMOUNT} — {PAYMENT_HOURS} часа сразу.\n\n"
            f"{invite_ru}"),
            Keyboard.from_flat([pay_btn("access"), _back_btn()]))

    # 2-этап: гейт ачык, бирок мөөнөт бүткөн → төлөм же дос чакыруу
    if not has_access(account):
        return _say(messenger, msg, account, L(
            f"⏳ Акысыз мөөнөтүңүз бүттү.\n\n"
            f"Улантуу үчүн:\n"
            f"🎁 {REQUIRED_REFERRALS} дос чакырыңыз — {REFERRAL_BONUS_DAYS} күн акысыз\n"
            f"💳 Же {PAYMENT_AMOUNT} төлөңүз — {PAYMENT_HOURS} саат\n\n"
            f"{PAYMENT_REQUISITES}\n\n"
            f"{invite}",
            f"⏳ Бесплатный период закончился.\n\n"
            f"Чтобы продолжить:\n"
            f"🎁 Пригласите {REQUIRED_REFERRALS} друзей — {REFERRAL_BONUS_DAYS} дней бесплатно\n"
            f"💳 Или оплатите {PAYMENT_AMOUNT} — {PAYMENT_HOURS} часа\n\n"
            f"{PAYMENT_REQUISITES}\n\n"
            f"{invite_ru}"),
            Keyboard.from_flat([pay_btn("access"), _back_btn()]))

    # 3-этап: баары ачык
    left = days_left(account)
    quota, _free_at = daily_limit_left(account["account_id"], "driver")
    q = max(0, quota) if quota is not None else None
    ky_q = f"📝 Бүгүн дагы {q} жарыя бере аласыз\n" if q is not None else ""
    ru_q = f"📝 Сегодня можно опубликовать ещё {q} объявл.\n" if q is not None else ""
    _say(messenger, msg, account, L(
         f"✅ Акысыз мөөнөтүңүз: дагы {left} күн\n{ky_q}\nТандаңыз:",
         f"✅ Ваш бесплатный период: ещё {left} дн.\n{ru_q}\nВыберите:"),
         driver_menu_kb())


def show_vip(messenger, msg, account):
    invite = _invite_block(account, msg.platform, "ky")
    invite_ru = _invite_block(account, msg.platform, "ru")
    _say(messenger, msg, account, L(
        f"⭐ <b>VIP айдоочу</b>\n\n"
        f"VIP болсоңуз, жарыяңыз издөө тизмесинин эң үстүнөн чыгат!\n\n"
        f"💳 Баасы: {VIP_PRICE}\n{PAYMENT_REQUISITES}\n\n"
        f"🎁 Же {VIP_REFERRAL_STEP} дос чакырсаңыз — акысыз:\n\n"
        f"{invite}",
        f"⭐ <b>VIP-водитель</b>\n\n"
        f"С VIP ваше объявление показывается в самом верху списка!\n\n"
        f"💳 Стоимость: {VIP_PRICE}\n{PAYMENT_REQUISITES}\n\n"
        f"🎁 Или пригласите {VIP_REFERRAL_STEP} друзей — бесплатно:\n\n"
        f"{invite_ru}"),
        Keyboard.from_flat([pay_btn("vip"), _back_btn()]))


# ============ ЖАРЫЯ БЕРҮҮ ============

def daily_limit_left(account_id, role):
    """24 саат ичинде дагы канча жарыя бере алат. (айдоочу үчүн гана)

    DRIVER_DAILY_LIMIT = 0 болсо — чектөө жок, (None, None) кайтарат.
    """
    if role != "driver" or not DRIVER_DAILY_LIMIT:
        return None, None
    times = posts.recent_posts_times(account_id, "driver", 24)
    left = DRIVER_DAILY_LIMIT - len(times)
    if left > 0 or not times:
        return left, None
    # Эң эски жарыя 24 сааттан өткөндө орун бошойт
    free_at = times[0] + timedelta(hours=24)
    return left, free_at


def post_types(messenger, msg, account, role):
    # Айдоочуга суткалык чектөө: спамдын алдын алат
    left, free_at = daily_limit_left(account["account_id"], role)
    if left is not None and left <= 0:
        when = free_at.strftime("%H:%M") if free_at else ""
        return _say(messenger, msg, account, L(
            f"🚫 Бир суткада эң көп <b>{DRIVER_DAILY_LIMIT} жарыя</b> бере аласыз.\n\n"
            f"⏰ Кийинки жарыяны саат <b>{when}</b> чамасында бере аласыз.\n\n"
            f"<i>Бул чектөө каналды жана издөө тизмесин таза кармоо үчүн "
            f"коюлган — ар бир айдоочунун жарыясы көрүнүктүү болсун.</i>",
            f"🚫 В сутки можно опубликовать не более <b>{DRIVER_DAILY_LIMIT} объявлений</b>.\n\n"
            f"⏰ Следующее объявление вы сможете дать примерно в <b>{when}</b>.\n\n"
            f"<i>Это ограничение нужно, чтобы канал и список поиска оставались "
            f"чистыми — и объявление каждого водителя было заметным.</i>"),
            back_kb())

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
        _back_btn(),
    ])
    ky_head = ru_head = ""
    if left is not None:
        n = max(0, left - 1)
        ky_head = (f"📝 Бул жарыядан кийин бүгүн дагы <b>{n} жарыя</b> бере аласыз.\n"
                   f"<i>(суткалык чектөө: {DRIVER_DAILY_LIMIT})</i>\n\n")
        ru_head = (f"📝 После этого объявления сегодня останется <b>{n}</b>.\n"
                   f"<i>(лимит в сутки: {DRIVER_DAILY_LIMIT})</i>\n\n")
    _say(messenger, msg, account, L(
        ky_head + "Кайсы багытта жарыя бересиз?",
        ru_head + "В каком направлении вы даёте объявление?"), kb)


def ask_route(messenger, msg, account, st):
    if st["data"].get("mode") == "local":
        st["step"] = "loreg"
        kb = Keyboard.from_flat(
            [Button(o, f"loreg:{i}") for i, o in enumerate(DISTRICT_OBLASTS)]
            + [_back_btn()])
        _say(messenger, msg, account, "🗺 Кайсы облустан чыгасыз?", kb)
    else:
        st["step"] = "dir"
        kb = Keyboard.from_flat([
            Button("🚕 Бишкекке барам", "route:to_bishkek"),
            Button("🚕 Бишкектен кайтам", "route:from_bishkek"),
            _back_btn(),
        ])
        _say(messenger, msg, account, L("Багытты тандаңыз:", "Выберите направление:"), kb)


# ============ ВИЗАРД КАДАМДАРЫ ============

def day_hours():
    """Мезгилге жараша күндүзгү сааттардын тизмеси.

    Жүргүнчүлөр негизинен күндүз жолго чыгат, ошондуктан түнкү сааттарды
    тизмеге салбайбыз — керек болсо колдонуучу кол менен жазат.

        Апрель–сентябрь : 06:00 – 21:00
        Октябрь–март    : 07:00 – 19:00
    """
    month = datetime.now().month
    if 4 <= month <= 9:
        start, end = 6, 21
    else:
        start, end = 7, 19
    return [f"{h:02d}:00" for h in range(start, end + 1)]


MONTHS_KY = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def date_label(offset):
    """«Бүгүн · 17-август» / «Эртең · 18-август» — чаташпашы үчүн."""
    d = datetime.now() + timedelta(days=offset)
    name = "Бүгүн" if offset == 0 else "Эртең"
    return f"{name} · {d.day}-{MONTHS_KY[d.month - 1]}"


def ask_step(messenger, msg, account, st, step):
    st["step"] = step
    role = st["role"]

    if step == "date":
        kb = Keyboard(rows=[[Button(date_label(0), "dq:0"),
                             Button(date_label(1), "dq:1")],
                            [_back_btn()]])
        return _say(messenger, msg, account, "📅 Качан жолго чыгасыз?", kb)

    if step == "time":
        hours = day_hours()
        rows = [[Button(h, f"tm:{h}") for h in hours[k:k + 4]]
                for k in range(0, len(hours), 4)]
        rows.append([_back_btn()])
        return _say(messenger, msg, account,
            "⏰ Саат канчада жолго чыгасыз?\n\n"
            "<i>Тизмеде жок убакыт болсо — жазып жибериңиз "
            "(мис. 05:30 же 22:00).</i>",
            Keyboard(rows=rows))

    if step == "price":
        kb = Keyboard.from_flat([Button("🤝 Келишим баада", "pr:deal"),
                                 _back_btn()])
        return _say(messenger, msg, account,
            "💰 Жол киреси канча?\n\n"
            "<i>Сумманы жазыңыз (мис. 1200), же төмөнкү баскычты басыңыз.</i>", kb)

    if step == "seats":
        rows = [[Button(str(i), f"seat:{i}") for i in range(1, 5)],
                [Button(str(i), f"seat:{i}") for i in range(5, 8)],
                [_back_btn()]]
        return _say(messenger, msg, account, "👥 Канча бош орун бар?",
                    Keyboard(rows=rows))

    if step == "people":
        rows = [[Button(str(i), f"ppl:{i}") for i in range(1, 5)],
                [_back_btn()]]
        return _say(messenger, msg, account,
            "👥 Канча киши жолго чыгасыңар?\n\n"
            "<i>Салон болсо — Салон деп жазып жибериңиз.</i>", Keyboard(rows=rows))

    if step == "baggage":
        kb = Keyboard.from_flat([Button("🚫 Жок", "bg:no"), _back_btn()])
        return _say(messenger, msg, account,
            "🎒 Багажыңыз барбы?\n\n"
            "<i>Жок болсо — төмөнкү баскычты басыңыз.\n"
            "Бар болсо — жазып жибериңиз (мис. 2 чемодан).</i>", kb)

    if step == "phone":
        ph = account.get("verified_phone")
        if ph:
            kb = Keyboard.from_flat([Button(f"📱 {ph}", "usephone"), _back_btn()])
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
        _say(messenger, msg, account, DRIVER_WARNING)
        kb = Keyboard.from_flat([Button("✅ Түшүндүм, жарыялаймын", "confirm"),
                                 _back_btn()])
        _say(messenger, msg, account, L(
            "🚦 <b>Коопсуздук эрежелерин окуп алыңыз!</b>\n\n"
            "Башкы менюдагы «🆘 Жардам» баскычын басып, андагы "
            "«🛡 Айдоочунун коопсуздугу» бөлүмүн окуп чыгыңыз.\n\n"
            "<i>Ал жерде жолдогу коопсуздуктун 6 негизги эрежеси жазылган — "
            "өз өмүрүңүз жана жүргүнчүлөрдүн өмүрү үчүн маанилүү.</i>",
            "🚦 <b>Обязательно прочитайте правила безопасности!</b>\n\n"
            "В главном меню нажмите «🆘 Помощь» и откройте раздел "
            "«🛡 Безопасность водителя».\n\n"
            "<i>Там изложены 6 главных правил безопасности в пути — "
            "это важно для вашей жизни и жизни пассажиров.</i>"), kb)
    else:
        save(messenger, msg, account, st)


def hashtag(frm, to):
    def short(s):
        s = re.sub(r"\s*(облусу|шаары|району|\(Раззаков\))\s*", "", s or "")
        return re.sub(r"\s+", "_", s.strip())
    return f"#{short(frm)}_{short(to)}"


def channel_text(d, role, tag=None):
    """Каналга чыгуучу жарыянын тексти.

    Хештег КОЛДОНУЛБАЙТ: Telegram аны басканда «Публичные посты»
    издөөсүн ачат, ал эми жарыялар жеке каналда — эч нерсе табылбайт.
    Анын ордуна жарыянын астындагы «🔍 Ушул багыттагы бардык жарыялар»
    баскычы иштейт — ал ботту ачып, эки платформадагы жарыяны тең берет.
    """
    if role == "driver":
        return (
            f"🚗 <b>АЙДООЧУ</b>\n"
            f"🚖 <b>{d.get('from_city')} ➡️ {d.get('to_city')}</b>\n"
            f"🧍 Аты: {d.get('name')}\n"
            f"🚘 Унаа: {d.get('car')}\n"
            f"📅 {d.get('date_text')} · ⏰ {d.get('time_text')}\n"
            f"👥 Бош орун: {d.get('seats')}\n"
            f"💰 Баасы: {d.get('price')}\n"
            f"📝 {d.get('comment')}\n"
            f"📞 Чалуу: +{_digits_only(d.get('phone'))}\n"
            f"<i>👆 Чалуу үчүн номерди басып көчүрүңүз</i>"
            )
    return ""


def _publish(messenger, text, links):
    """Каналга чыгарат — платформадан көз каранды эмес.

    core/channel.py түз Telegram API'ге кайрылат, ошондуктан WhatsApp'тан
    жазылган айдоочунун жарыясы да ошол эле каналга барат.
    """
    return channel.publish(text, links)


def save(messenger, msg, account, st):
    d = st["data"]
    role = st["role"]
    post_id = posts.create_post(account["account_id"], role, d)
    SESSIONS.pop(msg.user_id, None)

    _say(messenger, msg, account, L(
         "✅ Жарыя чыкты! Платформада 24 саат турат, андан кийин автоматтык өчүрүлөт.",
         "✅ Объявление опубликовано! Оно будет висеть 24 часа, затем удалится автоматически."))

    # Колдонуучу өз жарыясын дароо көрсүн
    fresh = posts.get_post(post_id)
    if fresh:
        _say(messenger, msg, account, L(
             "👇 <b>Сиздин жарыяңыз:</b>\n\n"
             + post_card(fresh, "ky") + "\n\n" + contact_lines(fresh["phone"], "ky"),
             "👇 <b>Ваше объявление:</b>\n\n"
             + post_card(fresh, "ru") + "\n\n" + contact_lines(fresh["phone"], "ru")))

    if role == "driver":
        # Каналга чыгарабыз — платформа өзү билет, core билбейт.
        # Астына байланыш баскычтарын кошобуз.
        msg_id = _publish(messenger, channel_text(d, role),
                          contact_links(d.get("phone"), post_id))
        if msg_id:
            posts.set_channel_msg(post_id, msg_id)
            _say(messenger, msg, account, L(
                 "📢 Жарыяңыз каналга да чыкты — жүргүнчүлөр аны ошол жерден көрө алат.",
                 "📢 Объявление также опубликовано в канале — пассажиры увидят его там."))
    else:
        _say(messenger, msg, account, L(
             "🔒 Жүргүнчүнүн жарыясы каналга чыкпайт — аны айдоочулар платформада гана көрөт.",
             "🔒 Объявление пассажира в канал не публикуется — его видят водители в боте."))

    # Хештегди БАСКЫЧ кылабыз — Telegram'да текст хештег ботко жетпейт
    other_ky = "айдоочуларды" if role == "passenger" else "жүргүнчүлөрдү"
    other_ru = "водителей" if role == "passenger" else "пассажиров"
    route = f"{d.get('from_city')} ➡️ {d.get('to_city')}"
    _say(messenger, msg, account, L(
         f"💡 <b>{route}</b>\n\nУшул багыттагы {other_ky} көрүү үчүн "
         f"төмөнкү баскычты басыңыз:",
         f"💡 <b>{route}</b>\n\nЧтобы увидеть {other_ru} по этому направлению, "
         f"нажмите кнопку:"),
         Keyboard.from_flat([Button(f"🔍 {route}", f"ht:{post_id}"), _back_btn()]))

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
            + [_back_btn()])
        return _say(messenger, msg, account,
                    f"📍 <b>{region}</b>\nШаар/район тандаңыз:", kb)

    if a.startswith("pcity:"):
        region = d.get("_region")
        city = REGIONS[region][int(a.split(":")[1])]
        if d.get("direction") == "to_bishkek":
            d["from_city"] = city
        else:
            d["to_city"] = city
        _say(messenger, msg, account, L(
             f"✅ Маршрут: {d.get('from_city')} ➡️ {d.get('to_city')}",
             f"✅ Маршрут: {d.get('from_city')} ➡️ {d.get('to_city')}"))
        return ask_step(messenger, msg, account, st, steps_of(st["role"])[0])

    if a.startswith("loreg:"):
        oblast = DISTRICT_OBLASTS[int(a.split(":")[1])]
        d["_oblast"] = oblast
        st["step"] = "lofrom"
        kb = Keyboard.from_flat(
            [Button(c, f"lofrom:{i}") for i, c in enumerate(DISTRICTS[oblast])]
            + [_back_btn()])
        return _say(messenger, msg, account,
                    f"📍 <b>{oblast}</b>\nКайсы райондон/шаардан чыгасыз?", kb)

    if a.startswith("lofrom:"):
        oblast = d["_oblast"]
        d["from_city"] = DISTRICTS[oblast][int(a.split(":")[1])]
        st["step"] = "lotoreg"
        kb = Keyboard.from_flat(
            [Button(o, f"lotoreg:{i}") for i, o in enumerate(DISTRICT_OBLASTS)]
            + [_back_btn()])
        return _say(messenger, msg, account,
            f"📍 Чыгуу: <b>{d['from_city']}</b>\n🗺 Кайсы облуска барасыз?", kb)

    if a.startswith("lotoreg:"):
        oblast = DISTRICT_OBLASTS[int(a.split(":")[1])]
        d["_to_oblast"] = oblast
        st["step"] = "loto"
        btns = [Button(c, f"loto:{i}") for i, c in enumerate(DISTRICTS[oblast])
                if c != d.get("from_city")]
        btns.append(_back_btn())
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
        d["date_text"] = date_label(int(a.split(":")[1]))
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

    # Маршрут тандоо кадамдарынан артка
    if step in ("pcity",):
        st["step"] = "preg"
        return _say(messenger, msg, account, "Облусту тандаңыз:", regions_kb())
    if step in ("preg", "dir", "loreg"):
        st["step"] = "mode"
        kb = Keyboard.from_flat([
            Button("Облустардын район/шаарларынан Бишкекке жана кайтуу",
                   "mode:bishkek"),
            Button("Район/шаар аралык", "mode:local"),
            _back_btn(),
        ])
        return _say(messenger, msg, account, "Кайсы багытта жарыя бересиз?", kb)
    if step == "lofrom":
        return ask_route(messenger, msg, account, st)
    if step in ("lotoreg", "loto"):
        st["step"] = "lofrom"
        oblast = st["data"].get("_oblast")
        if oblast:
            kb = Keyboard.from_flat(
                [Button(c, f"lofrom:{i}") for i, c in enumerate(DISTRICTS[oblast])]
                + [_back_btn()])
            return _say(messenger, msg, account,
                        f"📍 <b>{oblast}</b>\nКайсы райондон/шаардан чыгасыз?", kb)

    # Визарддын эң башы — менюга кайтабыз
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

def post_card(p, lang="ky"):
    """Жарыя карточкасы. lang='ru' болсо — орусча белгилер."""
    ru = lang == "ru"
    vip = " ⭐" if p.get("is_vip") else ""
    if p["role"] == "driver":
        role_tag = "🚗 <b>ВОДИТЕЛЬ</b>" if ru else "🚗 <b>АЙДООЧУ</b>"
    else:
        role_tag = "🧳 <b>ПАССАЖИР</b>" if ru else "🧳 <b>ЖҮРГҮНЧҮ</b>"
    lines = [role_tag,
             f"<b>{p['from_city']} ➡️ {p['to_city']}</b>{vip}",
             (f"🧍 Имя: {p['name']}" if ru else f"🧍 Аты: {p['name']}")]
    if p["role"] == "driver":
        lines += ([f"🚘 Авто: {p['car']}", f"👥 Свободно мест: {p['seats']}",
                   f"💰 Цена: {p['price']}"] if ru else
                  [f"🚘 Унаа: {p['car']}", f"👥 Бош орун: {p['seats']}",
                   f"💰 Баасы: {p['price']}"])
    else:
        lines += ([f"👥 Кол-во людей: {p['people_count']}", f"🎒 Багаж: {p['baggage']}"] if ru else
                  [f"👥 Адам саны: {p['people_count']}", f"🎒 Багаж: {p['baggage']}"])
    lines += [f"📅 {p['date_text']} · ⏰ {p['time_text']}"]
    if p.get("comment"):
        lines.append(f"📝 {p['comment']}")
    return "\n".join(lines)


def show_my_posts(messenger, msg, account, role):
    rows = posts.my_posts(account["account_id"], role)
    if not rows:
        return _say(messenger, msg, account, L(
                    "❌ Сиздин учурда активдүү жарыяңыз жок.",
                    "❌ У вас сейчас нет активных объявлений."), back_kb())
    _say(messenger, msg, account, L("📄 <b>Сиздин активдүү посттор</b>",
                                    "📄 <b>Ваши активные объявления</b>"))
    for p in rows:
        kb = Keyboard.from_flat([Button("❌ Өчүрүү", f"del:{p['id']}")])
        _say(messenger, msg, account,
             L(post_card(p, "ky"), post_card(p, "ru")), kb)
    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


def delete_post(messenger, msg, account, post_id):
    """Жарыяны өчүрөт — базадан да, каналдан да."""
    p = posts.get_post(post_id)
    ok = posts.deactivate_post(post_id, account["account_id"])
    if ok and p and p.get("channel_msg_id"):
        channel.delete(p["channel_msg_id"])
    _say(messenger, msg, account,
         L("🗑 Жарыя өчүрүлдү." if ok else "❌ Жарыя табылган жок.",
           "🗑 Объявление удалено." if ok else "❌ Объявление не найдено."), back_kb())


# ============ ИЗДӨӨ ============

def search_menu(messenger, msg, account, target_role):
    kb = Keyboard.from_flat([
        Button("➡️ Бишкекке бараткандар", f"sb:to:{target_role}"),
        Button("⬅️ Бишкектен кайткандар", f"sb:from:{target_role}"),
        Button("🗺 Район аралык", f"lo:{target_role}"),
        _back_btn(),
    ])
    _say(messenger, msg, account, L("Багытты тандаңыз:", "Выберите направление:"), kb)


# ---- Район аралык издөө: облус → район → маршрут ----

def local_oblast_from(messenger, msg, account, action):
    """1-кадам: кайсы облустан чыккандарды издейт."""
    role = action.split(":")[1]

    # Ар бир облустан канча жарыя бар экенин эсептейбиз
    rows = [r for r in posts.local_route_counts() if r["role"] == role]
    per_city = {}
    for r in rows:
        per_city[r["from_city"]] = per_city.get(r["from_city"], 0) + r["n"]

    btns = []
    for i, oblast in enumerate(DISTRICT_OBLASTS):
        n = sum(per_city.get(c, 0) for c in DISTRICTS[oblast])
        btns.append(Button(f"{oblast} · {n} жарыя", f"lof:{role}:{i}"))
    btns.append(_back_btn())

    _say(messenger, msg, account, L(
         "🗺 <b>Район аралык</b>\n\nКайсы облустан чыккандарды издейсиз?",
         "🗺 <b>Между районами</b>\n\nИз какой области ищете?"),
         Keyboard.from_flat(btns))


def local_oblast_to(messenger, msg, account, action):
    """2-кадам: ошол облустун кайсы районунан."""
    _, role, idx = action.split(":")
    oblast = DISTRICT_OBLASTS[int(idx)]

    rows = [r for r in posts.local_route_counts() if r["role"] == role]
    per_city = {}
    for r in rows:
        per_city[r["from_city"]] = per_city.get(r["from_city"], 0) + r["n"]

    btns = []
    for i, city in enumerate(DISTRICTS[oblast]):
        n = per_city.get(city, 0)
        btns.append(Button(f"{city} · {n} жарыя", f"lot:{role}:{idx}:{i}"))
    btns.append(_back_btn())

    _say(messenger, msg, account, L(
         f"📍 <b>{oblast}</b>\n\nКайсы райондон/шаардан чыккандарды издейсиз?",
         f"📍 <b>{oblast}</b>\n\nИз какого района/города ищете?"),
         Keyboard.from_flat(btns))


def local_oblast_results(messenger, msg, account, action):
    """3-кадам: ошол райондон чыккан маршруттар."""
    _, role, i_ob, i_city = action.split(":")
    oblast = DISTRICT_OBLASTS[int(i_ob)]
    city = DISTRICTS[oblast][int(i_city)]

    rows = [r for r in posts.local_route_counts()
            if r["role"] == role and r["from_city"] == city]

    if not rows:
        return _say(messenger, msg, account, L(
                    f"📍 <b>{city}</b>\n\n❌ Бул жерден чыккан жарыя азырынча жок.",
                    f"📍 <b>{city}</b>\n\n❌ Отсюда пока нет объявлений."), back_kb())

    btns = []
    pairs = []
    for i, r in enumerate(rows):
        btns.append(Button(f"{r['from_city']} ➡️ {r['to_city']} · {r['n']} жарыя",
                           f"lr:{role}:{i}"))
        pairs.append((r["from_city"], r["to_city"]))
    _SEARCH_CACHE[msg.user_id] = pairs
    btns.append(_back_btn())

    _say(messenger, msg, account, L(
         f"📍 <b>{city}</b> — кайда барат?",
         f"📍 <b>{city}</b> — куда едут?"), Keyboard.from_flat(btns))


def local_results(messenger, msg, account, action):
    """Тандалган маршруттун жарыялары."""
    _, role, idx = action.split(":")
    pairs = _SEARCH_CACHE.get(msg.user_id, [])
    if int(idx) >= len(pairs):
        return _say(messenger, msg, account,
                    L("❌ Кайра издеп көрүңүз.", "❌ Попробуйте поиск заново."), back_kb())
    frm, to = pairs[int(idx)]
    rows = posts.search_posts(role, from_city=frm, to_city=to)
    _say(messenger, msg, account, f"📋 <b>{frm} ➡️ {to}</b>")
    if not rows:
        return _say(messenger, msg, account,
                    L("❌ Бул багыт боюнча жарыя табылган жок.",
                      "❌ По этому направлению объявлений не найдено."), back_kb())
    for p in rows:
        _say(messenger, msg, account, L(
             post_card(p, "ky") + "\n\n" + contact_lines(p["phone"], "ky"),
             post_card(p, "ru") + "\n\n" + contact_lines(p["phone"], "ru")))
    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


def search_bishkek(messenger, msg, account, action):
    """Бишкек багыты — облус/шаар деңгээлинде тизме."""
    _, direction, role = action.split(":")
    to_bishkek = direction == "to"

    # Ар бир шаар/райондун жарыя санын алып, облус боюнча чогултабыз
    rows = posts.route_counts(role, to_bishkek)
    counts = {r["k"]: r["n"] for r in rows}

    btns = []
    for i, region in enumerate(REGION_LIST):
        n = sum(counts.get(c, 0) for c in REGIONS[region])
        if to_bishkek:
            label = f"{region} ➡️ Бишкек · {n} жарыя"
        else:
            label = f"Бишкек ➡️ {region} · {n} жарыя"
        btns.append(Button(label, f"sr:{role}:{direction}:{i}"))

    btns.append(_back_btn())
    title = L("➡️ <b>Бишкекке бараткандар</b>" if to_bishkek
              else "⬅️ <b>Бишкектен кайткандар</b>",
              "➡️ <b>Едут в Бишкек</b>" if to_bishkek
              else "⬅️ <b>Возвращаются из Бишкека</b>")
    _say(messenger, msg, account, title, Keyboard.from_flat(btns))


def show_results(messenger, msg, account, action):
    """Тандалган облустун бардык шаар/райондорунун жарыялары."""
    _, role, direction, idx = action.split(":")
    i = int(idx)
    if i >= len(REGION_LIST):
        return _say(messenger, msg, account,
                    L("❌ Кайра издеп көрүңүз.", "❌ Попробуйте поиск заново."), back_kb())

    region = REGION_LIST[i]
    to_bishkek = direction == "to"

    rows = []
    for city in REGIONS[region]:
        if to_bishkek:
            rows += posts.search_posts(role, from_city=city, to_city="Бишкек")
        else:
            rows += posts.search_posts(role, from_city="Бишкек", to_city=city)

    # VIP'тер башында, андан кийин жаңылары
    rows.sort(key=lambda p: (not p.get("is_vip"), ), reverse=False)

    header = (f"📋 <b>{region} ➡️ Бишкек</b>" if to_bishkek
              else f"📋 <b>Бишкек ➡️ {region}</b>")
    _say(messenger, msg, account, header)

    if not rows:
        return _say(messenger, msg, account,
                    L("❌ Бул багыт боюнча жарыя азырынча жок.",
                      "❌ По этому направлению пока нет объявлений."), back_kb())

    for p in rows:
        _say(messenger, msg, account, L(
             post_card(p, "ky") + "\n\n" + contact_lines(p["phone"], "ky"),
             post_card(p, "ru") + "\n\n" + contact_lines(p["phone"], "ru")))
    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


def _hashtag(messenger, msg, account, text):
    """#Ош_Бишкек деп КОЛ МЕНЕН жазылса — ошол багыттагы жарыялар."""
    parts = text[1:].split("_")
    if len(parts) < 2:
        return _say(messenger, msg, account, "❓ Бул хештегди тааныган жокмун.")
    frm, to = parts[0], "_".join(parts[1:])
    _show_hashtag_results(messenger, msg, account, text, frm, to)


def _show_hashtag_results(messenger, msg, account, tag, frm, to):
    """Багыт боюнча жарыяларды ролго бөлүп көрсөтөт."""
    def short(s):
        s = re.sub(r"\s*(облусу|шаары|району|\(Раззаков\))\s*", "", s or "")
        return s.strip()

    rows = posts.search_by_hashtag(short(frm), short(to))
    # '#' белгисин колдонбойбуз: Telegram аны шилтеме кылып, басканда
    # ботко эмес, өзүнүн издөөсүнө алып барат.
    route = f"{short(frm)} ➡️ {short(to)}"
    _say(messenger, msg, account, L(f"🔎 Издөө: <b>{route}</b>",
                                    f"🔎 Поиск: <b>{route}</b>"))
    if not rows:
        return _say(messenger, msg, account, L(
                    "❌ Бул багытта азырынча жарыя жок.",
                    "❌ По этому направлению пока нет объявлений."), back_kb())

    drivers = [p for p in rows if p["role"] == "driver"]
    passengers = [p for p in rows if p["role"] == "passenger"]

    if drivers:
        _say(messenger, msg, account,
             L(f"🚗 <b>Айдоочулар</b> ({len(drivers)})",
               f"🚗 <b>Водители</b> ({len(drivers)})"))
        for p in drivers:
            _say(messenger, msg, account,
                 post_card(p) + "\n\n" + contact_lines(p["phone"]))

    if passengers:
        _say(messenger, msg, account,
             L(f"🧳 <b>Жүргүнчүлөр</b> ({len(passengers)})",
               f"🧳 <b>Пассажиры</b> ({len(passengers)})"))
        for p in passengers:
            _say(messenger, msg, account,
                 post_card(p) + "\n\n" + contact_lines(p["phone"]))

    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


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



