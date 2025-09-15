import os
from ..utils.config import HOBBIES_HISTORY_FILE, ALIASES_FILE


def norm_hobby(name: str) -> str:
    """Нормализует название хобби для сопоставления"""
    name = name.strip().lower()
    replacements = {"ё": "е"}
    for a, b in replacements.items():
        name = name.replace(a, b)
    return name


def load_aliases() -> dict[str, str]:
    """Загружает алиасы для отображения увлечений"""
    aliases = {}
    if os.path.exists(ALIASES_FILE):
        try:
            with open(ALIASES_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line:
                        hobby_name, display_name = line.split('=', 1)
                        aliases[hobby_name.strip().lower()] = display_name.strip()
        except Exception:
            pass
    return aliases


def save_aliases(aliases: dict[str, str]) -> None:
    """Сохраняет алиасы в файл"""
    try:
        with open(ALIASES_FILE, 'w', encoding='utf-8') as f:
            for hobby_name, display_name in aliases.items():
                f.write(f"{hobby_name}={display_name}\n")
    except Exception:
        pass


def get_hobby_display_name(hobby_name: str) -> str:
    """Получает красивое название увлечения для отображения"""
    aliases = load_aliases()
    norm_name = norm_hobby(hobby_name)
    if norm_name in aliases:
        return aliases[norm_name]
    return f"📌 {hobby_name.capitalize()}"


def get_recent_hobbies(limit: int = 20) -> list[str]:
    """Загружает последние использованные увлечения из файла"""
    if not os.path.exists(HOBBIES_HISTORY_FILE):
        return []
    
    try:
        with open(HOBBIES_HISTORY_FILE, 'r', encoding='utf-8') as f:
            recent = [line.strip() for line in f.readlines() if line.strip()]
        
        # Убираем дубликаты, сохраняя порядок
        seen = set()
        unique_recent = []
        for hobby in recent:
            if hobby not in seen:
                seen.add(hobby)
                unique_recent.append(hobby)
        
        return unique_recent[:limit]
    except Exception:
        return []


def get_all_hobbies() -> list[str]:
    """Получает все увлечения из истории"""
    return get_recent_hobbies(limit=1000)


def save_hobby_to_history(hobby_name: str) -> None:
    """Сохраняет увлечение в начало файла истории"""
    recent = get_recent_hobbies()
    
    # Убираем hobby_name из списка, если он там есть
    if hobby_name in recent:
        recent.remove(hobby_name)
    
    # Добавляем в начало
    recent.insert(0, hobby_name)
    
    # Сохраняем в файл (максимум 20 записей)
    try:
        with open(HOBBIES_HISTORY_FILE, 'w', encoding='utf-8') as f:
            for hobby in recent[:20]:
                f.write(f"{hobby}\n")
    except Exception:
        pass


def create_sample_aliases() -> None:
    """Создает пример файла алиасов при первом запуске"""
    if not os.path.exists(ALIASES_FILE):
        sample_aliases = {
            "программирование": "💻 Программирование",
            "ютуб": "📺 YouTube",
            "чтение": "📚 Чтение", 
            "спорт": "🏃 Спорт",
            "музыка": "🎵 Музыка",
            "игры": "🎮 Игры",
            "мото": "🏍️ Мото"
        }
        save_aliases(sample_aliases)