# -*- coding: utf-8 -*-
# core/logic/menu.py — Меню экрандары.
# Импорттор жана жалпы аталыштар common.py'де; бул файл
# core/logic/__init__.py аркылуу ошол мейкиндикке жүктөлөт.

# ============ МЕНЮ ============

def _menu_button(messenger, msg, account):
    """Навигация тарыхын жүргүзүп, экранды көрсөтөт."""
    a = msg.button_action

    if a == "menu:home":
        SESSIONS.pop(msg.user_id, None)
        NAV.pop(msg.user_id, None)
        PAY_WAIT.pop(msg.user_id, None)
        return _say(messenger, msg, account, MENU_TITLE, main_menu_kb(msg.platform))

    if a == "wback":
        PAY_WAIT.pop(msg.user_id, None)
        stack = NAV.get(msg.user_id, [])
        if stack:
            stack.pop()                      # учурдагы экранды алып салабыз
        prev = stack[-1] if stack else None
        if not prev:
            NAV.pop(msg.user_id, None)
            return _say(messenger, msg, account, MENU_TITLE,
                        main_menu_kb(msg.platform))
        return _dispatch(messenger, msg, account, prev)

    if _is_screen(a):
        _nav_push(msg.user_id, a)

    return _dispatch(messenger, msg, account, a)


def _dispatch(messenger, msg, account, a):
    """Баскычтын кодун тиешелүү экранга багыттайт."""
    if a == "menu:driver":
        return driver_entry(messenger, msg, account)
    if a == "menu:passenger":
        free = account.get("free_posts", 0) or 0
        if free <= 0:
            invite = _invite_block(account, msg.platform, "ky")
            invite_ru = _invite_block(account, msg.platform, "ru")
            return _say(messenger, msg, account, L(
                 f"💡 Акысыз жарыяңыз бүттү, бирок улантсаңыз болот!\n\n"
                 f"💳 Баасы: {PASSENGER_POST_PRICE}\n{PAYMENT_REQUISITES}\n\n"
                 f"🎁 Же 1 дос чакырсаңыз — дагы {PASSENGER_NEXT_BONUS} жарыя:\n\n"
                 f"{invite}",
                 f"💡 Бесплатные объявления закончились, но вы можете продолжить!\n\n"
                 f"💳 Стоимость: {PASSENGER_POST_PRICE}\n{PAYMENT_REQUISITES}\n\n"
                 f"🎁 Или пригласите 1 друга — ещё {PASSENGER_NEXT_BONUS} объявл.:\n\n"
                 f"{invite_ru}"),
                 Keyboard.from_flat(_share_buttons(account, msg.platform,
                                   account.get("lang", "ky"))
                                   + [pay_btn("post"), _back_btn()]))
        return _say(messenger, msg, account, L(
            f"🧳 Акысыз жарыяңыз: дагы {free}\n\nТандаңыз:",
            f"🧳 Бесплатных объявлений: ещё {free}\n\nВыберите:"),
            passenger_menu_kb())
    if a.startswith("pay:start:"):
        return start_payment(messenger, msg, account, a.split(":")[2])
    if a == "menu:more":  #MORE1
        return _say(messenger, msg, account, MENU_TITLE, more_kb())
    if a == "menu:help":
        return help_menu(messenger, msg, account)
    if a == "menu:balance":
        return show_balance(messenger, msg, account)
    if a == "menu:site":
        return show_site(messenger, msg, account)
    if a == "menu:guide":
        return _say(messenger, msg, account, GUIDE, back_kb())
    if a == "menu:safety":
        return _say(messenger, msg, account, DRIVER_SAFETY, back_kb())
    if a == "menu:faq":
        return faq_menu(messenger, msg, account)
    if a.startswith("faq:"):
        return faq_section(messenger, msg, account, a.split(":")[1])
    if a == "menu:channel":
        # Telegram'да URL баскычы — басканда дароо каналга өтөт.
        # WhatsApp'та мындай баскыч жок, ошондуктан шилтеме текст менен.
        if msg.platform == "telegram":
            kb = Keyboard.from_flat([
                Button("📢 Каналга өтүү", "noop", CHANNEL_LINK),
                _back_btn(),
            ])
            return _say(messenger, msg, account, L(
                "📢 <b>Биздин канал</b>\n\n"
                "Айдоочулардын жарыялары каналга чыгып турат — "
                "жазылып койсоңуз, эң жаңыларын биринчи болуп көрөсүз.",
                "📢 <b>Наш канал</b>\n\n"
                "Объявления водителей публикуются в канале — подпишитесь, "
                "и вы первыми увидите самые свежие."), kb)
        return _say(messenger, msg, account,
            f"📢 <b>Биздин канал</b>\n\n"
            f"Айдоочулардын жарыялары каналга чыгып турат — "
            f"жазылып койсоңуз, эң жаңыларын биринчи болуп көрөсүз.\n\n"
            f"{CHANNEL_LINK}", back_kb())
    if a == "menu:lang":
        return _say(messenger, msg, account,
                    "🌐 Тилди тандаңыз / Выберите язык:", lang_kb())
    if a.startswith("setlang:"):
        new_lang = a.split(":")[1]
        db.update_account(account["account_id"], lang=new_lang)
        account = db.get_account(account["account_id"])
        NAV.pop(msg.user_id, None)
        return _say(messenger, msg, account, MENU_TITLE, main_menu_kb(msg.platform))
    if a == "d_types":
        return post_types(messenger, msg, account, "driver")
    if a == "p_types":
        return post_types(messenger, msg, account, "passenger")
    if a == "d_my":
        return show_my_posts(messenger, msg, account, "driver")
    if a == "p_my":
        return show_my_posts(messenger, msg, account, "passenger")
    if a == "d_vip":
        return show_vip(messenger, msg, account)
    if a == "pay_entry":
        return pay_entry(messenger, msg, account)
    if a in ("d_pay", "p_pay"):
        return pay_menu(messenger, msg, account,
                        "driver" if a == "d_pay" else "passenger")
    if a == "d_search":
        return search_menu(messenger, msg, account, "passenger")
    if a == "p_search":
        # Жүргүнчүгө айдоочулар керек — сайтта дал ошолор турат.
        # Ошондуктан алгач сайтты сунуштайбыз.
        return passenger_search(messenger, msg, account)
    if a == "p_search_bot":
        return search_menu(messenger, msg, account, "driver")
    if a.startswith("del:"):
        return delete_post(messenger, msg, account, int(a.split(":")[1]))
    if a.startswith("sd:"):
        return ask_new_seats(messenger, msg, account, int(a.split(":")[1]))
    if a.startswith("sset:"):
        _, pid, val = a.split(":", 2)
        return set_new_seats(messenger, msg, account, int(pid), int(val))
    if a.startswith("tw:"):
        return ask_new_time(messenger, msg, account, int(a.split(":")[1]))
    if a.startswith("tset:"):
        _, pid, val = a.split(":", 2)
        return set_new_time(messenger, msg, account, int(pid), val)
    if a.startswith("sb:"):
        return search_bishkek(messenger, msg, account, a)
    if a.startswith("sr:"):
        return show_results(messenger, msg, account, a)
    if a.startswith("lo:"):
        return local_oblast_from(messenger, msg, account, a)
    if a.startswith("lof:"):
        return local_oblast_to(messenger, msg, account, a)
    if a.startswith("lot:"):
        return local_oblast_results(messenger, msg, account, a)
    if a.startswith("lr:"):
        return local_results(messenger, msg, account, a)
    if a.startswith("ht:"):
        # «ht:12»    — ошол багыттагы БААРЫ (канал баскычы)
        # «ht:12:o»  — карама-каршы рол гана (өз жарыяңдан кийинки баскыч)
        parts = a.split(":")
        only_other = len(parts) > 2 and parts[2] == "o"
        return hashtag_search(messenger, msg, account, int(parts[1]),
                              only_other=only_other)

    _say(messenger, msg, account, "Бул баскыч азырынча иштелип чыккан жок.")


def show_site(messenger, msg, account):
    """🌐 Сайт — жарыяларды браузерден көрүү.

    Telegram'да басылуучу URL баскычы чыгат. WhatsApp мындай баскычты
    колдобойт, ошондуктан ал жерде шилтеме текст менен берилет —
    WhatsApp аны өзү басылуучу кылат.
    """
    body = SITE_INFO or L(
        f"🌐 <b>ТАКСИ роБОТ — сайтыбыз</b>\n\n"
        f"<b>{SITE_SHORT}</b>\n\n"
        f"Браузерден ачыла берет — каттоонун кереги жок.\n\n"
        f"Сайтта бардык активдүү айдоочулар багыт боюнча тизме менен "
        f"чыгат: облус боюнча чыпкалайсыз, шаар издейсиз, кыргызча же "
        f"орусчага которосуз. Ар бир жарыяда чалуу, WhatsApp жана "
        f"Telegram баскычтары даяр турат.\n\n"
        f"⚠️ Сайт жарыяларды <b>көрсөтөт гана</b> — жарыя берүү ботто "
        f"калат.\n\n"
        f"💡 Шилтемени досторуңузга жибериңиз: алар ботту орнотпой эле "
        f"айдоочуларды таба алат.",
        f"🌐 <b>ТАКСИ роБОТ — наш сайт</b>\n\n"
        f"<b>{SITE_SHORT}</b>\n\n"
        f"Открывается в браузере — регистрация не нужна.\n\n"
        f"На сайте все активные водители выводятся списком по "
        f"направлениям: можно отфильтровать по области, найти город, "
        f"переключить язык. У каждого объявления готовы кнопки звонка, "
        f"WhatsApp и Telegram.\n\n"
        f"⚠️ Сайт <b>только показывает</b> объявления — публикация "
        f"остаётся в боте.\n\n"
        f"💡 Отправьте ссылку друзьям: они найдут водителя, даже не "
        f"устанавливая бот.")

    if msg.platform == "telegram":
        kb = Keyboard.from_flat([
            Button("🌐 Сайтты ачуу", "noop", SITE_URL),
            _back_btn(),
        ])
        return _say(messenger, msg, account, body, kb)

    # WhatsApp: баскыч жок — шилтемени тексттин аягына кошобуз
    if isinstance(body, tuple):
        body = ("__L__",
                body[1] + f"\n\n{SITE_URL}",
                body[2] + f"\n\n{SITE_URL}")
        return _say(messenger, msg, account, body, back_kb())
    _say(messenger, msg, account, body, back_kb())


def hashtag_search(messenger, msg, account, post_id, only_other=False,
                   only_role=None):
    """Жарыянын багыты боюнча издейт (издөө баскычы басылганда).

    Telegram'да билдирүүдөгү хештегди басканда, ал ботко жиберилбейт —
    Telegram өзүнүн издөөсүн ачат. Ошондуктан баскыч колдонобуз.

    only_role — так кайсы рол керек ("driver" же "passenger").
        Каналдан келгендерге ар дайым "driver" берилет: каналда
        айдоочулардын жарыясы турат, аны көргөн адам да айдоочу
        издеп жүрөт. Айдоочулар жүргүнчүнү өз бөлүмүнөн табат.

    only_other=True — карама-каршы рол: айдоочу издесе жүргүнчүлөр,
        жүргүнчү издесе айдоочулар. Колдонуучу өз жарыясын жазып
        бүткөндөн кийин колдонулат.
    """
    p = posts.get_post(post_id)
    if not p:
        return _say(messenger, msg, account, "❌ Жарыя табылган жок.", back_kb())
    tag = hashtag(p.get("from_city"), p.get("to_city"))
    if only_other and not only_role:
        only_role = "passenger" if p.get("role") == "driver" else "driver"
    _show_hashtag_results(messenger, msg, account, tag,
                          p.get("from_city"), p.get("to_city"),
                          only_role=only_role)


def help_menu(messenger, msg, account):
    """🆘 Жардам — нускама, суроо-жооптор, коопсуздук жана сайт."""
    kb = Keyboard(rows=[
        [Button("📖 Нускама", "menu:guide")],
        [Button("❓ Көп берилүүчү суроолорго жооп", "menu:faq")],
        [Button("🛡 Айдоочунун коопсуздугу", "menu:safety"),
         Button("🌐 Сайт", "menu:site")],
        [_back_btn()],
    ])
    _say(messenger, msg, account, L(
         "🆘 <b>Жардам</b>\n\nЭмне керек экенин тандаңыз:",
         "🆘 <b>Помощь</b>\n\nВыберите, что вам нужно:"), kb)


def faq_menu(messenger, msg, account):
    """Көп берилүүчү суроолордун бөлүмдөрү."""
    kb = Keyboard(rows=[
        [Button("➕ Жарыя кантип берем?", "faq:howto")],
        [Button("📝 Жарыя жөнүндө", "faq:post"),
         Button("🎁 Акысыз мүмкүнчүлүк", "faq:free")],
        [Button("🔍 Издөө", "faq:search"),
         Button("💳 Төлөм жана баалар", "faq:pay")],
        [Button("🗺 Жүргүнчүлөрдү чогултуу", "faq:pickup")],
        [Button("📞 Байланыш", "faq:contact"),
         Button("🛡 Коопсуздук", "faq:safety")],
        [Button("🛠 Көйгөйлөр жана чечими", "faq:trouble")],
        [Button("📜 Колдонуу эрежелери", "faq:rules"),
         Button("🔒 Купуялык", "faq:privacy")],
        [_back_btn()],
    ])
    _say(messenger, msg, account, FAQ_INTRO, kb)


# Нускама core/texts.py'де — ботто да, сайтта да бир эле текст
from core.texts import FAQ_PICKUP as _TX_PICKUP
from core.texts import FAQ_PICKUP_RU as _TX_PICKUP_RU

FAQ_PICKUP = L(_TX_PICKUP, _TX_PICKUP_RU)


FAQ_SECTIONS = {
    "howto": FAQ_HOWTO,
    "post": FAQ_POST,
    "free": FAQ_FREE,
    "search": FAQ_SEARCH,
    "pickup": FAQ_PICKUP,
    "pay": FAQ_PAY,
    "contact": FAQ_CONTACT,
    "safety": FAQ_SAFETY,
    "trouble": FAQ_TROUBLE,
    "rules": FAQ_RULES,
    "privacy": FAQ_PRIVACY,
}


def faq_section(messenger, msg, account, key):
    """Тандалган бөлүмдүн суроо-жооптору."""
    text = FAQ_SECTIONS.get(key)
    if not text:
        return _say(messenger, msg, account, "❌ Бул бөлүм табылган жок.", back_kb())
    _say(messenger, msg, account, text, back_kb())


def driver_entry(messenger, msg, account):
    invite = _invite_block(account, msg.platform, "ky")
    invite_ru = _invite_block(account, msg.platform, "ru")

    # 1-этап: гейт ачыла элек
    if (account["ref_count"] or 0) < REQUIRED_REFERRALS:
        return _say(messenger, msg, account, L(
            f"🚫 Жарыя берүү үчүн {REQUIRED_REFERRALS} дос чакырышыңыз керек.\n"
            f"Учурдагы прогресс: {account['ref_count'] or 0}/{REQUIRED_REFERRALS}\n\n"
            f"🎁 Ачылганда {GATE_BONUS_DAYS} күн акысыз жарыя бересиз!\n\n"
            f"💳 Же {PAYMENT_AMOUNT} төлөп, {PAYMENT_HOURS} саатка дароо ачсаңыз болот.\n\n"
            f"{invite}",
            f"🚫 Чтобы оставить объявление, пригласите {REQUIRED_REFERRALS} друзей.\n"
            f"Текущий прогресс: {account['ref_count'] or 0}/{REQUIRED_REFERRALS}\n\n"
            f"🎁 После открытия вы получите {GATE_BONUS_DAYS} дней бесплатно!\n\n"
            f"💳 Или оплатите {PAYMENT_AMOUNT} — {PAYMENT_HOURS} часа сразу.\n\n"
            f"{invite_ru}"),
            Keyboard.from_flat(_share_buttons(account, msg.platform,
                              account.get("lang", "ky"))
                              + [pay_btn("access"), _back_btn()]))

    # 2-этап: гейт ачык, бирок мөөнөт бүткөн → төлөм же дос чакыруу
    if not has_access(account):
        return _say(messenger, msg, account, L(
            f"⏳ Акысыз мөөнөтүңүз бүттү.\n\n"
            f"Улантуу үчүн:\n"
            f"🎁 {REQUIRED_REFERRALS} дос чакырыңыз — {REFERRAL_BONUS_DAYS} күн акысыз\n"
            f"💳 Же {PAYMENT_AMOUNT} төлөңүз — {PAYMENT_HOURS} саат\n\n"
            f"{PAYMENT_REQUISITES}\n\n"
            f"{invite}",
            f"⏳ Бесплатный период закончился.\n\n"
            f"Чтобы продолжить:\n"
            f"🎁 Пригласите {REQUIRED_REFERRALS} друзей — {REFERRAL_BONUS_DAYS} дней бесплатно\n"
            f"💳 Или оплатите {PAYMENT_AMOUNT} — {PAYMENT_HOURS} часа\n\n"
            f"{PAYMENT_REQUISITES}\n\n"
            f"{invite_ru}"),
            Keyboard.from_flat(_share_buttons(account, msg.platform,
                              account.get("lang", "ky"))
                              + [pay_btn("access"), _back_btn()]))

    # 3-этап: баары ачык
    left = days_left(account)
    quota, _free_at = daily_limit_left(account["account_id"], "driver")
    q = max(0, quota) if quota is not None else None
    ky_q = f"📝 Бүгүн дагы {q} жарыя бере аласыз\n" if q is not None else ""
    ru_q = f"📝 Сегодня можно опубликовать ещё {q} объявл.\n" if q is not None else ""
    _say(messenger, msg, account, L(
         f"✅ Акысыз мөөнөтүңүз: дагы {left} күн\n{ky_q}\nТандаңыз:",
         f"✅ Ваш бесплатный период: ещё {left} дн.\n{ru_q}\nВыберите:"),
         driver_menu_kb())


def show_vip(messenger, msg, account):
    invite = _invite_block(account, msg.platform, "ky")
    invite_ru = _invite_block(account, msg.platform, "ru")
    _say(messenger, msg, account, L(
        f"⭐ <b>VIP айдоочу</b>\n\n"
        f"VIP болсоңуз, жарыяңыз издөө тизмесинин эң үстүнөн чыгат!\n\n"
        f"💳 Баасы: {VIP_PRICE}\n{PAYMENT_REQUISITES}\n\n"
        f"🎁 Же {VIP_REFERRAL_STEP} дос чакырсаңыз — акысыз:\n\n"
        f"{invite}",
        f"⭐ <b>VIP-водитель</b>\n\n"
        f"С VIP ваше объявление показывается в самом верху списка!\n\n"
        f"💳 Стоимость: {VIP_PRICE}\n{PAYMENT_REQUISITES}\n\n"
        f"🎁 Или пригласите {VIP_REFERRAL_STEP} друзей — бесплатно:\n\n"
        f"{invite_ru}"),
        Keyboard.from_flat(_share_buttons(account, msg.platform,
                          account.get("lang", "ky"))
                          + [pay_btn("vip"), _back_btn()]))


