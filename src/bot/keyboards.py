from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List

from ..data.files import get_recent_hobbies, get_all_hobbies, get_hobby_display_name
from ..data.reminders import get_user_reminders
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
    date_row.append(InlineKeyboardButton("⚡ Другой день", callback_data="quick_dates"))
    buttons.append(date_row)
    
    buttons.append([
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("⏰ Напоминания", callback_data="reminders")
    ])
    
    return InlineKeyboardMarkup(buttons)


def create_score_keyboard(hobby_name: str, target_date: str = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора количества звезд"""
    buttons = []
    
    # Кнопки с звездочками от 1 до 5
    star_buttons = []
    for i in range(1, 6):
        stars = "⭐" * i
        star_buttons.append(InlineKeyboardButton(f"{stars} {i}", callback_data=f"stars:{hobby_name}:{i}:{target_date}"))
    
    # Разбиваем на 2 ряда: 1-3 звезды и 4-5 звезд
    buttons.append(star_buttons[:3])
    buttons.append(star_buttons[3:])
    
    # Кнопка "Не было" (0 звезд)
    buttons.append([InlineKeyboardButton("❌ Не было (0)", callback_data=f"stars:{hobby_name}:0:{target_date}")])
    
    # Кнопки управления
    buttons.append([
        InlineKeyboardButton("← Назад", callback_data="back_to_hobbies"),
        InlineKeyboardButton("📅 Дата", callback_data="select_date")
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


def create_all_hobbies_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру со всеми увлечениями"""
    buttons = []
    all_hobbies = get_all_hobbies()
    
    for i in range(0, len(all_hobbies), 2):
        row = []
        for j in range(i, min(i + 2, len(all_hobbies))):
            hobby_key = all_hobbies[j]
            hobby_display = get_hobby_display_name(hobby_key)
            row.append(InlineKeyboardButton(hobby_display, callback_data=f"hobby:{hobby_key}"))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")])
    return InlineKeyboardMarkup(buttons)


def create_stats_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для статистики"""
    buttons = []
    dates = get_date_list(7)
    
    # Быстрые кнопки для последних дней
    for date_str, display in dates[:3]:  # Только последние 3 дня
        buttons.append([InlineKeyboardButton(f"📊 {display.replace('📅', '')}", callback_data=f"stats:{date_str}")])
    
    buttons.append([InlineKeyboardButton("📋 Другая дата", callback_data="stats_date")])
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")])
    return InlineKeyboardMarkup(buttons)


def create_quick_date_keyboard() -> InlineKeyboardMarkup:
    """Создает быстрые кнопки для заполнения других дней"""
    buttons = []
    dates = get_date_list(3)  # Последние 3 дня
    
    for date_str, display in dates:
        if "Сегодня" in display:
            continue  # Пропускаем сегодня
        # Убираем эмодзи и делаем короче
        short_display = display.replace("📅 ", "").replace(" (", " ").replace(")", "")
        buttons.append([InlineKeyboardButton(f"⚡ {short_display}", callback_data=f"quick_date:{date_str}")])
    
    buttons.append([InlineKeyboardButton("📅 Другая дата", callback_data="select_date")])
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
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")])
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