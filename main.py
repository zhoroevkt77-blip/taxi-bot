# -*- coding: utf-8 -*-
"""
main.py
=======
ТАКСИ роБОТ — "бир мээ, үч ооз".

Telegram, WhatsApp жана сайт үч өзүнчө потокто иштейт, бирок үчөө тең
ошол эле базага жана core/logic.py'ге таянат.

Бир бөлүк кулап калса, калгандары иштей берет — процесс өлбөйт.

Мындан тышкары фондо тазалоочу (core/scheduler.py) иштейт:
24 сааттан ашкан жарыяларды базадан да, каналдан да автоматтык өчүрөт.

САЙТ ТУУРАЛУУ:
    web/app.py — жарыяларды көрсөтүүчү бет. Ал база менен окуу
    режиминде гана иштейт: эч нерсе жазбайт, өзгөртпөйт. Ошондуктан
    ботко тобокелдик жок.

    Railway'де сайт көрүнүшү үчүн «Settings → Networking → Generate
    Domain» басылышы керек. PORT өзгөрмөсүн Railway өзү берет.
"""

import os
import threading
import time

from adapters.telegram_adapter import run as run_telegram
from adapters.whatsapp_adapter import run as run_whatsapp
from core.scheduler import start_cleanup_scheduler


def _guard(fn, name):
    """Бөлүктү кулатпай кармап турат."""
    def wrapper():
        while True:
            try:
                fn()
            except Exception as e:
                print(f"[{name}] кулады: {e}")
            print(f"[{name}] 15 секунддан кийин кайра башталат...")
            time.sleep(15)
    return wrapper


def _run_web():
    """Сайтты иштетет. Импорт функциянын ичинде — сайт кулап калса,
    бот ага кошулуп жыгылбашы үчүн."""
    from web.app import run as run_site
    run_site()


def main():
    # Эскирген жарыяларды тазалоочу — фондук thread'де иштейт
    start_cleanup_scheduler()

    threading.Thread(target=_guard(run_telegram, "telegram"),
                     daemon=True, name="telegram").start()
    threading.Thread(target=_guard(run_whatsapp, "whatsapp"),
                     daemon=True, name="whatsapp").start()
    threading.Thread(target=_guard(_run_web, "web"),
                     daemon=True, name="web").start()

    # Негизги поток жашап турат — бир да бөлүк процессти өлтүрбөйт
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
