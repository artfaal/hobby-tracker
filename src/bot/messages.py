"""Тексты сообщений для бота"""

HELP_TEXT = (
    "Привет! Я бот учёта увлечений со звездочками ⭐\n\n"
    "Команды:\n"
    "/start — приветствие\n"
    "/help — помощь\n"
    "/quick — быстрый ввод через кнопки 🚀\n"
    "/stats — статистика по дням 📊\n"
    "/list — показать все увлечения 📋\n"
    "/reminders — настройка напоминаний ⏰\n\n"
    "⭐ Система звезд (0.5-8) - отражает время:\n"
    "🌟 = 0.5 часа (30 минут)\n"
    "⭐ = 1 час времени\n"
    "⭐⭐⭐ = 3 часа времени\n"
    "⭐⭐⭐⭐⭐ = 5 часов времени\n"
    "⭐⭐⭐⭐⭐⭐⭐⭐ = 8 часов времени\n"
    "❌ = не было активности\n\n"
    "Все действия выполняются через интерактивные кнопки!\n"
    "Используйте /quick для начала работы."
)

STAR_EXPLANATION = (
    "🌟 = 0.5 часа (30 минут)\n"
    "⭐ = 1 час времени\n"
    "⭐⭐⭐ = 3 часа времени\n"
    "⭐⭐⭐⭐⭐ = 5 часов времени\n"
    "⭐⭐⭐⭐⭐⭐⭐⭐ = 8 часов времени\n"
    "Выберите количество часов, которое потратили на активность"
)


def format_stars_display(stars: float) -> str:
    """Создает визуальное представление звезд"""
    if stars == 0:
        return "❌"
    elif stars == 0.5:
        return "🌟"
    else:
        return "⭐" * int(stars)


def format_hobby_stars_result(hobby_display: str, stars: float) -> str:
    """Форматирует результат выбора звезд"""
    stars_display = format_stars_display(stars)
    
    # Форматируем число для отображения
    if stars == int(stars):
        stars_text = str(int(stars))
    else:
        stars_text = str(stars)
    
    result_text = f"✅ {stars_display} {hobby_display} = {stars_text} балл"
    
    # Склонение
    if stars == 1:
        pass  # "балл"
    elif stars in [0, 5, 6, 7, 8, 9, 10] or (stars % 1 == 0.5):
        result_text += "ов"
    else:
        result_text += "а"
    
    return result_text


def format_stats_message(date_str: str, data: dict, total: float) -> str:
    """Форматирует сообщение со статистикой за день"""
    if not data or total == 0:
        return f"📊 Статистика за {date_str}\n\n❌ Нет данных за этот день"
    
    lines = [f"📊 Статистика за {date_str}\n"]
    
    # Сортируем по убыванию баллов
    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
    
    for hobby, score in sorted_data:
        if score > 0:
            from ..data.files import get_hobby_display_name
            display_name = get_hobby_display_name(hobby)
            stars_display = format_stars_display(score)
            # Форматируем число для отображения
            if score == int(score):
                score_text = str(int(score))
            else:
                score_text = str(score)
            lines.append(f"{display_name}: {stars_display} ({score_text})")
    
    # Форматируем общий балл
    if total == int(total):
        total_text = str(int(total))
    else:
        total_text = str(total)
    
    lines.append(f"\n🎯 Общий балл: {total_text}")
    
    return "\n".join(lines)


def get_date_display_name(date_str: str) -> str:
    """Получает красивое название для даты"""
    from ..utils.dates import today_str, date_for_time
    
    if date_str == today_str():
        return "сегодня"
    elif date_str == date_for_time():
        return "сегодня (с учетом времени)"
    else:
        # Проверяем, вчера ли это
        import datetime as dt
        try:
            today = dt.datetime.now().date()
            target = dt.datetime.fromisoformat(date_str).date()
            diff = (today - target).days
            
            if diff == 1:
                return "вчера"
            elif diff == 2:
                return "позавчера"
            else:
                return date_str
        except:
            return date_str