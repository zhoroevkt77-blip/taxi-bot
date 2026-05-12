            import telebot
from telebot import types
import sqlite3
import time
import threading

TOKEN = "8735227955:AAEgEQmB4f6yPQw6ak1szZemSatLbiuuwSE"
CHANNEL_ID = -1003871616356
ADMIN_ID = 8693522887
MBANK_NUMBER = "0227(155603"

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
    "Ысык-Көл облусу": ["Каракол","Балыкчы","Чолпон-Ата","Түп","Ак-Суу","Жети-Өгүз","Тоң"],
    "Нарын облусу": ["Нарын","Ат-Башы","Ак-Талаа","Жумгал","Кочкор"],
    "Ош облусу": ["Ош шаар","Кара-Суу","Араван","Ноокат","Өзгөн","Кара-Кулжа","Чоң-Алай"],
    "Жалал-Абад облусу": ["Манас","Сузак","Базар-Коргон","Ноокен","Кара-Көл","Таш-Көмүр","Майлуу-Суу","Ала-Бука","Аксы","Чаткал"],
    "Баткен облусу": ["Баткен","Кадамжай","Лейлек (Раззаков)","Кызыл-Кыя","Сүлүктү"],
    "Талас облусу": ["Талас","Бакай-Ата","Кара-Буура","Манас району"]
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
    conn = sqlite3.connect("taxi.db")
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
    return REGION_PRICES.get(region_name, 500)

# ================= USER DATA =================
user_data = {}

def set_data(uid, k, v):
    user_data.setdefault(uid, {})[k] = v

def get_data(uid):
    return user_data.get(uid, {})

def reset(uid):
    user_data.pop(uid, None)

# ================= КНОПКАЛАР =================
def menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🚗 Айдоочумун", "🔍 Жүргүнчүмүн")
    kb.add("💳 Подпискам")
    return kb

def back_kb():
    """Артка кнопкасы бар клавиатура"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("◀️ Артка")
    return kb

def menu_with_back():
    """Меню + Артка кнопкасы"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🚗 Айдоочумун", "🔍 Жүргүнчүмүн")
    kb.add("💳 Подпискам", "◀️ Артка")
    return kb

# ================= АРТКА БАСКЫЧЫН ТЕКШЕРҮҮ =================
def check_back(message, next_step_handler=None):
    """
    Артка басылганда менюга кайтат.
    next_step_handler - кайсы функцияга кайра катталуу керек
    """
    if message.text == "◀️ Артка":
        reset(message.chat.id)
        bot.send_message(message.chat.id, "🏠 Башкы меню:", reply_markup=menu())
        return True
    return False

# ================= МЕНЮ =================
@bot.message_handler(commands=["start"])
def start(m):
    reset(m.chat.id)
    bot.send_message(m.chat.id, "🚕 Кош келиңиз!", reply_markup=menu())

@bot.message_handler(commands=["cancel"])
def cancel(m):
    reset(m.chat.id)
    bot.send_message(m.chat.id, "❌ Жокко чыгарылды.", reply_markup=menu())

@bot.message_handler(func=lambda m: m.text == "◀️ Артка")
def back_handler(m):
    """Артка кнопкасы глобалдык иштөөчү"""
    reset(m.chat.id)
    bot.send_message(m.chat.id, "🏠 Башкы меню:", reply_markup=menu())

# ================= ПОДПИСКА =================
@bot.message_handler(func=lambda m: m.text == "💳 Подпискам")
def check_sub(m):
    row = get_subscription(m.chat.id)
    if row and row[1] > time.time():
        days_left = int((row[1] - time.time()) / 86400)
        bot.send_message(
            m.chat.id,
            "✅ Подпискаңыз активдүү\n"
            "📍 Облус: " + row[0] + "\n"
            "📅 " + str(days_left) + " күн калды",
            reply_markup=menu()
        )
    else:
        bot.send_message(m.chat.id, "❌ Подпискаңыз жок же бүткөн.", reply_markup=menu())

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
    if is_subscribed(m.chat.id):
        set_data(m.chat.id, "pay_type", "subscribed")
        msg = bot.send_message(m.chat.id, "Атыңыз:", reply_markup=back_kb())
        bot.register_next_step_handler(msg, d_car)
    else:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            "📝 Жеке пост — " + str(POST_PRICE) + " сом",
            callback_data="pay_post"
        ))
        kb.add(types.InlineKeyboardButton(
            "🗓 Подписка — 1 ай (чектеусуз)",
            callback_data="pay_sub"
        ))
        bot.send_message(
            m.chat.id,
            "Пост жарыялоо үчүн тандаңыз:\n\n"
            "📝 Жеке пост — " + str(POST_PRICE) + " сом (бир жолу)\n"
            "🗓 Подписка — 1 ай, чектеусуз пост:\n"
            "  • Баткен — 700 сом\n"
            "  • Ош, Жалал-Абад — 600 сом\n"
            "  • Калгандары — 500 сом",
            reply_markup=kb
        )

def d_car(m):
    if check_back(m):
        return
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "name", m.text)
    msg = bot.send_message(m.chat.id, "Машинаңыздын маркасы жана модели:", reply_markup=back_kb())
    bot.register_next_step_handler(msg, d_route)

def d_route(m):
    if check_back(m):
        return
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "car", m.text)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="d_to"))
    kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="d_from"))
    bot.send_message(m.chat.id, "Маршрут тандаңыз:", reply_markup=kb)

def d_time(m):
    if check_back(m):
        return
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "time", m.text)
    msg = bot.send_message(m.chat.id, "Жол кире акы (сом):", reply_markup=back_kb())
    bot.register_next_step_handler(msg, d_price)

def d_price(m):
    if check_back(m):
        return
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "price", m.text)
    msg = bot.send_message(m.chat.id, "Бош орун саны:", reply_markup=back_kb())
    bot.register_next_step_handler(msg, d_seats)

def d_seats(m):
    if check_back(m):
        return
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "seats", m.text)
    msg = bot.send_message(m.chat.id, "Мобилдик телефон номериңиз:", reply_markup=back_kb())
    bot.register_next_step_handler(msg, d_phone)

def d_phone(m):
    if check_back(m):
        return
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "phone", m.text)
    msg = bot.send_message(m.chat.id, "Комментарий жазыңыз (болбосо — сызыкча коюңуз):", reply_markup=back_kb())
    bot.register_next_step_handler(msg, d_finish)

def d_finish(m):
    if check_back(m):
        return
    if m.text == "/cancel":
        return cancel(m)
    set_data(m.chat.id, "comment", m.text)
    data = get_data(m.chat.id)

    required = ["name", "car", "from", "to", "time", "price", "phone", "seats"]
    for field in required:
        if field not in data:
            bot.send_message(m.chat.id, "❌ Маалымат жетишсиз. Кайрадан баштаңыз.", reply_markup=menu())
            reset(m.chat.id)
            return

    pay_type = data.get("pay_type", "")

    if pay_type == "subscribed":
        publish_post(m.chat.id, data)
    elif pay_type == "post":
        set_data(m.chat.id, "waiting_payment", True)
        bot.send_message(
            m.chat.id,
            "💳 Төлөм маалыматы:\n\n"
            "💰 Сумма: " + str(POST_PRICE) + " сом (1 пост)\n\n"
            "Мбанк/Элкарт номери:\n" + MBANK_NUMBER + "\n\n"
            "Төлөгөндөн кийин чектин скриншотун жөнөтүңүз 👇",
            reply_markup=back_kb()
        )
    else:
        bot.send_message(m.chat.id, "❌ Ката. Кайрадан баштаңыз.", reply_markup=menu())
        reset(m.chat.id)

def publish_post(chat_id, data):
    clean_old_records()
    with db_lock:
        conn, c = get_db()
        c.execute(
            "INSERT INTO drivers (name,car,from_city,to_city,time,price,phone,seats,comment,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
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
        "🚗 Айдоочу\n\n"
        "👤 Аты: " + data["name"] + "\n"
        "🚘 Машина: " + data["car"] + "\n"
        "📍 Маршрут: " + data["from"] + " → " + data["to"] + "\n"
        "⏰ Убакыт: " + data["time"] + "\n"
        "💰 Баа: " + data["price"] + " сом\n"
        "🪑 Бош орун: " + data["seats"] + "\n"
        "📱 Тел: " + data["phone"] + "\n"
        "💬 Комментарий: " + data.get("comment", "-")
    )
    bot.send_message(CHANNEL_ID, text)
    bot.send_message(chat_id, "✅ Пост чыкты!", reply_markup=menu())
    reset(chat_id)

# ================= ОБЛУС / ШААР =================
def show_regions(mode, selected_rcode=None):
    kb = types.InlineKeyboardMarkup()
    for code, name in region_map.items():
        label = ("✅ " + name) if code == selected_rcode else name
        kb.add(types.InlineKeyboardButton(label, callback_data="reg|" + mode + "|" + code))
    return kb

def show_cities(region_name, mode, selected_ccode=None):
    kb = types.InlineKeyboardMarkup()
    city_list = regions.get(region_name, [])
    for code, name in city_map.items():
        if name in city_list:
            label = ("✅ " + name) if code == selected_ccode else name
            kb.add(types.InlineKeyboardButton(label, callback_data="cty|" + mode + "|" + code))
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
        bot.send_message(chat_id, "❌ Азырынча айдоочу табылган жок.\nКийинчерээк кайра текшериңиз.", reply_markup=menu())
        return

    bot.send_message(chat_id, "✅ " + str(len(rows)) + " айдоочу табылды:")
    for r in rows:
        text = (
            "🚗 Айдоочу\n\n"
            "👤 Аты: " + str(r[1]) + "\n"
            "🚘 Машина: " + str(r[2]) + "\n"
            "📍 Маршрут: " + str(r[3]) + " → " + str(r[4]) + "\n"
            "⏰ Качан жөнөйт: " + str(r[5]) + "\n"
            "💰 Жол кире: " + str(r[6]) + " сом\n"
            "🪑 Бош орун: " + str(r[8]) + "\n"
            "📞 Тел: " + str(r[7]) + "\n"
            "💬 Комментарий: " + str(r[9])
        )
        bot.send_message(chat_id, text)
    
    # Бардык натыйжалар чыгарылгандан кийин меню кайтарат
    bot.send_message(chat_id, "🏠 Башкы менюга кайттыңыз", reply_markup=menu())

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
            "INSERT OR REPLACE INTO pending_payments (user_id,pay_type,region,amount,photo_id,created_at) VALUES (?,?,?,?,?,?)",
            (m.chat.id, pay_type, region, amount, photo_id, time.time())
        )
        conn.commit()
        conn.close()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Тастыктоо", callback_data="approve|" + str(m.chat.id)),
        types.InlineKeyboardButton("❌ Четке кагуу", callback_data="reject|" + str(m.chat.id))
    )

    if pay_type == "post":
        pay_label = "Жеке пост"
    else:
        pay_label = "Подписка (" + region + ")"

    bot.send_photo(
        ADMIN_ID, photo_id,
        caption=(
            "💳 Жаңы төлөм!\n"
            "👤 ID: " + str(m.chat.id) + "\n"
            "👤 @" + (m.from_user.username or "жок") + "\n"
            "📌 Түрү: " + pay_label + "\n"
            "💰 Сумма: " + str(amount) + " сом"
        ),
        reply_markup=kb
    )
    bot.send_message(m.chat.id, "✅ Чекиңиз жөнөтүлдү! Админ текшергенден кийин пост чыгат.", reply_markup=menu())
    set_data(m.chat.id, "waiting_payment", False)

# ================= CALLBACK =================
@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    if data == "pay_post":
        set_data(chat_id, "pay_type", "post")
        set_data(chat_id, "pay_amount", POST_PRICE)
        msg = bot.send_message(chat_id, "Атыңыз:", reply_markup=back_kb())
        bot.register_next_step_handler(msg, d_car)

    elif data == "pay_sub":
        kb = types.InlineKeyboardMarkup()
        for code, name in region_map.items():
            price = get_price_for_region(name)
            kb.add(types.InlineKeyboardButton(
                name + " — " + str(price) + " сом",
                callback_data="sub|" + code
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
            "💳 Төлөм маалыматы:\n\n"
            "📍 Облус: " + region_name + "\n"
            "💰 Сумма: " + str(amount) + " сом/ай\n\n"
            "Мбанк/Элкарт номери:\n" + MBANK_NUMBER + "\n\n"
            "Төлөгөндөн кийин чектин скриншотун жөнөтүңүз 👇",
            reply_markup=back_kb()
        )

    elif data.startswith("approve|"):
        if call.from_user.id != ADMIN_ID:
            return
        uid = int(data.split("|")[1])
        with db_lock:
            conn, c = get_db()
            c.execute("SELECT pay_type, region FROM pending_payments WHERE user_id=?", (uid,))
            row = c.fetchone()
            conn.close()

        if not row:
            return

        pay_type, region = row

        if pay_type == "sub":
            expires = time.time() + 30 * 86400
            with db_lock:
                conn, c = get_db()
                c.execute(
                    "INSERT OR REPLACE INTO subscriptions (user_id,region,expires_at) VALUES (?,?,?)",
                    (uid, region, expires)
                )
                c.execute("DELETE FROM pending_payments WHERE user_id=?", (uid,))
                conn.commit()
                conn.close()
            bot.edit_message_caption(
                "✅ Тастыкталды — Подписка (" + region + ")",
                call.message.chat.id, msg_id
            )
            bot.send_message(
                uid,
                "✅ Подпискаңыз активдешти!\n"
                "📍 Облус: " + region + "\n"
                "📅 1 ай",
                reply_markup=menu()
            )

        elif pay_type == "post":
            with db_lock:
                conn, c = get_db()
                c.execute("DELETE FROM pending_payments WHERE user_id=?", (uid,))
                conn.commit()
                conn.close()
            bot.edit_message_caption("✅ Тастыкталды — Жеке пост", call.message.chat.id, msg_id)
            d = get_data(uid)
            if d.get("name"):
                publish_post(uid, d)
            else:
                bot.send_message(
                    uid,
                    "✅ Төлөмүңүз тастыкталды!\n"
                    "🚗 Айдоочумун баскычын басып, пост жазыңыз.",
                    reply_markup=menu()
                )

    elif data.startswith("reject|"):
        if call.from_user.id != ADMIN_ID:
            return
        uid = int(data.split("|")[1])
        with db_lock:
            conn, c = get_db()
            c.execute("DELETE FROM pending_payments WHERE user_id=?", (uid,))
            conn.commit()
            conn.close()
        bot.edit_message_caption("❌ Четке кагылды", call.message.chat.id, msg_id)
        bot.send_message(uid, "❌ Төлөмүңүз тастыкталган жок. Админ менен байланышыңыз.", reply_markup=menu())

    elif data == "to":
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

    elif data == "d_to":
        set_data(chat_id, "to", "Бишкек")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ 🏙 Бишкекке барам", callback_data="d_to"))
        kb.add(types.InlineKeyboardButton("🌄 Бишкектен кетем", callback_data="d_from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=show_regions("driver_from"))

    elif data == "d_from":
        set_data(chat_id, "from", "Бишкек")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🏙 Бишкекке барам", callback_data="d_to"))
        kb.add(types.InlineKeyboardButton("✅ 🌄 Бишкектен кетем", callback_data="d_from"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=kb)
        bot.send_message(chat_id, "🗺 Облус тандаңыз:", reply_markup=show_regions("driver_to"))

    elif data.startswith("reg|"):
        parts = data.split("|")
        mode = parts[1]
        rcode = parts[2]
        region_name = region_map.get(rcode)
        if not region_name:
            return
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=show_regions(mode, selected_rcode=rcode))
        bot.send_message(chat_id, "📍 " + region_name + "\nШаар тандаңыз:", reply_markup=show_cities(region_name, mode))

    elif data.startswith("cty|"):
        parts = data.split("|")
        mode = parts[1]
        ccode = parts[2]
        city = city_map.get(ccode)
        if not city:
            return
        region_name = None
        for r, cities in regions.items():
            if city in cities:
                region_name = r
                break
        if region_name:
            bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=show_cities(region_name, mode, selected_ccode=ccode))

        if mode in ("to", "from"):
            search_drivers(chat_id, mode, city)
        elif mode == "driver_from":
            set_data(chat_id, "from", city)
            msg = bot.send_message(chat_id, "⏰ Качан жолго чыгасыз:", reply_markup=back_kb())
            bot.register_next_step_handler(msg, d_time)
        elif mode == "driver_to":
            set_data(chat_id, "to", city)
            msg = bot.send_message(chat_id, "⏰ Качан жолго чыгасыз:", reply_markup=back_kb())
            bot.register_next_step_handler(msg, d_time)

# ================= RUN =================
init_db()
print("Bot started...")
while True:
    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            none_stop=True,
            interval=0
        )
    except Exception as e:
        print("Ката: " + str(e))
        time.sleep(3)
        try:
            bot.stop_polling()
        except:
            pass
