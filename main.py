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
MBANK_NUMBER = os.getenv("MBANK_NUMBER", "0227)155603")

POST_PRICE = 30

REGION_PRICES = {
    "Баткен облусу": 700,
    "Ош облусу": 600,
    "Жалал-Абад облусу": 600,
    "Ысык-Көл облусу": 500,
    "Нарын облусу": 500,
    "Талас облусу": 500,
}

CITY_PRICES = {"Ош шаар": 600}

bot = telebot.TeleBot(TOKEN)

regions = {
    "Ысык-Көл облусу": ["Каракол", "Балыкчы", "Чолпон-Ата", "Түп", "Ак-Суу", "Жети-Өгүз", "Тоң"],
    "Нарын облусу": ["Нарын", "Ат-Башы", "Ак-Талаа", "Жумгал", "Кочкор"],
    "Ош облусу": ["Ош шаар", "Кара-Суу", "Араван", "Ноокат", "Өзгөн", "Кара-Кулжа", "Чоң-Алай"],
    "Жалал-Абад облусу": ["Манас", "Сузак", "Базар-Коргон", "Ноокен", "Кара-Көл", "Таш-Көмүр", "Майлуу-Суу", "Ала-Бука", "Аксы", "Чаткал"],
    "Баткен облусу": ["Баткен", "Кадамжай", "Лейлек (Раззаков)", "Кызыл-Кыя", "Сүлүктү"],
    "Талас облусу": ["Талас", "Бакай-Ата", "Кара-Буура", "Манас району"]
}

region_map = {}
city_map = {}

def build_maps():
    ri, ci = 0, 0
    for region_name, cities in regions.items():
        ri += 1
        region_map["r" + str(ri)] = region_name
        for city_name in cities:
            ci += 1
            city_map["c" + str(ci)] = city_name

build_maps()

# ================= DB =================
db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect("taxi.db", check_same_thread=False)
    return conn, conn.cursor()

def init_db():
    with db_lock:
        conn, c = get_db()
        c.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, car TEXT,
            from_city TEXT, to_city TEXT,
            time TEXT, price TEXT,
            phone TEXT, seats TEXT,
            comment TEXT, created_at REAL
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            region TEXT,
            expires_at REAL
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS pending_payments (
            user_id INTEGER PRIMARY KEY,
            pay_type TEXT,
            region TEXT,
            amount INTEGER,
            photo_id TEXT,
            created_at REAL
        )""")
        conn.commit()
        conn.close()

def clean_old_records():
    with db_lock:
        conn, c = get_db()
        c.execute("DELETE FROM drivers WHERE created_at < ?", (time.time() - 86400,))
        conn.commit()
        conn.close()

def get_subscription(user_id):
    with db_lock:
        conn, c = get_db()
        c.execute("SELECT region, expires_at FROM subscriptions WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
    return row

def is_subscribed(user_id):
    row = get_subscription(user_id)
    return bool(row and row[1] > time.time())

def get_price_for_region(region_name):
    if region_name in CITY_PRICES:
        return CITY_PRICES[region_name]
    return REGION_PRICES.get(region_name, 500)

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
    kb.add("💳 Подпискам")
    return kb

@bot.message_handler(commands=["start"])
def start(m):
    reset(m.chat.id)
    bot.send_message(m.chat.id, "🚕 Кош келиңиз!", reply_markup=menu())

@bot.message_handler(commands=["cancel"])
def cancel(m):
    reset(m.chat.id)
    bot.send_message(m.chat.id, "❌ Жокко чыгарылды.", reply_markup=menu())

# ================= ПОДПИСКА =================
@bot.message_handler(func=lambda m: m.text == "💳 Подпискам")
def check_sub(m):
    row = get_subscription(m.chat.id)
    if row and row[1] > time.time():
        days_left = int((row[1] - time.time()) / 86400)
        bot.send_message(
            m.chat.id,
            f"✅ Подпискаңыз активдүү\n📍 Облус: {row[0]}\n📅 {days_left} күн калды"
        )
    else:
        bot.send_message(m.chat.id, "❌ Подпискаңыз жок же бүткөн.")

# ================= ЖҮРГҮНЧҮ =================
@bot.message_handler(func=lambda m: m.text and "Жүргүнчүмүн" in m.text)
def passenger(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="to_passenger"))
    kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="from_passenger"))
    bot.send_message(m.chat.id, "Маршрут тандаңыз:", reply_markup=kb)

# ================= АЙДООЧУ =================
@bot.message_handler(func=lambda m: m.text == "🚗 Айдоочумун")
def driver(m):
    if is_subscribed(m.chat.id):
        set_data(m.chat.id, "pay_type", "subscribed")
        msg = bot.send_message(m.chat.id, "Атыңыз:")
        bot.register_next_step_handler(msg, d_name)
    else:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            f"📝 Жеке пост — {POST_PRICE} сом",
            callback_data="pay_post"
        ))
        kb.add(types.InlineKeyboardButton(
            "🗓 Подписка — 1 ай (чектеусүз)",
            callback_data="pay_sub"
        ))
        bot.send_message(
            m.chat.id,
            f"Пост жарыялоо үчүн тандаңыз:\n\n"
            f"📝 Жеке пост — {POST_PRICE} сом (бир жолу)\n"
            f"🗓 Подписка — 1 ай, чектеусүз пост:\n"
            f"  • Баткен — 700 сом\n"
            f"  • Ош, Жалал-Абад — 600 сом\n"
            f"  • Калгандары — 500 сом",
            reply_markup=kb
        )

def d_name(m):
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "name", m.text)
    msg = bot.send_message(m.chat.id, "Машинаңыздын маркасы жана модели:")
    bot.register_next_step_handler(msg, d_car)

def d_car(m):
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "car", m.text)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="d_to"))
    kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="d_from"))
    bot.send_message(m.chat.id, "Маршрут тандаңыз:", reply_markup=kb)

def d_time(m):
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "time", m.text)
    msg = bot.send_message(m.chat.id, "Жол кире акы (сом):")
    bot.register_next_step_handler(msg, d_price)

def d_price(m):
    if m.text == "/cancel":
        return cancel(m)
    try:
        price = int(m.text)
        if price <= 0:
            raise ValueError
    except ValueError:
        msg = bot.send_message(m.chat.id, "❌ Баа туура сан болушу керек. Кайра жазыңыз:")
        bot.register_next_step_handler(msg, d_price)
        return
    set_data(m.chat.id, "price", str(price))
    msg = bot.send_message(m.chat.id, "Бош орун саны:")
    bot.register_next_step_handler(msg, d_seats)

def d_seats(m):
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "seats", m.text)
    msg = bot.send_message(m.chat.id, "Мобилдик телефон номериңиз (мисалы: 0700123456):")
    bot.register_next_step_handler(msg, d_phone)

def d_phone(m):
    if m.text == "/cancel":
        return cancel(m)
    phone = m.text.replace(" ", "").replace("-", "").replace("+", "")
    if not phone.isdigit() or len(phone) < 9:
        msg = bot.send_message(m.chat.id, "❌ Телефон номери туура эмес. Кайра жазыңыз:")
        bot.register_next_step_handler(msg, d_phone)
        return
    set_data(m.chat.id, "phone", m.text)
    msg = bot.send_message(m.chat.id, "Комментарий жазыңыз (болбосо — сызыкча коюңуз):")
    bot.register_next_step_handler(msg, d_finish)

def d_finish(m):
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "comment", m.text)
    data = get_data(m.chat.id)

    required = ["name", "car", "from", "to", "time", "price", "phone", "seats"]
    for field in required:
        if field not in data:
            bot.send_message(m.chat.id, f"❌ Маалымат жетишсиз ({field} жетишпейт). Кайрадан баштаңыз.", reply_markup=menu())
            reset(m.chat.id)
            return

    pay_type = data.get("pay_type", "")

    if pay_type == "subscribed":
        publish_post(m.chat.id, data)
    elif pay_type == "post":
        set_data(m.chat.id, "waiting_payment", True)
        bot.send_message(
            m.chat.id,
            f"💳 Төлөм маалыматы:\n\n"
            f"💰 Сумма: {POST_PRICE} сом (1 пост)\n\n"
            f"Мбанк/Элкарт номери:\n"
            f"{MBANK_NUMBER}\n\n"
            f"Төлөгөндөн кийин чектин скриншотун жөнөтүңүз 👇"
        )
    else:
        bot.send_message(m.chat.id, "❌ Ката. Кайрадан баштаңыз.", reply_markup=menu())
        reset(m.chat.id)

def publish_post(chat_id, data):
    clean_old_records()
    with db_lock:
        conn, c = get_db()
        c.execute(
            """INSERT INTO drivers (name,car,from_city,to_city,time,price,phone,seats,comment,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                data["name"], data["car"],
                data["from"], data["to"],
                data["time"], data["price"],
                data["phone"], data["seats"],
                data.get("comment", "-"), time.time()
            )
        )
        conn.commit()
        conn.close()

    text = (
        f"🚗 Айдоочу\n\n"
        f"👤 Аты: {data['name']}\n"
        f"🚘 Машина: {data['car']}\n"
        f"📍 Маршрут: {data['from']} → {data['to']}\n"
        f"⏰ Убакыт: {data['time']}\n"
        f"💰 Баа: {data['price']} сом\n"
        f"🪑 Бош орун: {data['seats']}\n"
        f"📱 Тел: {data['phone']}\n"
        f"💬 Комментарий: {data.get('comment', '-')}"
    )
    bot.send_message(CHANNEL_ID, text)
    bot.send_message(chat_id, "✅ Пост чыкты!", reply_markup=menu())
    reset(chat_id)

# ================= ОБЛУС / ШААР =================
def show_regions(mode, selected_rcode=None):
    kb = types.InlineKeyboardMarkup()
    for code, name in region_map.items():
        label = ("✅ " + name) if code == selected_rcode else name
        kb.add(types.InlineKeyboardButton(label, callback_data=f"reg|{mode}|{code}"))
    return kb

def show_cities(region_name, mode, selected_ccode=None):
    kb = types.InlineKeyboardMarkup()
    city_list = regions.get(region_name, [])
    for code, name in city_map.items():
        if name in city_list:
            label = ("✅ " + name) if code == selected_ccode else name
            kb.add(types.InlineKeyboardButton(label, callback_data=f"cty|{mode}|{code}"))
    return kb

# ================= ИЗДӨӨ =================
def search_drivers(chat_id, mode, city):
    clean_old_records()
    with db_lock:
        conn, c = get_db()
        if mode == "to":
            c.execute("SELECT * FROM drivers WHERE from_city=? AND to_city=?", (city, "Бишкек"))
        elif mode == "from":
            c.execute("SELECT * FROM drivers WHERE from_city=? AND to_city=?", ("Бишкек", city))
        rows = c.fetchall()
        conn.close()

    if not rows:
        bot.send_message(chat_id, "❌ Азырынча айдоочу табылган жок.\nКийинчерээк кайра текшериңиз.")
        return

    bot.send_message(chat_id, f"✅ {len(rows)} айдоочу табылды:")
    for r in rows:
        text = (
            f"🚗 Айдоочу\n\n"
            f"👤 Аты: {r[1]}\n"
            f"🚘 Машина: {r[2]}\n"
            f"📍 Маршрут: {r[3]} → {r[4]}\n"
            f"⏰ Качан жөнөйт: {r[5]}\n"
            f"💰 Жол кире: {r[6]} сом\n"
            f"🪑 Бош орун: {r[8]}\n"
            f"📞 Тел: {r[7]}\n"
            f"💬 Комментарий: {r[9]}"
        )
        bot.send_message(chat_id, text)

# ================= СКРИНШОТ =================
@bot.message_handler(content_types=["photo"])
def receive_payment_photo(m):
    data = get_data(m.chat.id)
    if not data.get("waiting_payment"):
        return

    pay_type = data.get("pay_type")
    region = data.get("pay_region", "-")
    amount = data.get("pay_amount", POST_PRICE)
    photo_id = m.photo[-1].file_id

    with db_lock:
        conn, c = get_db()
        c.execute(
            """INSERT OR REPLACE INTO pending_payments (user_id,pay_type,region,amount,photo_id,created_at)
            VALUES (?,?,?,?,?,?)""",
            (m.chat.id, pay_type, region, amount, photo_id, time.time())
        )
        conn.commit()
        conn.close()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Тастыктоо", callback_data=f"approve|{m.chat.id}"),
        types.InlineKeyboardButton("❌ Четке кагуу", callback_data=f"reject|{m.chat.id}")
    )

    pay_label = "Жеке пост" if pay_type == "post" else f"Подписка ({region})"

    bot.send_photo(
        ADMIN_ID, photo_id,
        caption=(
            f"💳 Жаңы төлөм!\n"
            f"👤 ID: {m.chat.id}\n"
            f"👤 @{m.from_user.username or 'жок'}\n"
            f"📌 Түрү: {pay_label}\n"
            f"💰 Сумма: {amount} сом"
        ),
        reply_markup=kb
    )
    bot.send_message(m.chat.id, "✅ Чекиңиз жөнөтүлдү! Админ текшергенден кийин пост чыгат.")
    set_data(m.chat.id, "waiting_payment", False)

# ================= CALLBACK =================
@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    data = call.data

    if data == "pay_post":
        set_data(chat_id, "pay_type", "post")
        set_data(chat_id, "pay_amount", POST_PRICE)
        msg = bot.send_message(chat_id, "Атыңыз:")
        bot.register_next_step_handler(msg, d_name)

    elif data == "pay_sub":
        kb = types.InlineKeyboardMarkup()
        for code, name in region_map.items():
            price = get_price_for_region(name)
            kb.add(types.InlineKeyboardButton(
                f"{name} — {price} сом",
                callback_data=f"sub|{code}"
            ))
        bot.send_message(chat_id, "📍 Облусуңузду тандаңыз:", reply_markup=kb)

    elif data.startswith("sub|"):
        parts = data.split("|")
        rcode = parts[1]
        region_name = region_map.get(rcode)
        if not region_name:
            return
        amount = get_price_for_region(region_name)
        set_data(chat_id, "pay_type", "sub")
        set_data(chat_id, "pay_region", region_name)
        set_data(chat_id, "pay_amount", amount)
        set_data(chat_id, "waiting_payment", True)
        bot.send_message(
            chat_id,
            f"💳 Төлөм маалыматы:\n\n"
            f"📍 Облус: {region_name}\n"
            f"💰 Сумма: {amount} сом/ай\n\n"
            f"Мбанк/Элкарт номери:\n"
            f"{MBANK_NUMBER}\n\n"
            f"Төлөгөндөн кийин чектин скриншотун жөнөтүңүз 👇"
        )

    elif data.startswith("approve|"):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Сиз админ эмессиз!")
            return
        uid = int(data.split("|")[1])
        with db_lock:
            conn, c = get_db()
            c.execute("SELECT pay_type, region FROM pending_payments WHERE user_id=?", (uid,))
            row = c.fetchone()
            conn.close()
        if not row:
            bot.send_message(ADMIN_ID, "❌ Төлөм табылган жок.")
            return
        pay_type, region = row
        if pay_type == "sub":
            expires = time.time() + 30 * 86400
            with db_lock:
                conn, c = get_db()
                c.execute(
                    "INSERT OR REPLACE INTO subscriptions (user_id, region, expires_at) VALUES (?,?,?)",
                    (uid, region, expires)
                )
                c.execute("DELETE FROM pending_payments WHERE user_id=?", (uid,))
                conn.commit()
                conn.close()
            bot.send_message(uid, f"✅ Подпискаңыз активдүү!\n📍 Облус: {region}\n📅 30 күн")
        elif pay_type == "post":
            with db_lock:
                conn, c = get_db()
                c.execute("DELETE FROM pending_payments WHERE user_id=?", (uid,))
                conn.commit()
                conn.close()
            set_data(uid, "pay_type", "post")
            set_data(uid, "waiting_payment", False)
            saved = get_data(uid)
            if all(k in saved for k in ["name", "car", "from", "to", "time", "price", "phone", "seats"]):
                publish_post(uid, saved)
            else:
                bot.send_message(uid, "✅ Төлөм тастыкталды! Кайрадан маалымат жазыңыз.", reply_markup=menu())
        bot.edit_message_caption(
            caption="✅ Тастыкталды",
            chat_id=ADMIN_ID,
            message_id=call.message.message_id
        )

    elif data.startswith("reject|"):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Сиз админ эмессиз!")
            return
        uid = int(data.split("|")[1])
        with db_lock:
            conn, c = get_db()
            c.execute("DELETE FROM pending_payments WHERE user_id=?", (uid,))
            conn.commit()
            conn.close()
        bot.send_message(uid, "❌ Төлөмүңүз четке кагылды. Кайра аракет кылыңыз.")
        bot.edit_message_caption(
            caption="❌ Четке кагылды",
            chat_id=ADMIN_ID,
            message_id=call.message.message_id
        )

    elif data == "to_passenger":
        set_data(chat_id, "p_mode", "to")
        bot.send_message(chat_id, "📍 Облусуңузду тандаңыз:", reply_markup=show_regions("p_to"))

    elif data == "from_passenger":
        set_data(chat_id, "p_mode", "from")
        bot.send_message(chat_id, "📍 Облусуңузду тандаңыз:", reply_markup=show_regions("p_from"))

    elif data == "d_to":
        set_data(chat_id, "to", "Бишкек")
        bot.send_message(chat_id, "📍 Кайсы шаардан жөнөйсүз? Облусту тандаңыз:", reply_markup=show_regions("d_from"))

    elif data == "d_from":
        set_data(chat_id, "from", "Бишкек")
        bot.send_message(chat_id, "📍 Кайсы шаарга барасыз? Облусту тандаңыз:", reply_markup=show_regions("d_to"))

    elif data.startswith("reg|"):
        parts = data.split("|")
        mode = parts[1]
        rcode = parts[2]
        region_name = region_map.get(rcode)
        if not region_name:
            return
        set_data(chat_id, "sel_region", region_name)
        bot.send_message(chat_id, f"📍 {region_name} — шаар тандаңыз:", reply_markup=show_cities(region_name, mode))

    elif data.startswith("cty|"):
        parts = data.split("|")
        mode = parts[1]
        ccode = parts[2]
        city_name = city_map.get(ccode)
        if not city_name:
            return

        if mode == "d_from":
            set_data(chat_id, "from", city_name)
            msg = bot.send_message(chat_id, "⏰ Жөнөө убактысы (мисалы: 14:00):")
            bot.register_next_step_handler(msg, d_time)

        elif mode == "d_to":
            set_data(chat_id, "to", city_name)
            msg = bot.send_message(chat_id, "⏰ Жөнөө убактысы (мисалы: 14:00):")
            bot.register_next_step_handler(msg, d_time)

        elif mode in ("p_to", "p_from"):
            p_mode = "to" if mode == "p_to" else "from"
            search_drivers(chat_id, p_mode, city_name)

# ================= СТАРТ =================
init_db()
print("✅ Бот иштеп жатат...")
bot.infinity_polling()
