# -*- coding: utf-8 -*-
# core/logic/wizard.py — Жарыя берүү визарды жана анын баскычтары.
# Импорттор жана жалпы аталыштар common.py'де; бул файл
# core/logic/__init__.py аркылуу ошол мейкиндикке жүктөлөт.

# ============ ЖАРЫЯ БЕРҮҮ ============

def daily_limit_left(account_id, role):
    """24 саат ичинде дагы канча жарыя бере алат. (айдоочу үчүн гана)

    DRIVER_DAILY_LIMIT = 0 болсо — чектөө жок, (None, None) кайтарат.
    """
    if role != "driver" or not DRIVER_DAILY_LIMIT:
        return None, None
    times = posts.recent_posts_times(account_id, "driver", 24)
    left = DRIVER_DAILY_LIMIT - len(times)
    if left > 0 or not times:
        return left, None
    # Эң эски жарыя 24 сааттан өткөндө орун бошойт
    free_at = times[0] + timedelta(hours=24)
    return left, free_at


def post_types(messenger, msg, account, role):
    # Айдоочуга суткалык чектөө: спамдын алдын алат
    left, free_at = daily_limit_left(account["account_id"], role)
    if left is not None and left <= 0:
        when = _to_local(free_at).strftime("%H:%M") if free_at else ""
        return _say(messenger, msg, account, L(
            f"🚫 Бир суткада эң көп <b>{DRIVER_DAILY_LIMIT} жарыя</b> бере аласыз.\n\n"
            f"⏰ Кийинки жарыяны саат <b>{when}</b> чамасында бере аласыз.\n\n"
            f"<i>Бул чектөө каналды жана издөө тизмесин таза кармоо үчүн "
            f"коюлган — ар бир айдоочунун жарыясы көрүнүктүү болсун.</i>",
            f"🚫 В сутки можно опубликовать не более <b>{DRIVER_DAILY_LIMIT} объявлений</b>.\n\n"
            f"⏰ Следующее объявление вы сможете дать примерно в <b>{when}</b>.\n\n"
            f"<i>Это ограничение нужно, чтобы канал и список поиска оставались "
            f"чистыми — и объявление каждого водителя было заметным.</i>"),
            back_kb())

    if not account.get("verified_phone"):
        SESSIONS[msg.user_id] = {"step": "await_phone", "role": role, "data": {}}
        lang = account.get("lang", "ky")
        messenger.ask_phone_contact(msg.user_id, render(
            "📱 Жарыя берүү үчүн бир жолу телефон номериңизди ырастооңуз керек.",
            lang, messenger.platform_name))
        return

    SESSIONS[msg.user_id] = {"step": "mode", "role": role, "data": {}}
    kb = Keyboard.from_flat([
        Button("Облустардын район/шаарларынан Бишкекке жана кайтуу", "mode:bishkek"),
        Button("Район/шаар аралык", "mode:local"),
        _back_btn(),
    ])
    ky_head = ru_head = ""
    if left is not None:
        n = max(0, left - 1)
        ky_head = (f"📝 Бул жарыядан кийин бүгүн дагы <b>{n} жарыя</b> бере аласыз.\n"
                   f"<i>(суткалык чектөө: {DRIVER_DAILY_LIMIT})</i>\n\n")
        ru_head = (f"📝 После этого объявления сегодня останется <b>{n}</b>.\n"
                   f"<i>(лимит в сутки: {DRIVER_DAILY_LIMIT})</i>\n\n")
    _say(messenger, msg, account, L(
        ky_head + "Кайсы багытта жарыя бересиз?",
        ru_head + "В каком направлении вы даёте объявление?"), kb)


def ask_route(messenger, msg, account, st):
    if st["data"].get("mode") == "local":
        st["step"] = "loreg"
        kb = two_col([Button(o, f"loreg:{i}")
                      for i, o in enumerate(DISTRICT_OBLASTS)])
        _say(messenger, msg, account, "🗺 Кайсы облустан чыгасыз?", kb)
    else:
        st["step"] = "dir"
        kb = Keyboard(rows=[
            [Button("🚕 Бишкекке барам", "route:to_bishkek"),
             Button("🚕 Бишкектен кайтам", "route:from_bishkek")],
            [_back_btn()],
        ])
        _say(messenger, msg, account, L("Багытты тандаңыз:", "Выберите направление:"), kb)


# ============ ВИЗАРД КАДАМДАРЫ ============

def day_hours():
    """Мезгилге жараша күндүзгү сааттардын тизмеси.

    Жүргүнчүлөр негизинен күндүз жолго чыгат, ошондуктан түнкү сааттарды
    тизмеге салбайбыз — керек болсо колдонуучу кол менен жазат.

        Апрель–сентябрь : 06:00 – 21:00
        Октябрь–март    : 07:00 – 19:00
    """
    month = _local_now().month
    if 4 <= month <= 9:
        start, end = 6, 21
    else:
        start, end = 7, 19
    return [f"{h:02d}:00" for h in range(start, end + 1)]


MONTHS_KY = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def date_label(offset):
    """«Бүгүн · 17-август» / «Эртең · 18-август» — чаташпашы үчүн."""
    d = _local_now() + timedelta(days=offset)
    name = "Бүгүн" if offset == 0 else "Эртең"
    return f"{name} · {d.day}-{MONTHS_KY[d.month - 1]}"


def ask_step(messenger, msg, account, st, step):
    st["step"] = step
    role = st["role"]

    if step == "date":
        kb = Keyboard(rows=[[Button(date_label(0), "dq:0"),
                             Button(date_label(1), "dq:1")],
                            [_back_btn()]])
        return _say(messenger, msg, account, "📅 Качан жолго чыгасыз?", kb)

    if step == "time":
        hours = day_hours()
        rows = [[Button(h, f"tm:{h}") for h in hours[k:k + 4]]
                for k in range(0, len(hours), 4)]
        # Айдоочу так убакыт коё албаганда: орун толгондо жолго чыгат.
        # Бул Кыргызстанда эң кеңири таралган иштөө ыкмасы.
        if role == "driver":
            rows.append([Button("🚗 Орун толгондо чыгам", "tm:full")])
        rows.append([_back_btn()])
        return _say(messenger, msg, account,
            "⏰ Саат канчада жолго чыгасыз?\n\n"
            "<i>Тизмеде жок убакыт болсо — жазып жибериңиз "
            "(мис. 05:30 же 22:00).</i>",
            Keyboard(rows=rows))

    if step == "price":
        kb = Keyboard.from_flat([Button("🤝 Келишим баада", "pr:deal"),
                                 _back_btn()])
        return _say(messenger, msg, account,
            "💰 Жол киреси канча?\n\n"
            "<i>Сумманы жазыңыз (мис. 1200), же төмөнкү баскычты басыңыз.</i>", kb)

    if step == "seats":
        rows = [[Button(str(i), f"seat:{i}") for i in range(1, 5)],
                [Button(str(i), f"seat:{i}") for i in range(5, 8)],
                [_back_btn()]]
        return _say(messenger, msg, account, "👥 Канча бош орун бар?",
                    Keyboard(rows=rows))

    if step == "people":
        rows = [[Button(str(i), f"ppl:{i}") for i in range(1, 5)],
                [Button(str(i), f"ppl:{i}") for i in range(5, 8)],
                [_back_btn()]]
        return _say(messenger, msg, account,
            "👥 Канча киши жолго чыгасыңар?\n\n"
            "<i>Салон болсо — Салон деп жазып жибериңиз.</i>", Keyboard(rows=rows))

    if step == "baggage":
        kb = Keyboard.from_flat([Button("🚫 Жок", "bg:no"), _back_btn()])
        return _say(messenger, msg, account,
            "🎒 Багажыңыз барбы?\n\n"
            "<i>Жок болсо — төмөнкү баскычты басыңыз.\n"
            "Бар болсо — жазып жибериңиз (мис. 2 чемодан).</i>", kb)

    if step == "photo":
        kb = Keyboard.from_flat([Button("⏭ Сүрөтсүз улантам", "skip:photo"),
                                 _back_btn()])
        wa = msg.platform == "whatsapp"
        ky_how = ("📎 <b>Кантип жиберем?</b>\n"
                  "Кабар талаасынын жанындагы <b>📎 кыстаргыч</b> "
                  "белгисин басыңыз ➔ «Галерея» же «Камера» ➔ сүрөттү "
                  "тандап, жөнөтүңүз.\n\n"
                  if not wa else
                  "📎 <b>Кантип жиберем?</b>\n"
                  "Кабар талаасынын жанындагы <b>📎 кыстаргыч</b> же "
                  "<b>камера</b> белгисин басыңыз ➔ сүрөттү тандап, "
                  "жөнөтүңүз.\n\n")
        ru_how = ("📎 <b>Как отправить?</b>\n"
                  "Нажмите <b>📎 скрепку</b> рядом с полем ввода ➔ "
                  "«Галерея» или «Камера» ➔ выберите фото и "
                  "отправьте.\n\n"
                  if not wa else
                  "📎 <b>Как отправить?</b>\n"
                  "Нажмите <b>📎 скрепку</b> или значок <b>камеры</b> "
                  "рядом с полем ввода ➔ выберите фото и "
                  "отправьте.\n\n")

        return _say(messenger, msg, account, L(
            "📷 <b>Унааңыздын сүрөтүн жиберсеңиз болот</b>\n\n"
            + ky_how +
            "📌 <b>Бир сүрөт жетиштүү.</b> Бир нече жиберсеңиз, "
            "акыркысы гана калат.\n\n"
            "💡 Унаа толук көрүнгөн, жарык жерде тартылган сүрөт "
            "жакшы. Сүрөтү бар жарыяга ишеним көбүрөөк — жүргүнчү "
            "кандай унаага түшөрүн алдын ала көрөт.\n\n"
            "<i>Сүрөт милдеттүү эмес. Каалабасаңыз, төмөнкү "
            "«⏭ Сүрөтсүз улантам» баскычын басыңыз.</i>",
            "📷 <b>Можно отправить фото вашей машины</b>\n\n"
            + ru_how +
            "📌 <b>Достаточно одного фото.</b> Если отправите "
            "несколько, останется последнее.\n\n"
            "💡 Лучше снимок, где машина видна целиком и при хорошем "
            "свете. Объявлению с фото доверяют больше — пассажир "
            "заранее видит машину.\n\n"
            "<i>Фото не обязательно. Не хотите — нажмите кнопку "
            "«⏭ Продолжить без фото» ниже.</i>"), kb)

    if step == "phone":
        ph = account.get("verified_phone")
        # Эски аккаунттарда КГ эмес номер калып калышы мүмкүн —
        # аны жарыяга сунуштабайбыз, кол менен сурайбыз.
        if ph and not normalize_phone(str(ph)):
            ph = None
        if ph:
            kb = Keyboard.from_flat([Button(f"📱 {ph}", "usephone"), _back_btn()])
            return _say(messenger, msg, account,
                "📞 Байланыш номериңиз:\n\n"
                "Жарыяга ырасталган номериңиз жазылат.\n"
                "Улантуу үчүн төмөнкү баскычты басыңыз.", kb)
        return _say(messenger, msg, account, "📞 Мобилдик телефон номериңиз:", back_kb())

    prompts = {
        "name": "Атыңызды жазыңыз:",
        "car": "Машинаңыздын маркасы жана модели:",
        "comment": ("📝 Кошумча комментарий (жазбасаңыз, жок деп жазыңыз):"
                    if role == "driver" else "📝 Айдоочуларга эмне деп жазасыз?"),
    }
    _say(messenger, msg, account, prompts.get(step, ""), back_kb())


def next_step(messenger, msg, account, st, current):
    steps = steps_of(st["role"])
    i = steps.index(current)
    if i < len(steps) - 1:
        ask_step(messenger, msg, account, st, steps[i + 1])
    else:
        finish(messenger, msg, account, st)


def finish(messenger, msg, account, st):
    if st["role"] == "driver":
        st["step"] = "confirm"
        _say(messenger, msg, account, DRIVER_WARNING)
        kb = Keyboard.from_flat([Button("✅ Түшүндүм, жарыялаймын", "confirm"),
                                 _back_btn()])
        _say(messenger, msg, account, L(
            "🚦 <b>Коопсуздук эрежелерин окуп алыңыз!</b>\n\n"
            "Башкы менюдагы «🆘 Жардам» баскычын басып, андагы "
            "«🛡 Айдоочунун коопсуздугу» бөлүмүн окуп чыгыңыз.\n\n"
            "<i>Ал жерде жолдогу коопсуздуктун 6 негизги эрежеси жазылган — "
            "өз өмүрүңүз жана жүргүнчүлөрдүн өмүрү үчүн маанилүү.</i>",
            "🚦 <b>Обязательно прочитайте правила безопасности!</b>\n\n"
            "В главном меню нажмите «🆘 Помощь» и откройте раздел "
            "«🛡 Безопасность водителя».\n\n"
            "<i>Там изложены 6 главных правил безопасности в пути — "
            "это важно для вашей жизни и жизни пассажиров.</i>"), kb)
    else:
        save(messenger, msg, account, st)


def hashtag(frm, to):
    def short(s):
        s = re.sub(r"\s*(облусу|шаары|району|\(Раззаков\))\s*", "", s or "")
        return re.sub(r"\s+", "_", s.strip())
    return f"#{short(frm)}_{short(to)}"


def channel_text(d, role, tag=None):
    """Каналга чыгуучу жарыянын тексти.

    Хештег КОЛДОНУЛБАЙТ: Telegram аны басканда «Публичные посты»
    издөөсүн ачат, ал эми жарыялар жеке каналда — эч нерсе табылбайт.
    Анын ордуна жарыянын астындагы эки издөө баскычы иштейт:
    «🔍 Telegram Ботто издөө» жана «🔍 WhatsApp Ботто издөө» —
    экөө тең ошол багыттагы бардык жарыяларды чыгарат.
    """
    if role == "driver":
        return (
            f"🚗 <b>АЙДООЧУ / ВОДИТЕЛЬ</b>\n"
            f"🚖 <b>{d.get('from_city')} ➡️ {d.get('to_city')}</b>\n"
            f"🧍 Аты / Имя: {d.get('name')}\n"
            f"🚘 Унаа / Авто: {d.get('car')}\n"
            f"📅 {d.get('date_text')} · ⏰ {d.get('time_text')}\n"
            f"👥 Бош орун / Мест: {d.get('seats')}\n"
            f"💰 Баасы / Цена: {d.get('price')}\n"
            f"📝 {(d.get('comment') or '')[:200]}\n"
            f"📞 {mask_phone(d.get('phone'))} · «📞 Байланышуу» 👇"
            )
    return ""


def _route_url(frm, to, lang="ky"):
    """Ошол багыттын сайттагы бети.

    Айдоочу жарыясын жазып бүткөндө, ага дал ушул шилтемени беребиз —
    издеп отурбай, өз жарыясын дароо көрөт.
    """
    # Кириллицаны кодолбойбуз: ошондо шилтеме «?from=Бишкек&to=Манас»
    # болуп окулат. Кодолсо «%D0%91%D0%B8...» болуп чубалып кетет.
    # Бош орун гана кодолушу керек — калганын браузер өзү түшүнөт.
    def _q(x):
        return (x or "").replace(" ", "%20").replace("&", "%26")
    return (f"{SITE_URL}/route?from={_q(frm)}"
            f"&to={_q(to)}&lang={lang}")


def _publish(messenger, text, links, photo=None):
    """Каналга чыгарат — платформадан көз каранды эмес.

    core/channel.py түз Telegram API'ге кайрылат, ошондуктан WhatsApp'тан
    жазылган айдоочунун жарыясы да ошол эле каналга барат.

    photo берилсе — жарыя сүрөт менен чыгат, текст кол жазуу болот.
    """
    return channel.publish(text, links, photo=photo)


def _photo_of(d):
    """Жарыянын сүрөтү (Telegram file_id же ачык URL). Жок болсо None."""
    return d.get("photo_id") or d.get("photo_url") or None


def _notify_opposite(author, post_id, d, role):
    """Жаңы жарыя тууралуу тескери ролдогуларга кабар берет.

    Айдоочу жазса → ошол багытта жарыясы бар ЖҮРГҮНЧҮЛӨРГӨ,
    жүргүнчү жазса → ошол багытта жарыясы бар АЙДООЧУЛАРГА.

    Кимдин жарыясы активдүү болсо, ошол кабар алат. Жарыя 24 саат
    жашайт — демек ал бир суткага «жазылып» калгандай болот, мөөнөт
    бүткөндө кабар өзүнөн-өзү токтойт. Өзүнчө таблица керек эмес.

    Кабарлоо экинчи даражадагы иш: ката чыкса, жарыя берүү агымы
    бузулбашы керек. Ошондуктан баары try ичинде.
    """
    try:
        from core import notify
        p = posts.get_post(post_id)
        if not p:
            return

        target_role = "passenger" if role == "driver" else "driver"
        ids = notify.accounts_with_active_posts(
            target_role, d.get("from_city"), d.get("to_city"),
            exclude_account_id=author["account_id"])
        if not ids:
            return

        route = f"{d.get('from_city')} ➡️ {d.get('to_city')}"
        ky_head = "🔔 <b>Жаңы айдоочу!</b>" if role == "driver" else "🔔 <b>Жаңы жүргүнчү!</b>"
        ru_head = "🔔 <b>Новый водитель!</b>" if role == "driver" else "🔔 <b>Новый пассажир!</b>"

        for acc_id in ids:
            other = db.get_account(acc_id)
            if not other or other.get("banned"):
                continue
            lang = other.get("lang", "ky")
            head = (ru_head if lang == "ru" else ky_head) + f"\n{route}\n\n"
            body = post_card(p, lang) + "\n\n" + contact_lines(p["phone"], lang)
            notify.send(acc_id, head + body)

        who = "жүргүнчүгө" if role == "driver" else "айдоочуга"
        print(f"🔔 Жаңы {role} жарыясы: {len(ids)} {who} кабарланды.")
    except Exception as e:
        print("Кабарлоо катасы:", e)


def save(messenger, msg, account, st):
    d = st["data"]
    role = st["role"]
    post_id = posts.create_post(account["account_id"], role, d)
    SESSIONS.pop(msg.user_id, None)

    _say(messenger, msg, account, L(
         "✅ Жарыя чыкты! Ботто 24 саат турат, андан кийин автоматтык өчүрүлөт.",
         "✅ Объявление опубликовано! Оно будет висеть 24 часа, затем удалится автоматически."))

    # Колдонуучу өз жарыясын дароо көрсүн
    fresh = posts.get_post(post_id)
    if fresh:
        _say(messenger, msg, account, L(
             "👇 <b>Сиздин жарыяңыз:</b>\n\n"
             + post_card(fresh, "ky") + "\n\n" + contact_lines(fresh["phone"], "ky"),
             "👇 <b>Ваше объявление:</b>\n\n"
             + post_card(fresh, "ru") + "\n\n" + contact_lines(fresh["phone"], "ru")))

    if role == "driver":
        # Каналга чыгарабыз — платформа өзү билет, core билбейт.
        # Астына байланыш баскычтарын кошобуз.
        msg_id = _publish(messenger, channel_text(d, role),
                          contact_links(d.get("phone"), post_id,
                                        d.get("from_city"), d.get("to_city")),
                          photo=_photo_of(d))
        if msg_id:
            posts.set_channel_msg(post_id, msg_id)
            _say(messenger, msg, account, L(
                 "📢 Жарыяңыз каналга да чыкты — жүргүнчүлөр аны ошол жерден көрө алат.",
                 "📢 Объявление также опубликовано в канале — пассажиры увидят его там."))
        # Ошол багытка жазылгандарга браузердин кабарын жиберебиз.
        # Ката болсо да жарыя жазылып бүткөн — программа токтобойт.
        try:
            from core import push
            push.notify_route(d.get("from_city"), d.get("to_city"), d)
        except Exception as e:
            print("[logic] push катасы:", e)

        # Сайтта да көрүнөт — өз багытына түз шилтеме беребиз
        lang = account.get("lang", "ky")
        url = _route_url(d.get("from_city"), d.get("to_city"), lang)
        if msg.platform == "telegram":
            kb = Keyboard.from_flat([
                Button("🌐 Сайттан көрүү", "noop", url),
            ])
            _say(messenger, msg, account, L(
                 "🌐 <b>Сайтта да турат!</b>\n\n"
                 "Жарыяңыз сайттан да көрүнөт — Telegram'ы да, WhatsApp'ы "
                 "да жок адамдар сизди ошол жерден таба алат.\n\n"
                 "Төмөнкү баскычты басып, өз багытыңызды көрүңүз. "
                 "Шилтемени досторуңузга да жибере аласыз.",
                 "🌐 <b>Также на сайте!</b>\n\n"
                 "Ваше объявление видно и на сайте — вас найдут даже те, "
                 "у кого нет ни Telegram, ни WhatsApp.\n\n"
                 "Нажмите кнопку ниже, чтобы посмотреть своё направление. "
                 "Ссылку можно отправить друзьям."), kb)
        else:
            _say(messenger, msg, account, L(
                 "🌐 <b>Сайтта да турат!</b>\n\n"
                 "Жарыяңыз сайттан да көрүнөт — Telegram'ы да, WhatsApp'ы "
                 "да жок адамдар сизди ошол жерден таба алат.\n\n"
                 "Өз багытыңыз:\n" + url,
                 "🌐 <b>Также на сайте!</b>\n\n"
                 "Ваше объявление видно и на сайте — вас найдут даже те, "
                 "у кого нет ни Telegram, ни WhatsApp.\n\n"
                 "Ваше направление:\n" + url))
    else:
        _say(messenger, msg, account, L(
             "🔒 Жүргүнчүнүн жарыясы каналга чыкпайт — аны айдоочулар ботто гана көрөт.",
             "🔒 Объявление пассажира в канал не публикуется — его видят водители в боте."))
        # Жүргүнчүнүн жарыясы сайтка чыкпайт, бирок сайт ага дагы пайдалуу:
        # ошол багыттагы айдоочуларды браузерден көрө алат.
        lang = account.get("lang", "ky")
        url = _route_url(d.get("from_city"), d.get("to_city"), lang)
        if msg.platform == "telegram":
            kb = Keyboard.from_flat([
                Button("🌐 Сайттан айдоочуларды көрүү", "noop", url),
            ])
            _say(messenger, msg, account, L(
                 "🌐 <b>Сайтыбызды да карап коюңуз</b>\n\n"
                 "Ошол багыттагы айдоочулар сайттан да көрүнөт — "
                 "чалуу, WhatsApp жана Telegram баскычтары менен.",
                 "🌐 <b>Загляните и на сайт</b>\n\n"
                 "Водители по этому направлению видны и на сайте — "
                 "с кнопками звонка, WhatsApp и Telegram."), kb)
        else:
            _say(messenger, msg, account, L(
                 "🌐 <b>Сайтыбызды да карап коюңуз</b>\n\n"
                 "Ошол багыттагы айдоочулар сайттан да көрүнөт:\n" + url,
                 "🌐 <b>Загляните и на сайт</b>\n\n"
                 "Водители по этому направлению видны и на сайте:\n" + url))

    # Жаңы жарыя — тескери ролдогуларга кабар кетет.
    # Айдоочу жазса → жүргүнчүлөргө, жүргүнчү жазса → айдоочуларга.
    _notify_opposite(account, post_id, d, role)

    # Жарыя жазылгандан кийин ошол багыттагы тескери ролдун жарыялары
    # ДАРОО тизме болуп чыгат — баскыч басып отуруунун кереги жок.
    # Айдоочу жазса → жүргүнчүлөр, жүргүнчү жазса → айдоочулар.
    other_role = "passenger" if role == "driver" else "driver"
    other_ky = "жүргүнчүлөр" if role == "driver" else "айдоочулар"
    other_ru = "пассажиры" if role == "driver" else "водители"
    route = f"{d.get('from_city')} ➡️ {d.get('to_city')}"
    _say(messenger, msg, account, L(
         f"💡 <b>{route}</b>\n\nУшул багыттагы {other_ky} төмөндө:",
         f"💡 <b>{route}</b>\n\nПо этому направлению {other_ru}:"))
    _show_hashtag_results(messenger, msg, account, route,
                          d.get("from_city"), d.get("to_city"),
                          only_role=other_role, show_header=False)
    # Ушуну менен бүтөт. Мурда бул жерде дагы бир «Тандаңыз:» менюсу
    # чыгып, тизменин артынан ашыкча болуп калчу. Telegram'да ылдыйкы
    # клавиатура ансыз да турат, WhatsApp'та «0 — башкы меню» эскертүүсү
    # бар, ошондуктан кошумча меню керек эмес.


# ============ БАСКЫЧТАР (визард ичинде) ============

def _wizard_button(messenger, msg, account, st):
    a = msg.button_action
    d = st["data"]

    if a == "wback":
        return wizard_back(messenger, msg, account, st)

    if a.startswith("mode:"):
        d["mode"] = a.split(":")[1]
        return ask_route(messenger, msg, account, st)

    if a.startswith("route:"):
        direction = a.split(":")[1]
        d["direction"] = direction
        st["step"] = "preg"
        if direction == "to_bishkek":
            d["to_city"] = "Бишкек"
            return _say(messenger, msg, account, "Кайсы облуска барасыз?", regions_kb())
        d["from_city"] = "Бишкек"
        return _say(messenger, msg, account,
                    "🗺 Барар жериңизди тандаңыз (облус):", regions_kb())

    if a.startswith("preg:"):
        region = REGION_LIST[int(a.split(":")[1])]
        d["_region"] = region
        st["step"] = "pcity"
        kb = two_col([Button(c, f"pcity:{i}")
                      for i, c in enumerate(REGIONS[region])])
        return _say(messenger, msg, account,
                    f"📍 <b>{region}</b>\nШаар/район тандаңыз:", kb)

    if a.startswith("pcity:"):
        region = d.get("_region")
        city = REGIONS[region][int(a.split(":")[1])]
        if d.get("direction") == "to_bishkek":
            d["from_city"] = city
        else:
            d["to_city"] = city
        _say(messenger, msg, account, L(
             f"✅ Маршрут: {d.get('from_city')} ➡️ {d.get('to_city')}",
             f"✅ Маршрут: {d.get('from_city')} ➡️ {d.get('to_city')}"))
        return ask_step(messenger, msg, account, st, steps_of(st["role"])[0])

    if a.startswith("loreg:"):
        oblast = DISTRICT_OBLASTS[int(a.split(":")[1])]
        d["_oblast"] = oblast
        st["step"] = "lofrom"
        kb = two_col([Button(c, f"lofrom:{i}")
                      for i, c in enumerate(DISTRICTS[oblast])])
        return _say(messenger, msg, account,
                    f"📍 <b>{oblast}</b>\nКайсы райондон/шаардан чыгасыз?", kb)

    if a.startswith("lofrom:"):
        oblast = d["_oblast"]
        d["from_city"] = DISTRICTS[oblast][int(a.split(":")[1])]
        st["step"] = "lotoreg"
        kb = two_col([Button(o, f"lotoreg:{i}")
                      for i, o in enumerate(DISTRICT_OBLASTS)])
        return _say(messenger, msg, account,
            f"📍 Чыгуу: <b>{d['from_city']}</b>\n🗺 Кайсы облуска барасыз?", kb)

    if a.startswith("lotoreg:"):
        oblast = DISTRICT_OBLASTS[int(a.split(":")[1])]
        d["_to_oblast"] = oblast
        st["step"] = "loto"
        btns = [Button(c, f"loto:{i}") for i, c in enumerate(DISTRICTS[oblast])
                if c != d.get("from_city")]
        return _say(messenger, msg, account,
                    f"📍 <b>{oblast}</b>\nКайсы районго/шаарга барасыз?",
                    two_col(btns))

    if a.startswith("loto:"):
        oblast = d["_to_oblast"]
        d["to_city"] = DISTRICTS[oblast][int(a.split(":")[1])]
        _say(messenger, msg, account,
             f"✅ Маршрут: {d['from_city']} ➡️ {d['to_city']}")
        return ask_step(messenger, msg, account, st, steps_of(st["role"])[0])

    if a.startswith("dq:"):
        d["date_text"] = date_label(int(a.split(":")[1]))
        return next_step(messenger, msg, account, st, "date")

    if a == "tm:full":
        d["time_text"] = "Орун толгондо жолго чыгам"
        return next_step(messenger, msg, account, st, "time")

    if a.startswith("tm:"):
        t = a.split(":", 1)[1]
        d["time_text"] = f"Саат {t}дө жолго чыгам"
        return next_step(messenger, msg, account, st, "time")

    if a == "pr:deal":
        d["price"] = "Келишим"
        return next_step(messenger, msg, account, st, "price")

    if a == "bg:no":
        d["baggage"] = "Жок"
        return next_step(messenger, msg, account, st, "baggage")

    if a.startswith("seat:"):
        d["seats"] = a.split(":")[1]
        return next_step(messenger, msg, account, st, "seats")

    if a.startswith("ppl:"):
        d["people_count"] = a.split(":")[1]
        return next_step(messenger, msg, account, st, "people")

    if a == "skip:photo":
        return next_step(messenger, msg, account, st, "photo")

    if a == "usephone":
        d["phone"] = account.get("verified_phone", "")
        return finish(messenger, msg, account, st)

    if a == "confirm":
        return save(messenger, msg, account, st)


def wizard_back(messenger, msg, account, st):
    step = st.get("step")
    steps = steps_of(st["role"])

    if step == "confirm":
        return ask_step(messenger, msg, account, st, steps[-1])
    if step in steps:
        i = steps.index(step)
        if i == 0:
            return ask_route(messenger, msg, account, st)
        return ask_step(messenger, msg, account, st, steps[i - 1])

    # Маршрут тандоо кадамдарынан артка
    if step in ("pcity",):
        st["step"] = "preg"
        return _say(messenger, msg, account, "Облусту тандаңыз:", regions_kb())
    if step in ("preg", "dir", "loreg"):
        st["step"] = "mode"
        kb = Keyboard.from_flat([
            Button("Облустардын район/шаарларынан Бишкекке жана кайтуу",
                   "mode:bishkek"),
            Button("Район/шаар аралык", "mode:local"),
            _back_btn(),
        ])
        return _say(messenger, msg, account, "Кайсы багытта жарыя бересиз?", kb)
    if step == "lofrom":
        return ask_route(messenger, msg, account, st)
    if step in ("lotoreg", "loto"):
        st["step"] = "lofrom"
        oblast = st["data"].get("_oblast")
        if oblast:
            kb = two_col([Button(c, f"lofrom:{i}")
                          for i, c in enumerate(DISTRICTS[oblast])])
            return _say(messenger, msg, account,
                        f"📍 <b>{oblast}</b>\nКайсы райондон/шаардан чыгасыз?", kb)

    # Визарддын эң башы — менюга кайтабыз
    SESSIONS.pop(msg.user_id, None)
    if st["role"] == "driver":
        _say(messenger, msg, account, "Тандаңыз:", driver_menu_kb())
    else:
        _say(messenger, msg, account, "Тандаңыз:", passenger_menu_kb())


def _wizard_text(messenger, msg, account, st):
    step = st.get("step")
    text = (msg.text or "").strip()

    if step == "await_phone":
        return verify_phone(messenger, msg, account, st, text)

    # Жарыяга жазылуучу номер — КГ форматында гана болушу керек.
    # Болбосо жарыяга чет өлкө номери түшүп, аны эч ким чала албай калат.
    if step == "phone":
        # Ырасталган номери бар болсо — башка номер жаздырбайбыз.
        # Антпесе жарыяга өзүнө таандык эмес номер түшүп калат.
        ph = account.get("verified_phone")
        if ph and normalize_phone(str(ph)):
            # Баскычтарды кайра чыгарабыз — «төмөнкү баскыч» чындап төмөндө болсун
            kb = Keyboard.from_flat([Button(f"📱 {ph}", "usephone"), _back_btn()])
            return _say(messenger, msg, account, L(
                "📱 Жарыяга ырасталган номериңиз гана жазылат.\n👉 Башка адам үчүн такси издесеңиз, анын номерин комментарийге жазыңыз.\n"
                "Төмөнкү баскычты басыңыз.",
                "📱 В объявлении указывается только ваш подтверждённый "
                "номер.\n👉 Если ищете такси для другого человека, укажите его номер в комментарии.\nНажмите кнопку ниже."), kb)
        ok = normalize_phone(text)
        if not ok:
            return _say(messenger, msg, account, L(
                "⚠️ Кыргызстандын номерин жазыңыз.\n"
                "Мисалы: <b>0700123456</b> же <b>996700123456</b>",
                "⚠️ Укажите номер Кыргызстана.\n"
                "Например: <b>0700123456</b> или <b>996700123456</b>"),
                hint=True)
        text = ok

    field = STEP_FIELD.get(step)
    if not field:
        return
    st["data"][field] = text
    next_step(messenger, msg, account, st, step)


def verify_phone(messenger, msg, account, st, raw):
    # Номер платформадан келиши керек: Telegram'да «номеримди
    # бөлүшөм» баскычы, WhatsApp'та өз номери. Колго жазылган
    # номерди кабыл алсак, бирөө башканын номерин жазып, ошол
    # адамдын аккаунтуна кирип алат.
    if not getattr(msg, "verified", False):
        lang = account.get("lang", "ky")
        messenger.ask_phone_contact(msg.user_id, render(
            "⚠️ Номерди колго жазууга болбойт.\n"
            "Төмөнкү «📱 Номеримди бөлүшөм» баскычын басыңыз.",
            lang, messenger.platform_name))
        return

    phone = normalize_phone(raw)
    if not phone:
        return _say(messenger, msg, account, L(
            "⚠️ Кыргызстандын номерин жазыңыз.\n"
            "Мисалы: <b>0700123456</b> же <b>996700123456</b>",
            "⚠️ Укажите номер Кыргызстана.\n"
            "Например: <b>0700123456</b> или <b>996700123456</b>"),
            hint=True)
    existing = db.find_account_by_phone(phone)
    if existing and existing["account_id"] != account["account_id"]:
        db.link_second_platform(existing["account_id"], msg.user_id, msg.platform)
        account = existing
        _say(messenger, msg, account, "✅ Номериңиз мурдагы аккаунтуңузга байланды!")
    else:
        db.update_account(account["account_id"], verified_phone=phone)
        account = db.get_account(account["account_id"])
    _say(messenger, msg, account, f"✅ Номериңиз ырасталды: <b>{phone}</b>")
    return post_types(messenger, msg, account, st["role"])


def normalize_phone(raw):
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        return "996" + digits[1:]
    if digits.startswith("996") and len(digits) == 12:
        return digits
    return None


