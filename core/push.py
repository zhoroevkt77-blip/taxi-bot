# -*- coding: utf-8 -*-
"""
core/push.py
============
Браузердин кабарлары (Web Push). Колдонуучу сайттан бир багытка
жазылат — ошол багытта жаңы айдоочу жарыя жазса, телефонуна кабар
келет. Сайт ачык болбосо да.

КАНТИП ИШТЕЙТ:
    1. Браузер өзүнүн «дарегин» (endpoint) жана эки ачкычын берет.
    2. Биз аны базага жазабыз, багыты менен кошо.
    3. Жаңы жарыя чыкканда, ошол багытка жазылгандардын баарына
       кабар жиберебиз — браузердин серверине (Google, Apple, Mozilla).
    4. Браузер аны телефонго жеткирет.

VAPID АЧКЫЧТАРЫ:
    Railway'дин Variables бөлүмүндө:
        VAPID_PUBLIC_KEY   — браузерге берилет, ачык
        VAPID_PRIVATE_KEY  — эч качан браузерге чыкпайт
        VAPID_EMAIL        — байланыш (mailto: коюлат)
    Экөө тең коюлбаса, кабарлар өчүк болот — сайт кадимкидей иштейт.

iPhone ЖӨНҮНДӨ:
    Safari кабарды сайт ТИРКЕМЕ КАТАРЫ орнотулганда гана берет
    («Бөлүшүү → Башкы экранга кошуу»). Ошондуктан сайтта iPhone
    колдонуучусуна алгач орнотуу сунушталат.
"""

import os
import json
from urllib.parse import quote

from core.db import db

PUSH_VERSION = "v2-safe"
print(f"🔔 core/push.py жүктөлдү. Версия = {PUSH_VERSION}")

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "admin@taxirobot.kg").strip()

SITE_URL = os.environ.get(
    "SITE_URL", "https://taxi-bot-taxirobot.up.railway.app").rstrip("/")


def enabled():
    """Кабарлар күйгүзүлгөнбү?"""
    return bool(VAPID_PUBLIC and VAPID_PRIVATE)


def init():
    """Жазылуулардын таблицасын түзөт."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS push_subs (
                id         SERIAL PRIMARY KEY,
                endpoint   TEXT UNIQUE NOT NULL,
                p256dh     TEXT NOT NULL,
                auth       TEXT NOT NULL,
                from_city  TEXT,
                to_city    TEXT,
                lang       TEXT DEFAULT 'ky',
                fails      INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS push_route_idx "
                        "ON push_subs (from_city, to_city)")
            conn.commit()
        print("🔔 push_subs таблицасы даяр.")
    except Exception as e:
        print("[push] таблица катасы:", e)


# Эски аталыш менен чакырылса да иштесин — модулдар ар кайсы
# версияда болуп калышы мүмкүн.
init_push_table = init


# ============ ЖАЗЫЛУУ ============

def subscribe(sub, from_city, to_city, lang="ky"):
    """Браузерди багытка жазат. Кайра жазылса — жаңыртат."""
    try:
        endpoint = sub.get("endpoint")
        keys = sub.get("keys") or {}
        p256dh, auth = keys.get("p256dh"), keys.get("auth")
        if not (endpoint and p256dh and auth):
            return False
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO push_subs (endpoint, p256dh, auth, from_city,
                                       to_city, lang, fails)
                VALUES (%s,%s,%s,%s,%s,%s,0)
                ON CONFLICT (endpoint) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    from_city = EXCLUDED.from_city,
                    to_city = EXCLUDED.to_city,
                    lang = EXCLUDED.lang,
                    fails = 0
            """, (endpoint, p256dh, auth, from_city, to_city, lang))
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
            return cur.rowcount > 0
    except Exception as e:
        print("[push] өчүрүү катасы:", e)
        return False


def count_for(from_city, to_city):
    """Ушул багытка канчоо жазылган."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM push_subs "
                        "WHERE from_city = %s AND to_city = %s",
                        (from_city, to_city))
            return cur.fetchone()["n"]
    except Exception:
        return 0


def _subs_for(from_city, to_city):
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM push_subs "
                        "WHERE from_city = %s AND to_city = %s",
                        (from_city, to_city))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print("[push] тизме катасы:", e)
        return []


def _drop(endpoint):
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM push_subs WHERE endpoint = %s",
                        (endpoint,))
            conn.commit()
    except Exception:
        pass


# ============ ЖИБЕРҮҮ ============

def _body(p, lang="ky"):
    """Кабардын кыска тексти."""
    parts = []
    name = p.get("name")
    car = p.get("car")
    if name and car:
        parts.append(f"{name} · {car}")
    elif name or car:
        parts.append(name or car)

    when = " ".join(x for x in [p.get("date_text"), p.get("time_text")] if x)
    if when:
        parts.append(when)

    tail = []
    if p.get("seats"):
        tail.append(f"{p['seats']} орун" if lang != "ru"
                    else f"{p['seats']} мест")
    if p.get("price"):
        tail.append(str(p["price"]))
    if tail:
        parts.append(" · ".join(tail))

    if not parts:
        return "Жаңы айдоочу чыкты" if lang != "ru" else "Появился водитель"
    return "\n".join(parts)


def notify_route(from_city, to_city, post=None):
    """Ошол багытка жазылгандардын баарына кабар жиберет.

    Жиберилген кабарлардын санын кайтарат. Ката болсо да программа
    токтобойт — кабар кошумча мүмкүнчүлүк, негизги иш эмес.
    """
    if not enabled():
        return 0

    subs = _subs_for(from_city, to_city)
    if not subs:
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[push] pywebpush орнотулган эмес — кабар жиберилбейт.")
        return 0

    p = post or {}
    url = (f"{SITE_URL}/route?from={quote(from_city or '')}"
           f"&to={quote(to_city or '')}")

    sent = 0
    for s in subs:
        lang = s.get("lang") or "ky"
        payload = json.dumps({
            "title": f"🚖 {from_city} → {to_city}",
            "body": _body(p, lang),
            "url": f"{url}&lang={lang}",
            "tag": f"route-{from_city}-{to_city}",
        }, ensure_ascii=False)

        try:
            webpush(
                subscription_info={
                    "endpoint": s["endpoint"],
                    "keys": {"p256dh": s["p256dh"], "auth": s["auth"]},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={"sub": f"mailto:{VAPID_EMAIL}"},
                timeout=15,
            )
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            # 404/410 — браузер жазылууну жокко чыгарган, өчүрөбүз
            if code in (404, 410):
                _drop(s["endpoint"])
            else:
                print(f"[push] жиберүү катасы ({code}):", e)
        except Exception as e:
            print("[push] күтүлбөгөн ката:", e)

    if sent:
        print(f"🔔 {from_city} → {to_city}: {sent} кабар жиберилди.")
    return sent
