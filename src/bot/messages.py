"""Тексты сообщений для бота"""

HELP_TEXT = (
    "Привет! Я бот учёта увлечений со звездочками ⭐\n\n"
    "Команды:\n"
    "/start — приветствие\n"
    "/help — помощь\n"
    "/quick — быстрый ввод через кнопки 🚀\n"
    "/stats — статистика по дням 📊\n"
    "/list — показать все увлечения 📋\n\n"
    "⭐ Система звезд (1-5):\n"
    "⭐ = минимальный приоритет\n"
    "⭐⭐⭐ = средний приоритет\n"
    "⭐⭐⭐⭐⭐ = максимальный приоритет\n"
    "❌ = не было активности\n\n"
    "Все действия выполняются через интерактивные кнопки!\n"
    "Используйте /quick для начала работы."
)

STAR_EXPLANATION = (
    "⭐ = минимальный приоритет\n"
    "⭐⭐⭐ = средний приоритет\n"
    "⭐⭐⭐⭐⭐ = максимальный приоритет"
)


def format_hobby_stars_result(hobby_display: str, stars: int) -> str:
    """Форматирует результат выбора звезд"""
    stars_display = "⭐" * stars if stars > 0 else "❌"
    result_text = f"✅ {stars_display} {hobby_display} = {stars} балл"
    
    if stars != 1:
        result_text += "ов" if stars in [0, 5, 6, 7, 8, 9, 10] else "а"
    
    return result_text


def format_stats_message(date_str: str, data: dict, total: int) -> str:
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
            stars = "⭐" * score
            lines.append(f"{display_name}: {stars} ({score})")
    
    lines.append(f"\n🎯 Общий балл: {total}")
    
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