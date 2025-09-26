"""Управление настройками звезд"""

import os
from typing import List
from ..utils.config import STARS_FILE


def load_star_values() -> List[float]:
    """Загружает значения звезд из файла, возвращает список по умолчанию если файла нет"""
    default_values = [0.5, 1, 2, 3, 4, 5, 6, 7, 8]
    
    if not os.path.exists(STARS_FILE):
        return default_values
    
    try:
        values = []
        with open(STARS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # Игнорируем комментарии
                    try:
                        value = float(line)
                        if 0 <= value <= 50:  # Разумные ограничения
                            values.append(value)
                    except ValueError:
                        continue  # Игнорируем неправильные строки
        
        return sorted(values) if values else default_values
    except Exception:
        return default_values


def create_default_stars_file():
    """Создает файл stars.txt с настройками по умолчанию"""
    if os.path.exists(STARS_FILE):
        return
    
    try:
        # Создаем папку data если её нет
        os.makedirs(os.path.dirname(STARS_FILE), exist_ok=True)
        
        content = """# Настройки звезд для трекера увлечений
# Каждая строка = одно значение звезд
# Поддерживаются десятичные значения (0.5, 1.5, etc.)
# Строки начинающиеся с # игнорируются

0.5
1
2
3
4
5
6
7
8
"""
        
        with open(STARS_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
            
    except Exception:
        pass  # Молчаливо игнорируем ошибки создания файла