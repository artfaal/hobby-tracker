import os
from typing import List, Tuple
from ..utils.config import REMINDERS_FILE


def load_reminders() -> List[Tuple[int, int]]:
    """Загружает напоминания из файла. Возвращает список (user_id, hour)"""
    reminders = []
    if os.path.exists(REMINDERS_FILE):
        try:
            with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        try:
                            user_id, hour = line.split(':', 1)
                            reminders.append((int(user_id), int(hour)))
                        except ValueError:
                            continue
        except Exception:
            pass
    return reminders


def save_reminders(reminders: List[Tuple[int, int]]) -> None:
    """Сохраняет напоминания в файл"""
    try:
        # Создаем папку data если её нет
        os.makedirs(os.path.dirname(REMINDERS_FILE), exist_ok=True)
        with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
            for user_id, hour in reminders:
                f.write(f"{user_id}:{hour}\n")
    except Exception:
        pass


def get_user_reminders(user_id: int) -> List[int]:
    """Получает все напоминания пользователя"""
    reminders = load_reminders()
    return [hour for uid, hour in reminders if uid == user_id]


def add_reminder(user_id: int, hour: int) -> bool:
    """Добавляет напоминание. Возвращает True если успешно, False если уже существует"""
    if not (0 <= hour <= 23):
        return False
    
    reminders = load_reminders()
    
    # Проверяем, нет ли уже такого напоминания
    for uid, h in reminders:
        if uid == user_id and h == hour:
            return False
    
    # Добавляем новое напоминание
    reminders.append((user_id, hour))
    save_reminders(reminders)
    return True


def remove_reminder(user_id: int, hour: int) -> bool:
    """Удаляет напоминание. Возвращает True если успешно, False если не найдено"""
    reminders = load_reminders()
    original_length = len(reminders)
    
    # Удаляем напоминание
    reminders = [(uid, h) for uid, h in reminders if not (uid == user_id and h == hour)]
    
    if len(reminders) < original_length:
        save_reminders(reminders)
        return True
    return False


def get_reminders_for_hour(hour: int) -> List[int]:
    """Получает всех пользователей для напоминания в указанный час"""
    reminders = load_reminders()
    return [user_id for user_id, h in reminders if h == hour]


def clear_user_reminders(user_id: int) -> int:
    """Удаляет все напоминания пользователя. Возвращает количество удаленных"""
    reminders = load_reminders()
    original_length = len(reminders)
    
    reminders = [(uid, h) for uid, h in reminders if uid != user_id]
    removed_count = original_length - len(reminders)
    
    if removed_count > 0:
        save_reminders(reminders)
    
    return removed_count