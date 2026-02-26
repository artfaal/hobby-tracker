from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List

from ..data.files import get_recent_hobbies, get_all_hobbies, get_hobby_display_name, get_all_aliases, add_alias
from ..data.reminders import get_user_reminders
from ..data.stars import load_star_values
from ..utils.dates import get_date_list


def create_hobby_keyboard(show_today_button: bool = False) -> InlineKeyboardMarkup:
    """Создает клавиатуру с последними 10 увлечениями"""
    buttons = []
    recent_hobbies = get_recent_hobbies(limit=10)
    
    if not recent_hobbies:
        buttons.append([InlineKeyboardButton("➕ Добавить первое увлечение", callback_data="add_new")])
    else:
        # Создаем кнопки по 2 в ряд
        for i in range(0, len(recent_hobbies), 2):
            row = []
            for j in range(i, min(i + 2, len(recent_hobbies))):
                hobby_key = recent_hobbies[j]
                hobby_display = get_hobby_display_name(hobby_key)
                row.append(InlineKeyboardButton(hobby_display, callback_data=f"hobby:{hobby_key}"))
            buttons.append(row)
    
    # Кнопки управления
    management_row = []
    if recent_hobbies:
        management_row.append(InlineKeyboardButton("📋 Все увлечения", callback_data="list_all"))
    management_row.append(InlineKeyboardButton("➕ Добавить новое", callback_data="add_new"))
    
    buttons.append(management_row)
    
    # Кнопки даты
    date_row = []
    if show_today_button:
        date_row.append(InlineKeyboardButton("🏠 Сегодня", callback_data="today"))
    date_row.append(InlineKeyboardButton("📅 Выбрать дату", callback_data="select_date"))
    buttons.append(date_row)
    
    buttons.append([
        InlineKeyboardButton("📊 Сегодня", callback_data="stats_today"),
        InlineKeyboardButton("📊 Вчера", callback_data="stats_yesterday"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
    ])
    
    return InlineKeyboardMarkup(buttons)


def create_score_keyboard(hobby_name: str, target_date: str = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора количества звезд (динамически из stars.txt)"""
    buttons = []
    
    # Загружаем значения звезд из файла
    star_values = load_star_values()
    
    # Создаем кнопки для каждого значения
    star_buttons = []
    for value in star_values:
        if value == 0.5:
            display = "0.5 🌟"  # Половинка звезды
        elif value == int(value):
            display = f"{int(value)} ⭐"  # Цифра + звезда для целых
        else:
            display = f"{value} ⭐"  # Десятичное число + звезда
        
        star_buttons.append(InlineKeyboardButton(display, callback_data=f"stars:{hobby_name}:{value}:{target_date}"))
    
    # Разбиваем на ряды по 3 кнопки
    for i in range(0, len(star_buttons), 3):
        row = star_buttons[i:i+3]
        buttons.append(row)
    
    # Кнопка "Не было" (0 звезд) и Custom
    buttons.append([
        InlineKeyboardButton("❌ Не было (0)", callback_data=f"stars:{hobby_name}:0:{target_date}"),
        InlineKeyboardButton("✏️ Custom", callback_data=f"custom_stars:{hobby_name}:{target_date}")
    ])
    
    # Кнопки управления
    buttons.append([
        InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")
    ])
    
    return InlineKeyboardMarkup(buttons)


def create_date_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора даты"""
    buttons = []
    dates = get_date_list(7)
    
    for date_str, display in dates:
        buttons.append([InlineKeyboardButton(display, callback_data=f"date:{date_str}")])
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")])
    return InlineKeyboardMarkup(buttons)


HOBBIES_PAGE_SIZE = 20


def create_all_hobbies_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    """Создает клавиатуру со всеми увлечениями с пагинацией"""
    buttons = []
    all_hobbies = get_all_hobbies()

    total = len(all_hobbies)
    total_pages = max(1, (total + HOBBIES_PAGE_SIZE - 1) // HOBBIES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * HOBBIES_PAGE_SIZE
    end = min(start + HOBBIES_PAGE_SIZE, total)
    page_hobbies = all_hobbies[start:end]

    for i in range(0, len(page_hobbies), 2):
        row = []
        for j in range(i, min(i + 2, len(page_hobbies))):
            hobby_key = page_hobbies[j]
            hobby_display = get_hobby_display_name(hobby_key)
            row.append(InlineKeyboardButton(hobby_display, callback_data=f"hobby:{hobby_key}"))
        buttons.append(row)

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"hobby_page:{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"hobby_page:{page + 1}"))
        if nav_row:
            buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("← К увлечениям", callback_data="back_to_hobbies")])
    return InlineKeyboardMarkup(buttons)


def create_stats_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для статистики"""
    buttons = []
    dates = get_date_list(7)
    
    # Быстрые кнопки для последних дней
    for date_str, display in dates[:3]:  # Только последние 3 дня
        buttons.append([InlineKeyboardButton(f"📊 {display.replace('📅', '')}", callback_data=f"stats:{date_str}")])
    
    # Аналитика
    buttons.append([
        InlineKeyboardButton("📈 7 дней", callback_data="analytics_week"),
        InlineKeyboardButton("🏆 Топ-3", callback_data="analytics_top3")
    ])
    
    buttons.append([InlineKeyboardButton("📋 Другая дата", callback_data="stats_date")])
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")])
    return InlineKeyboardMarkup(buttons)




def create_reminders_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру управления напоминаниями"""
    buttons = []
    user_reminders = get_user_reminders(user_id)
    
    if user_reminders:
        buttons.append([InlineKeyboardButton("📋 Мои напоминания", callback_data="reminders_list")])
    
    buttons.append([InlineKeyboardButton("➕ Добавить напоминание", callback_data="reminders_add")])
    
    if user_reminders:
        buttons.append([InlineKeyboardButton("🗑️ Удалить напоминание", callback_data="reminders_delete")])
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="settings")])
    return InlineKeyboardMarkup(buttons)


def create_add_reminder_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора времени напоминания"""
    buttons = []
    
    # Кнопки часов по 6 в ряд
    hours = list(range(24))
    for i in range(0, 24, 6):
        row = []
        for hour in hours[i:i+6]:
            row.append(InlineKeyboardButton(f"{hour:02d}:00", callback_data=f"add_reminder:{hour}"))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="reminders")])
    return InlineKeyboardMarkup(buttons)


def create_delete_reminder_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для удаления напоминаний"""
    buttons = []
    user_reminders = sorted(get_user_reminders(user_id))
    
    # Кнопки для каждого напоминания
    for hour in user_reminders:
        buttons.append([InlineKeyboardButton(f"🗑️ {hour:02d}:00", callback_data=f"delete_reminder:{hour}")])
    
    if not user_reminders:
        buttons.append([InlineKeyboardButton("❌ Нет напоминаний", callback_data="reminders")])
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="reminders")])
    return InlineKeyboardMarkup(buttons)


def create_settings_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру настроек"""
    buttons = [
        [InlineKeyboardButton("⏰ Напоминания", callback_data="reminders")],
        [InlineKeyboardButton("📝 Алиасы", callback_data="aliases")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")]
    ]
    return InlineKeyboardMarkup(buttons)


def create_aliases_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру управления алиасами"""
    buttons = [
        [InlineKeyboardButton("📋 Показать все алиасы", callback_data="aliases_list")],
        [InlineKeyboardButton("➕ Добавить алиас", callback_data="aliases_add")],
        [InlineKeyboardButton("← Назад", callback_data="settings")]
    ]
    return InlineKeyboardMarkup(buttons)


def create_aliases_list_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком всех алиасов"""
    buttons = []
    aliases = get_all_aliases()
    
    if aliases:
        # Группируем алиасы по hobby_key
        aliases_by_hobby = {}
        for hobby_key, display_name in aliases:
            if hobby_key not in aliases_by_hobby:
                aliases_by_hobby[hobby_key] = []
            aliases_by_hobby[hobby_key].append(display_name)
        
        # Создаем кнопки для каждого увлечения с его алиасами
        for hobby_key, display_names in aliases_by_hobby.items():
            display_text = ", ".join(display_names)
            text = f"{hobby_key} → {display_text}"
            # Обрезаем слишком длинные строки для кнопки
            if len(text) > 35:
                text = text[:32] + "..."
            buttons.append([InlineKeyboardButton(text, callback_data="aliases_noop")])
    else:
        buttons.append([InlineKeyboardButton("❌ Нет алиасов", callback_data="aliases_noop")])
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="aliases")])
    return InlineKeyboardMarkup(buttons)