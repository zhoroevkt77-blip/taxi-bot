# -*- coding: utf-8 -*-
"""
core/admin.py
=============
Админ панель — платформадан көз каранды эмес.
Админ ким экени ADMIN_ACCOUNT өзгөрмөсү менен аныкталат
(Railway'де ADMIN_ACCOUNT = аккаунттун id'си).
"""

import os
import time

from core import db, posts
from core.messenger import Keyboard, Button

ADMIN_ACCOUNT = int(os.environ.get("ADMIN_ACCOUNT", "0"))

# Админ эмнени күтүп жатканын эстеп турат
ADMIN_STATE = {}   # platform_id -> "broadcast" | "ban" | "unban" | "setref"


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
    ])


def handle_command(messenger, msg, account, say):
    """/admin буйругу."""
    if not is_admin(account):
        return False
    ADMIN_STATE.pop(msg.user_id, None)
    say(messenger, msg, account, "🎛 <b>Админ панель</b>", admin_kb())
    return True


def handle_button(messenger, msg, account, say):
    """adm: менен башталган баскычтар. True кайтарса — иштелди."""
    a = msg.button_action
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
            "Мисалы: <code>1 3</code> — 1-аккаунтка 3 referral коёт.")

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
        say(messenger, msg, account,
            f"✅ {acc_id}-аккаунттун referral саны {count} болду.")
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

    
