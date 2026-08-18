# -*- coding: utf-8 -*-
"""
core/notify.py
==============
Платформа аралык кабарлоо.

КӨЙГӨЙ: Telegram менен WhatsApp эки өзүнчө потокто иштейт (main.py'ды
караңыз) жана бири-бирин билбейт. Жүргүнчү Telegram'дан жарыя жазса,
logic.py'ге Telegram адаптери келет — ал эми айдоочу WhatsApp'та
отурушу мүмкүн. Ага кабар жиберүү үчүн WhatsApp адаптери керек.

ЧЕЧИМ: main.py эки адаптерди тең жүктөгөндүктөн, алардын `messenger`
объекттери эстутумда даяр турат. Аларды керек учурда импорттоп алабыз —
адаптерлердин кодуна тийүүнүн кажети жок.

ЭСКЕРТҮҮ: импорт функциянын ИЧИНДЕ жазылат. Модулдун башында жазсак,
айлампа импорт чыгат: logic → notify → adapters → logic.
"""

from core.db import db

NOTIFY_VERSION = "v1"
print(f"🔔 core/notify.py жүктөлдү. Версия = {NOTIFY_VERSION}")


def _messenger_for(platform):
    """Ошол платформанын messenger объектин кайтарат.

    main.py адаптерлерди мурда импорттогондуктан, бул жерде ошол эле
    объект кайтат — жаңысы түзүлбөйт.
    """
    try:
        if platform == "telegram":
            from adapters.telegram_adapter import messenger
            return messenger
        if platform == "whatsapp":
            from adapters.whatsapp_adapter import messenger
            return messenger
    except Exception as e:
        print(f"[notify] {platform} адаптерин алуу катасы: {e}")
    return None


def platform_ids_of(account_id):
    """Аккаунттун бардык platform_id'лери: [(platform_id, platform), ...]

    Бир адам эки платформада тең катталышы мүмкүн. Кайсынысында
    отурганын так билбегендиктен, экөөнө тең жиберебиз.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT platform_id, platform FROM platform_identities "
                        "WHERE account_id = %s", (account_id,))
            return [(r["platform_id"], r["platform"]) for r in cur.fetchall()]
    except Exception as e:
        print(f"[notify] platform_ids_of катасы: {e}")
        return []


def send(account_id, text):
    """Аккаунтка кабар жиберет — кайсы платформада болсо да.

    Бир да кабар жетпесе False кайтарат. Ката чыкса, процессти
    өлтүрбөйт: кабарлоо экинчи даражадагы иш, негизги агым бузулбашы
    керек.
    """
    sent = False
    for platform_id, platform in platform_ids_of(account_id):
        m = _messenger_for(platform)
        if not m:
            continue
        try:
            out = text
            if platform == "whatsapp":
                from core.texts import strip_html
                out = strip_html(text)
            m.send_text(platform_id, out)
            sent = True
        except Exception as e:
            print(f"[notify] {platform_id} жиберүү катасы: {e}")
    return sent


def accounts_with_active_posts(role, from_city, to_city, exclude_account_id=None):
    """Ошол багытта активдүү жарыясы бар аккаунттардын id'лери.

    Айдоочунун өз жарыясы «жазылуунун» ролун аткарат: жарыя жашап
    турганда кабар келет, 24 сааттан кийин жарыя өчкөндө кабар да
    автоматтык токтойт. Өзүнчө «жазылуу» таблицасы керек эмес.
    """
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT DISTINCT account_id FROM posts
                           WHERE role = %s AND active = 1
                             AND from_city = %s AND to_city = %s""",
                        (role, from_city, to_city))
            ids = [r["account_id"] for r in cur.fetchall()]
    except Exception as e:
        print(f"[notify] accounts_with_active_posts катасы: {e}")
        return []
    if exclude_account_id in ids:
        ids.remove(exclude_account_id)
    return ids
