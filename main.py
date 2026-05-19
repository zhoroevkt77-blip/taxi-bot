import os
import telebot
from telebot import types
import sqlite3
import time
import threading
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# ================= КОНФИГУРАЦИЯ =================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN жок!")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003871616356"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "8693522887"))
bot = telebot.TeleBot(TOKEN)

# ================= REGIONS =================
regions = {
    "Баткен облусу": ["Баткен", "Кадамжай", "Лейлек (Раззаков)", "Кызыл-Кыя", "Сүлүктү"],
    "Жалал-Абад облусу": ["Манас", "Сузак", "Базар-Коргон", "Ноокен", "Кара-Көл", "Таш-Көмүр", "Майлуу-Суу", "Ала-Бука", "Аксы", "Чаткал", "Тогуз-Торо"],
    "Нарын облусу": ["Нарын", "Ат-Башы", "Ак-Талаа", "Жумгал", "Кочкор"],
    "Ош облусу": ["Ош", "Кара-Суу", "Араван", "Ноокат", "Өзгөн", "Кара-Кулжа", "Алай", "Чоң-Алай"],
    "Талас облусу": ["Талас", "Бакай-Ата", "Кара-Буура", "Манас району"],
    "Чүй облусу": ["Жайыл", "Токмок", "Кемин"],
    "Ысык-Көл облусу": ["Каракол", "Балыкчы", "Чолпон-Ата", "Түп", "Ак-Суу", "Жети-Өгүз", "Тоң"]
}

region_map = {}
city_map = {}

def build_maps():
    ri = 0
    ci = 0
    for region_name, cities in regions.items():
        ri += 1
        region_map[f"r{ri}"] = region_name
        for city_name in cities:
            ci += 1
            city_map[f"c{ci}"] = city_name

build_maps()

# ================= DB =================
def get_db():
    conn = sqlite3.connect("taxi.db", check_same_thread=False)
    return conn, conn.cursor()

def init_db():
    conn, c = get_db()
    c.execute("""
    CREATE TABLE IF NOT EXISTS drivers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, car TEXT,
        from_city TEXT, to_city TEXT,
        time TEXT, price TEXT,
        phone TEXT, seats TEXT,
        comment TEXT, created_at REAL,
        message_id INTEGER
    )
    """)
    conn.commit()
    conn.close()

def clean_old_records():
    conn, c = get_db()
    cutoff = time.time() - 43200  # 12 саат
    c.execute("SELECT message_id FROM drivers WHERE created_at < ?", (cutoff,))
    rows = c.fetchall()
    for row in rows:
        if row[0]:
            try:
                bot.delete_message(CHANNEL_ID, row[0])
            except Exception:
                pass
    c.execute("DELETE FROM drivers WHERE created_at < ?", (cutoff,))
    conn.commit()
    conn.close()

def auto_clean_loop():
    while True:
        time.sleep(3600)
        clean_old_records()

# ================= USER DATA =================
user_data = {}

def set_data(uid, k, v):
    user_data.setdefault(uid, {})[k] = v

def get_data(uid):
    return user_data.get(uid, {})

def reset(uid):
    user_data.pop(uid, None)

# ================= МЕНЮ =================
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🚗 Айдоочумун", "🔍 Жүргүнчүмүн")
    return kb

@bot.message_handler(commands=["start"])
def start(m):
    reset(m.chat.id)
    bot.send_message(m.chat.id, "🚕 Кош келиңиз!", reply_markup=menu())

@bot.message_handler(commands=["cancel"])
def cancel(m):
    reset(m.chat.id)
    bot.send_message(m.chat.id, "❌ Жокко чыгарылды.", reply_markup=menu())

# ================= ЖҮРГҮНЧҮ =================
@bot.message_handler(func=lambda m: m.text and "Жүргүнчүмүн" in m.text)
def passenger(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="to"))
    kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="from"))
    bot.send_message(m.chat.id, "Маршрут тандаңыз:", reply_markup=kb)

# ================= АЙДООЧУ =================
@bot.message_handler(func=lambda m: m.text == "🚗 Айдоочумун")
def driver(m):
    msg = bot.send_message(m.chat.id, "Атыңыз:")
    bot.register_next_step_handler(msg, d_car)

def d_car(m):
    if m.text == "/cancel":
        cancel(m)
        return
    set_data(m.chat.id, "name", m.text)
    msg = bot.send_message(m.chat.id, "Машинаңыздын маркасы жана модели:")
    bot.register_next_step_handler(msg, d_route)

def d_route(m):
    if m.text == "/cancel":
        cancel(m)
        return
    set_data(m.chat.id, "car", m.text)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="d_to"))
    kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="d_from"))
    bot.send_message(m.chat.id, "Маршрут тандаңыз:", reply_markup=kb)

def d_time(m):
    if m.text == "/cancel":
        cancel(m)
        return
    set_data(m.chat.id, "time", m.text)
    msg = bot.send_message(m.chat.id, "Жол кире акы (сом):")
    bot.register_next_step_handler(msg, d_price)

def d_price(m):
    if m.text == "/cancel":
        cancel(m)
        return
    set_data(m.chat.id, "price", m.text)
    msg = bot.send_message(m.chat.id, "Бош орун саны:")
    bot.register_next_step_handler(msg, d_seats)

def d_seats(m):
    if m.text == "/cancel":
        cancel(m)
        return
    set_data(m.chat.id, "seats", m.text)
    msg = bot.send_message(m.chat.id, "Мобилдик телефон номериңиз:")
    bot.register_next_step_handler(msg, d_phone)

def d_phone(m):
    if m.text == "/cancel":
        cancel(m)
        return
    set_data(m.chat.id, "phone", m.text)
    msg = bot.send_message(m.chat.id, "Комментарий жазыңыз (болбосо — сызыкча коюңуз):")
    bot.register_next_step_handler(msg, d_finish)

def d_finish(m):
    if m.text == "/cancel":
        cancel(m)
        return
    set_data(m.chat.id, "comment", m.text)
    data = get_data(m.chat.id)

    required = ["name", "car", "from", "to", "time", "price", "phone", "seats"]
    for field in required:
        if field not in data:
            bot.send_message(m.chat.id, "❌ Маалымат жетишсиз. Кайрадан баштаңыз.", reply_markup=menu())
            reset(m.chat.id)
            return

    clean_old_records()

    text = (
        "🚗 <b>Айдоочу</b>\n\n"
        f"👤 Аты: {data['name']}\n"
        f"🚘 Машина: {data['car']}\n"
        f"📍 Маршрут: {data['from']} → {data['to']}\n"
        f"⏰ Убакыт: {data['time']}\n"
        f"💰 Баа: {data['price']} сом\n"
        f"🪑 Бош орун: {data['seats']}\n"
        f"📱 Тел: {data['phone']}\n"
        f"💬 Комментарий: {data.get('comment', '-')}\n"
    )

    sent = bot.send_message(CHANNEL_ID, text, parse_mode="HTML")

    conn, c = get_db()
    c.execute("""
        INSERT INTO drivers
        (name,car,from_city,to_city,time,price,phone,seats,comment,created_at,message_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data["name"], data["car"],
        data["from"], data["to"],
        data["time"], data["price"],
        data["phone"], data["seats"],
        data.get("comment", "-"), time.time(),
        sent.message_id
    ))
    conn.commit()
    conn.close()

    bot.send_message(m.chat.id, "✅ Пост чыкты!", reply_markup=menu())
    reset(m.chat.id)

# ================= ОБЛУС / ШААР =================
def show_regions(mode, selected_rcode=None):
    kb = types.InlineKeyboardMarkup()
    for code, name in region_map.items():
        text = f"✅ {name}" if code == selected_rcode else name
        kb.add(types.InlineKeyboardButton(text, callback_data=f"reg|{mode}|{code}"))
    return kb

def show_cities(region_name, mode, selected_ccode=None):
    kb = types.InlineKeyboardMarkup()
    city_list = regions.get(region_name, [])
    for code, name in city_map.items():
        if name in city_list:
            text = f"✅ {name}" if code == selected_ccode else name
            kb.add(types.InlineKeyboardButton(text, callback_data=f"cty|{mode}|{code}"))
    return kb

# ================= ИЗДӨӨ (жаңыртылган) =================
def search_drivers(chat_id, from_city=None, to_city=None, from_cities=None, to_cities=None):
    """
    from_city / to_city      — конкреттүү шаар боюнча издөө (айдоочулар үчүн колдонулбайт)
    from_cities              — облустун бардык шаарларынан Бишкекке издөө
    to_cities                — Бишкектен облустун бардык шаарларына издөө
    """
    clean_old_records()
    conn, c = get_db()

    if from_cities:
        # Бишкекке барам: облустун каалаган шаарынан → Бишкек
        placeholders = ",".join("?" * len(from_cities))
        c.execute(
            f"SELECT * FROM drivers WHERE from_city IN ({placeholders}) AND to_city='Бишкек'",
            from_cities
        )
    elif to_cities:
        # Бишкектен кетем: Бишкек → облустун каалаган шаарына
        placeholders = ",".join("?" * len(to_cities))
        c.execute(
            f"SELECT * FROM drivers WHERE from_city='Бишкек' AND to_city IN ({placeholders})",
            to_cities
        )
    else:
        # Конкреттүү шаар боюнча издөө
        c.execute(
            "SELECT * FROM drivers WHERE from_city=? AND to_city=?",
            (from_city, to_city)
        )

    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.send_message(
            chat_id,
            "❌ Азырынча айдоочу табылган жок.\nКийинчерээк кайра текшериңиз.",
            reply_markup=menu()
        )
        return

    bot.send_message(chat_id, f"✅ Жалпы <b>{len(rows)}</b> айдоочу табылды:", parse_mode="HTML")

    # Шаар боюнча топтоштуруу
    grouped = defaultdict(list)
    for r in rows:
        if from_cities:
            city_key = r[3]  # from_city
        elif to_cities:
            city_key = r[4]  # to_city
        else:
            city_key = r[3]
        grouped[city_key].append(r)

    for city_key, drivers in grouped.items():
        # Шаардын аталышын баш кылып жиберүү
        bot.send_message(
            chat_id,
            f"📍 <b>{city_key}</b> — {len(drivers)} айдоочу",
            parse_mode="HTML"
        )
        for r in drivers:
            text = (
                "🚗 <b>Айдоочу</b>\n\n"
                f"👤 Аты: {r[1]}\n"
                f"🚘 Машина: {r[2]}\n"
                f"📍 Маршрут: {r[3]} → {r[4]}\n"
                f"⏰ Убакыт: {r[5]}\n"
                f"💰 Баа: {r[6]} сом\n"
                f"🪑 Орун: {r[8]}\n"
                f"📞 Тел: {r[7]}\n"
                f"💬 Комментарий: {r[9]}\n"
            )
            bot.send_message(chat_id, text, parse_mode="HTML")

# ================= CALLBACK =================
@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    # ---------- Жүргүнчү: маршрут тандоо ----------
    if data == "to":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ 🏙 Бишкекке барам", callback_data="to"))
        kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=show_regions("to"))

    elif data == "from":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="to"))
        kb.add(types.InlineKeyboardButton("✅ 🌄 Бишкектен кетем", callback_data="from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=show_regions("from"))

    # ---------- Айдоочу: маршрут тандоо ----------
    elif data == "d_to":
        set_data(chat_id, "to", "Бишкек")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ 🏙 Бишкекке барам", callback_data="d_to"))
        kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="d_from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        bot.send_message(chat_id, "🗺 Чыккан жериңизди тандаңыз (облус):", reply_markup=show_regions("driver_from"))

    elif data == "d_from":
        set_data(chat_id, "from", "Бишкек")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="d_to"))
        kb.add(types.InlineKeyboardButton("✅ 🌄 Бишкектен кетем", callback_data="d_from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        bot.send_message(chat_id, "🗺 Барар жериңизди тандаңыз (облус):", reply_markup=show_regions("driver_to"))

    # ---------- Облус тандоо ----------
    elif data.startswith("reg|"):
        _, mode, rcode = data.split("|")
        region_name = region_map.get(rcode)
        if not region_name:
            return

        city_list = regions.get(region_name, [])

        try:
            bot.edit_message_reply_markup(
                chat_id, msg_id,
                reply_markup=show_regions(mode, selected_rcode=rcode)
            )
        except Exception:
            pass

        if mode == "to":
            # Жүргүнчү: Бишкекке барам → облустун бардык шаарларынан издөө
            bot.send_message(
                chat_id,
                f"🔍 <b>{region_name}</b> облусунан Бишкекке баткан айдоочулар:",
                parse_mode="HTML"
            )
            search_drivers(chat_id, from_cities=city_list)

        elif mode == "from":
            # Жүргүнчү: Бишкектен кетем → облустун бардык шаарларына издөө
            bot.send_message(
                chat_id,
                f"🔍 Бишкектен <b>{region_name}</b> облусуна кеткен айдоочулар:",
                parse_mode="HTML"
            )
            search_drivers(chat_id, to_cities=city_list)

        elif mode in ("driver_from", "driver_to"):
            # Айдоочу: шаар тандоосун көрсөтүү
            bot.send_message(
                chat_id,
                f"📍 <b>{region_name}</b>\nШаар/район тандаңыз:",
                parse_mode="HTML",
                reply_markup=show_cities(region_name, mode)
            )

    # ---------- Шаар тандоо (айдоочу үчүн гана) ----------
    elif data.startswith("cty|"):
        _, mode, ccode = data.split("|")
        city = city_map.get(ccode)
        if not city:
            return

        region_name = next((r for r, cities in regions.items() if city in cities), None)
        if region_name:
            try:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"📍 <b>{region_name}</b>\nШаар/район тандаңыз:",
                    parse_mode="HTML",
                    reply_markup=show_cities(region_name, mode, selected_ccode=ccode)
                )
            except Exception:
                pass

        if mode == "driver_from":
            set_data(chat_id, "from", city)
            msg = bot.send_message(chat_id, "⏰ Качан жолго чыгасыз:")
            bot.register_next_step_handler(msg, d_time)

        elif mode == "driver_to":
            set_data(chat_id, "to", city)
            msg = bot.send_message(chat_id, "⏰ Качан жолго чыгасыз:")
            bot.register_next_step_handler(msg, d_time)

# ================= RUN =================
init_db()
threading.Thread(target=auto_clean_loop, daemon=True).start()
print("Bot started...")
bot.infinity_polling()
