# -*- coding: utf-8 -*-
"""
core/logic/ — боттун "мээси" (мурунку core/logic.py), бөлүктөргө бөлүнгөн.

Бөлүктөр МУРУНКУДАЙ БИР аталыштар мейкиндигинде иштейт: ар бири ушул
файлдын globals()'уна төмөнкү тартип менен жүктөлөт. Ошондуктан:
  • бөлүктөр бири-бирин импортсуз чакыра берет, айланма импорт жок;
  • `from core import logic` жана `logic.X` мурункудай иштейт;
  • ката чыкса, логдо так файл жана сап көрүнөт.

Жаңы функцияны тиешелүү бөлүккө жазыңыз. Эрежелер:
  • импорттор жана жалпы сөздүктөр — common.py'де;
  • функциядан ТЫШКАРЫ (модуль деңгээлинде) колдонулган аталыш
    мурунку бөлүктө аныкталышы керек — тартип маанилүү.
Версия: grep -r LOGIC_VERSION core/logic/
"""
import os as _logic_os

_LOGIC_PARTS = ("common", "payment", "keyboards", "router", "menu", "wizard", "myposts", "search")

for _logic_part in _LOGIC_PARTS:
    _logic_path = _logic_os.path.join(_logic_os.path.dirname(__file__),
                                      _logic_part + ".py")
    with open(_logic_path, encoding="utf-8") as _logic_file:
        exec(compile(_logic_file.read(), _logic_path, "exec"), globals())

del _logic_os, _logic_part, _logic_path, _logic_file
