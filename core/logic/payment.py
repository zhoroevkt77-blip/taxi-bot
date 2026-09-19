# -*- coding: utf-8 -*-
# core/logic/payment.py — Төлөм: мөөнөт, VIP, чек күтүү.
# Импорттор жана жалпы аталыштар common.py'де; бул файл
# core/logic/__init__.py аркылуу ошол мейкиндикке жүктөлөт.

# ============ ТӨЛӨМ ============

PAY_KINDS = {
    "access": {
        "ky_title": "💳 <b>Жарыя берүү укугу</b>",
        "ru_title": "💳 <b>Право размещать объявления</b>",
        "amount": PAYMENT_AMOUNT,
        "ky_gives": f"{PAYMENT_HOURS} саат чектөөсүз жарыя",
        "ru_gives": f"{PAYMENT_HOURS} часа объявлений без ограничений",
    },
    "vip": {
        "ky_title": "⭐ <b>VIP айдоочу</b>",
        "ru_title": "⭐ <b>VIP-водитель</b>",
        "amount": VIP_PRICE,
        "ky_gives": f"{VIP_HOURS} саат тизменин эң үстүндө",
        "ru_gives": f"{VIP_HOURS} часа в самом верху списка",
    },
    "post": {
        "ky_title": "💳 <b>Жүргүнчүнүн жарыясы</b>",
        "ru_title": "💳 <b>Объявление пассажира</b>",
        "amount": PASSENGER_POST_PRICE,
        "ky_gives": "1 жарыя",
        "ru_gives": "1 объявление",
    },
}


def pay_btn(kind):
    """Ар бир жерге коюлуучу бирдей төлөм баскычы."""
    return Button("💳 Төлөдүм (чек жиберем)", f"pay:start:{kind}")


def show_balance(messenger, msg, account):
    """💼 Менин балансым — бир экранда бардык абал.

    Айдоочунун мөөнөтү, жүргүнчүнүн акысыз посттору, чакырылган
    достор, кийинки бонуска канча калганы жана ырасталган номер.
    """
    acc = db.get_account(account["account_id"]) or account
    lang = acc.get("lang", "ky")

    refs = acc.get("ref_count", 0) or 0
    free = acc.get("free_posts", 0) or 0
    phone = acc.get("verified_phone")
    left = days_left(acc)
    ok = has_access(acc)

    # Кийинки айдоочу бонусуна канча дос калды?
    need = REQUIRED_REFERRALS - (refs % REQUIRED_REFERRALS)
    if need == REQUIRED_REFERRALS and refs > 0:
        need = REQUIRED_REFERRALS

    # ---- Айдоочу катары ----
    if refs < REQUIRED_REFERRALS:
        ky_drv = (f"🔒 Жабык. Ачылышы үчүн дагы "
                  f"{REQUIRED_REFERRALS - refs} дос керек "
                  f"(же {PAYMENT_AMOUNT} төлөм).")
        ru_drv = (f"🔒 Закрыто. Нужно ещё "
                  f"{REQUIRED_REFERRALS - refs} друга "
                  f"(или оплата {PAYMENT_AMOUNT}).")
    elif ok:
        ky_drv = f"✅ Ачык. Дагы <b>{left} күн</b> калды."
        ru_drv = f"✅ Открыто. Осталось <b>{left} дн.</b>"
    else:
        ky_drv = (f"⏳ Мөөнөтү бүттү. Улантуу үчүн: "
                  f"{REFERRAL_BONUS_STEP} дос ({REFERRAL_BONUS_DAYS} күн) "
                  f"же {PAYMENT_AMOUNT} ({PAYMENT_HOURS} саат).")
        ru_drv = (f"⏳ Срок истёк. Чтобы продолжить: "
                  f"{REFERRAL_BONUS_STEP} друга ({REFERRAL_BONUS_DAYS} дня) "
                  f"или {PAYMENT_AMOUNT} ({PAYMENT_HOURS} часа).")

    # ---- Жүргүнчү катары ----
    if free > 0:
        ky_psg = f"✅ Дагы <b>{free} акысыз жарыя</b> бар."
        ru_psg = f"✅ Осталось <b>{free} бесплатных объявл.</b>"
    else:
        ky_psg = (f"⏳ Акысыз жарыя бүттү. 1 дос чакырсаңыз "
                  f"+{PASSENGER_NEXT_BONUS}, же {PASSENGER_POST_PRICE} "
                  f"төлөсөңүз +1 жарыя.")
        ru_psg = (f"⏳ Бесплатные закончились. Пригласите друга — "
                  f"+{PASSENGER_NEXT_BONUS}, или оплатите "
                  f"{PASSENGER_POST_PRICE} — +1 объявление.")

    ky_ph = f"📱 Номериңиз: <b>+{_digits_only(phone)}</b>" if phone else \
            "📱 Номер ырасталган эмес — биринчи жарыяда суралат."
    ru_ph = f"📱 Ваш номер: <b>+{_digits_only(phone)}</b>" if phone else \
            "📱 Номер не подтверждён — спросим при первом объявлении."

    body = L(
        f"💼 <b>Менин балансым</b>\n\n"
        f"🚖 <b>Айдоочу катары</b>\n{ky_drv}\n\n"
        f"🧳 <b>Жүргүнчү катары</b>\n{ky_psg}\n\n"
        f"👥 <b>Чакырган досторуңуз: {refs}</b>\n"
        f"Кийинки айдоочу бонусуна дагы {need} дос керек.\n\n"
        f"{ky_ph}",
        f"💼 <b>Мой баланс</b>\n\n"
        f"🚖 <b>Как водитель</b>\n{ru_drv}\n\n"
        f"🧳 <b>Как пассажир</b>\n{ru_psg}\n\n"
        f"👥 <b>Приглашено друзей: {refs}</b>\n"
        f"До следующего бонуса водителя — ещё {need}.\n\n"
        f"{ru_ph}")

    _say(messenger, msg, account, body)

    # Шилтемелер өзүнчө кабар менен — басууга ыңгайлуу болсун
    invite = _invite_block(acc, msg.platform, lang)
    kb = Keyboard.from_flat(
        _share_buttons(acc, msg.platform, lang)
        + [Button("💳 Төлөм төлөймүн", "pay_entry"),
           Button("🏠 Башкы меню", "menu:home")])
    _say(messenger, msg, account, L(
        "👥 <b>Дос чакырып, акысыз колдонуңуз</b>\n\n" + invite,
        "👥 <b>Приглашайте друзей и пользуйтесь бесплатно</b>\n\n"
        + _invite_block(acc, msg.platform, "ru")), kb)


def pay_entry(messenger, msg, account):
    """Сайттан төлөмгө түз келгенде — алгач ролду сурайбыз.

    Баалар ролго жараша башка, ошондуктан «айдоочу» же «жүргүнчү»
    экенин билбей туруп реквизит бере албайбыз.
    """
    kb = Keyboard.from_flat([
        Button("🚗 Айдоочу катары", "d_pay"),
        Button("🧳 Жүргүнчү катары", "p_pay"),
        Button("🏠 Башкы меню", "menu:home"),
    ])
    _say(messenger, msg, account, L(
        "💳 <b>Төлөм</b>\n\n"
        "Кайсы ролдо төлөйсүз?\n\n"
        f"🚗 <b>Айдоочу</b> — жарыя берүү укугу ({PAYMENT_AMOUNT}) "
        f"же VIP ({VIP_PRICE}).\n"
        f"🧳 <b>Жүргүнчү</b> — бир жарыя ({PASSENGER_POST_PRICE}).",
        "💳 <b>Оплата</b>\n\n"
        "В какой роли вы платите?\n\n"
        f"🚗 <b>Водитель</b> — право размещать объявления "
        f"({PAYMENT_AMOUNT}) или VIP ({VIP_PRICE}).\n"
        f"🧳 <b>Пассажир</b> — одно объявление "
        f"({PASSENGER_POST_PRICE})."), kb)


def pay_menu(messenger, msg, account, role):
    """«💳 Төлөм төлөймүн» — эмне үчүн төлөөрүн тандоо экраны.

    Айдоочуга эки нерсе: жарыя берүү укугу жана VIP.
    Жүргүнчүгө бирөө: бир жарыя.
    """
    if role == "driver":
        kb = Keyboard.from_flat([
            Button(f"💳 Жарыя берүү укугу — {PAYMENT_AMOUNT}", "pay:start:access"),
            Button(f"⭐ VIP айдоочу — {VIP_PRICE}", "pay:start:vip"),
            _back_btn(),
        ])
        return _say(messenger, msg, account, L(
            f"💳 <b>Төлөм</b>\n\n"
            f"Эмне үчүн төлөөрүңүздү тандаңыз:\n\n"
            f"<b>💳 Жарыя берүү укугу — {PAYMENT_AMOUNT}</b>\n"
            f"{PAYMENT_HOURS} саат бою чектөөсүз жарыя бересиз.\n\n"
            f"<b>⭐ VIP айдоочу — {VIP_PRICE}</b>\n"
            f"{VIP_HOURS} саат бою жарыяңыз издөө тизмесинин эң "
            f"үстүндө турат.\n\n"
            f"<i>Тандагандан кийин реквизиттер чыгат. Төлөп, чектин "
            f"скриншотун ушул жерге жиберсеңиз, админ текшерип, "
            f"автоматтык ачылат.</i>",
            f"💳 <b>Оплата</b>\n\n"
            f"Выберите, за что платите:\n\n"
            f"<b>💳 Право размещать объявления — {PAYMENT_AMOUNT}</b>\n"
            f"{PAYMENT_HOURS} часа объявлений без ограничений.\n\n"
            f"<b>⭐ VIP-водитель — {VIP_PRICE}</b>\n"
            f"{VIP_HOURS} часа ваше объявление в самом верху списка.\n\n"
            f"<i>После выбора появятся реквизиты. Оплатите и отправьте "
            f"сюда скриншот чека — администратор проверит, и доступ "
            f"откроется автоматически.</i>"), kb)

    kb = Keyboard.from_flat([
        Button(f"💳 Бир жарыя — {PASSENGER_POST_PRICE}", "pay:start:post"),
        _back_btn(),
    ])
    _say(messenger, msg, account, L(
        f"💳 <b>Төлөм</b>\n\n"
        f"<b>Бир жарыя — {PASSENGER_POST_PRICE}</b>\n\n"
        f"Акысыз жарыяңыз бүтсө, ушул аркылуу улантасыз.\n\n"
        f"<i>Баскычты бассаңыз реквизиттер чыгат. Төлөп, чектин "
        f"скриншотун ушул жерге жиберсеңиз, админ текшерип, "
        f"автоматтык кошулат.</i>",
        f"💳 <b>Оплата</b>\n\n"
        f"<b>Одно объявление — {PASSENGER_POST_PRICE}</b>\n\n"
        f"Когда бесплатные объявления закончатся, продолжить можно "
        f"так.\n\n"
        f"<i>Нажмите кнопку — появятся реквизиты. Оплатите и отправьте "
        f"сюда скриншот чека: администратор проверит, и объявление "
        f"добавится автоматически.</i>"), kb)


def start_payment(messenger, msg, account, kind):
    """«💳 Төлөдүм» басылды — реквизиттерди берип, чек күтөбүз."""
    info = PAY_KINDS.get(kind)
    if not info:
        return _say(messenger, msg, account, "❌ Төлөмдүн түрү белгисиз.", back_kb())

    PAY_WAIT[msg.user_id] = kind
    _say(messenger, msg, account, L(
        f"{info['ky_title']}\n\n"
        f"{PAYMENT_REQUISITES}\n\n"
        f"💰 Сумма: <b>{info['amount']}</b>\n"
        f"🎁 Берет: {info['ky_gives']}\n\n"
        f"📷 Төлөгөндөн кийин чектин скриншотун ушул жерге жибериңиз.\n"
        f"Админ текшергенден кийин автоматтык ачылат.",
        f"{info['ru_title']}\n\n"
        f"{PAYMENT_REQUISITES}\n\n"
        f"💰 Сумма: <b>{info['amount']}</b>\n"
        f"🎁 Даёт: {info['ru_gives']}\n\n"
        f"📷 После оплаты отправьте сюда скриншот чека.\n"
        f"После проверки доступ откроется автоматически."), back_kb())


def receive_receipt(messenger, msg, account, kind):
    """Колдонуучудан келген төлөм чегин админге жиберет."""
    ok = admin.notify_payment(account, msg.photo_id, msg.platform, kind)
    if ok:
        _say(messenger, msg, account, L(
            "✅ Чегиңиз админге жиберилди.\n\n"
            "Текшерилгенден кийин сизге кабар келет.",
            "✅ Ваш чек отправлен администратору.\n\n"
            "После проверки вы получите уведомление."))
    else:
        _say(messenger, msg, account, L(
            "⚠️ Чекти жиберүүдө ката кетти. Кайра аракет кылыңыз.",
            "⚠️ Ошибка при отправке чека. Попробуйте ещё раз."), hint=True)


