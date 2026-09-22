# -*- coding: utf-8 -*-
# core/logic/myposts.py — «Менин посторум»: түзөтүү, орундар, убакыт.
# Импорттор жана жалпы аталыштар common.py'де; бул файл
# core/logic/__init__.py аркылуу ошол мейкиндикке жүктөлөт.

# ============ МЕНИН ПОСТОРУМ ============

def post_card(p, lang="ky"):
    """Жарыя карточкасы. lang='ru' болсо — орусча белгилер.

    Базада сакталган маанилер ар дайым КЫРГЫЗЧА: колдонуучу «Бүгүн»,
    «Келишим», «Саат 12:00дө жолго чыгам» деген баскычтарды басканда
    ошол бойдон жазылат. Ошондуктан орусча карточкада аларды котормо
    катмарынан өткөрөбүз — болбосо эки тил аралашып чыгат.
    """
    ru = lang == "ru"

    def v(x):
        """Базадан келген кыргызча маанини керек болсо которот."""
        if not ru or x is None:
            return x
        return render(str(x), "ru")

    vip = " ⭐" if p.get("is_vip") else ""
    if p["role"] == "driver":
        role_tag = "🚗 <b>ВОДИТЕЛЬ</b>" if ru else "🚗 <b>АЙДООЧУ</b>"
    else:
        role_tag = "🧳 <b>ПАССАЖИР</b>" if ru else "🧳 <b>ЖҮРГҮНЧҮ</b>"
    lines = [role_tag,
             f"<b>{p['from_city']} ➡️ {p['to_city']}</b>{vip}",
             (f"🧍 Имя: {p['name']}" if ru else f"🧍 Аты: {p['name']}")]
    if p["role"] == "driver":
        lines += ([f"🚘 Авто: {p['car']}", f"👥 Свободно мест: {p['seats']}",
                   f"💰 Цена: {v(p['price'])}"] if ru else
                  [f"🚘 Унаа: {p['car']}", f"👥 Бош орун: {p['seats']}",
                   f"💰 Баасы: {p['price']}"])
    else:
        lines += ([f"👥 Кол-во людей: {v(p['people_count'])}",
                   f"🎒 Багаж: {v(p['baggage'])}"] if ru else
                  [f"👥 Адам саны: {p['people_count']}", f"🎒 Багаж: {p['baggage']}"])
    lines += [f"📅 {v(p['date_text'])} · ⏰ {v(p['time_text'])}"]
    if p.get("comment"):
        lines.append(f"📝 {p['comment']}")
    return "\n".join(lines)


def show_my_posts(messenger, msg, account, role):
    rows = posts.my_posts(account["account_id"], role)
    if not rows:
        return _say(messenger, msg, account, L(
                    "❌ Сиздин учурда активдүү жарыяңыз жок.",
                    "❌ У вас сейчас нет активных объявлений."), back_kb())
    _say(messenger, msg, account, L("📄 <b>Сиздин активдүү посттор</b>",
                                    "📄 <b>Ваши активные объявления</b>"))
    for p in rows:
        btns = []
        if role == "driver":
            # Айдоочу орун толгон сайын санды азайта алат жана
            # убакытты өзгөртө алат — жарыяны кайра жазуунун кереги жок.
            btns.append(Button("👥 Бош орун", f"sd:{p['id']}"))
            btns.append(Button("⏰ Убакыт", f"tw:{p['id']}"))
            btns.append(Button("🗺 Жүргүнчүлөрдү чогултуу", f"pku:start:{p['id']}"))
        btns.append(Button("❌ Өчүрүү", f"del:{p['id']}"))
        # Айдоочуда: орун+убакыт катар, андан кийин чогултуу, өчүрүү
        if len(btns) == 4:
            kb = Keyboard(rows=[[btns[0], btns[1]], [btns[2]], [btns[3]]])
        else:
            kb = Keyboard.from_flat(btns)
        _say(messenger, msg, account,
             L(post_card(p, "ky"), post_card(p, "ru")), kb)
    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


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


def _update_post_field(post_id, account_id, **fields):
    """Жарыянын талааларын жаңыртат (ээси гана).

    posts.py'де мындай функция жок, ошондуктан базага түз кайрылабыз.
    Ээсин да текшеребиз — башканын жарыясын өзгөртүп коюуга болбойт.
    """
    if not fields:
        return False
    sets = ", ".join(f"{k} = %s" for k in fields)
    vals = list(fields.values()) + [post_id, account_id]
    try:
        with db.db() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE posts SET {sets} WHERE id = %s AND account_id = %s",
                vals)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        print("Жарыяны жаңыртуу катасы:", e)
        return False


def _refresh_channel(post_id):
    """Каналдагы жарыяны жаңы маалымат менен жаңыртат.

    Жарыя каналда турса гана иштейт (channel_msg_id бар болсо).
    Баскычтарды кайра курабыз — editMessageText аларды сактабайт.
    """
    p = posts.get_post(post_id)
    if not p or not p.get("channel_msg_id") or p["role"] != "driver":
        return
    try:
        channel.edit(p["channel_msg_id"],
                     channel_text(p, "driver"),
                     contact_links(p.get("phone"), post_id,
                                   p.get("from_city"), p.get("to_city")),
                     has_photo=bool(_photo_of(p)))
    except Exception as e:
        print("Каналды жаңыртуу катасы:", e)


def ask_new_seats(messenger, msg, account, post_id):
    """«👥 Бош орун» — калган орундун санын тандоо.

    Бир эмес, бир нече жүргүнчү бирден табылышы мүмкүн. Ошондуктан
    санды бирден азайтпай, калган санды түз тандатабыз.
    """
    p = posts.get_post(post_id)
    if not p or p["account_id"] != account["account_id"]:
        return _say(messenger, msg, account, L(
            "❌ Жарыя табылган жок.", "❌ Объявление не найдено."), back_kb())

    rows = [[Button(str(i), f"sset:{post_id}:{i}") for i in range(0, 4)],
            [Button(str(i), f"sset:{post_id}:{i}") for i in range(4, 8)],
            [_back_btn()]]
    _say(messenger, msg, account, L(
        "👥 Азыр канча бош орун калды?\n\n"
        "<i>0 тандасаңыз — унаа толду, жарыя жабылат.</i>",
        "👥 Сколько свободных мест осталось?\n\n"
        "<i>Если выбрать 0 — машина заполнена, объявление закроется.</i>"),
        Keyboard(rows=rows))


def set_new_seats(messenger, msg, account, post_id, left):
    """Тандалган санды сактайт. 0 болсо — жарыя жабылат."""
    p = posts.get_post(post_id)
    if not p or p["account_id"] != account["account_id"]:
        return _say(messenger, msg, account, L(
            "❌ Жарыя табылган жок.", "❌ Объявление не найдено."), back_kb())

    if left <= 0:
        # Унаа толду — жарыянын каналда туруусунун мааниси жок
        posts.deactivate_post(post_id, account["account_id"])
        if p.get("channel_msg_id"):
            channel.delete(p["channel_msg_id"])
        return _say(messenger, msg, account, L(
            "🚗 Унааңыз толду — жарыя жабылды.\n"
            "Жаңы сапарга кайра жарыя бере аласыз.\n\n"
            "🤲 Ак жол каалайбыз!",
            "🚗 Машина заполнена — объявление закрыто.\n"
            "Для новой поездки можно дать объявление снова.\n\n"
            "🤲 Счастливого пути!"), back_kb())

    _update_post_field(post_id, account["account_id"], seats=str(left))
    _refresh_channel(post_id)
    fresh = posts.get_post(post_id)
    _say(messenger, msg, account, L(
        f"✅ Бош орун: <b>{left}</b>\n\n" + post_card(fresh, "ky"),
        f"✅ Свободных мест: <b>{left}</b>\n\n" + post_card(fresh, "ru")),
        back_kb())


def ask_new_time(messenger, msg, account, post_id):
    """«⏰ Убакыт» — жаңы жөнөө убактысын тандоо."""
    p = posts.get_post(post_id)
    if not p or p["account_id"] != account["account_id"]:
        return _say(messenger, msg, account, L(
            "❌ Жарыя табылган жок.", "❌ Объявление не найдено."), back_kb())

    hours = day_hours()
    rows = [[Button(h, f"tset:{post_id}:{h}") for h in hours[k:k + 4]]
            for k in range(0, len(hours), 4)]
    rows.append([Button("🚗 Орун толгондо чыгам", f"tset:{post_id}:full")])
    rows.append([_back_btn()])
    _say(messenger, msg, account, L(
        "⏰ Жаңы убакытты тандаңыз:",
        "⏰ Выберите новое время:"), Keyboard(rows=rows))


def set_new_time(messenger, msg, account, post_id, val):
    """Тандалган жаңы убакытты сактайт жана каналды жаңыртат."""
    p = posts.get_post(post_id)
    if not p or p["account_id"] != account["account_id"]:
        return _say(messenger, msg, account, L(
            "❌ Жарыя табылган жок.", "❌ Объявление не найдено."), back_kb())

    if val == "full":
        new_time = "Орун толгондо жолго чыгам"
    else:
        new_time = f"Саат {val}дө жолго чыгам"

    _update_post_field(post_id, account["account_id"], time_text=new_time)
    _refresh_channel(post_id)
    fresh = posts.get_post(post_id)
    _say(messenger, msg, account, L(
        "✅ Убакыт жаңырды:\n\n" + post_card(fresh, "ky"),
        "✅ Время обновлено:\n\n" + post_card(fresh, "ru")), back_kb())


def delete_post(messenger, msg, account, post_id):
    """Жарыяны өчүрөт — базадан да, каналдан да."""
    p = posts.get_post(post_id)
    ok = posts.deactivate_post(post_id, account["account_id"])
    if ok and p and p.get("channel_msg_id"):
        channel.delete(p["channel_msg_id"])
    _say(messenger, msg, account,
         L("🗑 Жарыя өчүрүлдү." if ok else "❌ Жарыя табылган жок.",
           "🗑 Объявление удалено." if ok else "❌ Объявление не найдено."), back_kb())


