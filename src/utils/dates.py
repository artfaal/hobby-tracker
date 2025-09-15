import datetime as dt

# Timezone setup
try:
    import zoneinfo
    from .config import TZ_NAME
    TZ = zoneinfo.ZoneInfo(TZ_NAME)
except Exception:
    TZ = None


def today_str() -> str:
    """Возвращает сегодняшнюю дату в формате YYYY-MM-DD"""
    now = dt.datetime.now(tz=TZ) if TZ else dt.datetime.now()
    return now.date().isoformat()


def date_for_time(target_hour: int = 6) -> str:
    """
    Возвращает дату с учетом времени суток.
    Если время меньше target_hour (например, 6 утра), 
    считаем это предыдущим днем.
    """
    now = dt.datetime.now(tz=TZ) if TZ else dt.datetime.now()
    if now.hour < target_hour:
        yesterday = now - dt.timedelta(days=1)
        return yesterday.date().isoformat()
    return now.date().isoformat()


def get_date_list(days: int = 7) -> list[tuple[str, str]]:
    """
    Возвращает список дат для последних N дней.
    Возвращает: [(date_str, display_name), ...]
    """
    today = dt.datetime.now(tz=TZ) if TZ else dt.datetime.now()
    dates = []
    
    for i in range(days):
        date_obj = today - dt.timedelta(days=i)
        date_str = date_obj.date().isoformat()
        
        if i == 0:
            display = f"📅 Сегодня ({date_str})"
        elif i == 1:
            display = f"📅 Вчера ({date_str})"
        else:
            display = f"📅 {date_str}"
        
        dates.append((date_str, display))
    
    return dates