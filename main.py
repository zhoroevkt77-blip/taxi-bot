# -*- coding: utf-8 -*-
"""
main.py
=======
ТАКСИ роБОТ — "бир мээ, эки ооз".

Telegram жана WhatsApp эки өзүнчө потокто иштейт, бирок экөө тең
ошол эле core/logic.py'ди колдонот.

Бир адаптер кулап калса, экинчиси иштей берет — процесс өлбөйт.
"""

import threading
import time

from adapters.telegram_adapter import run as run_telegram
from adapters.whatsapp_adapter import run as run_whatsapp


def _guard(fn, name):
    """Адаптерди кулатпай кармап турат."""
    def wrapper():
        while True:
            try:
                fn()
            except Exception as e:
                print(f"[{name}] кулады: {e}")
            print(f"[{name}] 15 секунддан кийин кайра башталат...")
            time.sleep(15)
    return wrapper


def main():
    threading.Thread(target=_guard(run_telegram, "telegram"),
                     daemon=True, name="telegram").start()
    threading.Thread(target=_guard(run_whatsapp, "whatsapp"),
                     daemon=True, name="whatsapp").start()

    # Негизги поток жашап турат — бир да адаптер процессти өлтүрбөйт
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()


