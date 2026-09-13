# -*- coding: utf-8 -*-
"""
core/push.py
============
Браузердин кабарлары (Web Push). Жүргүнчү сайттан багытты ачып,
«🔔 Кабар алам» дегенде — ошол багытка жаңы айдоочу жарыя жазса,
телефонуна кабар келет. Сайт ачык болбошу да мүмкүн.

КАНТИП ИШТЕЙТ:
    1. Браузер өзүнүн «endpoint» дарегин берет (ар бир телефонго
       уникалдуу). Аны багыт менен кошо базага жазабыз.
    2. Жаңы жарыя чыкканда, ошол багытка жазылгандардын баарына
       кабар жиберебиз.
    3. Браузер кабарды service worker аркылуу көрсөтөт.

VAPID АЧКЫЧТАРЫ:
    Push кызматтары (Google, Apple) кабарды ким жиберип жатканын
    билиши керек. Ошон үчүн эки ачкыч керек — Railway'дин
    Variables бөлүмүндө:
        VAPID_PUBLIC_KEY   — браузерге берилет, жашыруун эмес
        VAPID_PRIVATE_KEY  — эч жерге чыкпайт
        VAPID_EMAIL        — байланыш почтасы (mailto: керек эмес)
    Алар коюлбаса, модуль унчукпай өчүк турат — сайт кадимкидей
    иштей берет.

iPhone ЖӨНҮНДӨ:
    iOS'то Web Push сайт ЭКРАНГА ОРНОТУЛГАН болсо гана иштейт
    (Safari → Бөлүшүү → Башкы экранга кошуу). Жөн эле браузерде
    ачык турса, уруксат сурала да албайт. Бул Apple'дын чектөөсү,
    коддон айланып өтүү мүмкүн эмес — ошондуктан сайт колдонуучуга
    нускама көрсөтөт.
"""

import os
import json
import threading

from core.db import db

PUSH_VERSION = "v1"

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "admin@taxirobot.kg").strip()

# pywebpush орнотулбаса да сайт кулабашы керек
try:
    from pywebpush import webpush, WebPushException
    _LIB = True
except Exception as e:
    print("[push] pywebpush жок:", e)
    _LIB = False

ENABLED = bool(_LIB and VAPID_PUBLIC and VAPID_PRIVATE)
print(f"🔔 core/push.py жүктөлдү. Версия = {PUSH_VERSION}, "
      f"абалы = {'күйүк' if ENABLED else 'өчүк'}")


def init_push_table():
    """Жазылуулардын таблицасы. Бир жолу түзүлөт."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS push_subs (
                endpoint    TEXT PRIMARY KEY,
                p256dh      TEXT NOT NULL,
                auth        TEXT NOT NULL,
                from_city   TEXT,
                to_city     TEXT,
                lang        TEXT DEFAULT 'ky',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS push_route_idx "
                        "ON push_subs (from_city, to_city)")
            conn.commit()
    except Exception as e:
        print("[push] таблица түзүү катасы:", e)


def subscribe(sub, from_city, to_city, lang="ky"):
    """Жазылууну сактайт. Бир эле браузер бир багытка бир жолу.

    sub — браузер берген объект: {endpoint, keys: {p256dh, auth}}
    """
    try:
        keys = sub.get("keys") or {}
        endpoint = sub.get("endpoint")
        if not (endpoint and keys.get("p256dh") and keys.get("auth")):
            return False
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO push_subs (endpoint, p256dh, auth,
                                       from_city, to_city, lang)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (endpoint) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    from_city = EXCLUDED.from_city,
                    to_city = EXCLUDED.to_city,
                    lang = EXCLUDED.lang
            """, (endpoint, keys["p256dh"], keys["auth"],
                  from_city, to_city, lang))
            conn.commit()
        return True
    except Exception as e:
        print("[push] жазылуу катасы:", e)
        return False


def unsubscribe(endpoint):
    """Жазылууну өчүрөт."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM push_subs WHERE endpoint = %s",
                        (endpoint,))
            conn.commit()
        return True
    except Exception as e:
        print("[push] өчүрүү катасы:", e)
        return False


def _subs_for(from_city, to_city):
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM push_subs WHERE from_city = %s "
                        "AND to_city = %s", (from_city, to_city))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print("[push] тизме катасы:", e)
        return []


def _send_one(row, payload):
    """Бир жазылууга кабар. Жараксыз болсо базадан өчүрөт."""
    try:
        webpush(
            subscription_info={
                "endpoint": row["endpoint"],
                "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=VAPID_PRIVATE,
            vapid_claims={"sub": f"mailto:{VAPID_EMAIL}"},
            timeout=20,
        )
        return True
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        # 404/410 — колдонуучу жазылуудан чыккан же браузер тазаланган
        if code in (404, 410):
            unsubscribe(row["endpoint"])
        else:
            print("[push] жиберүү катасы:", code, e)
        return False
    except Exception as e:
        print("[push] жиберүү катасы:", e)
        return False


def notify_new_post(post, site_url=""):
    """Жаңы АЙДООЧУ жарыясы чыкканда чакырылат.

    Жүргүнчүлөрдүн жарыясы сайтта көрүнбөйт, ошондуктан аларга
    кабар жиберилбейт.

    Өзүнчө агымда иштейт: жарыя жазган адам күтүп калбашы үчүн.
    """
    if not ENABLED:
        return 0
    frm = post.get("from_city")
    to = post.get("to_city")
    if not (frm and to):
        return 0

    rows = _subs_for(frm, to)
    if not rows:
        return 0

    def _work():
        sent = 0
        for r in rows:
            ru = (r.get("lang") == "ru")
            title = (f"🚖 Новый водитель: {frm} → {to}" if ru
                     else f"🚖 Жаңы айдоочу: {frm} → {to}")
            bits = []
            if post.get("date_text"):
                bits.append(post["date_text"])
            if post.get("time_text"):
                bits.append(post["time_text"])
            if post.get("price"):
                bits.append(post["price"])
            if post.get("seats"):
                bits.append((f"{post['seats']} мест" if ru
                             else f"{post['seats']} орун"))
            body = " · ".join(str(b) for b in bits) or (
                "Открыть объявление" if ru else "Жарыяны ачуу")

            url = (f"{site_url}/route?from={frm}&to={to}"
                   f"&lang={r.get('lang', 'ky')}")
            if _send_one(r, {"title": title, "body": body, "url": url}):
                sent += 1
        print(f"🔔 Push: {sent}/{len(rows)} жиберилди ({frm} → {to})")

    threading.Thread(target=_work, daemon=True).start()
    return len(rows)
