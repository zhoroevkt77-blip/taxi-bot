# -*- coding: utf-8 -*-
"""
core/messenger.py
==================
Бул — "МЭЭ" менен "ООЗДОРДУН" ортосундагы жалгыз көпүрө.

Эреже жөнөкөй: core/ ичиндеги эч бир файл telebot же Green API'ди
түз чакырбайт. Ал болгону ушул Messenger интерфейсин колдонот.
Ар бир платформа (Telegram, WhatsApp) бул интерфейсти өзүнчө
которот — adapters/ папкасында.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Button:
    """Бир баскыч — платформага көз каранды эмес."""
    text: str          # Колдонуучуга көрүнчү жазуу
    action: str        # core логикасы тааныган ички код, мис. "route:to_bishkek"


@dataclass
class Keyboard:
    """Баскычтардын тобу."""
    rows: list = field(default_factory=list)

    @staticmethod
    def from_flat(buttons, per_row=1):
        rows = [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]
        return Keyboard(rows=rows)


@dataclass
class IncomingMessage:
    """Ар кайсы платформадан келген билдирүү ушул бир түргө айланат."""
    user_id: str
    platform: str
    text: str = ""
    is_button: bool = False
    button_action: str = ""
    contact_phone: str = None


class Messenger(ABC):
    """Ар бир адаптер ушул классты мурастап, өз API'сине которот."""

    platform_name = "abstract"

    @abstractmethod
    def send_text(self, user_id, text):
        ...

    @abstractmethod
    def send_buttons(self, user_id, text, keyboard):
        ...

    @abstractmethod
    def ask_phone_contact(self, user_id, text):
        ...


def make_uid(platform, raw_id):
    """Ар кайсы платформанын ID'син бирдиктүү форматка келтирет."""
    prefix = {"telegram": "tg", "whatsapp": "wa"}.get(platform, platform)
    return f"{prefix}:{raw_id}"
