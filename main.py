# -*- coding: utf-8 -*-
"""
main.py
=======
Кирүү чекити. Бул файлда логика ЖОК — ал болгону Telegram оозун
иштетет. Бардык эреже core/logic.py ичинде.

WhatsApp оозун өзүнчө иштетесиң:
    gunicorn adapters.whatsapp_adapter:app
"""

from adapters.telegram_adapter import run

if __name__ == "__main__":
    run()
