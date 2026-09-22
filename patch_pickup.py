# -*- coding: utf-8 -*-
# patch_pickup.py — «🗺 Жүргүнчүлөрдү чогултуу» (logic v101-pickup, tg v12-loc, wa v4-loc)
# Иштетүү: cd ~/taxi-bot && python patch_pickup.py
import ast, sys

def patch(path, pairs):
    src = open(path, encoding="utf-8").read()
    if "PICKUP" in src or "pickup" in src:
        print(f"⏭  {path}: мурда патчталган, өткөрүлдү")
        return
    for old, new in pairs:
        if src.count(old) != 1:
            sys.exit(f"❌ {path}: издеген сап {src.count(old)} жолу табылды:\n{old[:80]}")
        src = src.replace(old, new)
    ast.parse(src)
    open(path, "w", encoding="utf-8").write(src)
    print(f"✅ {path}")

# ---------------- core/logic/myposts.py ----------------
PICKUP_CODE = r'''

# ============ ЖҮРГҮНЧҮЛӨРДҮ ЧОГУЛТУУ МАРШРУТУ ============
# Айдоочу жүргүнчүлөрдөн келген 📍 локацияларды ботко forward кылат,
# бот эң кыска иретти таап, Yandex/Google навигатор шилтемесин берет.
# Локациялар базага ЖАЗЫЛБАЙТ — эс тутумда гана, 6 сааттан кийин өчөт.
import math as _pk_math
import itertools as _pk_it
import time as _pk_time

PICKUP_LOC_PREFIX = "📍LOC:"      # адаптерлер локацияны ушул текст менен жөнөтөт
PICKUP = {}                       # user_id -> {"post_id", "pts", "ts"}
PICKUP_TTL = 6 * 3600
PICKUP_MAX = 7                    # 7! = 5040 ирет — бат эсептелет

# Жол багытын аныктоо үчүн шаарлардын болжолдуу координаттары
PICKUP_CITIES = {
    "бишкек": (42.8746, 74.5698), "ош": (40.5283, 72.7985),
    "жалал-абад": (40.9333, 73.0000), "нарын": (41.4287, 75.9911),
    "каракол": (42.4907, 78.3936), "талас": (42.5228, 72.2427),
    "баткен": (40.0625, 70.8194), "чолпон-ата": (42.6496, 77.0826),
    "токмок": (42.8421, 75.3015), "кара-балта": (42.8142, 73.8481),
    "балыкчы": (42.4600, 76.1870), "кызыл-кыя": (40.2567, 72.1278),
    "озгон": (40.7667, 73.3000), "кант": (42.8911, 74.8508),
    "базар-коргон": (41.0375, 72.7458), "кочкор": (42.2150, 75.7528),
    "токтогул": (41.8722, 72.9406), "кара-суу": (40.7033, 72.8697),
}


def _pk_city(name):
    n = (name or "").lower().replace("ө", "о").replace("ү", "у").replace("ң", "н")
    # узун аттарды биринчи текшеребиз: «кара-суу» «ош» болуп калбасын
    for key in sorted(PICKUP_CITIES, key=len, reverse=True):
        if key in n:
            return PICKUP_CITIES[key]
    return None


def _pk_km(a, b):
    la1, lo1, la2, lo2 = map(_pk_math.radians, (a[0], a[1], b[0], b[1]))
    h = (_pk_math.sin((la2 - la1) / 2) ** 2 +
         _pk_math.cos(la1) * _pk_math.cos(la2) * _pk_math.sin((lo2 - lo1) / 2) ** 2)
    return 6371 * 2 * _pk_math.asin(_pk_math.sqrt(h))


def _pk_order(pts, dest):
    """Бардык ирет-тартипти салыштырып, эң кыскасын тандайт.
    dest белгилүү болсо — акыркы жүргүнчү ошол багытка эң ыңгайлуу болот."""
    if len(pts) < 2:
        return list(pts)
    best, best_len = None, float("inf")
    for perm in _pk_it.permutations(pts):
        d = sum(_pk_km(perm[i], perm[i + 1]) for i in range(len(perm) - 1))
        if dest:
            d += _pk_km(perm[-1], dest)
        if d < best_len:
            best, best_len = perm, d
    return list(best)


def _pk_state(user_id):
    st = PICKUP.get(user_id)
    if st and _pk_time.time() - st["ts"] > PICKUP_TTL:
        PICKUP.pop(user_id, None)
        return None
    return st


def _pk_kb():
    return Keyboard(rows=[
        [Button("✅ Маршрут түз", "pku:go"), Button("🧹 Тазалоо", "pku:clr")],
        [_back_btn()],
    ])


def pickup_button(messenger, msg, account):
    act = msg.button_action or ""
    if act.startswith("pku:start:"):
        try:
            return pickup_start(messenger, msg, account, int(act.split(":")[2]))
        except ValueError:
            pass
    if act == "pku:go":
        return pickup_build(messenger, msg, account)
    if act == "pku:clr":
        st = _pk_state(msg.user_id)
        if st:
            st["pts"] = []
        return _say(messenger, msg, account, L(
            "🧹 Чекиттер тазаланды. Жаңы локацияларды жөнөтө бериңиз.",
            "🧹 Точки очищены. Можно отправлять новые локации."), _pk_kb())
    return _say(messenger, msg, account, L(
        "❌ Бул баскыч эскирип калды. /start",
        "❌ Кнопка устарела. /start"), back_kb())


def pickup_start(messenger, msg, account, post_id):
    p = posts.get_post(post_id)
    if not p or p["account_id"] != account["account_id"] or p["role"] != "driver":
        return _say(messenger, msg, account, L(
            "❌ Жарыя табылган жок.", "❌ Объявление не найдено."), back_kb())
    PICKUP[msg.user_id] = {"post_id": post_id, "pts": [], "ts": _pk_time.time()}
    _say(messenger, msg, account, L(
        f"🗺 <b>Жүргүнчүлөрдү чогултуу</b>\n"
        f"{p['from_city']} ➡️ {p['to_city']}\n\n"
        f"Жүргүнчүлөр сизге жөнөткөн 📍 локацияларды ушул жерге "
        f"forward кылыңыз — ар бирин өзүнчө. Эң көп {PICKUP_MAX} чекит.\n\n"
        f"Баары кошулгандан кийин «✅ Маршрут түз» басыңыз.",
        f"🗺 <b>Сбор пассажиров</b>\n"
        f"{p['from_city']} ➡️ {p['to_city']}\n\n"
        f"Перешлите сюда 📍 локации, которые прислали вам пассажиры — "
        f"каждую отдельно. Максимум {PICKUP_MAX} точек.\n\n"
        f"Когда все добавлены, нажмите «✅ Маршрут түз»."), _pk_kb())


def pickup_location(messenger, msg, account, text):
    try:
        body = text[len(PICKUP_LOC_PREFIX):]
        coords, _, label = body.partition("|")
        lat, lon = (float(x) for x in coords.split(","))
    except ValueError:
        return
    st = _pk_state(msg.user_id)
    if not st:
        return _say(messenger, msg, account, L(
            "📍 Локация алдым. Маршрут түзүү үчүн: 🚗 Айдоочумун → "
            "📄 Менин посторум → 🗺 Жүргүнчүлөрдү чогултуу.",
            "📍 Локация получена. Чтобы построить маршрут: 🚗 Я водитель → "
            "📄 Мои объявления → 🗺 Жүргүнчүлөрдү чогултуу."), hint=True)
    if len(st["pts"]) >= PICKUP_MAX:
        return _say(messenger, msg, account, L(
            f"⚠️ Эң көп {PICKUP_MAX} чекит. «✅ Маршрут түз» басыңыз.",
            f"⚠️ Максимум {PICKUP_MAX} точек. Нажмите «✅ Маршрут түз»."), _pk_kb())
    n = len(st["pts"]) + 1
    label = (label or "").strip()[:40] or f"{n}-жүргүнчү"
    st["pts"].append((lat, lon, label))
    st["ts"] = _pk_time.time()
    _say(messenger, msg, account, L(
        f"✅ {n}-чекит кошулду: {label}",
        f"✅ Точка {n} добавлена: {label}"), _pk_kb())


def pickup_build(messenger, msg, account):
    st = _pk_state(msg.user_id)
    if not st or not st["pts"]:
        return _say(messenger, msg, account, L(
            "📍 Адегенде жүргүнчүлөрдүн локацияларын жөнөтүңүз.",
            "📍 Сначала отправьте локации пассажиров."), _pk_kb())
    p = posts.get_post(st["post_id"]) or {}
    dest = _pk_city(p.get("to_city"))
    order = _pk_order(st["pts"], dest)
    ll = lambda q: f"{q[0]:.6f},{q[1]:.6f}"

    # Баштапкы чекит бош — навигатор айдоочунун азыркы ордунан баштайт
    ypts = [ll(q) for q in order] + ([ll(dest)] if dest else [])
    yandex = "https://yandex.ru/maps/?rtext=~" + "~".join(ypts) + "&rtt=auto"
    if dest:
        g_dest, g_way = ll(dest), [ll(q) for q in order]
    else:
        g_dest, g_way = ll(order[-1]), [ll(q) for q in order[:-1]]
    google = ("https://www.google.com/maps/dir/?api=1&travelmode=driving"
              f"&destination={g_dest}")
    if g_way:
        google += "&waypoints=" + "%7C".join(g_way)
    if msg.platform == "telegram":        # HTML режиминде & качылышы керек
        yandex, google = yandex.replace("&", "&amp;"), google.replace("&", "&amp;")

    lst = "\n".join(f"{i}. {q[2]}" for i, q in enumerate(order, 1))
    tail_ky = f"\nАндан кийин ➡️ {p.get('to_city')}" if dest else ""
    tail_ru = f"\nЗатем ➡️ {p.get('to_city')}" if dest else ""
    _say(messenger, msg, account, L(
        f"🗺 <b>Чогултуу тартиби:</b>\n{lst}{tail_ky}\n\n"
        f"🟡 Yandex Карта:\n{yandex}\n\n🔵 Google Maps:\n{google}",
        f"🗺 <b>Порядок сбора:</b>\n{lst}{tail_ru}\n\n"
        f"🟡 Яндекс Карты:\n{yandex}\n\n🔵 Google Maps:\n{google}"), _pk_kb())
'''

patch("core/logic/myposts.py", [
    ('''            btns.append(Button("⏰ Убакыт", f"tw:{p['id']}"))
        btns.append(Button("❌ Өчүрүү", f"del:{p['id']}"))
        # Айдоочуда үч баскыч: экөө катар, өчүрүү өзүнчө
        if len(btns) == 3:
            kb = Keyboard(rows=[[btns[0], btns[1]], [btns[2]]])''',
     '''            btns.append(Button("⏰ Убакыт", f"tw:{p['id']}"))
            btns.append(Button("🗺 Жүргүнчүлөрдү чогултуу", f"pku:start:{p['id']}"))
        btns.append(Button("❌ Өчүрүү", f"del:{p['id']}"))
        # Айдоочуда: орун+убакыт катар, андан кийин чогултуу, өчүрүү
        if len(btns) == 4:
            kb = Keyboard(rows=[[btns[0], btns[1]], [btns[2]], [btns[3]]])'''),
    ('''def _update_post_field(''', PICKUP_CODE.lstrip("\n") + '''\n\ndef _update_post_field('''),
])

# ---------------- core/logic/router.py ----------------
patch("core/logic/router.py", [
    ('''    text = (msg.text or "").strip()
    if text == "/admin"''',
     '''    text = (msg.text or "").strip()
    # Айдоочу forward кылган 📍 локация (адаптерлер ушул префикс менен берет)
    if text.startswith(PICKUP_LOC_PREFIX):
        return pickup_location(messenger, msg, account, text)
    if text == "/admin"'''),
    ('''    if session:
        # "🏠 Башкы меню" визарддын ичинен да иштеши керек''',
     '''    # «🗺 Жүргүнчүлөрдү чогултуу» баскычтары — визарддан көз карандысыз
    if msg.is_button and (msg.button_action or "").startswith("pku:"):
        return pickup_button(messenger, msg, account)

    if session:
        # "🏠 Башкы меню" визарддын ичинен да иштеши керек'''),
])

# ---------------- adapters/telegram_adapter.py ----------------
patch("adapters/telegram_adapter.py", [
    ('TG_ADAPTER_VERSION = "v11-more"', 'TG_ADAPTER_VERSION = "v12-loc"'),
    ('''@bot.message_handler(func=lambda m: True, content_types=["text"])''',
     '''def _pickup_fwd_name(m):
    """Forward кылынган кабардын ээсинин аты (pyTeleBot'тун ар кандай версиясы үчүн)."""
    o = getattr(m, "forward_origin", None)
    if o is not None:
        u = getattr(o, "sender_user", None)
        if u is not None:
            return u.first_name or ""
        n = getattr(o, "sender_user_name", None)
        if n:
            return n
    u = getattr(m, "forward_from", None)
    if u is not None:
        return u.first_name or ""
    return getattr(m, "forward_sender_name", None) or ""


@bot.message_handler(content_types=["location", "venue"])
def _location(m):
    """📍 Локация — «Жүргүнчүлөрдү чогултуу» үчүн core'го текст катары беребиз."""
    loc = m.location
    parts = [_pickup_fwd_name(m)]
    venue = getattr(m, "venue", None)
    if venue is not None and getattr(venue, "title", None):
        parts.append(venue.title)
    label = " — ".join(x for x in parts if x).replace("|", " ").replace("\\n", " ")
    prefix = getattr(logic, "PICKUP_LOC_PREFIX", "📍LOC:")
    msg = IncomingMessage(user_id=make_uid("telegram", m.from_user.id),
                          platform="telegram",
                          text=f"{prefix}{loc.latitude},{loc.longitude}|{label}")
    logic.handle_update(messenger, msg)


@bot.message_handler(func=lambda m: True, content_types=["text"])'''),
])

# ---------------- adapters/whatsapp_adapter.py ----------------
patch("adapters/whatsapp_adapter.py", [
    ('WA_ADAPTER_VERSION = "v3-ttl"', 'WA_ADAPTER_VERSION = "v4-loc"'),
    ('''    else:
        return   # аудио, видео ж.б. — азырынча эске алынбайт''',
     '''    elif tmsg in ("locationMessage", "liveLocationMessage"):
        # 📍 «Жүргүнчүлөрдү чогултуу» үчүн — core'го текст катары
        ld = md.get("locationMessageData") or md.get("liveLocationMessageData") or {}
        lat, lon = ld.get("latitude"), ld.get("longitude")
        if lat is None or lon is None:
            return
        label = (ld.get("nameLocation") or ld.get("address") or "")
        label = label.replace("|", " ").replace("\\n", " ")
        prefix = getattr(logic, "PICKUP_LOC_PREFIX", "📍LOC:")
        text = f"{prefix}{lat},{lon}|{label}"
    else:
        return   # аудио, видео ж.б. — азырынча эске алынбайт'''),
])

print("\n🎉 Даяр. Текшерүү: git diff --stat, андан кийин git push")
