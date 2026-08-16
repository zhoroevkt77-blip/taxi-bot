# -*- coding: utf-8 -*-
"""
core/scheduler.py
==================
Фондо иштеген тазалоочу — эскирген (24 сааттан ашкан) жарыяларды
базадан ӨЧҮРӨТ ЖАНА каналдан да ӨЧҮРӨТ.

Мурда: posts.cleanup_expired() базада өчүрчү, бирок эч жерде
чакырылчу эмес — ошондуктан каналдагы посттор түбөлүк калып жүрчү.

Эми: бул scheduler ар N мүнөт сайын иштеп, экөөнү тең кылат.

КОЛДОНУУ (негизги файлда, мисалы main.py же app.py):

    from core.scheduler import start_cleanup_scheduler
    start_cleanup_scheduler()

Мунусун бот polling башталгандан МУРУН чакырыңыз — ал фондук
thread'де иштейт, негизги ботту бөгөттөбөйт.
"""

import threading
import time

from core import posts, channel

SCHEDULER_VERSION = "v1-cleanup"
CHECK_INTERVAL_SECONDS = 5 * 60   # ар 5 мүнөт сайын текшерет

print(f"⏰ core/scheduler.py жүктөлдү. Версия = {SCHEDULER_VERSION}")


def _run_cleanup_once():
    """Бир жолу тазалайт: базадан өчүрөт, каналдан да өчүрөт."""
    try:
        expired = posts.cleanup_expired()
    except Exception as e:
        print("⚠️ cleanup_expired() катасы:", e)
        return

    if not expired:
        return

    print(f"🧹 {len(expired)} эскирген жарыя базадан өчүрүлдү.")

    for row in expired:
        msg_id = row.get("channel_msg_id")
        if not msg_id:
            continue
        ok = channel.delete(msg_id)
        if ok:
            print(f"🗑 Каналдан да өчүрүлдү: post_id={row.get('id')}, "
                  f"channel_msg_id={msg_id}")
        else:
            print(f"⚠️ Каналдан өчүрүлгөн жок: post_id={row.get('id')}, "
                  f"channel_msg_id={msg_id}")


def _loop():
    while True:
        _run_cleanup_once()
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_cleanup_scheduler():
    """Фондук thread'де тазалоочуну иштетет. Ботту бөгөттөбөйт."""
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"⏰ Тазалоочу scheduler иштетилди "
          f"(ар {CHECK_INTERVAL_SECONDS // 60} мүнөт сайын текшерет).")
    return t
