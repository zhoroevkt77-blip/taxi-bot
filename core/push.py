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

PUSH_VERSION = "v182-role"
print(f"🔔 core/push.py жүктөлдү. Версия = {PUSH_VERSION}")

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "admin@taxirobot.kg").strip()

SITE_URL = os.environ.get(
    "SITE_URL", "https://taxi-bot-taxirobot.up.railway.app").rstrip("/")

# v170: чогултуу кабарлары ошол эле push_subs таблицасында жатат,
# бирок багыттын ордуна ушул белги коюлат. Жаңы таблица керек эмес.
# Бул белги чыныгы шаардын аты болушу мүмкүн эмес, ошондуктан
# башка жазуулар менен чаташпайт.
PICKUP_TAG = "__pickup__"


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
                endpoint   TEXT NOT NULL,
                p256dh     TEXT NOT NULL,
                auth       TEXT NOT NULL,
                from_city  TEXT,
                to_city    TEXT,
                lang       TEXT DEFAULT 'ky',
                fails      INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            # Эски таблицада endpoint UNIQUE болчу — ошондо бир браузер
            # бир гана багытка жазыла алмак. Аны алып салабыз.
            try:
                cur.execute("ALTER TABLE push_subs "
                            "DROP CONSTRAINT IF EXISTS push_subs_endpoint_key")
            except Exception as e:
                print("[push] эски чектөөнү алуу:", e)
            # v182: жазылуу кимдин жарыясын күтөт — 'driver' же
            # 'passenger'. Мурдагылардын баары 'driver' болуп калат:
            # алар жүргүнчүлөр, айдоочу күтүшөт.
            cur.execute("ALTER TABLE push_subs ADD COLUMN IF NOT EXISTS "
                        "want TEXT DEFAULT 'driver'")
            cur.execute("UPDATE push_subs SET want = 'driver' "
                        "WHERE want IS NULL")
            # Бир браузер + бир багыт + бир рол = бир жазуу.
            # Эски индекс ролду билчү эмес: айдоочу менен жүргүнчү
            # бир браузерден бир багытка жазыла алмак эмес.
            cur.execute("DROP INDEX IF EXISTS push_uni_idx")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS push_uni2_idx "
                        "ON push_subs (endpoint, from_city, to_city, want)")
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

def _want(w):
    """v182: 'passenger' болбосо — 'driver'. Башка маани кабыл алынбайт."""
    return "passenger" if w == "passenger" else "driver"


def subscribe(sub, from_city, to_city, lang="ky", want="driver"):
    """Браузерди багытка жазат. Кайра жазылса — жаңыртат.

    v182: want — кимдин жарыясы күтүлөт: 'driver' (жүргүнчү
    жазылат) же 'passenger' (айдоочу жазылат).
    """
    want = _want(want)
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not (endpoint and p256dh and auth):
        return False
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO push_subs (endpoint, p256dh, auth, from_city,
                                       to_city, lang, fails, want)
                VALUES (%s,%s,%s,%s,%s,%s,0,%s)
                ON CONFLICT (endpoint, from_city, to_city, want) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    lang = EXCLUDED.lang,
                    fails = 0
            """, (endpoint, p256dh, auth, from_city, to_city, lang, want))
            conn.commit()
        return True
    except Exception as e:
        print("[push] жазылуу катасы:", e)
    # База жаңыланбай калса — айдоочу жарыясына жазылуу эски
    # жол менен иштей берсин. Жаңы мүмкүнчүлүк гана токтойт.
    if want != "driver":
        return False
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO push_subs (endpoint, p256dh, auth, from_city,
                                       to_city, lang, fails)
                VALUES (%s,%s,%s,%s,%s,%s,0)
                ON CONFLICT (endpoint, from_city, to_city) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    lang = EXCLUDED.lang,
                    fails = 0
            """, (endpoint, p256dh, auth, from_city, to_city, lang))
            conn.commit()
        return True
    except Exception as e:
        print("[push] жазылуу катасы (эски жол):", e)
        return False


def unsubscribe(endpoint, from_city=None, to_city=None, want=None):
    """Жазылууну өчүрөт.

    Багыт берилсе — ошол багыт гана. Берилбесе — ушул браузердин
    бардык жазылуулары (браузер уруксатты алып салганда керек).

    v182: want берилсе — ошол багыттын ошол ролу гана өчөт.
    """
    if from_city and to_city and want:
        try:
            with db() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM push_subs WHERE endpoint = %s "
                            "AND from_city = %s AND to_city = %s "
                            "AND COALESCE(want, 'driver') = %s",
                            (endpoint, from_city, to_city, _want(want)))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            print("[push] өчүрүү катасы (рол менен):", e)
            # тилке жок болсо — төмөндөгү эски жол менен өчөт
    try:
        with db() as conn:
            cur = conn.cursor()
            if from_city and to_city:
                cur.execute("DELETE FROM push_subs WHERE endpoint = %s "
                            "AND from_city = %s AND to_city = %s",
                            (endpoint, from_city, to_city))
            else:
                cur.execute("DELETE FROM push_subs WHERE endpoint = %s",
                            (endpoint,))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        print("[push] өчүрүү катасы:", e)
        return False


def routes_of(endpoint):
    """Ушул браузер кайсы багыттарга жазылган.

    v182: ар бир багыт менен кошо кимдин жарыясы күтүлөрү да
    кайтат (want). Тилке жок болсо — мурдагыдай, ролсуз.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT from_city, to_city, "
                        "COALESCE(want, 'driver') AS want FROM push_subs "
                        "WHERE endpoint = %s AND from_city <> %s "
                        "ORDER BY created_at", (endpoint, PICKUP_TAG))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print("[push] тизме (рол менен):", e)
    try:
        with db() as conn:
            cur = conn.cursor()
            # v170: чогултуу жазуусу багыт эмес — тизмеде чыкпасын
            cur.execute("SELECT from_city, to_city FROM push_subs "
                        "WHERE endpoint = %s AND from_city <> %s "
                        "ORDER BY created_at", (endpoint, PICKUP_TAG))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print("[push] тизме катасы:", e)
        return []


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


def _subs_for(from_city, to_city, want=None):
    """Ушул багытка жазылгандар.

    v182: want берилсе — ошол ролдун жарыясын күткөндөр гана.
    Тилке жок болсо, айдоочу жарыясы үчүн эски жол менен табылат,
    ал эми жүргүнчү жарыясы үчүн эч ким табылбайт — ашыкча кабар
    кеткенден көрө, кетпегени жакшы.
    """
    if want:
        want = _want(want)
        try:
            with db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM push_subs "
                            "WHERE from_city = %s AND to_city = %s "
                            "AND COALESCE(want, 'driver') = %s",
                            (from_city, to_city, want))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print("[push] тизме катасы (рол менен):", e)
            if want != "driver":
                return []
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
            # Endpoint жараксыз болсо, анын БАРДЫК багыттары өчөт
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


def _body_p(p, lang="ky"):
    """v182: жүргүнчүнүн жарыясынын кыска тексти."""
    parts = []
    if p.get("name"):
        parts.append(str(p["name"]))

    when = " ".join(x for x in [p.get("date_text"), p.get("time_text")] if x)
    if when:
        parts.append(when)

    tail = []
    n = str(p.get("people_count") or "").strip()
    if n:
        if n.isdigit():
            tail.append(f"{n} киши" if lang != "ru" else f"{n} чел.")
        else:
            tail.append(n)              # «Салон» ж.б.
    if p.get("price"):
        tail.append(str(p["price"]))
    if tail:
        parts.append(" · ".join(tail))

    if not parts:
        return "Жаңы жүргүнчү чыкты" if lang != "ru" else "Появился пассажир"
    return "\n".join(parts)


# ============ 🗺 ЧОГУЛТУУ КАБАРЫ (v170) ============

def subscribe_pickup(sub, mtoken, lang="ky"):
    """Айдоочунун браузерин ушул чогултууга жазат."""
    if not mtoken:
        return False
    return subscribe(sub, PICKUP_TAG, mtoken, lang)


def unsubscribe_pickup(endpoint, mtoken):
    """Ушул чогултуунун кабарын өчүрөт. Башка жазылуулары калат."""
    if not (endpoint and mtoken):
        return False
    return unsubscribe(endpoint, PICKUP_TAG, mtoken)


def notify_pickup(mtoken, name, total):
    """Жүргүнчү белгиленди — айдоочунун телефонуна кабар.

    Кабар кошумча мүмкүнчүлүк: ката болсо да чекит базада калат,
    жүргүнчүгө эч нерсе билинбейт.
    """
    if not (enabled() and mtoken):
        return 0

    subs = _subs_for(PICKUP_TAG, mtoken)
    if not subs:
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[push] pywebpush орнотулган эмес — кабар жиберилбейт.")
        return 0

    url = f"{SITE_URL}/pickup/m/{quote(str(mtoken))}"
    who = (str(name or "").strip() or "—")[:40]

    sent = 0
    for s in subs:
        lang = s.get("lang") or "ky"
        if lang == "ru":
            title, body = "🧳 Пассажир отметился", f"{who} · готовы: {total}"
        else:
            title, body = "🧳 Жүргүнчү белгиленди", f"{who} · даяр: {total}"

        payload = json.dumps({
            "title": title,
            "body": body,
            "url": f"{url}?lang={lang}",
            # Бир эле чогултуунун кабарлары бири-бирин алмаштырсын,
            # телефондун экранын толтурбасын
            "tag": f"pickup-{mtoken}",
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
            if code in (404, 410):
                _drop(s["endpoint"])
            else:
                print(f"[push] чогултуу кабары ({code}):", e)
        except Exception as e:
            print("[push] чогултуу кабары, күтүлбөгөн ката:", e)

    if sent:
        print(f"🔔 чогултуу {mtoken}: {sent} кабар жиберилди.")
    return sent


def notify_route(from_city, to_city, post=None, want="driver"):
    """Ошол багытка жазылгандардын баарына кабар жиберет.

    Жиберилген кабарлардын санын кайтарат. Ката болсо да программа
    токтобойт — кабар кошумча мүмкүнчүлүк, негизги иш эмес.

    v182: want — кимдин жарыясы чыкты. 'driver' болсо жүргүнчүлөргө,
    'passenger' болсо айдоочуларга кетет.
    """
    if not enabled():
        return 0

    want = _want(want)
    subs = _subs_for(from_city, to_city, want)
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
    if want == "passenger":
        # Басканда ошол багыттагы ЖҮРГҮНЧҮЛӨРДҮН тизмеси ачылсын
        url += "&role=passenger"

    sent = 0
    for s in subs:
        lang = s.get("lang") or "ky"
        if want == "passenger":
            who = "Пассажир" if lang == "ru" else "Жүргүнчү"
            title = f"🧍 {who}: {from_city} → {to_city}"
            body = _body_p(p, lang)
        else:
            title = f"🚖 {from_city} → {to_city}"
            body = _body(p, lang)
        payload = json.dumps({
            "title": title,
            "body": body,
            "url": f"{url}&lang={lang}",
            "tag": f"route-{want}-{from_city}-{to_city}",
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
