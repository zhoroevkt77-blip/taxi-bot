# -*- coding: utf-8 -*-
# core/logic/router.py — Кирүү чекити: handle_update жана callback'тер.
# Импорттор жана жалпы аталыштар common.py'де; бул файл
# core/logic/__init__.py аркылуу ошол мейкиндикке жүктөлөт.

# ============ КИРҮҮ НУКТАСЫ ============

def handle_update(messenger, msg):
    account = db.get_or_create_account(msg.user_id, msg.platform)
    session = SESSIONS.get(msg.user_id)

    # ---- Сүрөт келдиби? ----
    if getattr(msg, "photo_id", None):
        # 1) Визардда сүрөт кадамында турабызбы? — жарыянын сүрөтү
        st = SESSIONS.get(msg.user_id)
        if st and st.get("step") == "photo":
            ref = msg.photo_id
            # Telegram file_id берет, WhatsApp — ачык шилтеме.
            # Экөөнү эки башка мамычага жазабыз.
            if str(ref).startswith("http"):
                st["data"]["photo_url"] = ref
            else:
                st["data"]["photo_id"] = ref
            _say(messenger, msg, account, L(
                "✅ Сүрөт кабыл алынды.", "✅ Фото принято."))
            return next_step(messenger, msg, account, st, "photo")

        # Сүрөт кадамынан өтүп кеткенден кийин дагы сүрөт келсе —
        # аны жарыяга кошпойбуз, бирок колдонуучу чаташпасын
        if st and st.get("step") in steps_of(st.get("role", "driver")):
            return _say(messenger, msg, account, L(
                "📷 Сүрөт кадамы өтүп кетти. Суроого жооп бериңиз, "
                "же «🔙 Артка» басып кайтыңыз.",
                "📷 Шаг с фото уже пройден. Ответьте на вопрос или "
                "нажмите «🔙 Назад», чтобы вернуться."), hint=True)

        # 2) Болбосо — төлөм чеги
        kind = PAY_WAIT.pop(msg.user_id, None)
        if kind:
            return receive_receipt(messenger, msg, account, kind)
        return _say(messenger, msg, account, L(
            "📷 Сүрөт алдым, бирок азыр ал керек эмес.",
            "📷 Фото получено, но сейчас оно не требуется."), hint=True)

    text = (msg.text or "").strip()
    if text == "/admin" and admin.handle_command(messenger, msg, account, _say):
        return
    if text.startswith("/start") or text in ("старт", "start"):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        PAY_WAIT.pop(msg.user_id, None)
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith("ref"):
            try:
                inviter_id = int(parts[1][3:])
                register_referral(messenger, account, inviter_id)
                account = db.get_account(account["account_id"])
            except ValueError:
                pass
        elif len(parts) > 1 and parts[1].startswith("ht"):
            # Каналдагы «🔍 Telegram Ботто издөө» баскычы.
            # Каналда айдоочулардын жарыясы турат — ошондуктан
            # айдоочуларды гана чыгарабыз.
            try:
                return hashtag_search(messenger, msg, account,
                                      int(parts[1][2:]), only_role="driver")
            except ValueError:
                pass
        elif len(parts) > 1 and parts[1] == "balance":
            # Сайттын «Кабинет» бетинен балансты көрүүгө келди
            return show_balance(messenger, msg, account)
        elif len(parts) > 1 and parts[1] == "myposts":
            # Сайттын «Кабинет» бетинен өз жарыяларын көрүүгө келди
            kb = Keyboard.from_flat([
                Button("🚗 Айдоочу катары", "d_my"),
                Button("🧳 Жүргүнчү катары", "p_my"),
                Button("🏠 Башкы меню", "menu:home"),
            ])
            return _say(messenger, msg, account, L(
                "📄 <b>Менин жарыяларым</b>\n\nКайсы ролдогу жарыяларыңыз?",
                "📄 <b>Мои объявления</b>\n\nОбъявления в какой роли?"), kb)
        elif len(parts) > 1 and parts[1] == "pay":
            # Сайттын «Кабинет» бетинен төлөмгө түз келди
            return pay_entry(messenger, msg, account)
        elif len(parts) > 1 and parts[1] in ("postd", "postp"):
            # Сайттагы «Жарыя берүү» бетинен түз келди —
            # дароо жарыя жазуу визардын баштайбыз
            role = "driver" if parts[1] == "postd" else "passenger"
            return post_types(messenger, msg, account, role)
        elif len(parts) > 1 and parts[1].startswith("tag_"):
            frm, _, to = parts[1][4:].partition("_")
            if frm and to:
                return _show_hashtag_results(messenger, msg, account, f"#{frm}_{to}", frm, to)

        # Таза "/start" — биринчи таанышуу, толук текст.
        # "/start home" (каналдан) же башка параметр — кыска аталыш.
        head = MENU_TITLE if len(parts) > 1 else WELCOME
        return _say(messenger, msg, account, head, main_menu_kb(msg.platform))

    # WhatsApp referral: колдонуучу "REF12" деген текст жиберет
    if re.fullmatch(r"(?i)ref\d+", text):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        try:
            register_referral(messenger, account, int(text[3:]))
            account = db.get_account(account["account_id"])
        except ValueError:
            pass
        return _say(messenger, msg, account, MENU_TITLE, main_menu_kb(msg.platform))

    # Каналдагы «🔍 WhatsApp Ботто издөө» баскычы даярдаган текст:
    # «Издөө: Манас району ➡️ Бишкек». Колдонуучу жөнөтүү басканда,
    # бот аны таанып, ошол багыттагы АЙДООЧУЛАРДЫ чыгарат.
    if text.startswith(SEARCH_PREFIX):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        body = text[len(SEARCH_PREFIX):]
        parts = re.split(r"[➡→>]+\ufe0f?", body)
        if len(parts) >= 2:
            frm, to = parts[0].strip(), parts[1].strip()
            if frm and to:
                return _show_hashtag_results(messenger, msg, account,
                                             f"{frm}_{to}", frm, to,
                                             only_role="driver")

    # Сайттын «Кабинет» бетинен WhatsApp ботко жарыяларын көрүүгө келгендер
    if text.strip().lower() == MYPOSTS_TEXT.lower():
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        kb = Keyboard.from_flat([
            Button("🚗 Айдоочу катары", "d_my"),
            Button("🧳 Жүргүнчү катары", "p_my"),
            Button("🏠 Башкы меню", "menu:home"),
        ])
        return _say(messenger, msg, account, L(
            "📄 <b>Менин жарыяларым</b>\n\nКайсы ролдогу жарыяларыңыз?",
            "📄 <b>Мои объявления</b>\n\nОбъявления в какой роли?"), kb)

    # Сайттын «Кабинет» бетинен WhatsApp ботко баланс көрүүгө келгендер
    if text.strip().lower() == BALANCE_TEXT.lower():
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return show_balance(messenger, msg, account)

    # Сайттын «Кабинет» бетинен WhatsApp ботко төлөмгө келгендер
    if text.strip().lower() == PAY_TEXT.lower():
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return pay_entry(messenger, msg, account)

    # Сайттагы «Жарыя берүү» бетинен WhatsApp ботко түз келгендер:
    # «Жарыя берем: айдоочу» же «Жарыя берем: жүргүнчү»
    if text.startswith(POST_PREFIX):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        who = text[len(POST_PREFIX):].strip().lower()
        role = "driver" if who.startswith("айдооч") else "passenger"
        return post_types(messenger, msg, account, role)

    # Эски формат: «HT85» деген кыска код (багыт белгисиз болгон учурда)
    if re.fullmatch(r"(?i)ht\d+", text):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        try:
            return hashtag_search(messenger, msg, account, int(text[2:]),
                                  only_role="driver")
        except ValueError:
            pass

    if session:
        # "🏠 Башкы меню" визарддын ичинен да иштеши керек
        if msg.is_button and msg.button_action == "menu:home":
            SESSIONS.pop(msg.user_id, None)
            NAV.pop(msg.user_id, None)
            return _say(messenger, msg, account, MENU_TITLE, main_menu_kb(msg.platform))
        if msg.is_button:
            return _wizard_button(messenger, msg, account, session)
        return _wizard_text(messenger, msg, account, session)

    if msg.is_button:
        if admin.handle_button(messenger, msg, account, _say):
            return
        return _menu_button(messenger, msg, account)

    if admin.handle_text(messenger, msg, account, _say):
        return

    if text.startswith("#"):
        return _hashtag(messenger, msg, account, text)

    _say(messenger, msg, account, L(
        "Түшүнбөй калдым 🙈 /start деп жазып көрүңүз.",
        "Не понял 🙈 Попробуйте написать /start."), hint=True)


