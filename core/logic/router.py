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
    # Айдоочу forward кылган 📍 локация (адаптерлер ушул префикс менен берет)
    if text.startswith(PICKUP_LOC_PREFIX):
        return pickup_location(messenger, msg, account, text)
    # Сайттагы жарыя үчүн Telegram'дан контакт келди
    if msg.user_id in WEB_WAIT and getattr(msg, "verified", False):
        return web_phone(messenger, msg, account, text)
    # Сайттагы төлөм үчүн контакт келди
    if msg.user_id in LOGIN_WAIT and getattr(msg, "verified", False):
        return login_phone(messenger, msg, account, text)
    if msg.user_id in PAY_LINK_WAIT and getattr(msg, "verified", False):
        return pay_phone(messenger, msg, account, text)
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
        elif len(parts) > 1 and (parts[1].startswith("ht")
                                 or parts[1].startswith("tag_")
                                 or parts[1] in ("balance", "myposts",
                                                 "pay", "postd", "postp")):
            # v133: жарыя берүү, издөө, баланс, төлөм бөлүмү — баары
            # сайтта. Эски шилтемелер сайтка чакырууну көрсөтөт.
            return show_site(messenger, msg, account)
        elif len(parts) > 1 and parts[1].startswith("pay_"):
            # Сайттагы «Төлөм» бетинен түз келди — түрү белгилүү
            return pay_from_web(messenger, msg, account, parts[1][4:])
        elif len(parts) > 1 and parts[1].startswith("l_"):
            # Сайтка кирүү: браузерди аккаунтка байлайбыз
            return web_login(messenger, msg, account, parts[1][2:])
        elif len(parts) > 1 and parts[1].startswith("v_"):
            # Сайттан берилген жарыяны ырастоо
            return web_start(messenger, msg, account, parts[1][2:])
        # Таза "/start" — биринчи таанышуу, толук текст.
        # "/start home" (каналдан) же башка параметр — кыска аталыш.
        # v133: эски узун WELCOME эми туура эмес — боттун
        # милдети номер ырастоо гана
        head = BOT_WELCOME
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
        # v133: издөө сайтка көчтү
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return show_site(messenger, msg, account)

    # Сайттын «Кабинет» бетинен WhatsApp ботко жарыяларын көрүүгө келгендер
    # v133: бул үч бөлүм сайтка көчтү
    if text.strip().lower() in (MYPOSTS_TEXT.lower(), BALANCE_TEXT.lower(),
                                PAY_TEXT.lower()):
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return show_site(messenger, msg, account)

    # Сайттагы «Жарыя берүү» бетинен WhatsApp ботко түз келгендер:
    # «Жарыя берем: айдоочу» же «Жарыя берем: жүргүнчү»
    if text.startswith(POST_PREFIX):
        # v133: жарыя берүү сайтта
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return show_site(messenger, msg, account)

    # Сайттагы төлөм бетинен WhatsApp аркылуу: «ТӨЛӨМ access»
    _mp = re.match(r"(?i)^\s*т[өо]л[өо]м\s+(access|vip|post)\b", text)
    if _mp:
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return pay_from_web(messenger, msg, account, _mp.group(1).lower())

    # Сайтка кирүү коду — кабардын каалаган жеринде болсо жетиштүү
    _ml = re.search(r"(?i)\bl_([A-Za-z0-9_-]{6,})\b", text)
    if _ml:
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return web_login(messenger, msg, account, _ml.group(1))

    # Сайттан берилген жарыяны ырастоо. Telegram кээде шилтемедеги
    # параметрди ботко жеткирбейт, ошондуктан кодду кабардын каалаган
    # жеринен издейбиз: «ЫРАСТОО v_XXXX», «v_XXXX» же жөн эле көчүрүлгөн.
    _mv = re.search(r"(?i)\bv_([A-Za-z0-9_-]{6,})\b", text)
    if _mv:
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return web_start(messenger, msg, account, _mv.group(1))

    # Төлөм коду да ушундай: «pay_access» кабардын ичинде болсо жетиштүү
    _mpc = re.search(r"(?i)\bpay_(access|vip|post)\b", text)
    if _mpc:
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return pay_from_web(messenger, msg, account, _mpc.group(1).lower())

    # Эски формат: «HT85» деген кыска код (багыт белгисиз болгон учурда)
    if re.fullmatch(r"(?i)ht\d+", text):
        # v133: издөө сайтка көчтү
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        return show_site(messenger, msg, account)

    # «🗺 Жүргүнчүлөрдү чогултуу» баскычтары — визарддан көз карандысыз
    if msg.is_button and (msg.button_action or "").startswith("pku:"):
        return pickup_button(messenger, msg, account)

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
        # v133: издөө сайтка көчтү
        return show_site(messenger, msg, account)

    # v133: бот бөлүмдөрү сайтта — колдонуучуну ошол жакка жөнөтөбүз
    _say(messenger, msg, account, BOT_WELCOME,
         main_menu_kb(msg.platform))


