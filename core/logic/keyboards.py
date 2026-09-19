# -*- coding: utf-8 -*-
# core/logic/keyboards.py — Клавиатуралар.
# Импорттор жана жалпы аталыштар common.py'де; бул файл
# core/logic/__init__.py аркылуу ошол мейкиндикке жүктөлөт.

# ============ КЛАВИАТУРАЛАР ============

def main_menu_kb(platform="telegram"):
    """Башкы меню — эки мамыча болуп жайгашат.

    Тартиби telegram_adapter'деги ылдыйкы клавиатура менен бирдей:
    колдонуучу кайсынысын колдонсо да, баскычтар ошол эле жерде турат.

    WhatsApp'та бул номерленген тизмеге айланат — катарлардын тартиби
    сакталат, ошондуктан сандар да ошол эле бойдон калат.
    """
    channel_label = "📢 Telegram каналыбыз"
    return Keyboard(rows=[
        [Button("🚗 Айдоочумун", "menu:driver"),
         Button("🔍 Жүргүнчүмүн", "menu:passenger")],
        [Button("⚙️ Дагы", "menu:more")],  #MENU2
    ])


def more_kb():
    """«Дагы» — сейрек колдонулган баскычтар."""
    channel_label = "📣 Telegram каналыбыз"
    return Keyboard(rows=[
        [Button("💼 Менин балансым", "menu:balance")],
        [Button(channel_label, "menu:channel"),
         Button("🌐 Сайт", "menu:site")],
        [Button("🆘 Жардам", "menu:help"),
         Button("🌐 Тил / Язык", "menu:lang")],
        [_back_btn()],
    ])

def lang_kb():
    return Keyboard(rows=[
        [Button("🇰🇬 Кыргызча", "setlang:ky"),
         Button("🇷🇺 Русский", "setlang:ru")],
        [_back_btn()],
    ])


def driver_menu_kb():
    return Keyboard(rows=[
        [Button("📝 Пост жазам", "d_types")],
        [Button("🔍 Жүргүнчүлөрдү издейм", "d_search")],
        [Button("📄 Менин посторум", "d_my"),
         Button("⭐ VIP болуу", "d_vip")],
        [Button("💳 Төлөм төлөймүн", "d_pay")],
        [_back_btn()],
    ])


def passenger_menu_kb():
    return Keyboard(rows=[
        [Button("📝 Пост жазам", "p_types")],
        [Button("🔍 Айдоочуларды издейм", "p_search")],
        [Button("📄 Менин посторум", "p_my"),
         Button("💳 Төлөм төлөймүн", "p_pay")],
        [_back_btn()],
    ])


def two_col(buttons, back=True):
    """Баскычтарды эки мамычага бөлөт.

    Узун тизмелер (облустар, FAQ бөлүмдөрү) экранды толтуруп
    кетпеши үчүн керек. «🔙 Артка» ар дайым өзүнчө акыркы катарда
    турат — орду өзгөрбөсүн.
    """
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if back:
        rows.append([_back_btn()])
    return Keyboard(rows=rows)


def back_kb():
    return Keyboard.from_flat([_back_btn()])


def regions_kb():
    return two_col([Button(r, f"preg:{i}")
                    for i, r in enumerate(REGION_LIST)])


