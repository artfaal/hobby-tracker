import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from .keyboards import (
    create_hobby_keyboard, create_score_keyboard, create_date_keyboard,
    create_all_hobbies_keyboard, create_stats_keyboard,
    create_reminders_keyboard, create_add_reminder_keyboard, create_delete_reminder_keyboard,
    create_settings_keyboard, create_aliases_keyboard, create_aliases_list_keyboard,
    HOBBIES_PAGE_SIZE
)
from .messages import (
    HELP_TEXT, STAR_EXPLANATION, format_hobby_stars_result, 
    format_stats_message, get_date_display_name
)
from ..data.files import (
    save_hobby_to_history, get_all_hobbies, get_hobby_display_name, get_all_aliases, add_alias
)
from ..data.reminders import (
    add_reminder, remove_reminder, get_user_reminders
)
from ..data.sheets import SheetsManager
from ..utils.dates import date_for_time
from ..utils.config import SPREADSHEET_ID

# Состояние пользователей (в реальном приложении лучше использовать Redis/DB)
user_states = {}

# Глобальный экземпляр SheetsManager
sheets = SheetsManager()

# Логгер для этого модуля
logger = logging.getLogger(__name__)





async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "unknown"
    logger.info(f"Start command from {username} ({user_id})")
    await update.message.reply_text(HELP_TEXT)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(HELP_TEXT)


async def quick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /quick - быстрый ввод через кнопки"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "unknown"
    logger.info(f"Quick command from {username} ({user_id})")
    # Сбрасываем состояние пользователя к сегодняшнему дню
    user_states.pop(user_id, None)
    
    target_date = date_for_time()
    keyboard = create_hobby_keyboard()
    date_display = get_date_display_name(target_date)
    await update.message.reply_text(
        f"🚀 Заполнение на {date_display}\n\nВыберите увлечение:", 
        reply_markup=keyboard
    )


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats - статистика"""
    keyboard = create_stats_keyboard()
    await update.message.reply_text(
        "📊 Выберите день для статистики:",
        reply_markup=keyboard
    )


async def list_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /list - все увлечения"""
    all_hobbies = get_all_hobbies()
    if not all_hobbies:
        await update.message.reply_text(
            "📋 Пока нет увлечений в истории.\n\n"
            "Используйте /quick чтобы добавить первое увлечение!"
        )
    else:
        hobbies_text = "\n".join([f"• {get_hobby_display_name(h)}" for h in all_hobbies])
        message = f"📋 Все ваши увлечения ({len(all_hobbies)}):\n\n{hobbies_text}"
        
        # Разбиваем на части, если сообщение слишком длинное
        if len(message) > 4000:
            hobbies_text = "\n".join([f"• {get_hobby_display_name(h)}" for h in all_hobbies[:30]])
            message = f"📋 Ваши увлечения ({len(all_hobbies)}):\n\n{hobbies_text}"
            if len(all_hobbies) > 30:
                message += f"\n\n... и ещё {len(all_hobbies) - 30} увлечений"
        
        await update.message.reply_text(message)


async def reminders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reminders - настройка напоминаний"""
    user_id = update.message.from_user.id
    keyboard = create_reminders_keyboard(user_id)
    user_reminders = get_user_reminders(user_id)
    
    if user_reminders:
        reminders_text = ", ".join([f"{h:02d}:00" for h in sorted(user_reminders)])
        message = f"⏰ Ваши напоминания: {reminders_text}"
    else:
        message = "⏰ У вас пока нет напоминаний"
    
    await update.message.reply_text(message, reply_markup=keyboard)




async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("hobby:"):
        await handle_hobby_selection(query, user_id, data)
    elif data.startswith("stars:"):
        await handle_stars_selection(query, user_id, data)
    elif data.startswith("date:"):
        await handle_date_selection(query, user_id, data)
    elif data == "stats_today":
        await handle_stats_today(query)
    elif data == "stats_yesterday":
        await handle_stats_yesterday(query)
    elif data.startswith("stats"):
        await handle_stats_selection(query, user_id, data)
    elif data == "list_all":
        await handle_list_all(query)
    elif data.startswith("hobby_page:"):
        page = int(data.split(":", 1)[1])
        await handle_list_all(query, page=page)
    elif data == "add_new":
        await handle_add_new(query, user_id)
    elif data == "select_date":
        await handle_select_date(query)
    elif data == "back_to_hobbies":
        await handle_back_to_hobbies(query)
    elif data == "today":
        await handle_today_selection(query, user_id)
    elif data.startswith("reminder"):
        await handle_reminders(query, user_id, data)
    elif data.startswith("add_reminder"):
        await handle_add_reminder(query, user_id, data)
    elif data.startswith("delete_reminder"):
        await handle_delete_reminder(query, user_id, data)
    elif data == "settings":
        await handle_settings(query)
    elif data.startswith("aliases"):
        await handle_aliases(query, user_id, data)
    elif data.startswith("custom_stars:"):
        await handle_custom_stars_request(query, user_id, data)
    elif data.startswith("analytics"):
        await handle_analytics(query, user_id, data)


async def handle_hobby_selection(query, user_id: int, data: str):
    """Обработка выбора увлечения"""
    hobby_key = data.split(":", 1)[1]
    hobby_display = get_hobby_display_name(hobby_key)
    
    # Получаем выбранную дату из состояния пользователя
    target_date = date_for_time()
    if user_id in user_states and user_states[user_id].startswith("selected_date:"):
        target_date = user_states[user_id].split(":", 1)[1]
    
    keyboard = create_score_keyboard(hobby_key, target_date)
    
    date_display = get_date_display_name(target_date)
    await query.edit_message_text(
        f"⭐ Оцените '{hobby_display}' на {date_display}:\n\n{STAR_EXPLANATION}",
        reply_markup=keyboard
    )


async def handle_stars_selection(query, user_id: int, data: str):
    """Обработка выбора количества звезд"""
    parts = data.split(":")
    if len(parts) >= 4:
        hobby_key = parts[1]
        stars = float(parts[2])  # Теперь поддерживаем десятичные значения
        target_date = parts[3]
        
        # Сохраняем увлечение в историю
        save_hobby_to_history(hobby_key)
        
        # Записываем в Google Sheets
        score_values = {hobby_key: stars}
        
        # Показываем результат
        hobby_display = get_hobby_display_name(hobby_key)
        result_text = format_hobby_stars_result(hobby_display, stars)
        
        await query.edit_message_text(result_text)
        
        # Возвращаемся к списку увлечений
        current_date = date_for_time()
        show_today = target_date != current_date
        keyboard = create_hobby_keyboard(show_today_button=show_today)
        date_display = get_date_display_name(target_date)
        await asyncio.sleep(0.5)
        await query.edit_message_text(
            f"🚀 Заполнение на {date_display}\n\nВыберите следующее увлечение:",
            reply_markup=keyboard
        )
        
        # Записываем в Google Sheets в фоне
        try:
            sheets.write_values(score_values, target_date)
        except Exception:
            pass  # Игнорируем ошибки для скорости


async def handle_date_selection(query, user_id: int, data: str):
    """Обработка выбора даты"""
    selected_date = data.split(":", 1)[1]
    user_states[user_id] = f"selected_date:{selected_date}"
    
    # Показываем кнопку "Сегодня" если выбрана не сегодняшняя дата
    current_date = date_for_time()
    show_today = selected_date != current_date
    keyboard = create_hobby_keyboard(show_today_button=show_today)
    date_display = get_date_display_name(selected_date)
    await query.edit_message_text(
        f"🚀 Заполнение на {date_display}\n\nВыберите увлечение:",
        reply_markup=keyboard
    )


async def handle_quick_date_selection(query, user_id: int, data: str):
    """Обработка быстрого выбора даты"""
    selected_date = data.split(":", 1)[1]
    user_states[user_id] = f"selected_date:{selected_date}"
    
    # Показываем кнопку "Сегодня" если выбрана не сегодняшняя дата
    current_date = date_for_time()
    show_today = selected_date != current_date
    keyboard = create_hobby_keyboard(show_today_button=show_today)
    date_display = get_date_display_name(selected_date)
    await query.edit_message_text(
        f"🚀 Заполнение на {date_display}\n\nВыберите увлечение:",
        reply_markup=keyboard
    )


async def handle_stats_selection(query, user_id: int, data: str):
    """Обработка выбора статистики"""
    if data == "stats":
        keyboard = create_stats_keyboard()
        await query.edit_message_text(
            "📊 Выберите день для статистики:",
            reply_markup=keyboard
        )
    elif data == "stats_date":
        keyboard = create_date_keyboard()
        await query.edit_message_text(
            "📅 Выберите дату для статистики:",
            reply_markup=keyboard
        )
        user_states[user_id] = "stats_mode"
    elif data.startswith("stats:"):
        target_date = data.split(":", 1)[1]
        await show_stats_for_date(query, target_date)


async def show_stats_for_date(query, target_date: str, show_stats_keyboard: bool = True):
    """Показывает статистику за указанную дату"""
    try:
        data = sheets.get_day_data(target_date)
        total = sheets.get_total_for_date(target_date)
        
        message = format_stats_message(target_date, data, total)
        
        # Сначала отправляем статистику
        await query.message.reply_text(message)
        
        # Затем отправляем новое сообщение с кнопками навигации (оно будет внизу)
        if show_stats_keyboard:
            keyboard = create_stats_keyboard()
            await query.message.reply_text("📊 Статистика по дням:", reply_markup=keyboard)
        else:
            from .keyboards import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")]])
            await query.message.reply_text("📊 Навигация:", reply_markup=keyboard)
        
        # Удаляем исходное сообщение с кнопкой
        await query.message.delete()
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Ошибка получения статистики: {str(e)}\n\n"
            "Попробуйте еще раз или обратитесь к администратору."
        )


async def handle_stats_today(query):
    """Обработка статистики за сегодня"""
    today = date_for_time()
    await show_stats_for_date(query, today, show_stats_keyboard=False)


async def handle_stats_yesterday(query):
    """Обработка статистики за вчера"""
    from datetime import datetime, timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    await show_stats_for_date(query, yesterday, show_stats_keyboard=False)


async def handle_list_all(query, page: int = 0):
    """Обработка показа всех увлечений с пагинацией"""
    all_hobbies = get_all_hobbies()
    if not all_hobbies:
        await query.edit_message_text("📋 Пока нет увлечений в истории.")
    else:
        total_pages = max(1, (len(all_hobbies) + HOBBIES_PAGE_SIZE - 1) // HOBBIES_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        keyboard = create_all_hobbies_keyboard(page=page)
        page_info = f" • стр. {page + 1}/{total_pages}" if total_pages > 1 else ""
        await query.edit_message_text(
            f"📋 Все ваши увлечения ({len(all_hobbies)}){page_info}:",
            reply_markup=keyboard
        )


async def handle_add_new(query, user_id: int):
    """Обработка добавления нового увлечения"""
    username = query.from_user.username or "unknown"
    target_date = date_for_time()
    if user_id in user_states and user_states[user_id].startswith("selected_date:"):
        target_date = user_states[user_id].split(":", 1)[1]
    
    user_states[user_id] = f"waiting_new_hobby:{target_date}"
    logger.info(f"Add new hobby requested by {username} ({user_id}) for date {target_date}")
    await query.edit_message_text("✏️ Напишите название нового увлечения:")


async def handle_select_date(query):
    """Обработка выбора даты"""
    keyboard = create_date_keyboard()
    await query.edit_message_text(
        "📅 Выберите дату для записи:",
        reply_markup=keyboard
    )




async def handle_today_selection(query, user_id: int):
    """Обработка возврата к сегодняшнему дню"""
    # Сбрасываем состояние пользователя к сегодняшнему дню
    user_states.pop(user_id, None)
    
    target_date = date_for_time()
    keyboard = create_hobby_keyboard()  # Без кнопки "Сегодня" для сегодняшнего дня
    date_display = get_date_display_name(target_date)
    await query.edit_message_text(
        f"🚀 Заполнение на {date_display}\n\nВыберите увлечение:",
        reply_markup=keyboard
    )


async def handle_back_to_hobbies(query):
    """Обработка возврата к списку увлечений"""
    user_id = query.from_user.id
    
    # Получаем выбранную дату из состояния пользователя
    target_date = date_for_time()
    if user_id in user_states and user_states[user_id].startswith("selected_date:"):
        target_date = user_states[user_id].split(":", 1)[1]
    
    # Показываем кнопку "Сегодня" если выбрана не сегодняшняя дата
    current_date = date_for_time()
    show_today = target_date != current_date
    keyboard = create_hobby_keyboard(show_today_button=show_today)
    date_display = get_date_display_name(target_date)
    await query.edit_message_text(
        f"🚀 Заполнение на {date_display}\n\nВыберите увлечение:",
        reply_markup=keyboard
    )



async def reminders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reminders - управление напоминаниями"""
    user_id = update.message.from_user.id
    keyboard = create_reminders_keyboard(user_id)
    user_reminders = get_user_reminders(user_id)
    
    if user_reminders:
        reminders_text = ", ".join([f"{h:02d}:00" for h in sorted(user_reminders)])
        message = f"⏰ Ваши напоминания: {reminders_text}"
    else:
        message = "⏰ У вас пока нет напоминаний"
    
    await update.message.reply_text(message, reply_markup=keyboard)


async def handle_reminders(query, user_id: int, data: str):
    """Обработка управления напоминаниями"""
    if data == "reminders":
        keyboard = create_reminders_keyboard(user_id)
        user_reminders = get_user_reminders(user_id)
        
        if user_reminders:
            reminders_text = ", ".join([f"{h:02d}:00" for h in sorted(user_reminders)])
            message = f"⏰ Ваши напоминания: {reminders_text}"
        else:
            message = "⏰ У вас пока нет напоминаний"
        
        await query.edit_message_text(message, reply_markup=keyboard)
    
    elif data == "reminders_list":
        user_reminders = sorted(get_user_reminders(user_id))
        if user_reminders:
            reminders_text = "\n".join([f"• {h:02d}:00" for h in user_reminders])
            message = f"📋 Ваши напоминания:\n\n{reminders_text}"
        else:
            message = "📋 У вас нет активных напоминаний"
        
        keyboard = create_reminders_keyboard(user_id)
        await query.edit_message_text(message, reply_markup=keyboard)
    
    elif data == "reminders_add":
        keyboard = create_add_reminder_keyboard()
        await query.edit_message_text(
            "⏰ Выберите время для напоминания:",
            reply_markup=keyboard
        )
    
    elif data == "reminders_delete":
        keyboard = create_delete_reminder_keyboard(user_id)
        await query.edit_message_text(
            "🗑️ Выберите напоминание для удаления:",
            reply_markup=keyboard
        )


async def handle_add_reminder(query, user_id: int, data: str):
    """Обработка добавления напоминания"""
    hour = int(data.split(":", 1)[1])
    success = add_reminder(user_id, hour)
    
    if success:
        message = f"✅ Напоминание на {hour:02d}:00 добавлено!"
    else:
        message = f"❌ Напоминание на {hour:02d}:00 уже существует"
    
    keyboard = create_reminders_keyboard(user_id)
    await query.edit_message_text(message, reply_markup=keyboard)


async def handle_delete_reminder(query, user_id: int, data: str):
    """Обработка удаления напоминания"""
    hour = int(data.split(":", 1)[1])
    success = remove_reminder(user_id, hour)
    
    if success:
        message = f"✅ Напоминание на {hour:02d}:00 удалено!"
    else:
        message = f"❌ Напоминание на {hour:02d}:00 не найдено"
    
    keyboard = create_reminders_keyboard(user_id)
    await query.edit_message_text(message, reply_markup=keyboard)


async def handle_settings(query):
    """Обработка меню настроек"""
    keyboard = create_settings_keyboard()
    await query.edit_message_text(
        "⚙️ Настройки бота:",
        reply_markup=keyboard
    )


async def handle_aliases(query, user_id: int, data: str):
    """Обработка управления алиасами"""
    if data == "aliases":
        keyboard = create_aliases_keyboard()
        await query.edit_message_text(
            "📝 Управление алиасами:",
            reply_markup=keyboard
        )
    
    elif data == "aliases_list":
        aliases = get_all_aliases()
        keyboard = create_aliases_list_keyboard()
        
        if aliases:
            # Группируем алиасы по hobby_key для отображения
            aliases_by_hobby = {}
            for hobby_key, display_name in aliases:
                if hobby_key not in aliases_by_hobby:
                    aliases_by_hobby[hobby_key] = []
                aliases_by_hobby[hobby_key].append(display_name)
            
            message_lines = ["📋 Все алиасы:\n"]
            for hobby_key, display_names in aliases_by_hobby.items():
                display_text = ", ".join(display_names)
                message_lines.append(f"• {hobby_key} → {display_text}")
            
            message = "\n".join(message_lines)
        else:
            message = "📋 У вас пока нет алиасов"
        
        await query.edit_message_text(message, reply_markup=keyboard)
    
    elif data == "aliases_add":
        user_states[user_id] = "awaiting_alias"
        await query.edit_message_text(
            "➕ Добавление нового алиаса\n\n"
            "Отправьте сообщение в формате:\n"
            "`название_хобби = Красивое название`\n\n"
            "Например:\n"
            "`программирование = 💻 Программирование`",
            parse_mode="Markdown"
        )
    
    elif data == "aliases_noop":
        # Ничего не делаем для информационных кнопок
        pass


async def handle_custom_stars_request(query, user_id: int, data: str):
    """Обработка запроса на ввод custom значения звезд"""
    parts = data.split(":")
    if len(parts) >= 3:
        hobby_name = parts[1]
        target_date = parts[2] if parts[2] != "None" else date_for_time()
        
        # Устанавливаем состояние пользователя для ожидания custom значения
        user_states[user_id] = f"awaiting_custom_stars:{hobby_name}:{target_date}"
        
        hobby_display = get_hobby_display_name(hobby_name)
        date_display = get_date_display_name(target_date)
        
        await query.edit_message_text(
            f"✏️ Введите количество часов для '{hobby_display}' на {date_display}:\n\n"
            f"Можно использовать десятичные значения:\n"
            f"• 0.5 или 0,5 (30 минут)\n"
            f"• 1.5 или 1,5 (1 час 30 минут)\n"
            f"• 12 или 12,0 (12 часов)\n\n"
            f"Просто напишите число и отправьте сообщение."
        )


async def handle_analytics(query, user_id: int, data: str):
    """Обработка запросов аналитики"""
    if data == "analytics_week":
        await show_weekly_analytics(query)
    elif data == "analytics_top3":
        await show_top3_analytics(query)


def create_unicode_chart(values: list, max_height: int = 8) -> str:
    """Создает Unicode график из значений"""
    if not values or max(values) == 0:
        return "▁" * len(values)
    
    chars = "▁▂▃▄▅▆▇█"
    max_val = max(values)
    
    chart = ""
    for val in values:
        if val == 0:
            chart += "▁"
        else:
            level = min(int((val / max_val) * (len(chars) - 1)), len(chars) - 1)
            chart += chars[level]
    
    return chart


def get_week_data() -> dict:
    """Получает данные за последние 7 дней"""
    from datetime import datetime, timedelta
    
    week_data = {}
    today = datetime.now()
    
    for i in range(7):
        date = today - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        try:
            day_data = sheets.get_day_data(date_str)
            week_data[date_str] = day_data if day_data else {}
        except:
            week_data[date_str] = {}
    
    return week_data


async def show_weekly_analytics(query):
    """Показывает еженедельную аналитику"""
    try:
        week_data = get_week_data()
        
        # Собираем статистику по увлечениям
        hobby_totals = {}
        daily_totals = []
        dates = []
        
        # Сортируем даты по порядку (от старых к новым)
        sorted_dates = sorted(week_data.keys())
        
        for date_str in sorted_dates:
            day_data = week_data[date_str]
            day_total = sum(day_data.values()) if day_data else 0
            daily_totals.append(day_total)
            dates.append(date_str)
            
            for hobby, hours in day_data.items():
                if hobby not in hobby_totals:
                    hobby_totals[hobby] = 0
                hobby_totals[hobby] += hours
        
        # Создаем график недельной активности
        chart = create_unicode_chart(daily_totals)
        
        # Форматируем даты для отображения
        formatted_dates = []
        for date_str in sorted_dates:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            day_name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][date_obj.weekday()]
            formatted_dates.append(f"{day_name} {date_obj.strftime('%d.%m')}")
        
        # Общее время за 7 дней
        total_week_hours = sum(daily_totals)
        avg_daily = total_week_hours / 7 if total_week_hours > 0 else 0
        
        # Формируем сообщение
        message = f"📈 **Последние 7 дней**\n\n"
        message += f"📊 График активности:\n"
        message += f"`{chart}`\n"
        message += f"`{''.join([d[:2] for d in formatted_dates])}`\n\n"
        
        message += f"📋 **Сводка за 7 дней:**\n"
        message += f"🎯 Общее время: {total_week_hours:.1f} ч.\n"
        message += f"📊 Среднее в день: {avg_daily:.1f} ч.\n\n"
        
        # Топ-3 активности за 7 дней
        if hobby_totals:
            sorted_hobbies = sorted(hobby_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            message += f"🏆 **Топ-3 за 7 дней:**\n"
            for i, (hobby, hours) in enumerate(sorted_hobbies, 1):
                hobby_display = get_hobby_display_name(hobby)
                message += f"{i}. {hobby_display}: {hours:.1f} ч.\n"
        
        # Отправляем аналитику
        await query.message.reply_text(message, parse_mode='Markdown')
        
        # Отправляем новое меню внизу
        keyboard = create_stats_keyboard()
        await query.message.reply_text("📈 Навигация по аналитике:", reply_markup=keyboard)
        
        # Удаляем исходное сообщение
        await query.message.delete()
        
    except Exception as e:
        logger.error(f"Error in weekly analytics: {e}")
        await query.message.reply_text("❌ Ошибка при создании еженедельной аналитики")


async def show_top3_analytics(query):
    """Показывает топ-3 активности за разные периоды"""
    try:
        from datetime import datetime, timedelta
        
        # Данные за неделю
        week_data = get_week_data()
        week_totals = {}
        for day_data in week_data.values():
            for hobby, hours in day_data.items():
                week_totals[hobby] = week_totals.get(hobby, 0) + hours
        
        # Данные за месяц (последние 30 дней)
        month_totals = {}
        today = datetime.now()
        for i in range(30):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            try:
                day_data = sheets.get_day_data(date_str)
                if day_data:
                    for hobby, hours in day_data.items():
                        month_totals[hobby] = month_totals.get(hobby, 0) + hours
            except:
                continue
        
        message = "🏆 **Топ-3 активности**\n\n"
        
        # Топ-3 за последние 7 дней
        if week_totals:
            week_top3 = sorted(week_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            message += "📅 **Последние 7 дней:**\n"
            for i, (hobby, hours) in enumerate(week_top3, 1):
                hobby_display = get_hobby_display_name(hobby)
                
                # Простой тренд (сравниваем первую и вторую половину периода)
                first_half = sum([week_data[d].get(hobby, 0) for d in sorted(week_data.keys())[:4]])
                second_half = sum([week_data[d].get(hobby, 0) for d in sorted(week_data.keys())[4:]])
                
                trend = ""
                if second_half > first_half * 1.1:
                    trend = "📈"
                elif second_half < first_half * 0.9:
                    trend = "📉"
                else:
                    trend = "➡️"
                
                message += f"{i}. {hobby_display}: {hours:.1f} ч. {trend}\n"
            message += "\n"
        
        # Топ-3 за последние 30 дней
        if month_totals:
            month_top3 = sorted(month_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            message += "🗓️ **Последние 30 дней:**\n"
            for i, (hobby, hours) in enumerate(month_top3, 1):
                hobby_display = get_hobby_display_name(hobby)
                avg_daily = hours / 30
                message += f"{i}. {hobby_display}: {hours:.1f} ч. ({avg_daily:.1f} ч/день)\n"
        
        if not week_totals and not month_totals:
            message += "📊 Пока недостаточно данных для анализа"
        
        # Отправляем аналитику
        await query.message.reply_text(message, parse_mode='Markdown')
        
        # Отправляем новое меню внизу
        keyboard = create_stats_keyboard()
        await query.message.reply_text("🏆 Навигация по рейтингу:", reply_markup=keyboard)
        
        # Удаляем исходное сообщение
        await query.message.delete()
        
    except Exception as e:
        logger.error(f"Error in top3 analytics: {e}")
        await query.message.reply_text("❌ Ошибка при создании топ-3 аналитики")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (для алиасов и новых увлечений)"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "unknown"
    text = update.message.text.strip()
    
    logger.info(f"Text message from {username} ({user_id}): '{text}', state: {user_states.get(user_id, 'none')}")
    
    # Обрабатываем добавление нового увлечения
    if user_id in user_states and user_states[user_id].startswith("waiting_new_hobby:"):
        hobby_name = text.lower()
        target_date = user_states[user_id].split(":", 1)[1]
        user_states.pop(user_id, None)
        
        logger.info(f"Adding new hobby '{hobby_name}' for user {username} ({user_id}) on {target_date}")
        
        # Создаем клавиатуру для выбора оценки
        keyboard = create_score_keyboard(hobby_name, target_date)
        
        date_display = get_date_display_name(target_date)
        await update.message.reply_text(
            f"⭐ Оцените '{hobby_name.capitalize()}' на {date_display}:\n\n{STAR_EXPLANATION}",
            reply_markup=keyboard
        )
        return
    
    # Обрабатываем ввод custom количества звезд
    elif user_id in user_states and user_states[user_id].startswith("awaiting_custom_stars:"):
        parts = user_states[user_id].split(":", 2)
        hobby_name = parts[1]
        target_date = parts[2]
        
        # Парсим введенное значение, поддерживая и точку, и запятую
        try:
            # Заменяем запятую на точку для стандартизации
            normalized_text = text.replace(",", ".")
            stars_value = float(normalized_text)
            
            # Проверяем разумные границы
            if stars_value < 0:
                await update.message.reply_text("❌ Количество часов не может быть отрицательным!")
                return
            elif stars_value > 24:
                await update.message.reply_text("❌ Количество часов не может быть больше 24!")
                return
            
            logger.info(f"Custom stars value '{stars_value}' for hobby '{hobby_name}' by user {username} ({user_id}) on {target_date}")
            
            # Сохраняем увлечение в историю
            save_hobby_to_history(hobby_name)
            
            # Записываем в Google Sheets
            score_values = {hobby_name: stars_value}
            
            # Показываем результат
            hobby_display = get_hobby_display_name(hobby_name)
            result_text = format_hobby_stars_result(hobby_display, stars_value)
            
            await update.message.reply_text(result_text)
            
            # Сбрасываем состояние
            user_states.pop(user_id, None)
            
            # Возвращаемся к главному меню
            current_date = date_for_time()
            keyboard = create_hobby_keyboard()
            date_display = get_date_display_name(current_date)
            await update.message.reply_text(
                f"🚀 Заполнение на {date_display}\n\nВыберите увлечение:", 
                reply_markup=keyboard
            )
            
            # Асинхронно записываем в Google Sheets
            try:
                await asyncio.create_task(
                    asyncio.to_thread(sheets.write_values, score_values, target_date)
                )
                logger.info(f"Successfully wrote custom stars data to sheets: {score_values}")
            except Exception as e:
                logger.error(f"Failed to write custom stars data to sheets: {e}")
            
            return
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неправильный формат числа!\n\n"
                "Используйте числа, например:\n"
                "• 1 или 1.0\n"
                "• 2.5 или 2,5\n"
                "• 12"
            )
            return
    
    # Обрабатываем добавление алиаса
    elif user_id in user_states and user_states[user_id] == "awaiting_alias":
        if "=" in text:
            parts = text.split("=", 1)
            hobby_key = parts[0].strip()
            display_name = parts[1].strip()
            
            if hobby_key and display_name:
                success = add_alias(hobby_key, display_name)
                if success:
                    keyboard = create_aliases_keyboard()
                    await update.message.reply_text(
                        f"✅ Алиас добавлен!\n\n"
                        f"• {hobby_key} → {display_name}",
                        reply_markup=keyboard
                    )
                else:
                    await update.message.reply_text("❌ Ошибка при добавлении алиаса")
            else:
                await update.message.reply_text(
                    "❌ Неправильный формат. Используйте:\n"
                    "`название_хобби = Красивое название`",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(
                "❌ Неправильный формат. Используйте:\n"
                "`название_хобби = Красивое название`",
                parse_mode="Markdown"
            )
        
        # Сбрасываем состояние
        user_states.pop(user_id, None)
    
    # Если это не команда создания нового увлечения или алиаса, направляем к /quick
    else:
        await update.message.reply_text(
            "Используйте /quick для быстрого заполнения увлечений через кнопки!"
        )