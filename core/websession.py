# -*- coding: utf-8 -*-
"""
core/websession.py
===================
Сайтка кирүү: браузерди аккаунтка байлоо.

Агым:
  1. Сайтта «Кирүү» басылат      → start() токен кайтарат (l_ТОКЕН)
  2. Адам Telegram/WhatsApp ботко ошол кодду жөнөтөт
  3. Бот номерин тастыктап, attach() менен аккаунтту байлайт
  4. Сайт status() аркылуу көрөт да, браузерге cookie жазат

Токен 10 мүнөттө эскирет, сессия 30 күн жашайт.
"""

import secrets
from core.db import db

WEBSESSION_VERSION = "v1"
print(f"🔑 core/websession.py жүктөлдү. Версия = {WEBSESSION_VERSION}")

TOKEN_MINUTES = 10      # кирүү коду ушунча убакыт жашайт
SESSION_DAYS = 30       # cookie ушунча күн жашайт


# ============ КИРҮҮ КОДУ ============

def start():
    """Жаңы кирүү коду."""
    cleanup()
    token = secrets.token_urlsafe(6)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO web_logins (token) VALUES (%s)", (token,))
        conn.commit()
    return token


def get(token):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT token, account_id, "
            "       (created_at < NOW() - INTERVAL '%s minutes') AS old "
            "FROM web_logins WHERE token = %%s" % TOKEN_MINUTES, (token,))
        row = cur.fetchone()
    if not row:
        return None
    row = dict(row)
    row["expired"] = bool(row.pop("old", False)) and not row["account_id"]
    return row


def attach(token, account_id):
    """Бот аккаунтту байлады."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE web_logins SET account_id = %s WHERE token = %s",
                    (account_id, token))
        conn.commit()
    print(f"[websession] {token} → account {account_id}")


# ============ СЕССИЯ (cookie) ============

def open_session(account_id):
    """Браузер үчүн жаңы сессия ачат, sid кайтарат."""
    sid = secrets.token_urlsafe(24)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO web_sessions (sid, account_id) VALUES (%s, %s)",
                    (sid, account_id))
        conn.commit()
    return sid


def account_id_of(sid):
    """Cookie'деги sid кайсы аккаунтка таандык? Эскирсе — None."""
    if not sid:
        return None
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT account_id FROM web_sessions "
            "WHERE sid = %%s AND created_at > NOW() - INTERVAL '%s days'"
            % SESSION_DAYS, (sid,))
        row = cur.fetchone()
    return row["account_id"] if row else None


def close_session(sid):
    if not sid:
        return
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM web_sessions WHERE sid = %s", (sid,))
        conn.commit()


def cleanup():
    """Эскирген коддорду жана сессияларды өчүрөт."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM web_logins WHERE created_at < "
                        "NOW() - INTERVAL '1 day'")
            cur.execute("DELETE FROM web_sessions WHERE created_at < "
                        "NOW() - INTERVAL '%s days'" % (SESSION_DAYS * 2))
            conn.commit()
    except Exception as e:
        print("[websession] тазалоо катасы:", e)
