# -*- coding: utf-8 -*-
# core/logic/search.py — Издөө.
# Импорттор жана жалпы аталыштар common.py'де; бул файл
# core/logic/__init__.py аркылуу ошол мейкиндикке жүктөлөт.

# ============ ИЗДӨӨ ============

def passenger_search(messenger, msg, account):
    """«🔍 Айдоочуларды издейм» — сайтка багыттайт.

    Сайтта так айдоочулардын жарыялары турат: багыт боюнча тизме,
    облус чыпкасы, ар бир жарыяда чалуу/WhatsApp/Telegram баскычтары.
    Ботто издөө да калат — кичине баскыч менен, интернети начар же
    браузерге чыккысы келбегендер үчүн.
    """
    if msg.platform == "telegram":
        kb = Keyboard.from_flat([
            Button("🌐 Сайттан айдоочуларды көрүү", "noop", SITE_URL),
            Button("🔍 Ботто издөө", "p_search_bot"),
            _back_btn(),
        ])
        return _say(messenger, msg, account, L(
            "🌐 <b>Айдоочуларды сайттан издеңиз</b>\n\n"
            "Сайтта бардык айдоочулар багыт боюнча тизме менен турат. "
            "Облус боюнча чыпкалайсыз, шаар издейсиз, ар бир жарыяда "
            "чалуу, WhatsApp жана Telegram баскычтары даяр.\n\n"
            "<i>Каалабасаңыз, ботто да издей аласыз — ылдыйкы "
            "баскычты басыңыз.</i>",
            "🌐 <b>Ищите водителей на сайте</b>\n\n"
            "На сайте все водители выведены списком по направлениям. "
            "Можно отфильтровать по области, найти город, а у каждого "
            "объявления готовы кнопки звонка, WhatsApp и Telegram.\n\n"
            "<i>Если не хотите — можно искать и в боте, нажмите "
            "кнопку ниже.</i>"), kb)

    # WhatsApp: URL баскычы жок — шилтеме текст менен
    kb = Keyboard.from_flat([
        Button("🔍 Ботто издөө", "p_search_bot"),
        _back_btn(),
    ])
    _say(messenger, msg, account, L(
        "🌐 <b>Айдоочуларды сайттан издеңиз</b>\n\n"
        "Сайтта бардык айдоочулар багыт боюнча тизме менен турат — "
        "чалуу, WhatsApp жана Telegram баскычтары менен:\n"
        + SITE_URL + "\n\n"
        "<i>Каалабасаңыз, ботто да издей аласыз.</i>",
        "🌐 <b>Ищите водителей на сайте</b>\n\n"
        "На сайте все водители выведены списком по направлениям — "
        "с кнопками звонка, WhatsApp и Telegram:\n"
        + SITE_URL + "\n\n"
        "<i>Если не хотите — можно искать и в боте.</i>"), kb)


def search_menu(messenger, msg, account, target_role):
    kb = Keyboard.from_flat([
        Button("➡️ Бишкекке бараткандар", f"sb:to:{target_role}"),
        Button("⬅️ Бишкектен кайткандар", f"sb:from:{target_role}"),
        Button("🗺 Район/шаар аралык", f"lo:{target_role}"),
        _back_btn(),
    ])
    _say(messenger, msg, account, L("Багытты тандаңыз:", "Выберите направление:"), kb)


# ---- Район аралык издөө: облус → район → маршрут ----

def local_oblast_from(messenger, msg, account, action):
    """1-кадам: кайсы облустан чыккандарды издейт."""
    role = action.split(":")[1]

    # Ар бир облустан канча жарыя бар экенин эсептейбиз
    rows = [r for r in posts.local_route_counts() if r["role"] == role]
    per_city = {}
    for r in rows:
        per_city[r["from_city"]] = per_city.get(r["from_city"], 0) + r["n"]

    btns = []
    for i, oblast in enumerate(DISTRICT_OBLASTS):
        n = sum(per_city.get(c, 0) for c in DISTRICTS[oblast])
        btns.append(Button(f"{oblast} · {n} жарыя", f"lof:{role}:{i}"))
    btns.append(_back_btn())

    _say(messenger, msg, account, L(
         "🗺 <b>Район/шаар аралык</b>\n\nКайсы облустан чыккандарды издейсиз?",
         "🗺 <b>Между районами</b>\n\nИз какой области ищете?"),
         Keyboard.from_flat(btns))


def local_oblast_to(messenger, msg, account, action):
    """2-кадам: ошол облустун кайсы районунан."""
    _, role, idx = action.split(":")
    oblast = DISTRICT_OBLASTS[int(idx)]

    rows = [r for r in posts.local_route_counts() if r["role"] == role]
    per_city = {}
    for r in rows:
        per_city[r["from_city"]] = per_city.get(r["from_city"], 0) + r["n"]

    btns = []
    for i, city in enumerate(DISTRICTS[oblast]):
        n = per_city.get(city, 0)
        btns.append(Button(f"{city} · {n} жарыя", f"lot:{role}:{idx}:{i}"))
    btns.append(_back_btn())

    _say(messenger, msg, account, L(
         f"📍 <b>{oblast}</b>\n\nКайсы райондон/шаардан чыккандарды издейсиз?",
         f"📍 <b>{oblast}</b>\n\nИз какого района/города ищете?"),
         Keyboard.from_flat(btns))


def local_oblast_results(messenger, msg, account, action):
    """3-кадам: ошол райондон чыккан маршруттар."""
    _, role, i_ob, i_city = action.split(":")
    oblast = DISTRICT_OBLASTS[int(i_ob)]
    city = DISTRICTS[oblast][int(i_city)]

    rows = [r for r in posts.local_route_counts()
            if r["role"] == role and r["from_city"] == city]

    if not rows:
        return _say(messenger, msg, account, L(
                    f"📍 <b>{city}</b>\n\n❌ Бул жерден чыккан жарыя азырынча жок.",
                    f"📍 <b>{city}</b>\n\n❌ Отсюда пока нет объявлений."), back_kb())

    btns = []
    pairs = []
    for i, r in enumerate(rows):
        btns.append(Button(f"{r['from_city']} ➡️ {r['to_city']} · {r['n']} жарыя",
                           f"lr:{role}:{i}"))
        pairs.append((r["from_city"], r["to_city"]))
    _SEARCH_CACHE[msg.user_id] = pairs
    btns.append(_back_btn())

    _say(messenger, msg, account, L(
         f"📍 <b>{city}</b> — кайда барат?",
         f"📍 <b>{city}</b> — куда едут?"), Keyboard.from_flat(btns))


def local_results(messenger, msg, account, action):
    """Тандалган маршруттун жарыялары."""
    _, role, idx = action.split(":")
    pairs = _SEARCH_CACHE.get(msg.user_id, [])
    if int(idx) >= len(pairs):
        return _say(messenger, msg, account,
                    L("❌ Кайра издеп көрүңүз.", "❌ Попробуйте поиск заново."), back_kb())
    frm, to = pairs[int(idx)]
    rows = posts.search_posts(role, from_city=frm, to_city=to)
    _say(messenger, msg, account, f"📋 <b>{frm} ➡️ {to}</b>")
    if not rows:
        return _say(messenger, msg, account,
                    L("❌ Бул багыт боюнча жарыя табылган жок.",
                      "❌ По этому направлению объявлений не найдено."), back_kb())
    for p in rows:
        _say(messenger, msg, account, L(
             post_card(p, "ky") + "\n\n" + contact_lines(p["phone"], "ky"),
             post_card(p, "ru") + "\n\n" + contact_lines(p["phone"], "ru")))
    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


def search_bishkek(messenger, msg, account, action):
    """Бишкек багыты — облус/шаар деңгээлинде тизме."""
    _, direction, role = action.split(":")
    to_bishkek = direction == "to"

    # Ар бир шаар/райондун жарыя санын алып, облус боюнча чогултабыз
    rows = posts.route_counts(role, to_bishkek)
    counts = {r["k"]: r["n"] for r in rows}

    btns = []
    for i, region in enumerate(REGION_LIST):
        n = sum(counts.get(c, 0) for c in REGIONS[region])
        if to_bishkek:
            label = f"{region} ➡️ Бишкек · {n} жарыя"
        else:
            label = f"Бишкек ➡️ {region} · {n} жарыя"
        btns.append(Button(label, f"sr:{role}:{direction}:{i}"))

    btns.append(_back_btn())
    title = L("➡️ <b>Бишкекке бараткандар</b>" if to_bishkek
              else "⬅️ <b>Бишкектен кайткандар</b>",
              "➡️ <b>Едут в Бишкек</b>" if to_bishkek
              else "⬅️ <b>Возвращаются из Бишкека</b>")
    _say(messenger, msg, account, title, Keyboard.from_flat(btns))


def show_results(messenger, msg, account, action):
    """Тандалган облустун бардык шаар/райондорунун жарыялары."""
    _, role, direction, idx = action.split(":")
    i = int(idx)
    if i >= len(REGION_LIST):
        return _say(messenger, msg, account,
                    L("❌ Кайра издеп көрүңүз.", "❌ Попробуйте поиск заново."), back_kb())

    region = REGION_LIST[i]
    to_bishkek = direction == "to"

    rows = []
    for city in REGIONS[region]:
        if to_bishkek:
            rows += posts.search_posts(role, from_city=city, to_city="Бишкек")
        else:
            rows += posts.search_posts(role, from_city="Бишкек", to_city=city)

    # VIP'тер башында, андан кийин жаңылары
    rows.sort(key=lambda p: (not p.get("is_vip"), ), reverse=False)

    header = (f"📋 <b>{region} ➡️ Бишкек</b>" if to_bishkek
              else f"📋 <b>Бишкек ➡️ {region}</b>")
    _say(messenger, msg, account, header)

    if not rows:
        return _say(messenger, msg, account,
                    L("❌ Бул багыт боюнча жарыя азырынча жок.",
                      "❌ По этому направлению пока нет объявлений."), back_kb())

    for p in rows:
        _say(messenger, msg, account, L(
             post_card(p, "ky") + "\n\n" + contact_lines(p["phone"], "ky"),
             post_card(p, "ru") + "\n\n" + contact_lines(p["phone"], "ru")))
    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


def _hashtag(messenger, msg, account, text):
    """#Ош_Бишкек деп КОЛ МЕНЕН жазылса — ошол багыттагы жарыялар."""
    parts = text[1:].split("_")
    if len(parts) < 2:
        return _say(messenger, msg, account, "❓ Бул хештегди тааныган жокмун.")
    frm, to = parts[0], "_".join(parts[1:])
    _show_hashtag_results(messenger, msg, account, text, frm, to)


def _show_hashtag_results(messenger, msg, account, tag, frm, to, only_role=None,
                          show_header=True):
    """Багыт боюнча жарыяларды ролго бөлүп көрсөтөт.

    only_role берилсе — ошол рол гана чыгат ("driver" же "passenger").

    show_header=False — «🔎 Издөө: ...» деген баш сап чыкпайт. Жарыя
    жазып бүткөндөн кийин чакырылганда керек: ал жерде багыт өйдө жакта
    ансыз да жазылып турат, эки баш сап катар турса ашыкча болот.
    """
    def short(s):
        s = re.sub(r"\s*(облусу|шаары|району|\(Раззаков\))\s*", "", s or "")
        return s.strip()

    rows = posts.search_by_hashtag(short(frm), short(to))
    if only_role:
        rows = [p for p in rows if p["role"] == only_role]
    # '#' белгисин колдонбойбуз: Telegram аны шилтеме кылып, басканда
    # ботко эмес, өзүнүн издөөсүнө алып барат.
    route = f"{short(frm)} ➡️ {short(to)}"
    if show_header:
        _say(messenger, msg, account, L(f"🔎 Издөө: <b>{route}</b>",
                                        f"🔎 Поиск: <b>{route}</b>"))
    if not rows:
        if only_role == "passenger":
            return _say(messenger, msg, account, L(
                "❌ Бул багытта азырынча жүргүнчү жок.",
                "❌ По этому направлению пока нет пассажиров."), back_kb())
        if only_role == "driver":
            return _say(messenger, msg, account, L(
                "❌ Бул багытта азырынча айдоочу жок.",
                "❌ По этому направлению пока нет водителей."), back_kb())
        return _say(messenger, msg, account, L(
                    "❌ Бул багытта азырынча жарыя жок.",
                    "❌ По этому направлению пока нет объявлений."), back_kb())

    drivers = [p for p in rows if p["role"] == "driver"]
    passengers = [p for p in rows if p["role"] == "passenger"]

    if drivers:
        _say(messenger, msg, account,
             L(f"🚗 <b>Айдоочулар</b> ({len(drivers)})",
               f"🚗 <b>Водители</b> ({len(drivers)})"))
        for p in drivers:
            _say(messenger, msg, account,
                 post_card(p) + "\n\n" + contact_lines(p["phone"]))

    if passengers:
        _say(messenger, msg, account,
             L(f"🧳 <b>Жүргүнчүлөр</b> ({len(passengers)})",
               f"🧳 <b>Пассажиры</b> ({len(passengers)})"))
        for p in passengers:
            _say(messenger, msg, account,
                 post_card(p) + "\n\n" + contact_lines(p["phone"]))

    _say(messenger, msg, account, L("⬇️ Кайтуу үчүн:", "⬇️ Чтобы вернуться:"), back_kb())


def register_referral(messenger, newbie, inviter_id):
    if inviter_id == newbie["account_id"]:
        return
    if newbie.get("referred_by"):
        return
    inviter = db.get_account(inviter_id)
    if not inviter:
        return

    db.update_account(newbie["account_id"], referred_by=inviter_id)
    new_count = (inviter["ref_count"] or 0) + 1
    granted = inviter.get("gate_bonus", 0) or 0   # канча жолу бонус берилди

    # ---- Жүргүнчү бонусу: ар бир дос ----
    old_free = inviter.get("free_posts", 0) or 0
    add_posts = PASSENGER_FIRST_BONUS if new_count == 1 else PASSENGER_NEXT_BONUS
    db.update_account(inviter_id, ref_count=new_count,
                      free_posts=old_free + add_posts)

    pid = db.platform_id_of(inviter_id)
    if not pid:
        return

    def tell(text):
        try:
            messenger.send_text(pid, text)
        except Exception:
            pass

    tell(f"✅ Жаңы дос кошулду! Жалпы: {new_count} дос.\n"
         f"🧳 Жүргүнчү катары +{add_posts} акысыз пост.")

    # ---- Айдоочу бонусу: ар 3 дос сайын ----
    earned = new_count // REQUIRED_REFERRALS      # канча бонус татыктуу
    if earned > granted:
        days = GATE_BONUS_DAYS if granted == 0 else REFERRAL_BONUS_DAYS

        grant_days(inviter_id, days)
        db.update_account(inviter_id, gate_bonus=earned)
        if granted == 0:
            tell(f"🎉 Куттуктайбыз! Платформа толук ачылды!\n"
                 f"🎁 {days} күн акысыз жарыя бере аласыз.")
        else:
            tell(f"🎁 Дагы {days} күн акысыз кошулду!")
