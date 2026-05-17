import os
import telebot
from telebot import types
import sqlite3
import time
import threading
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
    "Ысык-Көл облусу": ["Каракол","Балыкчы","Чолпон-Ата","Түп","Ак-Суу","Жети-Өгүз","Тоң"],
    "Нарын облусу": ["Нарын","Ат-Башы","Ак-Талаа","Жумгал","Кочкор"],
    "Ош облусу": ["Ош шаар","Кара-Суу","Араван","Ноокат","Өзгөн","Кара-Кулжа","Чоң-Алай"],
    "Жалал-Абад облусу": ["Манас","Сузак","Базар-Коргон","Ноокен","Кара-Көл","Таш-Көмүр","Майлуу-Суу","Ала-Бука","Аксы","Чаткал"],
    "Баткен облусу": ["Баткен","Кадамжай","Лейлек (Раззаков)","Кызыл-Кыя","Сүлүктү"],
    "Талас облусу": ["Талас","Бакай-Ата","Кара-Буура","Манас району"]
}

region_map = {}   # {"r1": "Ысык-Көл облусу", ...}
city_map = {}     # {"c1": "Каракол", ...}

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
        comment TEXT, created_at REAL
    )
    """)
    conn.commit()
    conn.close()

def clean_old_records():
    """24 саатттан эски жазууларды өчүр"""
    conn, c = get_db()
    cutoff = time.time() - 86400
    c.execute("DELETE FROM drivers WHERE created_at < ?", (cutoff,))
    conn.commit()
    conn.close()

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

# /cancel — агымдан чыгуу
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

    # Маалыматтар толук экенин текшер
    required = ["name", "car", "from", "to", "time", "price", "phone", "seats"]
    for field in required:
        if field not in data:
            bot.send_message(m.chat.id, "❌ Маалымат жетишсиз. Кайрадан баштаңыз.", reply_markup=menu())
            reset(m.chat.id)
            return

    # Эски жазууларды өчүр
    clean_old_records()

    conn, c = get_db()
    c.execute("""
        INSERT INTO drivers
        (name,car,from_city,to_city,time,price,phone,seats,comment,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        data["name"], data["car"],
        data["from"], data["to"],
        data["time"], data["price"],
        data["phone"], data["seats"],
        data.get("comment", "-"), time.time()
    ))
    conn.commit()
    conn.close()

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

    bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
    bot.send_message(m.chat.id, "✅ Пост чыкты!", reply_markup=menu())
    reset(m.chat.id)

# ================= ОБЛУС / ШААР =================
def show_regions(chat_id, mode, selected_rcode=None):
    kb = types.InlineKeyboardMarkup()
    for code, name in region_map.items():
        text = f"✅ {name}" if code == selected_rcode else name
        kb.add(types.InlineKeyboardButton(text, callback_data=f"reg|{mode}|{code}"))
    return kb  # ← kb кайтарабыз, send жок
    bot.send_message(chat_id, "Облус тандаңыз:")
    bot.send_message(chat_id, "👇", reply_markup=kb)

def show_cities(chat_id, region_name, mode, selected_ccode=None):
    kb = types.InlineKeyboardMarkup()
    city_list = regions.get(region_name, [])
    for code, name in city_map.items():
        if name in city_list:
            text = f"✅ {name}" if code == selected_ccode else name
            kb.add(types.InlineKeyboardButton(text, callback_data=f"cty|{mode}|{code}"))
    return kb  # ← kb кайтарабыз, send жок
    bot.send_message(chat_id, f"📍 {region_name}\nШаар тандаңыз:", reply_markup=kb)

# ================= ИЗДӨӨ =================
def search_drivers(chat_id, mode, city):
    clean_old_records()
    conn, c = get_db()

    if mode == "to":       # Жүргүнчү Бишкекке барат → айдоочу облустан Бишкекке барат
        c.execute("SELECT * FROM drivers WHERE from_city=? AND to_city=?", (city, "Бишкек"))
    elif mode == "from":   # Жүргүнчү Бишкектен кетет → айдоочу Бишкектен облуска барат
        c.execute("SELECT * FROM drivers WHERE from_city=? AND to_city=?", ("Бишкек", city))

    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.send_message(chat_id, "❌ Азырынча айдоочу табылган жок.\nКийинчерээк кайра текшериңиз.")
        return

    bot.send_message(chat_id, f"✅ {len(rows)} айдоочу табылды:")
    for r in rows:
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

    if data == "to":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ 🏙 Бишкекке барам", callback_data="to"))
        kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        region_kb = show_regions(chat_id, "to")
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=region_kb)

    elif data == "from":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="to"))
        kb.add(types.InlineKeyboardButton("✅ 🌄 Бишкектен кетем", callback_data="from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        region_kb = show_regions(chat_id, "from")
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=region_kb)

    elif data == "d_to":
        set_data(chat_id, "to", "Бишкек")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ 🏙 Бишкекке барам", callback_data="d_to"))
        kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="d_from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        region_kb = show_regions(chat_id, "driver_from")
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=region_kb)

    elif data == "d_from":
        set_data(chat_id, "from", "Бишкек")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="d_to"))
        kb.add(types.InlineKeyboardButton("✅ 🌄 Бишкектен кетем", callback_data="d_from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        region_kb = show_regions(chat_id, "driver_to")
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=region_kb)

    elif data.startswith("reg|"):
        _, mode, rcode = data.split("|")
        region_name = region_map.get(rcode)
        if not region_name:
            return
        kb = show_regions(chat_id, mode, selected_rcode=rcode)
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        city_kb = show_cities(chat_id, region_name, mode)
        bot.send_message(chat_id, f"📍 {region_name}\nШаар тандаңыз:", reply_markup=city_kb)

    elif data.startswith("cty|"):
        _, mode, ccode = data.split("|")
        city = city_map.get(ccode)
        if not city:
            return
        region_name = None
        for rname, cities in regions.items():
            if city in cities:
                region_name = rname
                break
        if region_name:
            city_kb = show_cities(chat_id, region_name, mode, selected_ccode=ccode)
            bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=city_kb)

        if mode in ("to", "from"):
            search_drivers(chat_id, mode, city)
        elif mode == "driver_from":
            set_data(chat_id, "from", city)
            msg = bot.send_message(chat_id, "⏰ Качан жолго чыгасыз:")
            bot.register_next_step_handler(msg, d_time)
        elif mode == "driver_to":
            set_data(chat_id, "to", city)
            msg = bot.send_message(chat_id, "⏰ Качан жолго чыгасыз:")
            bot.register_next_step_handler(msg, d_time)

# ================= RUN =================
init_db()
print("Bot started...")
bot.infinity_polling()
