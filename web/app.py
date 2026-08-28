# -*- coding: utf-8 -*-
"""
web/app.py
==========
ТАКСИ роБОТ — сайт бөлүгү.

Эмне кылат: базадагы АКТИВДҮҮ жарыяларды көрсөтөт. Жарыя жазуу
ботто калат — сайттан жазуу үчүн телефон ырастоо, спамдан коргоо,
сессия керек болмок, ал өзүнчө чоң иш.

Маалымат булагы — ошол эле PostgreSQL база. Сайт эч нерсе түзбөйт,
жаңыртпайт: болгонун окуп, көрсөтөт гана. Ошондуктан ботко эч
кандай тобокелдик жок.

Беттер:
    /                 — багыттардын тизмеси, ар биринде канча жарыя бар
    /route?from=&to=  — ошол багыттагы айдоочулар
    /?lang=ru         — тил алмаштыруу (кука менен эсте калат)
"""

import os
from flask import Flask, render_template, request, make_response

from core.db import db
from core import posts
from core.texts import render as tr_render

WEB_VERSION = "v1"
print(f"🌐 web/app.py жүктөлдү. Версия = {WEB_VERSION}")

BOT_USERNAME = os.environ.get("BOT_USERNAME", "taxirobot_bot")
WA_BOT_NUMBER = os.environ.get("WA_BOT_NUMBER", "996227155603")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/taxirobotbot")

app = Flask(__name__)


# ============ ЖАРДАМЧЫЛАР ============

def _lang():
    """Тил: URL'ден келсе — ошону алабыз, болбосо кукадан."""
    q = request.args.get("lang")
    if q in ("ky", "ru"):
        return q
    return request.cookies.get("lang", "ky")


def _t(ky, ru):
    """Эки тилдүү кыска текст."""
    return ru if _lang() == "ru" else ky


def _v(x):
    """Базадагы кыргызча маанини керек болсо орусчага которот.

    Күн, убакыт, баа базага кыргызча жазылат («Бүгүн», «Келишим»),
    ошондуктан орусча бетте аларды котормо катмарынан өткөрөбүз.
    """
    if x is None:
        return ""
    if _lang() != "ru":
        return str(x)
    return tr_render(str(x), "ru")


def _digits(phone):
    """'0555112233' -> '996555112233'"""
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if d.startswith("0") and len(d) == 10:
        d = "996" + d[1:]
    return d


def driver_routes():
    """Активдүү айдоочу жарыялары бар багыттар жана алардын саны.

    Бир суроо менен баарын алабыз — Бишкекке, Бишкектен жана
    район аралык маршруттардын баары бир тизмеде.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT from_city, to_city, COUNT(*) AS n
                FROM posts
                WHERE role = 'driver' AND active = 1
                GROUP BY from_city, to_city
                ORDER BY n DESC, from_city
            """)
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print("[web] багыттарды алуу катасы:", e)
        return []


def _grouped(rows):
    """Багыттарды үч топко бөлөт — бетте окууга оңой болушу үчүн."""
    to_bishkek, from_bishkek, local = [], [], []
    for r in rows:
        if r["to_city"] == "Бишкек":
            to_bishkek.append(r)
        elif r["from_city"] == "Бишкек":
            from_bishkek.append(r)
        else:
            local.append(r)
    return to_bishkek, from_bishkek, local


def _card(p):
    """Жарыяны бетке ыңгайлуу түргө келтирет."""
    d = _digits(p.get("phone"))
    return {
        "name": p.get("name") or "",
        "car": p.get("car") or "",
        "date": _v(p.get("date_text")),
        "time": _v(p.get("time_text")),
        "seats": p.get("seats") or "",
        "price": _v(p.get("price")),
        "comment": p.get("comment") or "",
        "from_city": p.get("from_city") or "",
        "to_city": p.get("to_city") or "",
        "is_vip": bool(p.get("is_vip")),
        "phone": f"+{d}" if d else "",
        "tel_url": f"tel:+{d}" if d else "",
        "tg_url": f"https://t.me/+{d}" if d else "",
        "wa_url": f"https://wa.me/{d}" if d else "",
    }


def _base_ctx():
    """Ар бир бетке керектүү жалпы маалымат."""
    lang = _lang()
    return {
        "lang": lang,
        "t": _t,
        "bot_url": f"https://t.me/{BOT_USERNAME}?start=home",
        "wa_bot_url": f"https://wa.me/{WA_BOT_NUMBER}?text=/start",
        "channel_url": CHANNEL_LINK,
    }


def _with_lang(resp):
    """Тил URL'ден келсе — кукага сактайбыз (бир жыл)."""
    q = request.args.get("lang")
    if q in ("ky", "ru"):
        resp.set_cookie("lang", q, max_age=365 * 24 * 3600)
    return resp


# ============ БЕТТЕР ============

@app.route("/")
def index():
    rows = driver_routes()
    to_bishkek, from_bishkek, local = _grouped(rows)
    total = sum(r["n"] for r in rows)
    html = render_template("index.html",
                           to_bishkek=to_bishkek,
                           from_bishkek=from_bishkek,
                           local=local,
                           total=total,
                           **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/route")
def route():
    frm = (request.args.get("from") or "").strip()
    to = (request.args.get("to") or "").strip()
    if not frm or not to:
        html = render_template("route.html", frm="", to="", cards=[],
                               **_base_ctx())
        return _with_lang(make_response(html))

    try:
        rows = posts.search_posts("driver", from_city=frm, to_city=to)
    except Exception as e:
        print("[web] издөө катасы:", e)
        rows = []

    cards = [_card(p) for p in rows]
    html = render_template("route.html", frm=frm, to=to, cards=cards,
                           **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/healthz")
def healthz():
    """Railway жана мониторинг үчүн — сайт тирүүбү?"""
    return "ok", 200


def run(host="0.0.0.0", port=None):
    """Сайтты иштетет. main.py'ден өзүнчө потокто чакырылат."""
    port = port or int(os.environ.get("PORT", 8080))
    print(f"🌐 Сайт башталды. http://{host}:{port}")
    # threaded=True — бир нече колдонуучу бир убакта кире алат
    app.run(host=host, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    run()
