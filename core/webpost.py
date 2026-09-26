# -*- coding: utf-8 -*-
"""
core/webpost.py
================
Сайттан берилген жарыянын убактылуу «долбоору».

Агым:
  1. Адам сайттагы форманы толтурат  → create() токен кайтарат
  2. Ал Telegram же WhatsApp ботко өтөт (t.me/…?start=v_ТОКЕН)
  3. Бот номерин тастыктайт → wizard.save() жарыяны чыгарат
  4. mark_done() жазылат, сайттагы бет «✅ Жарыяланды» дейт

Долбоор 2 сааттан кийин эскирет: ырасталбаса, жарыя чыкпайт.
"""

import json
import secrets
from core.db import db

WEBPOST_VERSION = "v1"
print(f"📝 core/webpost.py жүктөлдү. Версия = {WEBPOST_VERSION}")

TTL_HOURS = 2       # ушунча сааттын ичинде ырасталышы керек
KEEP_HOURS = 24     # эски жазуулар ушундан кийин өчүрүлөт


def create(role, data):
    """Долбоорду сактап, токен кайтарат."""
    cleanup()
    token = secrets.token_urlsafe(8)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO web_drafts (token, role, data) "
                    "VALUES (%s, %s, %s)",
                    (token, role, json.dumps(data, ensure_ascii=False)))
        conn.commit()
    return token


def get(token):
    """Долбоорду кайтарат. Эскирген болсо — status='expired'."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT token, role, data, status, post_id, note, "
            "       (created_at < NOW() - INTERVAL '%s hours') AS old "
            "FROM web_drafts WHERE token = %%s" % TTL_HOURS, (token,))
        row = cur.fetchone()
    if not row:
        return None
    row = dict(row)
    if isinstance(row.get("data"), str):
        try:
            row["data"] = json.loads(row["data"])
        except ValueError:
            row["data"] = {}
    if row.pop("old", False) and row["status"] == "pending":
        row["status"] = "expired"
    return row


def mark_done(token, post_id):
    _set(token, "done", post_id=post_id)


def mark_error(token, note):
    _set(token, "error", note=(note or "")[:300])


def _set(token, status, post_id=None, note=None):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE web_drafts SET status = %s, post_id = %s, "
                    "note = %s WHERE token = %s",
                    (status, post_id, note, token))
        conn.commit()


def cleanup():
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM web_drafts WHERE created_at < "
                        f"NOW() - INTERVAL '{KEEP_HOURS} hours'")
            conn.commit()
    except Exception as e:
        print("[webpost] тазалоо катасы:", e)
