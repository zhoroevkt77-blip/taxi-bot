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

САЙТ:
    Башкы менюдагы «🌐 Сайт» баскычы жарыяларды браузерден көрсөтөт.
    Дареги texts.py'деги SITE_URL'ден алынат.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from core.ttldict import TTLDict
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
                        FAQ_INTRO, FAQ_HOWTO, FAQ_POST, FAQ_FREE,
                        FAQ_SEARCH, FAQ_PAY, FAQ_CONTACT, FAQ_SAFETY,
                        FAQ_TROUBLE, FAQ_RULES, FAQ_PRIVACY)

# Сайттын дареги жана «🌐 Сайт» бөлүмүнүн тексти.
# texts.py эски версия болуп калса да бот кулабашы үчүн — коргоо менен.
try:
    from core.texts import SITE_URL, SITE_INFO
except ImportError:
    SITE_URL = os.environ.get(
        "SITE_URL", "https://taxi-bot-production-fdb5.up.railway.app")
    SITE_INFO = None

SITE_SHORT = SITE_URL.replace("https://", "").replace("http://", "").rstrip("/")

LOGIC_VERSION = "v100-time"
print(f"🧩 core/logic/ жүктөлдү. Версия = {LOGIC_VERSION}")

SESSIONS = TTLDict(ttl=2 * 3600)  # 2 саат тийилбесе өчөт
_SEARCH_CACHE = TTLDict(ttl=2 * 3600)
PAY_WAIT = TTLDict(ttl=24 * 3600)     # user_id -> "access" | "vip" (чек күтүлүүдө)
NAV = TTLDict(ttl=2 * 3600)          # user_id -> [экран действиелери] — "Артка" үчүн тарых
BOT_USERNAME = "taxirobot_bot"
WA_BOT_NUMBER = os.environ.get("WA_BOT_NUMBER", "996227155603")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/taxirobotbot")

# WhatsApp'тагы «издөө» кабарынын башталышы. Каналдагы баскыч ушул
# сөздөр менен башталган текстти даярдайт, бот аны кайра таанып алат.
SEARCH_PREFIX = "Издөө:"

# Сайттагы «Жарыя берүү» бетинен WhatsApp ботко түз кирүү үчүн.
# Баскыч кабар талаасына ушул текстти даярдап коёт, колдонуучу
# жөнөтүү басат — бот аны таанып, дароо визардды баштайт.
POST_PREFIX = "Жарыя берем:"

# Сайттын «Кабинет» бетинен WhatsApp ботко түз кирүү — төлөм бөлүмүнө.
PAY_TEXT = "Төлөм төлөймүн"

# Сайттын «Кабинет» бетинен балансты көрүү үчүн
BALANCE_TEXT = "Менин балансым"

# Сайттын «Кабинет» бетинен өз жарыяларын көрүү үчүн
MYPOSTS_TEXT = "Менин жарыяларым"

# Башкы менюнун кыска аталышы. Толук WELCOME тексти /start деп КОЛ МЕНЕН
# жазылганда гана чыгат — ал биринчи таанышуу үчүн. Каналдан ботко
# өткөндө, тил алмашканда же менюга кайтканда ушул кыска сап чыгат,
# антпесе узун текст ар жолу кайталанып жүдөтөт.
MENU_TITLE = ("__L__",
              "🚕 <b>ТАКСИ роБОТ</b>\n\nТандаңыз:",
              "🚕 <b>ТАКСИ роБОТ</b>\n\nВыберите:")

REGION_LIST = list(REGIONS.keys())

DRIVER_STEPS = ["name", "car", "date", "time", "seats", "price",
                "comment", "photo", "phone"]
PASSENGER_STEPS = ["name", "date", "time", "people", "baggage", "comment", "phone"]

STEP_FIELD = {
    "name": "name", "car": "car", "date": "date_text", "time": "time_text",
    "seats": "seats", "price": "price", "people": "people_count",
    "baggage": "baggage", "comment": "comment", "phone": "phone",
}

# Тарыхка жазылуучу экрандар (баскыч коддорунун башы)
SCREEN_PREFIXES = (
    "menu:driver", "menu:passenger", "menu:help", "menu:channel", "menu:lang",
    "menu:site", "menu:more",
    "menu:faq", "faq:", "menu:guide", "menu:safety",
    "d_search", "p_search", "p_search_bot", "d_my", "p_my", "d_vip",
    "d_pay", "p_pay", "pay_entry", "menu:balance",
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
    return f"{SITE_URL}/wa?text=REF{account_id}"


def _share_link(link, lang="ky"):
    """Telegram'дын контакт тандоо терезесин ачуучу шилтеме."""
    text = ("ТАКСИ роБОТ — самый простой способ найти такси!" if lang == "ru"
            else "ТАКСИ роБОТ — Бишкекке такси табуунун эң оңой жолу!")
    return "https://t.me/share/url?url=" + link + "&text=" + text


def _invite_block(account, platform, lang="ky"):
    """Чакыруу блогу — эки платформада тең бирдей көрүнөт.

    Бот Telegram'да да, WhatsApp'та да иштегендиктен, колдонуучу
    досуна кайсы мессенджер ыңгайлуу болсо, ошону жибере алат.
    """
    acc_id = account["account_id"]
    tg_link = referral_link(acc_id, "telegram")
    wa_link = referral_link(acc_id, "whatsapp")

    # МААНИЛҮҮ: контакт ачуучу шилтемелер (wa.me/?text=…) бул жерге
    # ЖАЗЫЛБАЙТ. Алардын ичине бүт кабар кодолуп кетет да, экранда
    # жүздөгөн белгилүү «%D0%A1%D0%B0…» болуп созулуп калат.
    # Telegram'да алар БАСКЫЧ болуп чыгат (_share_buttons), ал эми
    # WhatsApp'та колдонуучу кабарды кармап туруп «Переслать» кылат.
    if lang == "ru":
        if platform == "telegram":
            tail = ("<i>Нажмите кнопку ниже — откроется список "
                    "контактов.</i>")
        else:
            tail = ("📤 <b>Как отправить другу:</b>\n"
                    "Нажмите <b>кнопку пересылки</b> справа от этого "
                    "сообщения — откроется список контактов, выберите друга.\n"
                    "<i>Если значка нет: задержите палец на "
                    "сообщении и выберите «Переслать».</i>")
        return (f"🔗 <b>Ваша ссылка:</b>\n\n"
                f"📱 WhatsApp:\n{wa_link}\n\n"
                f"💬 Telegram:\n{tg_link}\n\n"
                f"{tail}\n"
                f"<i>Друг должен войти именно по вашей ссылке — тогда "
                f"бонус засчитается.</i>")

    if platform == "telegram":
        tail = ("<i>Төмөнкү баскычты бассаңыз, контакттарыңыз "
                "ачылат.</i>")
    else:
        tail = ("📤 <b>Досуңузга кантип жиберем?</b>\n"
                "Ушул кабардын оң жагындагы <b>кош жебе</b> белгисин "
                "басыңыз — контакттарыңыз ачылат, досуңузду тандайсыз.\n"
                "<i>Белги көрүнбөсө: кабарды манжаңыз менен кармап "
                "туруп «Переслать» тандаңыз.</i>")
    return (f"🔗 <b>Сиздин шилтемеңиз:</b>\n\n"
            f"📱 WhatsApp:\n{wa_link}\n\n"
            f"💬 Telegram:\n{tg_link}\n\n"
            f"{tail}\n"
            f"<i>Досуңуз так сиздин шилтемеңиз аркылуу кириши керек — "
            f"ошондо бонус эсептелет.</i>")


def _wa_share_link(account, lang="ky"):
    """WhatsApp'тын контакт тандоо терезесин ачуучу шилтеме."""
    from urllib.parse import quote
    link = referral_link(account["account_id"], "whatsapp")
    text = ("ТАКСИ роБОТ — самый простой способ найти такси!" if lang == "ru"
            else "ТАКСИ роБОТ — Бишкекке такси табуунун эң оңой жолу!")
    return "https://wa.me/?text=" + quote(f"{text}\n{link}")


def _invite_text(account, lang="ky"):
    """Досуна жиберилчү даяр кабар — шилтемеси менен кошо."""
    acc_id = account["account_id"]
    tg = referral_link(acc_id, "telegram")
    wa = referral_link(acc_id, "whatsapp")
    if lang == "ru":
        return (f"«ТАКСИ роБОТ» — водители и пассажиры по всему "
                f"Кыргызстану.\n{tg}")
    return (f"«ТАКСИ роБОТ» — Кыргызстан боюнча айдоочулар менен "
            f"жүргүнчүлөр.\n{tg}")


def _share_urls(account, lang="ky"):
    """Контакт тандоочу терезени ачуучу шилтемелер.

    МААНИЛҮҮ: кадимки чакыруу шилтемеси (wa.me/НОМЕР) басканда
    БОТТУН өзү ачылат — ал досуңуз баса турган шилтеме. Ал эми
    ушулар контакттарыңызды ачат: кимге жиберерди тандайсыз.

        WhatsApp: wa.me/?text=...      (номерсиз!)
        Telegram: t.me/share/url?...
    """
    from urllib.parse import quote
    acc_id = account["account_id"]
    tg_link = referral_link(acc_id, "telegram")
    wa_link = referral_link(acc_id, "whatsapp")

    if lang == "ru":
        head = "«ТАКСИ роБОТ» — водители и пассажиры по всему Кыргызстану."
    else:
        head = "«ТАКСИ роБОТ» — Кыргызстан боюнча айдоочулар менен жүргүнчүлөр."

    # WhatsApp досторуна WhatsApp шилтемеси, Telegram досторуна —
    # Telegram шилтемеси кетет. Ошондо дос өз колдонмосунда калат.
    wa_share = f"https://wa.me/?text={quote(head + chr(10) + wa_link)}"
    tg_share = (f"https://t.me/share/url?url={quote(tg_link)}"
                f"&text={quote(head)}")
    return wa_share, tg_share


def _share_buttons(account, platform, lang="ky"):
    """«Досторго жиберүү» баскычтары.

    Telegram'да URL баскычы болот — басканда контакттар ачылат.
    WhatsApp'та URL баскычы жок, ошондуктан ал жакта шилтемелер
    тексттин ичинде берилет (_invite_block'ту караңыз).
    """
    if platform != "telegram":
        return []
    wa_share, tg_share = _share_urls(account, lang)
    ru = (lang == "ru")
    return [
        Button("📤 Telegram'дагы досторго" if not ru
               else "📤 Друзьям в Telegram", "noop", tg_share),
        Button("📤 WhatsApp'тагы досторго" if not ru
               else "📤 Друзьям в WhatsApp", "noop", wa_share),
    ]


def _digits_only(phone):
    """Номерди эл аралык форматка келтирет: '0555112233' -> '996555112233'.

    Кыргызстандын номери эмес болсо, сандары кандай болсо ошондой
    кайтарат — бул жерде текшербейбиз. Текшерүү normalize_phone()
    аркылуу жарыя жазылып жатканда болот.
    """
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "996" + digits[1:]
    return digits


def mask_phone(phone):
    """«0777773125» → «+996 777 *** 125». Каналда толук номер чыкпайт."""
    d = _digits_only(phone)
    if len(d) == 12 and d.startswith("996"):
        return f"+996 {d[3:6]} *** {d[-3:]}"
    return ("+" + d[:4] + " *** " + d[-2:]) if len(d) >= 6 else ""


def contact_links(phone, post_id=None, from_city=None, to_city=None):
    """Каналдагы жарыянын астындагы баскычтар.

    1-катар — жарыя ээси менен байланыш:
        «💬 Telegram» жана «📱 WhatsApp» — экөө тең анын чатын ачат,
        андан кийин колдонуучу ошол жерден жаза же чала алат.

    2-катар — ошол багыттагы БАРДЫК жарыяларды издөө. Эки баскыч:
        «🔍 Telegram Ботто издөө»  — Telegram боту ачылып, дароо чыгарат.
        «🔍 WhatsApp Ботто издөө» — WhatsApp боту ачылып, кабар талаасына
        «Издөө: Манас району ➡️ Бишкек» деген даяр текст турат.
        Колдонуучу жөн эле жөнөтүү басат — бот дароо жарыяларды чыгарат.

        WhatsApp'та кабарды автоматтык жөнөтүү мүмкүн эмес (платформа
        уруксат бербейт), ошондуктан текстти адам түшүнгөндөй кылабыз —
        код эмес, кадимки суроо болуп көрүнөт.

    3-катар — ботту ачып, дароо башкы менюну көрсөтөт.
    """
    from urllib.parse import quote

    d = _digits_only(phone)
    rows = []
    if len(d) >= 9:
        # Номер шилтемеде ачык турбасын (скрейперлер окуйт) — сайтка
        # жиберебиз: ал жакта номер баскыч басылганда гана чыгат.
        # Кириллица кодолот — Telegram баскычы туура эмес URL'ди кабыл албайт.
        url = (f"{SITE_URL}/route?from={quote(from_city)}&to={quote(to_city)}"
               if from_city and to_city else SITE_URL)
        rows.append([("📞 Байланышуу / Связаться", url)])
    if post_id:
        # Багыт белгилүү болсо — адамча суроо, болбосо кыска код
        if from_city and to_city:
            wa_text = f"{SEARCH_PREFIX} {from_city} ➡️ {to_city}"
        else:
            wa_text = f"HT{post_id}"
        # Эки издөө баскычы БИР КАТАРДА — пост кыскараак көрүнөт.
        # Аттары кыска: жанындагы 🔍 белгиси эмне кыларын билдирет.
        rows.append([
            ("✈️ Маршрут издөө",
             f"https://t.me/{BOT_USERNAME}?start=ht{post_id}"),
            ("🟢 Маршрут издөө",
             f"{SITE_URL}/wa?text={quote(wa_text)}"),
        ])
    # Ботту ачуу — эки платформа үчүн өзүнчө. Колдонуучу кайсынысын
    # колдонсо, ошону басат: экөө тең ошол эле ботко, ошол эле базага
    # алып барат.
    # tg:// шилтемеси браузерди аттап, түз Telegram колдонмосун ачат.
    # (Telegram inline баскычтары http, https жана tg:// кабыл алат.)
    # Ботту ачуу — экөө тең бир катарда
    rows.append([
        ("✈️ Ботко өтүү",
         f"tg://resolve?domain={BOT_USERNAME}&start=home"),
        ("🟢 Ботко өтүү",
         f"{SITE_URL}/wa?text={quote('/start')}"),
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
                f"📱 WhatsApp: https://wa.me/{d}")
    return (f"📞 Чалуу: +{d}\n"
            f"💬 Telegram: https://t.me/+{d}\n"
            f"📱 WhatsApp: https://wa.me/{d}")


def _now():
    """Ички салыштыруулар үчүн (сервер жана база UTC'де)."""
    return datetime.now()


# Кыргызстан — UTC+6, жайкы убакыт жок. Railway сервери UTC'де.
# Колдонуучуга КӨРҮНГӨН даталар/сааттар үчүн гана колдонулат.
BISHKEK_OFFSET = timedelta(hours=6)


def _local_now():
    return datetime.now(timezone.utc).replace(tzinfo=None) + BISHKEK_OFFSET


def _to_local(dt):
    """Базадагы UTC убакытты Бишкек убактысына которот."""
    return dt + BISHKEK_OFFSET


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


def _say(messenger, msg, account, text, keyboard=None, hint=False):
    """Кабар жиберет.

    hint=True болсо, WhatsApp'та кабардын аягына «0 — Башкы меню»
    эскертүүсү кошулат. Ал колдонуучудан ЖООП КҮТҮЛГӨН жерде гана
    керек: визард суроолорунда жана тизме бүткөндөн кийин. Маалымат
    берүүчү кабарларга (жарыя карточкасы, «жарыя чыкты» ж.б.) кошулбайт —
    болбосо бир экранда ондогон жолу кайталанып, жүдөтөт.
    """
    lang = account.get("lang", "ky") if account else "ky"

    # Эки тилдүү текст болсо — даяр вариантты алабыз, котормо катмарын аттайбыз
    if isinstance(text, tuple) and len(text) == 3 and text[0] == "__L__":
        out = text[2] if lang == "ru" else text[1]
        if messenger.platform_name == "whatsapp":
            from core.texts import strip_html
            out = strip_html(out)
    else:
        out = render(text, lang, messenger.platform_name)

    # WhatsApp кабардын биринчи шилтемесине превью тартат. Telegram
    # шилтемеси турса, «Join group chat on Telegram» деген пайдасыз
    # карточка чыгат. WhatsApp колдонуучусу Telegram'га өтпөйт да —
    # ошондуктан ал сапты бул жерде алып салабыз.
    if messenger.platform_name == "whatsapp" and "t.me/+" in out:
        out = "\n".join(ln for ln in out.split("\n")
                        if "t.me/+" not in ln)
    # WhatsApp адаптери ар бир кабардын аягына «0 — Башкы меню»
    # эскертүүсүн өзү кошот. Клавиатурада да ошондой баскыч турса,
    # эки жолу кайталанып чыгат — ошондуктан бул жерде алып салабыз.
    if keyboard and messenger.platform_name == "whatsapp":
        rows = [[b for b in row if b.action != "menu:home"]
                for row in keyboard.rows]
        keyboard.rows = [r for r in rows if r]
        if not keyboard.rows:
            keyboard = None

    if keyboard:
        if lang != "ky":
            for row in keyboard.rows:
                for b in row:
                    b.text = render(b.text, lang, messenger.platform_name)
        messenger.send_buttons(msg.user_id, out, keyboard)
    elif hint and hasattr(messenger, "send_prompt"):
        # Жооп күтүлгөн кабар — платформа «0 — башкы меню» эскертүүсүн кошот
        messenger.send_prompt(msg.user_id, out)
    else:
        messenger.send_text(msg.user_id, out)


