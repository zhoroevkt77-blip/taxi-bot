# -*- coding: utf-8 -*-
"""
main.py
=======
ТАКСИ роБОТ — "бир мээ, эки ооз".

Telegram жана WhatsApp эки өзүнчө потокто иштейт, бирок экөө тең
ошол эле core/logic.py'ди колдонот.
"""

import threading

from adapters.telegram_adapter import run as run_telegram
from adapters.whatsapp_adapter import run as run_whatsapp


def main():
    # WhatsApp'ты фондо иштетебиз
    threading.Thread(target=run_whatsapp, daemon=True, name="whatsapp").start()

    # Telegram негизги потокто (ал polling'ди өзү кармайт)
    run_telegram()


if __name__ == "__main__":
    main()

