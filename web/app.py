# -*- coding: utf-8 -*-
"""
web/app.py
==========
ТАКСИ роБОТ — сайт бөлүгү.

Түзүлүшү ТАП! сайтындай: башкы тилке → издөө сабы → категория
карточкалары → облус чиптери → жарыялар. Түстөрү такси: кара, сары.

Эмне кылат: базадагы АКТИВДҮҮ жарыяларды көрсөтөт. Жарыя жазуу
ботто калат — сайттан жазуу үчүн телефон ырастоо, спамдан коргоо,
сессия керек болмок.

Маалымат булагы — ошол эле PostgreSQL база. Сайт эч нерсе жазбайт,
өзгөртпөйт: окуп, көрсөтөт гана.

Беттер:
    /                        — багыттар (категория + облус чыпкасы)
    /?cat=to|from|local      — категория
    /?obl=Ош облусу          — облус боюнча чыпка
    /?q=Ош                   — издөө
    /route?from=&to=         — ошол багыттагы айдоочулар
"""

import os
import re
import traceback
from urllib.parse import quote
from flask import (Flask, render_template, request, make_response,
                   send_from_directory)

from core.db import db
from core import posts
from core.texts import render as tr_render

WEB_VERSION = "v22-bots-page"
print(f"🌐 web/app.py жүктөлдү. Версия = {WEB_VERSION}")

BOT_USERNAME = os.environ.get("BOT_USERNAME", "taxirobot_bot")
WA_BOT_NUMBER = os.environ.get("WA_BOT_NUMBER", "996227155603")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/taxirobotbot")

app = Flask(__name__)


# ============ ШААР → ОБЛУС ТАБЛИЦАСЫ ============
# core/geo.py'деги эки сөздүктөн бир жолу курулат: шаардын атынан
# облусун табуу үчүн. Ошондо бетте «Ош облусу · 5» деген чиптерди
# көрсөтө алабыз.

def _build_city_oblast():
    table = {}
    try:
        from core.geo import REGIONS, DISTRICTS
        for oblast, cities in REGIONS.items():
            for c in cities:
                table[c] = oblast
        for oblast, cities in DISTRICTS.items():
            for c in cities:
                table.setdefault(c, oblast)
    except Exception as e:
        print("[web] geo жүктөө катасы:", e)
    return table


CITY_OBLAST = _build_city_oblast()


def _all_oblasts():
    """Кыргызстандын бардык облустарынын туруктуу тизмеси.

    Чиптер ар дайым толук көрүнүшү үчүн керек: жарыясы жок облус да
    «0» менен турат. Ошондо колдонуучу тизменин өзгөрүп кетишинен
    чаташпайт — чиптер жоголуп-пайда болбойт.
    """
    names = []
    try:
        from core.geo import REGIONS, DISTRICTS
        for o in list(REGIONS.keys()) + list(DISTRICTS.keys()):
            if o not in names:
                names.append(o)
    except Exception as e:
        print("[web] облустардын тизмеси катасы:", e)
    return names


ALL_OBLASTS = _all_oblasts()


# ============ ИЗДӨӨНҮ ЖӨНӨКӨЙЛӨТҮҮ ============
# Колдонуучу «Жети Огуз», «жети-өгүз», «ЖЕТИӨГҮЗ» деп ар кандай
# жазат. Экөөнү тең бирдей эрежеден өткөрүп, анан салыштырабыз.

# Кыргызча өзгөчө тамгалар → жөнөкөй варианты.
# Көпчүлүк адамдын клавиатурасында ө, ү, ң жок.
_FOLD = str.maketrans({
    "ө": "о", "Ө": "о", "ү": "у", "Ү": "у",
    "ң": "н", "Ң": "н", "ё": "е", "Ё": "е",
    "һ": "х", "Һ": "х",
})

# Аталыштын куйругу — издөөдө маани бербейт
_TAILS = re.compile(
    r"\s*(шаары|шаар|району|район|облусу|облус|айылы|айыл|"
    r"город|городе|район[аеу]?|область|области)\s*", re.I)


def norm(s):
    """Издөө үчүн текстти бирдей түргө келтирет.

        «Жети-Өгүз району» → «жетиогуз»
        «жети огуз»        → «жетиогуз»
        «ЖЕТИӨГҮЗ»         → «жетиогуз»
    """
    if not s:
        return ""
    s = str(s).lower().translate(_FOLD)
    s = _TAILS.sub(" ", s)
    # тамга менен сандан башкасын алып салабыз (дефис, боштук, чекит)
    return "".join(ch for ch in s if ch.isalnum())


def _close(a, b, max_diff=1):
    """Эки сөз бири-бирине жакынбы? (тамга ката кечирүү)

    «бишкик» → «бишкек» табылсын үчүн. Бир тамга айырма кечирилет,
    узун сөздөрдө экөө.
    """
    if not a or not b:
        return False
    if abs(len(a) - len(b)) > max_diff:
        return False
    # Levenshtein — кыска сөздөр үчүн жөнөкөй эсеп жетиштүү
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= max_diff


def _matches(q, *fields):
    """Сурам ушул талаалардын бирине дал келеби?

    Үч деңгээл: ичинде барбы → башталабы → тамга катасы менен жакынбы.
    """
    nq = norm(q)
    if not nq:
        return True
    for f in fields:
        nf = norm(f)
        if not nf:
            continue
        if nq in nf:
            return True
        # Узун сурамда тамга катасын кечиребиз
        if len(nq) >= 4 and _close(nq, nf, 2 if len(nq) > 6 else 1):
            return True
    return False


def _oblast_of(row):
    """Багыттын облусу — Бишкек эмес шаардын облусу."""
    frm, to = row["from_city"], row["to_city"]
    city = to if frm == "Бишкек" else frm
    return CITY_OBLAST.get(city) or CITY_OBLAST.get(to) or "Башка"


# ============ ЖАРДАМЧЫЛАР ============

def _lang():
    q = request.args.get("lang")
    if q in ("ky", "ru"):
        return q
    return request.cookies.get("lang", "ky")


def _t(ky, ru):
    return ru if _lang() == "ru" else ky


def _v(x):
    """Базадагы кыргызча маанини керек болсо орусчага которот."""
    if x is None:
        return ""
    if _lang() != "ru":
        return str(x)
    return tr_render(str(x), "ru")


def _digits(phone):
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if d.startswith("0") and len(d) == 10:
        d = "996" + d[1:]
    return d


def driver_routes():
    """Активдүү айдоочу жарыялары бар багыттар жана алардын саны."""
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


def _category_of(r):
    if r["to_city"] == "Бишкек":
        return "to"
    if r["from_city"] == "Бишкек":
        return "from"
    return "local"


def _card(p):
    d = _digits(p.get("phone"))
    return {
        "name": p.get("name") or "",
        "car": p.get("car") or "",
        "date": _v(p.get("date_text")),
        "time": _v(p.get("time_text")),
        "seats": p.get("seats") or "",
        "price": _v(p.get("price")),
        "comment": p.get("comment") or "",
        "is_vip": bool(p.get("is_vip")),
        "phone": f"+{d}" if d else "",
        "tel_url": f"tel:+{d}" if d else "",
        "tg_url": f"https://t.me/+{d}" if d else "",
        "wa_url": f"https://wa.me/{d}" if d else "",
    }


def _lang_url(target):
    """Учурдагы бетти башка тилде ачуучу шилтеме.

    Чыпкалар (cat, obl, q) сакталып калат — тил алмашканда
    колдонуучу баштан баштабашы үчүн.
    """
    args = {k: v for k, v in request.args.items() if k != "lang"}
    args["lang"] = target
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in args.items())
    return f"{request.path}?{qs}"


def _base_ctx():
    return {
        "lang": _lang(),
        "lang_ky_url": _lang_url("ky"),
        "lang_ru_url": _lang_url("ru"),
        "t": _t,
        "bot_url": f"https://t.me/{BOT_USERNAME}?start=home",
        "help_url": f"https://t.me/{BOT_USERNAME}?start=home",
        "wa_bot_url": f"https://wa.me/{WA_BOT_NUMBER}?text=/start",
        "channel_url": CHANNEL_LINK,
        # «Жарыя берүү» бетинен ботко ТҮЗ кирүү — ролу менен кошо.
        # Telegram start-параметрди өзү берет, WhatsApp'та кабар
        # талаасына даяр текст коюлат.
        "tg_post_driver": f"https://t.me/{BOT_USERNAME}?start=postd",
        "tg_post_passenger": f"https://t.me/{BOT_USERNAME}?start=postp",
        "wa_post_driver": (f"https://wa.me/{WA_BOT_NUMBER}"
                           f"?text={quote('Жарыя берем: айдоочу')}"),
        "wa_post_passenger": (f"https://wa.me/{WA_BOT_NUMBER}"
                              f"?text={quote('Жарыя берем: жүргүнчү')}"),
    }


def _with_lang(resp):
    q = request.args.get("lang")
    if q in ("ky", "ru"):
        resp.set_cookie("lang", q, max_age=365 * 24 * 3600)
    return resp


@app.after_request
def _no_cache(resp):
    """HTML беттерин браузер кештебесин — жаңы версия дароо көрүнсүн."""
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


# ============ БЕТТЕР ============

@app.route("/")
def index():
    cat = request.args.get("cat") or "all"
    obl = (request.args.get("obl") or "").strip()
    q = (request.args.get("q") or "").strip()

    rows = driver_routes()
    for r in rows:
        r["cat"] = _category_of(r)
        r["obl"] = _oblast_of(r)

    # Категориялардын саны — карточкаларда көрсөтүү үчүн
    cat_counts = {"all": sum(r["n"] for r in rows), "to": 0, "from": 0, "local": 0}
    for r in rows:
        cat_counts[r["cat"]] += r["n"]

    # 1) Категория боюнча чыпкалайбыз
    sel = rows if cat == "all" else [r for r in rows if r["cat"] == cat]

    # 2) Облус чиптери — БАРДЫГЫ ар дайым көрүнөт.
    #    Жарыясы жок болсо «0» деп турат: тизме туруксуз болбошу үчүн.
    obl_counts = {}
    for r in sel:
        obl_counts[r["obl"]] = obl_counts.get(r["obl"], 0) + r["n"]

    oblasts = [(name, obl_counts.get(name, 0)) for name in ALL_OBLASTS]
    # Тизмеде жок аталыш чыгып калса («Башка» ж.б.) — аны да кошобуз
    for name, n in obl_counts.items():
        if name not in ALL_OBLASTS:
            oblasts.append((name, n))
    # Көбүрөөк жарыясы барлары башында, нөлдөр аягында
    oblasts.sort(key=lambda kv: (-kv[1], kv[0]))

    # 3) Облус тандалса — ошону гана калтырабыз
    if obl:
        sel = [r for r in sel if r["obl"] == obl]

    # 4) Издөө — жазылышына карабай табылсын
    suggest = []
    if q:
        found = [r for r in sel if _matches(q, r["from_city"], r["to_city"])]
        if not found:
            # Эч нерсе табылбады — бүт тизмеден жакын аталыштарды
            # чогултуп, «мүмкүн ушуну издедиңизби?» деп сунуштайбыз
            nq = norm(q)
            seen = set()
            for r in rows:
                for city in (r["from_city"], r["to_city"]):
                    nc = norm(city)
                    if city in seen or not nc:
                        continue
                    if nq[:3] and nc.startswith(nq[:3]) or _close(nq, nc, 2):
                        seen.add(city)
                        suggest.append(city)
            suggest = suggest[:6]
        sel = found

    html = render_template("index.html",
                           routes=sel,
                           cat=cat,
                           cat_counts=cat_counts,
                           oblasts=oblasts,
                           obl=obl,
                           q=q,
                           suggest=suggest,
                           total=sum(r["n"] for r in sel),
                           **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/route")
def route():
    frm = (request.args.get("from") or "").strip()
    to = (request.args.get("to") or "").strip()
    cards = []
    if frm and to:
        try:
            cards = [_card(p) for p in
                     posts.search_posts("driver", from_city=frm, to_city=to)]
        except Exception as e:
            print("[web] издөө катасы:", e)
    html = render_template("route.html", frm=frm, to=to, cards=cards,
                           **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/post")
def post_page():
    """«➕ Жарыя берүү» — эки ботко өтүү."""
    html = render_template("post.html", **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/bots")
def bots_page():
    """«🤖 Боттор» — эки ботко өтүү."""
    html = render_template("bots.html", **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/help")
def help_page():
    """«❓ Жардам» — боттогу нускаманын ошол эле тексти.

    Тексттер core/texts.py'ден алынат: бир жерде оңдосок, ботто да,
    сайтта да бирдей жаңырат.
    """
    lang = _lang()
    try:
        from core.texts import (GUIDE, FAQ_POST, FAQ_FREE, FAQ_SEARCH,
                                FAQ_PAY, FAQ_CONTACT, FAQ_SAFETY,
                                DRIVER_SAFETY)
        blocks = [
            (_t("📖 Нускама", "📖 Инструкция"), tr_render(GUIDE, lang)),
            (_t("📝 Жарыя жөнүндө", "📝 Об объявлении"), tr_render(FAQ_POST, lang)),
            (_t("🎁 Акысыз мүмкүнчүлүк", "🎁 Бесплатный доступ"), tr_render(FAQ_FREE, lang)),
            (_t("🔍 Издөө", "🔍 Поиск"), tr_render(FAQ_SEARCH, lang)),
            (_t("💳 Төлөм жана баалар", "💳 Оплата и цены"),
             tr_render(FAQ_PAY, lang)),
            (_t("📞 Байланыш", "📞 Связь"), tr_render(FAQ_CONTACT, lang)),
            (_t("🛡 Коопсуздук", "🛡 Безопасность"), tr_render(FAQ_SAFETY, lang)),
            (_t("🚦 Айдоочунун коопсуздугу", "🚦 Безопасность водителя"),
             tr_render(DRIVER_SAFETY, lang)),
        ]
    except Exception as e:
        print("[web] жардам текстин алуу катасы:", e)
        blocks = []
    html = render_template("help.html", blocks=blocks, **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/me")
def me_page():
    """«👤 Кабинет» — тил, шилтемелер, платформа тууралуу."""
    html = render_template("me.html", **_base_ctx())
    return _with_lang(make_response(html))


@app.errorhandler(500)
@app.errorhandler(Exception)
def _oops(e):
    """Ката чыкса — логго толук жазабыз, колдонуучуга жөнөкөй бет."""
    print("=" * 60)
    print("[web] КАТА:", request.path)
    traceback.print_exc()
    print("=" * 60)
    return ("<h2 style='font-family:sans-serif'>Кечиресиз, ката кетти</h2>"
            "<p style='font-family:sans-serif'>Бир аздан кийин кайра "
            "аракет кылыңыз.</p>"), 500


# ============ PWA (телефонго орнотуу) ============
# Эки файл тең web/static/ ичинде жатат, бирок сайттын ТҮБҮНӨН
# берилиши керек: service worker өз папкасынан жогорку беттерди
# башкара албайт. Ошондуктан өзүнчө жол жазабыз.

@app.route("/manifest.json")
def manifest():
    """Тиркеменин аты, түсү, иконкалары."""
    return send_from_directory(app.static_folder, "manifest.json",
                               mimetype="application/manifest+json")


@app.route("/sw.js")
def service_worker():
    """Кештөө жана «интернет жок» бети."""
    resp = make_response(send_from_directory(
        app.static_folder, "sw.js", mimetype="application/javascript"))
    # Түбүнөн берилгенин браузерге ырастайбыз
    resp.headers["Service-Worker-Allowed"] = "/"
    # Жаңы версия дароо жетсин
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/healthz")
def healthz():
    return "ok", 200


def run(host="0.0.0.0", port=None):
    port = port or int(os.environ.get("PORT", 8080))
    print(f"🌐 Сайт башталды. http://{host}:{port}")
    app.run(host=host, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    run()

