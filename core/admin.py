# -*- coding: utf-8 -*-
"""
core/admin.py
=============
Админ панель — платформадан көз каранды эмес.
Админ ким экени ADMIN_ACCOUNT өзгөрмөсү менен аныкталат
(Railway'де ADMIN_ACCOUNT = аккаунттун id'си).

ТӨЛӨМ ЫРАСТОО:
    Колдонуучу «💳 Төлөдүм» басып, чектин скриншотун жиберет.
    Чек админдин Telegram'ына [✅ Ырастоо] [❌ Четке кагуу] баскычтары
    менен барат. Админ ырастаса — мөөнөт автоматтык кошулат.
"""

import os
import time
import requests

from core import db, posts
from core.messenger import Keyboard, Button

ADMIN_ACCOUNT = int(os.environ.get("ADMIN_ACCOUNT", "0"))

# Чек админдин Telegram'ына барат — WhatsApp колдонуучусунуку да
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# WhatsApp колдонуучусуна жооп жиберүү үчүн
GREEN_ID = os.environ.get("GREEN_API_ID")
GREEN_TOKEN = os.environ.get("GREEN_API_TOKEN")
_GREEN_URL = os.environ.get(
    "GREEN_API_URL",
    f"https://{str(GREEN_ID)[:4]}.api.greenapi.com" if GREEN_ID else "")

# Админ эмнени күтүп жатканын эстеп турат
ADMIN_STATE = {}   # platform_id -> "broadcast" | "ban" | "unban" | "setref" | "grant"


def is_admin(account):
    return ADMIN_ACCOUNT and account["account_id"] == ADMIN_ACCOUNT


def admin_kb():
    return Keyboard.from_flat([
        Button("📊 Статистика", "adm:stats"),
        Button("👥 Акыркы колдонуучулар", "adm:users"),
        Button("📢 Жалпы билдирүү", "adm:broadcast"),
        Button("🚫 Бөгөттөө", "adm:ban"),
        Button("✅ Бөгөттөн чыгаруу", "adm:unban"),
        Button("🧪 Referral коюу (тест)", "adm:setref"),
        Button("🎁 Мөөнөт кошуу (тест)", "adm:grant"),
        Button("⚡ Мага толук уруксат", "adm:me"),
    ])


def handle_command(messenger, msg, account, say):
    """/admin буйругу."""
    if not is_admin(account):
        return False
    ADMIN_STATE.pop(msg.user_id, None)
    say(messenger, msg, account, "🎛 <b>Админ панель</b>", admin_kb())
    return True


def _grant_days(account_id, days):
    """logic.grant_days'ти чакырат (тегерек импорттон качуу үчүн ичинде)."""
    from core import logic
    return logic.grant_days(account_id, days)


# ============ ТӨЛӨМ ЫРАСТОО ============

def _admin_chat_id():
    """Админдин Telegram chat_id'си — чек ошол жакка барат."""
    pid = db.platform_id_of(ADMIN_ACCOUNT)
    if pid and pid.startswith("tg:"):
        return pid.split(":", 1)[1]
    return None


def _wa_send(pid, text):
    """WhatsApp колдонуучусуна түз Green API аркылуу кабар."""
    if not (GREEN_ID and GREEN_TOKEN):
        return
    raw = pid.split(":", 1)[1]
    url = f"{_GREEN_URL}/waInstance{GREEN_ID}/sendMessage/{GREEN_TOKEN}"
    try:
        requests.post(url, json={"chatId": f"{raw}@c.us", "message": text},
                      timeout=20)
    except Exception as e:
        print("WA кабар катасы:", e)


def _tell_user(messenger, account_id, text):
    """Колдонуучуга өз платформасы аркылуу кабар жиберет.

    Админ Telegram'да отурат, ал эми колдонуучу WhatsApp'та болушу
    мүмкүн — ошондуктан messenger'ди эмес, платформаны карайбыз.
    """
    pid = db.platform_id_of(account_id)
    if not pid:
        return
    if pid.startswith("wa:"):
        _wa_send(pid, text)
    else:
        try:
            messenger.send_text(pid, text)
        except Exception as e:
            print("Колдонуучуга кабар катасы:", e)


KIND_LABEL = {
    "access": "Жарыя берүү укугу",
    "vip": "VIP айдоочу",
}


def notify_payment(account, photo_ref, platform, kind="access"):
    """Төлөм чегин админге жиберет. True кайтарса — жиберилди."""
    chat_id = _admin_chat_id()
    if not (chat_id and BOT_TOKEN and photo_ref):
        print("⚠️ Чек жиберилген жок: админдин Telegram'ы табылган жок.")
        return False

    acc_id = account["account_id"]
    name = account.get("first_name") or "—"
    phone = account.get("verified_phone") or "—"
    label = KIND_LABEL.get(kind, kind)
    caption = (f"💳 <b>Төлөм чеги</b>\n\n"
               f"🎯 Эмне үчүн: <b>{label}</b>\n"
               f"👤 Аккаунт: <code>{acc_id}</code>\n"
               f"🧍 Аты: {name}\n"
               f"📞 {phone}\n"
               f"🌐 Платформа: {platform}")

    kb = {"inline_keyboard": [[
        {"text": "✅ Ырастоо", "callback_data": f"pay:ok:{kind}:{acc_id}"},
        {"text": "❌ Четке кагуу", "callback_data": f"pay:no:{kind}:{acc_id}"},
    ]]}

    try:
        r = requests.post(f"{TG_API}/sendPhoto", json={
            "chat_id": chat_id,
            "photo": photo_ref,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": kb,
        }, timeout=30)
        data = r.json()
        if not data.get("ok"):
            print("Чек жиберүү катасы:", data)
        return bool(data.get("ok"))
    except Exception as e:
        print("Чек жиберүү катасы:", e)
        return False


def _payment_decision(messenger, msg, account, say, a):
    """Админ чекти ырастады же четке какты."""
    parts = a.split(":")
    if len(parts) != 4:
        return True
    _, decision, kind, raw_id = parts
    try:
        acc_id = int(raw_id)
    except ValueError:
        return True
    if not db.get_account(acc_id):
        say(messenger, msg, account, "❌ Мындай аккаунт жок.")
        return True

    label = KIND_LABEL.get(kind, kind)

    if decision != "ok":
        say(messenger, msg, account,
            f"❌ {acc_id}-аккаунттун чеги четке кагылды ({label}).")
        _tell_user(messenger, acc_id,
                   "❌ Төлөмүңүз ырасталган жок.\n\n"
                   "Чекти кайра жиберип көрүңүз же админге кайрылыңыз.")
        return True

    from core import logic

    if kind == "vip":
        from core.texts import VIP_HOURS
        ok = _set_vip(acc_id, VIP_HOURS)
        if ok:
            say(messenger, msg, account,
                f"⭐ {acc_id}-аккаунт {VIP_HOURS} саатка VIP болду.")
            _tell_user(messenger, acc_id,
                       f"⭐ Төлөмүңүз ырасталды!\n\n"
                       f"{VIP_HOURS} саат бою жарыяңыз тизменин эң үстүндө турат.")
        else:
            say(messenger, msg, account,
                f"⚠️ VIP коюлган жок — базада VIP талаасы жок окшойт.\n"
                f"Кол менен коюп коюңуз.")
        return True

    # kind == "access" (жана башка белгисиз түрлөр)
    from core.texts import PAYMENT_HOURS
    logic.grant_hours(acc_id, PAYMENT_HOURS)
    # Гейт жабык болсо — төлөм аны да ачат
    acc = db.get_account(acc_id)
    from core.texts import REQUIRED_REFERRALS
    if (acc.get("ref_count") or 0) < REQUIRED_REFERRALS:
        db.update_account(acc_id, ref_count=REQUIRED_REFERRALS)
    say(messenger, msg, account,
        f"✅ {acc_id}-аккаунтка {PAYMENT_HOURS} саат кошулду.")
    _tell_user(messenger, acc_id,
               f"✅ Төлөмүңүз ырасталды!\n\n"
               f"{PAYMENT_HOURS} саат бою жарыя бере аласыз. Ак жол!")
    return True


def _set_vip(account_id, hours):
    """Аккаунтка VIP мөөнөтүн коёт (accounts.vip_until).

    Мөөнөт бүтө элек болсо — үстүнө кошот.
    """
    from datetime import datetime, timedelta
    acc = db.get_account(account_id)
    base = datetime.now()
    cur = acc.get("vip_until") if acc else None
    if cur:
        try:
            prev = datetime.fromisoformat(str(cur))
            if prev > base:
                base = prev
        except (ValueError, TypeError):
            pass
    until = (base + timedelta(hours=hours)).isoformat()
    try:
        db.update_account(account_id, vip_until=until)
        return True
    except Exception as e:
        print("VIP коюу катасы:", e)
        return False


# ============ БАСКЫЧТАР ============

def handle_button(messenger, msg, account, say):
    """adm: менен башталган баскычтар. True кайтарса — иштелди."""
    a = msg.button_action

    # Төлөм чечими — админдин гана колунан келет
    if (a.startswith("pay:ok:") or a.startswith("pay:no:")) and is_admin(account):
        return _payment_decision(messenger, msg, account, say, a)

    if not a.startswith("adm:") or not is_admin(account):
        return False

    action = a.split(":")[1]

    if action == "stats":
        total = db.count_accounts()
        banned = db.count_banned()
        active = len(posts.search_posts("driver")) + len(posts.search_posts("passenger"))
        say(messenger, msg, account,
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Колдонуучулар: {total}\n"
            f"🚫 Бөгөттөлгөндөр: {banned}\n"
            f"📄 Активдүү жарыялар: {active}")

    elif action == "users":
        rows = db.recent_accounts(10)
        lines = ["👥 <b>Акыркы колдонуучулар</b>\n"]
        for u in rows:
            ban = " 🚫" if u.get("banned") else ""
            name = u.get("first_name") or "—"
            phone = u.get("verified_phone") or "номерсиз"
            lines.append(f"<code>{u['account_id']}</code> — {name} · {phone}{ban}")
        say(messenger, msg, account, "\n".join(lines))

    elif action == "broadcast":
        ADMIN_STATE[msg.user_id] = "broadcast"
        say(messenger, msg, account,
            "📢 <b>Жалпы билдирүү</b>\n\nБардык колдонуучуларга жиберилчү текстти жазыңыз:")

    elif action == "ban":
        ADMIN_STATE[msg.user_id] = "ban"
        say(messenger, msg, account, "🚫 Бөгөттөөчү колдонуучунун ID'син жазыңыз:")

    elif action == "unban":
        ADMIN_STATE[msg.user_id] = "unban"
        say(messenger, msg, account, "✅ Бөгөттөн чыгаруучу колдонуучунун ID'син жазыңыз:")

    elif action == "setref":
        ADMIN_STATE[msg.user_id] = "setref"
        say(messenger, msg, account,
            "🧪 <b>Referral коюу</b>\n\n"
            "Форматы: <code>account_id саны</code>\n"
            "Мисалы: <code>1 3</code> — 1-аккаунтка 3 referral коёт.\n\n"
            "<i>Эскертүү: бул 30 күн мөөнөттү да кошуп берет, "
            "ошондо айдоочу жарыя бере алат.</i>")

    elif action == "grant":
        ADMIN_STATE[msg.user_id] = "grant"
        say(messenger, msg, account,
            "🎁 <b>Мөөнөт кошуу</b>\n\n"
            "Форматы: <code>account_id күн</code>\n"
            "Мисалы: <code>1 30</code> — 1-аккаунтка 30 күн кошот.")

    elif action == "me":
        # Өзүнө дароо толук уруксат — тестирлөө үчүн эң тез жол
        acc_id = account["account_id"]
        db.update_account(acc_id, ref_count=99)
        _grant_days(acc_id, 365)
        say(messenger, msg, account,
            f"⚡ <b>Даяр!</b>\n\n"
            f"Referral: 99\n"
            f"Мөөнөт: 365 күн\n\n"
            f"Эми «🚗 Айдоочумун» бөлүмүнөн жарыя бере аласыз.")

    return True


def handle_text(messenger, msg, account, say):
    """Админ бир нерсе күтүп жатканда келген текст."""
    state = ADMIN_STATE.get(msg.user_id)
    if not state or not is_admin(account):
        return False

    ADMIN_STATE.pop(msg.user_id, None)
    text = (msg.text or "").strip()

    if state == "broadcast":
        ids = db.all_platform_ids()
        sent, failed = 0, 0
        for pid in ids:
            try:
                messenger.send_text(pid, text)
                sent += 1
            except Exception:
                failed += 1
            time.sleep(0.05)
        say(messenger, msg, account,
            f"✅ <b>Жиберилди</b>\n\n{sent} колдонуучуга жеткирилди.\n"
            f"❌ Жеткен жок: {failed}")
        return True

    if state == "setref":
        parts = text.split()
        if len(parts) != 2:
            say(messenger, msg, account, "⚠️ Формат: account_id саны (мис. 1 3)")
            return True
        try:
            acc_id, count = int(parts[0]), int(parts[1])
        except ValueError:
            say(messenger, msg, account, "⚠️ Эки сан жазыңыз (мис. 1 3)")
            return True
        if not db.get_account(acc_id):
            say(messenger, msg, account, "❌ Мындай аккаунт жок.")
            return True
        db.update_account(acc_id, ref_count=count)
        # Гейт эки шарттуу: referral саны ЖАНА мөөнөт. Экөөнү тең берип коёбуз.
        _grant_days(acc_id, 30)
        say(messenger, msg, account,
            f"✅ {acc_id}-аккаунттун referral саны {count} болду.\n"
            f"🎁 Ошондой эле 30 күн мөөнөт кошулду.")
        return True

    if state == "grant":
        parts = text.split()
        if len(parts) != 2:
            say(messenger, msg, account, "⚠️ Формат: account_id күн (мис. 1 30)")
            return True
        try:
            acc_id, days = int(parts[0]), int(parts[1])
        except ValueError:
            say(messenger, msg, account, "⚠️ Эки сан жазыңыз (мис. 1 30)")
            return True
        if not db.get_account(acc_id):
            say(messenger, msg, account, "❌ Мындай аккаунт жок.")
            return True
        _grant_days(acc_id, days)
        say(messenger, msg, account,
            f"🎁 {acc_id}-аккаунтка {days} күн кошулду.")
        return True

    try:
        target = int(text)
    except ValueError:
        say(messenger, msg, account, "⚠️ Туура эмес ID.")
        return True

    if state == "ban":
        ok = db.set_banned(target, True)
        say(messenger, msg, account,
            f"🚫 {target} бөгөттөлдү." if ok else "❌ Колдонуучу табылган жок.")
        pid = db.platform_id_of(target)
        if pid:
            try:
                messenger.send_text(pid, "🚫 Сиз бул платформада бөгөттөлдүңүз.")
            except Exception:
                pass
    else:
        ok = db.set_banned(target, False)
        say(messenger, msg, account,
            f"✅ {target} бөгөттөн чыгарылды." if ok else "❌ Колдонуучу табылган жок.")
        pid = db.platform_id_of(target)
        if pid:
            try:
                messenger.send_text(pid,
                    "✅ Бөгөттөн чыгарылдыңыз. Платформаны кайра колдонсоңуз болот.")
            except Exception:
                pass

    return True

