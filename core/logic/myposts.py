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


# ============ ЖҮРГҮНЧҮЛӨРДҮ ЧОГУЛТУУ (САЙТ АРКЫЛУУ) ============
# Бот эки шилтеме берет — калганынын баары сайтта.
import os as _pk_os
from core import pickup as _pickup

PICKUP_LOC_PREFIX = "📍LOC:"     # адаптерлер локацияны ушул префикс менен берет


def pickup_button(messenger, msg, account):
    act = msg.button_action or ""
    if act.startswith("pku:start:"):
        try:
            return pickup_start(messenger, msg, account, int(act.split(":")[2]))
        except ValueError:
            pass
    return _say(messenger, msg, account, L(
        "🗺 Эми чогултуу сайтта иштейт — «📄 Менин посторум» бөлүмүнөн "
        "«🗺 Жүргүнчүлөрдү чогултуу» баскычын басыңыз.",
        "🗺 Теперь сбор работает на сайте — в «📄 Мои объявления» нажмите "
        "«🗺 Жүргүнчүлөрдү чогултуу»."), back_kb())


def pickup_start(messenger, msg, account, post_id):
    """Сапарга эки шилтеме берет: жүргүнчүлөргө жана айдоочуга."""
    p = posts.get_post(post_id)
    if not p or p["account_id"] != account["account_id"] or p["role"] != "driver":
        return _say(messenger, msg, account, L(
            "❌ Жарыя табылган жок.", "❌ Объявление не найдено."), back_kb())
    try:
        token, mtoken = _pickup.create(post_id, account["account_id"])
    except Exception as e:
        print("Чогултуу шилтемеси катасы:", e)
        return _say(messenger, msg, account, L(
            "⚠️ Азыр шилтеме түзүлбөй жатат. Бир аздан кийин кайталаңыз.",
            "⚠️ Сейчас не удалось создать ссылку. Попробуйте позже."), back_kb())

    base = (globals().get("SITE_URL")
            or _pk_os.environ.get("SITE_URL")
            or "https://taxi-bot-taxirobot.up.railway.app").rstrip("/")
    base = base.replace("http://", "https://")   # геолокация https талап кылат
    _say(messenger, msg, account, L(
        f"🗺 <b>Жүргүнчүлөрдү чогултуу</b>\n"
        f"{p['from_city']} ➡️ {p['to_city']}\n\n"
        f"Картаңызды ачыңыз:\n{base}/pickup/m/{mtoken}\n\n"
        f"Ал жерден «📤 Жүргүнчүгө жөнөтүү» басып, даяр кабарды ар бир "
        f"жүргүнчүгө жөнөтөсүз. Алар бир баскыч басканда ошол эле "
        f"картада номерленип чыгат, андан соң навигатор аларды эң кыска "
        f"жол менен чогултуп берет.\n\n"
        f"ℹ️ Толук нускама: 🆘 Жардам → ❓ Суроолор → "
        f"🗺 Жүргүнчүлөрдү чогултуу\n"
        f"<i>Бул шилтемени жүргүнчүлөргө бербеңиз — ал сиздики. "
        f"Локациялар 3 күндөн кийин өзү өчөт.</i>",
        f"🗺 <b>Сбор пассажиров</b>\n"
        f"{p['from_city']} ➡️ {p['to_city']}\n\n"
        f"Откройте свою карту:\n{base}/pickup/m/{mtoken}\n\n"
        f"На ней нажмите «📤 Отправить пассажиру» — готовое сообщение "
        f"уйдёт каждому пассажиру. Они отметятся одним нажатием и "
        f"появятся на этой же карте с номерами, а навигатор проведёт "
        f"вас по самому короткому пути.\n\n"
        f"ℹ️ Полная инструкция: 🆘 Помощь → ❓ Вопросы → "
        f"🗺 Жүргүнчүлөрдү чогултуу\n"
        f"<i>Эту ссылку пассажирам не давайте — она ваша. "
        f"Локации удаляются через 3 дня.</i>"), back_kb())


def pickup_location(messenger, msg, account, text):
    """Эски жол: ботко forward кылынган 📍 локация."""
    _say(messenger, msg, account, L(
        "📍 Эми локацияны ботко жөнөтүүнүн кереги жок.\n\n"
        "«📄 Менин посторум» → «🗺 Жүргүнчүлөрдү чогултуу» басып, "
        "шилтемени жүргүнчүлөргө жөнөтүңүз — алар өздөрү белгилейт.",
        "📍 Теперь локацию боту пересылать не нужно.\n\n"
        "Нажмите «📄 Мои объявления» → «🗺 Жүргүнчүлөрдү чогултуу» и "
        "отправьте ссылку пассажирам — они отметятся сами."), hint=True)


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


