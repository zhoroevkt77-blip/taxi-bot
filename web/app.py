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
from datetime import datetime, timedelta
from urllib.parse import quote
from flask import (Flask, render_template, request, make_response,
                   send_from_directory)

from core.db import db
from core import posts
from core.texts import render as tr_render

WEB_VERSION = "v47-left"
print(f"🌐 web/app.py жүктөлдү. Версия = {WEB_VERSION}")

BOT_USERNAME = os.environ.get("BOT_USERNAME", "taxirobot_bot")
WA_BOT_NUMBER = os.environ.get("WA_BOT_NUMBER", "996227155603")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/taxirobotbot")

app = Flask(__name__)

# Админ панелдин сессиясы үчүн. SECRET_KEY коюлбаса, ар бир кайра
# жүктөөдө жаңы ачкыч түзүлөт — админ кайра кирүүгө туура келет,
# бирок коопсуздук бузулбайт.
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.permanent_session_lifetime = timedelta(days=7)

# Кабарлардын таблицасы (жок болсо түзүлөт).
# Ката болсо толук жазабыз — логдон себебин так көрүү үчүн.
try:
    from core import push
    starter = getattr(push, "init", None) or getattr(push, "init_push_table", None)
    if starter:
        starter()
    else:
        print("[web] push модулунда init() жок — таблица түзүлгөн жок.")
except Exception as e:
    import traceback
    print("[web] push жүктөлгөн жок:", repr(e))
    traceback.print_exc()

# Админ панель — өзүнчө модулда, /admin дареги боюнча
try:
    from web.admin import bp as admin_bp
    app.register_blueprint(admin_bp)
except Exception as e:
    print("[web] админ панель жүктөлгөн жок:", e)


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


def _all_cities():
    """Ар бир облустун шаар/райондорунун тизмеси.

    МААНИЛҮҮ: geo.py'де бир эле жер эки башка жазылат —
    REGIONS ичинде «Аксы», DISTRICTS ичинде «Аксы району».
    Тизмеде экөө тең турса, колдонуучу чаташат. Ошондуктан
    аларды БИРИКТИРЕБИЗ: жалпы ачкыч (norm) боюнча топтоп,
    эң толук аталышын көрсөтөбүз.

    Кайтарат: {облус: [(ачкыч, көрсөтүлүүчү ат), ...]}
    """
    table = {}
    try:
        from core.geo import REGIONS, DISTRICTS
        for src_map in (REGIONS, DISTRICTS):
            for oblast, cities in src_map.items():
                bucket = table.setdefault(oblast, {})
                for c in cities:
                    key = norm(c)
                    if not key:
                        continue
                    # Эң толук аталышты калтырабыз: «Аксы району»
                    # «Аксы» дегенден түшүнүктүү
                    if key not in bucket or len(c) > len(bucket[key]):
                        bucket[key] = c
    except Exception as e:
        print("[web] шаарлардын тизмеси катасы:", e)

    table.setdefault("Бишкек", {norm("Бишкек"): "Бишкек"})
    return {o: sorted(d.items(), key=lambda kv: kv[1])
            for o, d in table.items()}


ALL_CITIES = _all_cities()

# Бишкек тизменин башында турсун — эң көп колдонулган жер
OBLAST_LIST = ["Бишкек"] + [o for o in ALL_OBLASTS if o != "Бишкек"]


def _obl_of(city):
    """Шаардын облусу. Бишкек өзүнчө турат."""
    if city == "Бишкек":
        return "Бишкек"
    return CITY_OBLAST.get(city) or "Башка"


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


# Кыска атоо — index() ичинде көп колдонулат
t_ = _t


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


def _ago(ts, lang="ky"):
    """«2 саат мурун» деген кыска жазуу.

    Базада created_at TIMESTAMP болуп турат. Убакыт өтпөсө «азыр эле».
    """
    if not ts:
        return ""
    try:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        secs = (datetime.now() - ts).total_seconds()
    except Exception:
        return ""
    if secs < 60:
        return "азыр эле" if lang != "ru" else "только что"
    mins = int(secs // 60)
    if mins < 60:
        return f"{mins} мүнөт мурун" if lang != "ru" else f"{mins} мин. назад"
    hours = mins // 60
    if hours < 24:
        return f"{hours} саат мурун" if lang != "ru" else f"{hours} ч. назад"
    days = hours // 24
    return f"{days} күн мурун" if lang != "ru" else f"{days} дн. назад"


def _mask_phone(d):
    """«996777773125» → «+996 777 *** 125»."""
    if not d:
        return ""
    if len(d) == 12 and d.startswith("996"):
        return f"+996 {d[3:6]} *** {d[-3:]}"
    return "+" + d[:4] + " *** " + d[-2:]


# ── Карточка: калган мөөнөт жана «Бүгүн/Эртең»ди кайра эсептөө ──────
_MONTHS_KY = ["январь", "февраль", "март", "апрель", "май", "июнь",
              "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
_MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
_DAY_WORDS = {-1: ("Кечээ", "Вчера"), 0: ("Бүгүн", "Сегодня"),
              1: ("Эртең", "Завтра"), 2: ("Бүрсүгүнү", "Послезавтра")}
_DATE_RE = re.compile(r"^\s*(Бүгүн|Эртең)\s*·\s*(\d{1,2})-([^\s·]+)\s*$")
_BISHKEK = timedelta(hours=6)          # Кыргызстан: UTC+6, жайкы убакыт жок


def _as_dt(ts):
    if isinstance(ts, str):
        return datetime.fromisoformat(ts)
    return ts


def _left(ts, lang="ky"):
    """«⏳ 2 саат калды» — жарыя канча убакыттан кийин өчөт."""
    try:
        ts = _as_dt(ts)
        hours = getattr(posts, "POST_LIFETIME_HOURS", 24)
        secs = (ts + timedelta(hours=hours) - datetime.now()).total_seconds()
    except Exception:
        return ""
    ru = lang == "ru"
    if secs <= 0:
        return "⏳ скоро удалится" if ru else "⏳ жакында өчөт"
    mins = int(secs // 60)
    if mins < 60:
        mins = max(mins, 1)
        return f"⏳ осталось {mins} мин." if ru else f"⏳ {mins} мүнөт калды"
    h = mins // 60
    return f"⏳ осталось {h} ч." if ru else f"⏳ {h} саат калды"


def _date_label(text, created, lang="ky"):
    """«Бүгүн · 20-сентябрь» → бүгүнкү күнгө карата кайра эсептелет.

    Жарыя берилгенде «Бүгүн» деп жазылат да, эртеси да «Бүгүн» бойдон
    калчу. Эми жол жүрүүчү күн менен бүгүнкү күндүн айырмасы саналат.
    Туура келбеген текст (кол менен жазылган ж.б.) мурункудай көрсөтүлөт.
    """
    m = _DATE_RE.match(str(text or ""))
    if not m or m.group(3) not in _MONTHS_KY:
        return None
    try:
        day, month = int(m.group(2)), _MONTHS_KY.index(m.group(3)) + 1
        made = (_as_dt(created) + _BISHKEK).date()
        trip = made.replace(month=month, day=day)
        if (trip - made).days < -300:          # декабрда берилген январь сапары
            trip = trip.replace(year=trip.year + 1)
        today = (datetime.utcnow() + _BISHKEK).date()
    except Exception:
        return None
    diff = (trip - today).days
    ru = lang == "ru"
    word = _DAY_WORDS.get(diff, (None, None))[1 if ru else 0]
    date = f"{day} {_MONTHS_RU[month - 1]}" if ru else f"{day}-{_MONTHS_KY[month - 1]}"
    return f"{word} · {date}" if word else date


def _card(p):
    d = _digits(p.get("phone"))
    lang = _lang()
    return {
        "id": p.get("id"),
        "photo": bool(p.get("photo_id") or p.get("photo_url")),
        "ago": _ago(p.get("created_at"), lang),
        "left": _left(p.get("created_at"), lang),
        "views": p.get("views") or 0,
        "name": p.get("name") or "",
        "car": p.get("car") or "",
        "date": (_date_label(p.get("date_text"), p.get("created_at"), lang)
                 or _v(p.get("date_text"))),
        "time": _v(p.get("time_text")),
        "seats": p.get("seats") or "",
        "price": _v(p.get("price")),
        "comment": p.get("comment") or "",
        "is_vip": bool(p.get("is_vip")),
        # Номердин өзү HTML'ге чыкпайт — /phone/<id> аркылуу гана.
        "has_phone": bool(d),
        "phone_mask": _mask_phone(d),
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
        "wa_bot_url": f"/wa?text=/start",
        "channel_url": CHANNEL_LINK,
        # «Жарыя берүү» бетинен ботко ТҮЗ кирүү — ролу менен кошо.
        # Telegram start-параметрди өзү берет, WhatsApp'та кабар
        # талаасына даяр текст коюлат.
        "tg_post_driver": f"https://t.me/{BOT_USERNAME}?start=postd",
        "tg_post_passenger": f"https://t.me/{BOT_USERNAME}?start=postp",
        "wa_post_driver": (f"/wa"
                           f"?text={quote('Жарыя берем: айдоочу')}"),
        "wa_post_passenger": (f"/wa"
                              f"?text={quote('Жарыя берем: жүргүнчү')}"),
        # «Кабинет» бетинен ботко төлөм бөлүмүнө түз кирүү
        "tg_myposts": f"https://t.me/{BOT_USERNAME}?start=myposts",
        "wa_myposts": (f"/wa"
                       f"?text={quote('Менин жарыяларым')}"),
        "tg_balance": f"https://t.me/{BOT_USERNAME}?start=balance",
        "wa_balance": (f"/wa"
                       f"?text={quote('Менин балансым')}"),
        "tg_pay": f"https://t.me/{BOT_USERNAME}?start=pay",
        "wa_pay": (f"/wa"
                   f"?text={quote('Төлөм төлөймүн')}"),
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

def _row_ok(r, cat, obl, fo, fc, to, tc, q, city=""):
    """Багыт ушул чыпкалардын баарына дал келеби?"""
    if cat != "all" and r["cat"] != cat:
        return False
    if obl and r["obl"] != obl:
        return False
    if fo and r["fo"] != fo:
        return False
    if fc and norm(r["from_city"]) != fc:
        return False
    if to and r["to"] != to:
        return False
    if tc and norm(r["to_city"]) != tc:
        return False
    if city and city not in (norm(r["from_city"]), norm(r["to_city"])):
        return False
    if q and not _matches(q, r["from_city"], r["to_city"]):
        return False
    return True


@app.route("/")
def index():
    cat = request.args.get("cat") or "all"
    obl = (request.args.get("obl") or "").strip()
    q = (request.args.get("q") or "").strip()
    city = (request.args.get("city") or "").strip()
    # Кеңейтилген чыпка: кайдан → кайда
    f_obl = (request.args.get("fobl") or "").strip()
    f_city = (request.args.get("fcity") or "").strip()
    t_obl = (request.args.get("tobl") or "").strip()
    t_city = (request.args.get("tcity") or "").strip()

    # Кеңири издөө «Район/шаар аралык» бөлүмүндө гана иштейт.
    # Бишкек багыттарында маршруттун бир жагы ансыз да белгилүү,
    # ошондуктан «кайдан → кайда» тандоосу керексиз. Категория
    # алмашканда чыпкалар тазаланат — жашырынып туруп иштебеши үчүн.
    show_filter = cat == "local"
    if not show_filter:
        f_obl = f_city = t_obl = t_city = ""

    rows = driver_routes()
    for r in rows:
        r["cat"] = _category_of(r)
        r["obl"] = _oblast_of(r)
        r["fo"] = _obl_of(r["from_city"])
        r["to"] = _obl_of(r["to_city"])

    # Облус алмашса, ичиндеги шаар тандоосу күчүн жоготот.
    # f_city — «ачкыч» (мис. «аксы»), ошондуктан облустун
    # тизмесинде бар-жогун ачкыч боюнча текшеребиз.
    def _in_oblast(key, oblast):
        return any(k == key for k, _ in ALL_CITIES.get(oblast, []))

    if f_city and f_obl and not _in_oblast(f_city, f_obl):
        f_city = ""
    if t_city and t_obl and not _in_oblast(t_city, t_obl):
        t_city = ""

    def cnt(**over):
        """Ушул чыпка коюлса, канча жарыя калат?

        Тизмелердеги сандар ушундан чыгат — адам бош жыйынтыкка
        чейин барбашы үчүн.
        """
        st = dict(cat=cat, obl=obl, fo=f_obl, fc=f_city,
                  to=t_obl, tc=t_city, q=q, city=city)
        st.update(over)
        return sum(r["n"] for r in rows if _row_ok(r, **st))

    # ---- Тизмелерди курабыз ----
    fo_opts = [("", t_("Бүт Кыргызстан", "Весь Кыргызстан"), cnt(fo="", fc=""))]
    for o in OBLAST_LIST:
        fo_opts.append((o, o, cnt(fo=o, fc="")))

    fc_opts = []
    if f_obl:
        fc_opts.append(("", t_("Бүт облус", "Вся область"), cnt(fc="")))
        for key, label in ALL_CITIES.get(f_obl, []):
            fc_opts.append((key, label, cnt(fc=key)))

    to_opts = [("", t_("Бүт Кыргызстан", "Весь Кыргызстан"), cnt(to="", tc=""))]
    for o in OBLAST_LIST:
        to_opts.append((o, o, cnt(to=o, tc="")))

    tc_opts = []
    if t_obl:
        tc_opts.append(("", t_("Бүт облус", "Вся область"), cnt(tc="")))
        for key, label in ALL_CITIES.get(t_obl, []):
            tc_opts.append((key, label, cnt(tc=key)))

    # Категориялардын саны — карточкалар да чыпкаларды эске алат
    cat_counts = {k: cnt(cat=k) for k in ("all", "to", "from", "local")}

    # Облус чиптери — БАРДЫГЫ ар дайым көрүнөт, жарыясы жок болсо «0».
    obl_counts = {name: cnt(obl=name) for name in ALL_OBLASTS}
    oblasts = sorted(obl_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    districts = []
    if cat == "local":
        src = ALL_CITIES.get(obl, []) if obl else [p for v in ALL_CITIES.values() for p in v]
        seen = set()
        for key, label in src:
            if key in seen:
                continue
            seen.add(key)
            c = cnt(city=key)
            if obl or c:
                districts.append((key, label, c))

    # Акыркы тизме — бардык чыпкалар кошо
    sel = [r for r in rows
           if _row_ok(r, cat, obl, f_obl, f_city, t_obl, t_city, q, city=city)]

    # Издөө боюнча эч нерсе табылбаса — жакын аталыштарды сунуштайбыз
    suggest = []
    if q and not sel:
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

    # Чыпкалардын бирөө коюлганбы? (шаблондо «тазалоо» баскычы үчүн)
    has_filter = bool(obl or f_obl or f_city or t_obl or t_city or q)
    # Блоктун ИЧИНДЕГИ чыпкалар гана. Облус чиби менен издөө сабы
    # блоктон тышкары турат, ошондуктан аларды санабайбыз — болбосо
    # чип басылганда блок бекеринен ачылып калат.
    filter_n = sum(1 for v in (f_obl, f_city, t_obl, t_city) if v)

    # Блок ачык турабы? Ар дайым ЖАБЫК — колдонуучу өзү басканда гана
    # ачылат. Ичиндеги тизмени тандаганда форма «flt=1» белгисин
    # жиберет, ошондуктан иштеп жатканда жабылып калбайт.
    # Карточка, чип же издөө — баары жабык калтырат.
    box_open = request.args.get("flt") == "1"

    def link(**over):
        """Учурдагы чыпкаларды сактап, бирөөнү гана алмаштырган шилтеме."""
        st = {"cat": cat, "obl": obl, "city": city, "fobl": f_obl, "fcity": f_city,
              "tobl": t_obl, "tcity": t_city, "q": q, "lang": _lang()}
        st.update(over)
        parts = [f"{k}={quote(str(v))}" for k, v in st.items() if v]
        return "/?" + "&".join(parts)

    html = render_template("index.html",
                           routes=sel,
                           cat=cat,
                           cat_counts=cat_counts,
                           oblasts=oblasts, districts=districts, city=city,
                           obl=obl,
                           q=q,
                           suggest=suggest,
                           f_obl=f_obl, f_city=f_city,
                           t_obl=t_obl, t_city=t_city,
                           fo_opts=fo_opts, fc_opts=fc_opts,
                           to_opts=to_opts, tc_opts=tc_opts,
                           has_filter=has_filter,
                           all_cities=ALL_CITIES,
                           oblast_list=OBLAST_LIST,
                           filter_n=filter_n,
                           box_open=box_open,
                           show_filter=show_filter,
                           link=link,
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


@app.route("/myposts")
def myposts_page():
    """«📋 Менин жарыяларым» — эки ботко өтүү."""
    html = render_template("myposts.html", **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/post")
def post_page():
    """«➕ Жарыя берүү» — эки ботко өтүү."""
    html = render_template("post.html", **_base_ctx())
    return _with_lang(make_response(html))


# Telegram шилтемеси ~1 саат жашайт, ошондуктан кештейбиз
_PHOTO_CACHE = {}      # post_id -> (url, качан алынды)
_PHOTO_TTL = 45 * 60   # 45 мүнөт


@app.route("/photo/<int:post_id>")
def post_photo(post_id):
    """Жарыянын сүрөтүн көрсөтөт.

    Эки булак болушу мүмкүн:
      photo_url — WhatsApp берген ачык шилтеме, түз багыттайбыз
      photo_id  — Telegram'дын file_id'си, браузер аны түшүнбөйт.
                  Ошондуктан getFile аркылуу түз шилтеме алабыз.

    Боттун токени эч качан браузерге чыкпайт: биз шилтемени өзүбүз
    алып, колдонуучуну ошого багыттайбыз.
    """
    import time
    from flask import redirect, abort

    p = posts.get_post(post_id)
    if not p or not p.get("active"):
        abort(404)

    if p.get("photo_url"):
        return redirect(p["photo_url"], code=302)

    fid = p.get("photo_id")
    if not fid:
        abort(404)

    hit = _PHOTO_CACHE.get(post_id)
    now = time.time()
    if hit and now - hit[1] < _PHOTO_TTL:
        return _proxy_photo(hit[0])

    from core import channel
    url = channel.file_url(fid)
    if not url:
        abort(404)
    _PHOTO_CACHE[post_id] = (url, now)
    return _proxy_photo(url)


def _proxy_photo(url):
    """Сүрөттү сервер өзү берет.

    Мурда браузер Telegram'га багытталчу, бирок ал шилтеменин ичинде
    боттун токени турат — ар ким көрө алмак. Эми байттарды өзүбүз
    өткөрөбүз, токен эч качан сыртка чыкпайт.
    """
    import requests
    from flask import Response, abort
    try:
        r = requests.get(url, timeout=20, stream=True)
        if r.status_code != 200:
            abort(404)
        return Response(
            r.iter_content(8192),
            mimetype=r.headers.get("Content-Type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600"})
    except Exception as e:
        print("[web] сүрөт берүү катасы:", e)
        abort(404)


@app.route("/push/key")
def push_key():
    """Браузерге ачык VAPID ачкычын берет.

    Ачкыч ачык болушу керек — браузер аны жазылуу үчүн колдонот.
    Жашыруун ачкыч бул жерде эч качан чыкпайт.
    """
    from flask import jsonify
    try:
        from core import push
        return jsonify({"key": push.VAPID_PUBLIC, "on": push.enabled()})
    except Exception:
        return jsonify({"key": "", "on": False})


@app.route("/push/routes", methods=["POST"])
def push_routes():
    """Ушул браузер кайсы багыттарга жазылган."""
    data = request.get_json(silent=True) or {}
    ep = (data.get("endpoint") or "").strip()
    if not ep:
        return jsonify({"routes": []})
    from core import push
    return jsonify({"routes": push.routes_of(ep)})


@app.route("/push/subscribe", methods=["POST"])
def push_subscribe():
    """Багытка жазылуу."""
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    sub = data.get("sub") or {}
    frm = (data.get("from") or "").strip()
    to = (data.get("to") or "").strip()
    if not (sub and frm and to):
        return jsonify({"ok": False}), 400
    from core import push
    ok = push.subscribe(sub, frm, to, _lang())
    return jsonify({"ok": bool(ok)})


@app.route("/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    """Жазылуудан баш тартуу."""
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    ep = (data.get("endpoint") or "").strip()
    if not ep:
        return jsonify({"ok": False}), 400
    frm = (data.get("from") or "").strip() or None
    to = (data.get("to") or "").strip() or None
    from core import push
    return jsonify({"ok": bool(push.unsubscribe(ep, frm, to))})


@app.route("/view/<int:post_id>", methods=["POST"])
def view_post(post_id):
    """Көрүү эсептегичи.

    Браузер ар бир жарыяны БИР ЖОЛУ гана билдирет — ал жагы
    route.html'деги кичине скриптте (localStorage) чечилет.
    Ошондуктан бетти жаңырткан сайын сан өспөйт.
    """
    posts.bump_views(post_id)
    return "", 204


# ── Номерди ачуу: скрейперлерден коргоо ─────────────────────────
# Номер барактын HTML'инде жок; баскыч басылганда ушул жерден алынат.
# Бир IP'ге саатына PHONE_LIMIT номер — адамга жетет, скрейперге жетпейт.
import threading as _threading
import time as _time

PHONE_LIMIT = 30
_PHONE_HITS = {}
_PHONE_LOCK = _threading.Lock()


def _client_ip():
    """Railway проксиси чыныгы IP'ни X-Real-IP же X-Forwarded-For'до берет."""
    ip = request.headers.get("X-Real-IP", "").strip()
    if not ip:
        xff = request.headers.get("X-Forwarded-For", "")
        ip = xff.split(",")[-1].strip() if xff else ""
    return ip or request.remote_addr or "?"


def _phone_allowed(ip):
    now = _time.time()
    with _PHONE_LOCK:
        hits = [t for t in _PHONE_HITS.get(ip, ()) if now - t < 3600]
        if len(hits) >= PHONE_LIMIT:
            _PHONE_HITS[ip] = hits
            return False
        hits.append(now)
        _PHONE_HITS[ip] = hits
        if len(_PHONE_HITS) > 5000:          # эстутум толбосун
            for k in [k for k, v in _PHONE_HITS.items()
                      if not v or now - v[-1] > 3600]:
                _PHONE_HITS.pop(k, None)
    return True


@app.route("/phone/<int:post_id>", methods=["POST"])
def reveal_phone(post_id):
    """Жарыянын номерин берет (Чалуу / Telegram / WhatsApp басылганда)."""
    from flask import jsonify
    ip = _client_ip()
    if not _phone_allowed(ip):
        print(f"[web] номер чеги: {ip}")
        return jsonify(error="limit"), 429
    p = posts.get_post(post_id)
    d = _digits(p.get("phone")) if p and p.get("active") else ""
    if not d:
        return jsonify(error="none"), 404
    resp = jsonify(phone=f"+{d}", tel=f"tel:+{d}",
                   tg=f"https://t.me/+{d}", wa=f"https://wa.me/{d}")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/wa")
def wa_redirect():
    """WhatsApp ботуна багыттоо — номер шилтемелерде көрүнбөйт.

    /wa?text=REF12 → https://wa.me/<WA_BOT_NUMBER>?text=REF12
    Номер алмашса, WA_BOT_NUMBER'ди гана өзгөртөсүз — эски
    шилтемелердин баары жаңы номерге барат.
    """
    from flask import redirect
    qs = request.query_string.decode("utf-8", "ignore")
    url = f"https://wa.me/{WA_BOT_NUMBER}" + (f"?{qs}" if qs else "")
    return redirect(url, code=302)


@app.route("/favorites")
def favorites_page():
    """«❤️ Тандалгандар» — телефондун өзүндө сакталат.

    Каттоо жок болгондуктан сервер эч нерсе билбейт: тизме
    браузердин эсинде (localStorage) турат жана ошол жерден
    чыгарылат.
    """
    html = render_template("favorites.html", **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/balance")
def balance_page():
    """«💼 Менин балансым» — ботко багыттайт.

    Сайт колдонуучуну тааныбайт (каттоо жок), ошондуктан балансты
    өзү көрсөтө албайт. Ботто болсо номер ырасталган — ал бардыгын
    билет.
    """
    html = render_template("balance.html", **_base_ctx())
    return _with_lang(make_response(html))


@app.route("/pay")
def pay_page():
    """«💳 Төлөм төлөймүн» — эки ботко өтүү.

    Төлөм сайтта кабыл алынбайт: телефон ырастоо, чек текшерүү жана
    админ ырастоосу боттордо жүргүзүлөт. Ошондуктан бул бет жөн
    гана ботко багыттайт.
    """
    html = render_template("pay.html", **_base_ctx())
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
        from core.texts import (GUIDE, FAQ_HOWTO, FAQ_POST, FAQ_FREE,
                                FAQ_SEARCH, FAQ_PAY, FAQ_CONTACT,
                                FAQ_SAFETY, FAQ_TROUBLE, FAQ_RULES,
                                FAQ_PRIVACY, DRIVER_SAFETY)
        blocks = [
            (_t("📖 Нускама", "📖 Инструкция"), tr_render(GUIDE, lang)),
            (_t("➕ Жарыя кантип берем?", "➕ Как дать объявление?"),
             tr_render(FAQ_HOWTO, lang)),
            (_t("📝 Жарыя жөнүндө", "📝 Об объявлении"), tr_render(FAQ_POST, lang)),
            (_t("🎁 Акысыз мүмкүнчүлүк", "🎁 Бесплатный доступ"), tr_render(FAQ_FREE, lang)),
            (_t("🔍 Издөө", "🔍 Поиск"), tr_render(FAQ_SEARCH, lang)),
            (_t("💳 Төлөм жана баалар", "💳 Оплата и цены"),
             tr_render(FAQ_PAY, lang)),
            (_t("📞 Байланыш", "📞 Связь"), tr_render(FAQ_CONTACT, lang)),
            (_t("🛡 Коопсуздук", "🛡 Безопасность"), tr_render(FAQ_SAFETY, lang)),
            (_t("🚦 Айдоочунун коопсуздугу", "🚦 Безопасность водителя"),
             tr_render(DRIVER_SAFETY, lang)),
            (_t("🛠 Көйгөйлөр жана чечими", "🛠 Проблемы и решения"),
             tr_render(FAQ_TROUBLE, lang)),
            (_t("📜 Колдонуу эрежелери", "📜 Правила использования"),
             tr_render(FAQ_RULES, lang)),
            (_t("🔒 Купуялык", "🔒 Конфиденциальность"),
             tr_render(FAQ_PRIVACY, lang)),
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
    # Продакшен сервер. waitress жок болсо (мис. Termux) — эски жол
    try:
        from waitress import serve
    except ImportError:
        serve = None
    if serve:
        print("[web] waitress сервери башталды")
        serve(app, host=host, port=port, threads=8)
    else:
        app.run(host=host, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    run()
