import os
import re
import time
import asyncio
import datetime as dt
from collections import defaultdict

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ──────────────────────────────────────────────────────────────────────────────
# Конфиг
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME     = os.getenv("SHEET_NAME", "Данные")
TZ_NAME        = os.getenv("TZ", "Europe/Moscow")

if not BOT_TOKEN or not SPREADSHEET_ID:
    raise SystemExit("Отсутствуют TELEGRAM_BOT_TOKEN или SPREADSHEET_ID в .env")

# Локальная таймзона для сегодняшней даты
try:
    import zoneinfo
    TZ = zoneinfo.ZoneInfo(TZ_NAME)
except Exception:
    TZ = None

# ──────────────────────────────────────────────────────────────────────────────
# Конфигурация файлов и состояния
# ──────────────────────────────────────────────────────────────────────────────
# Состояние пользователей (в реальном приложении лучше использовать Redis/DB)
user_states = {}

# Файлы для хранения данных
HOBBIES_HISTORY_FILE = "hobbies_history.txt"
ALIASES_FILE = "aliases.txt"

# Пример начального файла aliases.txt для красивого отображения
def create_sample_aliases():
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

# ──────────────────────────────────────────────────────────────────────────────
# Подключение к Google Sheets через service_account.json
# ──────────────────────────────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

if not os.path.exists("service_account.json"):
    raise SystemExit("Нет файла service_account.json рядом с main.py")

creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
gc = gspread.authorize(creds)

def open_or_create_sheet(spreadsheet_id: str, sheet_name: str):
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=26)
        ws.update("A1", "Дата")
    return ws

ws = open_or_create_sheet(SPREADSHEET_ID, SHEET_NAME)

# ──────────────────────────────────────────────────────────────────────────────
# Помощники: дата, нормализация, парсинг
# ──────────────────────────────────────────────────────────────────────────────
def today_str():
    now = dt.datetime.now(tz=TZ) if TZ else dt.datetime.now()
    return now.date().isoformat()  # YYYY-MM-DD

def date_for_time(target_hour=6):
    # Если время меньше target_hour (например, 6 утра), считаем это предыдущим днем
    now = dt.datetime.now(tz=TZ) if TZ else dt.datetime.now()
    if now.hour < target_hour:
        yesterday = now - dt.timedelta(days=1)
        return yesterday.date().isoformat()
    return now.date().isoformat()

def load_aliases():
    # Загружает алиасы для отображения увлечений
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

def save_aliases(aliases):
    # Сохраняет алиасы в файл
    try:
        with open(ALIASES_FILE, 'w', encoding='utf-8') as f:
            for hobby_name, display_name in aliases.items():
                f.write(f"{hobby_name}={display_name}\n")
    except Exception:
        pass

def get_hobby_display_name(hobby_name):
    # Получает красивое название увлечения для отображения
    aliases = load_aliases()
    norm_name = norm_hobby(hobby_name)
    if norm_name in aliases:
        return aliases[norm_name]
    return f"📌 {hobby_name.capitalize()}"

def get_recent_hobbies(limit=20):
    # Загружает последние использованные увлечения из файла
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

def get_all_hobbies():
    # Получает все увлечения из истории
    return get_recent_hobbies(limit=1000)

def save_hobby_to_history(hobby_name):
    # Сохраняет увлечение в начало файла истории
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

def get_day_total(target_date):
    # Получает сумму всех увлечений за указанную дату
    try:
        dates = ws.col_values(1)
        headers = ws.row_values(1)
        
        for i, date_str in enumerate(dates, start=1):
            if date_str == target_date:
                row_values = ws.row_values(i)
                total = 0
                for j, val in enumerate(row_values[1:], start=1):  # Пропускаем колонку даты
                    if val and val.replace('.', '').replace(',', '').isdigit():
                        total += float(val.replace(',', '.'))
                return total
        return 0
    except Exception:
        return 0



def norm_hobby(name: str) -> str:
    # Нормируем название хобби для сопоставления с заголовками
    name = name.strip().lower()
    replacements = {
        "ё": "е",
    }
    for a, b in replacements.items():
        name = name.replace(a, b)
    return name

def load_headers() -> list[str]:
    headers = ws.row_values(1)
    if not headers:
        ws.update("A1", "Дата")
        headers = ["Дата"]
    return headers

def ensure_columns(hobby_names: list[str]) -> list[str]:
    """Гарантирует наличие столбцов под каждое хобби. Возвращает итоговый список заголовков."""
    headers = load_headers()
    header_norm_map = {norm_hobby(h): h for h in headers}
    to_add = []
    for raw in hobby_names:
        n = norm_hobby(raw)
        if n not in header_norm_map:
            # Добавим новый столбец справа
            to_add.append(raw.strip())
    if to_add:
        # Добавляем пачкой, сохраняя регистр, как ввёл пользователь
        # Заголовки в Google Sheets — первая строка
        new_headers = headers + to_add
        ws.update([new_headers], f"A1:{gspread.utils.rowcol_to_a1(1, len(new_headers))}")
        return new_headers
    return headers

PAIR_PAT = re.compile(r"([a-zA-Zа-яА-ЯёЁ]+)\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)")

def parse_log_text(text: str) -> dict[str, float]:
    """
    Принимает строки вида:
    - "чтение 7 спорт 4 музыка 0"
    - "чтение:7, спорт=4; музыка 0"
    - "reading 8"
    Возвращает словарь {хобби: значение(float)}.
    """
    found = PAIR_PAT.findall(text)
    pairs = defaultdict(float)
    for hobby, val in found:
        v = float(val.replace(",", "."))
        pairs[hobby] = v
    return dict(pairs)

def clamp_0_10(v: float) -> float:
    return max(0.0, min(10.0, v))

# ──────────────────────────────────────────────────────────────────────────────
# Работа с таблицей: найти/создать сегодняшнюю строку, обновить значения
# ──────────────────────────────────────────────────────────────────────────────
def find_today_row_idx() -> int | None:
    # Ищем индекс строки (1-based) по сегодняшней дате в колонке A
    dates = ws.col_values(1)
    target = today_str()
    for i, d in enumerate(dates, start=1):
        if d == target:
            return i
    return None

def create_today_row():
    # Добавляем пустую строку с сегодняшней датой в A
    ws.append_row([today_str()])

def write_values(values: dict[str, float]) -> tuple[list[str], int]:
    """
    values: {hobby: score}
    1) гарантируем наличие колонок
    2) находим/создаём строку на сегодня
    3) записываем значения
    Возвращает: (финальные заголовки, индекс строки)
    """
    hobby_list = list(values.keys())
    headers = ensure_columns(hobby_list)
    row_idx = find_today_row_idx()
    if row_idx is None:
        create_today_row()
        # После append_row индекс = последняя строка
        row_idx = len(ws.get_all_values())

    # Карта: нормализованное название -> индекс столбца
    header_norm_to_col = {norm_hobby(h): i+1 for i, h in enumerate(headers)}  # 1-based

    updates = []
    for hobby, raw_v in values.items():
        v = clamp_0_10(float(raw_v))
        col = header_norm_to_col[norm_hobby(hobby)]
        a1 = gspread.utils.rowcol_to_a1(row_idx, col)
        updates.append({"range": a1, "values": [[v]]})

    if updates:
        ws.batch_update(updates)
    return headers, row_idx

# ──────────────────────────────────────────────────────────────────────────────
# Хэндлеры бота
# ──────────────────────────────────────────────────────────────────────────────
HELP_TEXT = (
    "Привет! Я бот учёта увлечений со звездочками ⭐\n\n"
    "Команды:\n"
    "/start — приветствие\n"
    "/help — помощь\n"
    "/quick — быстрый ввод через кнопки 🚀\n"
    "/list — показать все увлечения 📋\n"
    "/log <данные> — записать оценки за сегодня\n"
    "  Примеры:\n"
    "  /log чтение 7 спорт 4 музыка 0\n"
    "  /log чтение:7, спорт=4; музыка 0\n\n"
    "⭐ Система звезд:\n"
    "⭐ = минимальный приоритет\n"
    "⭐⭐⭐ = средний приоритет\n"
    "⭐⭐⭐⭐⭐ = максимальный приоритет\n\n"
    "Новые увлечения можно добавлять прямо через /quick!"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def log_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    payload = text.partition(" ")[2] if " " in text else ""
    await process_log(update, payload)

async def quick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = create_hobby_keyboard()
    await update.message.reply_text(
        "🚀 Выберите увлечение:", 
        reply_markup=keyboard
    )

def create_hobby_keyboard():
    buttons = []
    recent_hobbies = get_recent_hobbies(limit=10)  # Только последние 10
    
    if not recent_hobbies:
        # Если нет истории, показываем кнопку для добавления
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
    buttons.append([InlineKeyboardButton("📅 Выбрать дату", callback_data="select_date")])
    
    return InlineKeyboardMarkup(buttons)

def create_score_keyboard(hobby_name: str, target_date: str = None):
    if target_date is None:
        target_date = date_for_time()
    
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


def create_date_keyboard():
    buttons = []
    today = dt.datetime.now(tz=TZ) if TZ else dt.datetime.now()
    
    # Последние 7 дней
    for i in range(7):
        date_obj = today - dt.timedelta(days=i)
        date_str = date_obj.date().isoformat()
        
        if i == 0:
            display = f"📅 Сегодня ({date_str})"
        elif i == 1:
            display = f"📅 Вчера ({date_str})"
        else:
            display = f"📅 {date_str}"
        
        buttons.append([InlineKeyboardButton(display, callback_data=f"date:{date_str}")])
    
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")])
    return InlineKeyboardMarkup(buttons)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("hobby:"):
        hobby_key = data.split(":", 1)[1]
        hobby_display = get_hobby_display_name(hobby_key)
        
        # Получаем выбранную дату из состояния пользователя
        target_date = date_for_time()
        if user_id in user_states and user_states[user_id].startswith("selected_date:"):
            target_date = user_states[user_id].split(":", 1)[1]
        
        keyboard = create_score_keyboard(hobby_key, target_date)
        
        date_display = "сегодня" if target_date == date_for_time() else target_date
        await query.edit_message_text(
            f"⭐ Оцените '{hobby_display}' на {date_display}:\n\n" +
            "⭐ = минимальный приоритет\n" +
            "⭐⭐⭐ = средний приоритет\n" +
            "⭐⭐⭐⭐⭐ = максимальный приоритет",
            reply_markup=keyboard
        )
    
    elif data.startswith("stars:"):
        parts = data.split(":")
        if len(parts) >= 4:
            hobby_key = parts[1]
            stars = int(parts[2])
            target_date = parts[3]
            
            # Сохраняем увлечение в историю
            save_hobby_to_history(hobby_key)
            
            # Простая система: звезды = баллы (1:1)
            # Просто записываем количество звезд как баллы
            score_values = {hobby_key: stars}
            
            # Быстрый отклик: показываем короткое подтверждение
            hobby_display = get_hobby_display_name(hobby_key)
            stars_display = "⭐" * stars if stars > 0 else "❌"
            
            # Показываем простое подтверждение  
            result_text = f"✅ {stars_display} {hobby_display} = {stars} балл"
            if stars != 1:
                result_text += "ов" if stars in [0, 5, 6, 7, 8, 9, 10] else "а"
            
            await query.edit_message_text(result_text)
            
            # Мгновенно возвращаемся к списку увлечений
            keyboard = create_hobby_keyboard()
            
            # Показываем список снова через 0.5 секунды
            await asyncio.sleep(0.5)
            await query.edit_message_text(
                "🚀 Выберите следующее увлечение:",
                reply_markup=keyboard
            )
            
            # Записываем в Google Sheets в фоне
            try:
                old_today_str = globals()['today_str']
                globals()['today_str'] = lambda: target_date
                write_values(score_values)
            except Exception:
                pass  # Игнорируем ошибки Google Sheets для скорости
            finally:
                globals()['today_str'] = old_today_str
    
    elif data.startswith("date:"):
        selected_date = data.split(":", 1)[1]
        user_states[user_id] = f"selected_date:{selected_date}"
        
        keyboard = create_hobby_keyboard()
        await query.edit_message_text(
            f"📅 Выбрана дата: {selected_date}\n🚀 Выберите увлечение:",
            reply_markup=keyboard
        )
    
    elif data == "select_date":
        keyboard = create_date_keyboard()
        await query.edit_message_text(
            "📅 Выберите дату для записи:",
            reply_markup=keyboard
        )
    
    elif data == "list_all":
        all_hobbies = get_all_hobbies()
        if not all_hobbies:
            await query.edit_message_text(
                "📋 Пока нет увлечений в истории."
            )
        else:
            # Показываем список с кнопками для выбора
            buttons = []
            for i in range(0, len(all_hobbies), 2):
                row = []
                for j in range(i, min(i + 2, len(all_hobbies))):
                    hobby_key = all_hobbies[j]
                    hobby_display = get_hobby_display_name(hobby_key)
                    row.append(InlineKeyboardButton(hobby_display, callback_data=f"hobby:{hobby_key}"))
                buttons.append(row)
            
            buttons.append([InlineKeyboardButton("← Назад", callback_data="back_to_hobbies")])
            keyboard = InlineKeyboardMarkup(buttons)
            
            await query.edit_message_text(
                f"📋 Все ваши увлечения ({len(all_hobbies)}):",
                reply_markup=keyboard
            )
    
    elif data == "add_new":
        # Получаем выбранную дату из состояния пользователя
        target_date = date_for_time()
        if user_id in user_states and user_states[user_id].startswith("selected_date:"):
            target_date = user_states[user_id].split(":", 1)[1]
        
        user_states[user_id] = f"waiting_new_hobby:{target_date}"
        await query.edit_message_text(
            "✏️ Напишите название нового увлечения:"
        )
    
    elif data == "back_to_hobbies":
        keyboard = create_hobby_keyboard()
        await query.edit_message_text(
            "🚀 Выберите увлечение:",
            reply_markup=keyboard
        )
    
async def list_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            # Отображаем только первые 30 увлечений
            hobbies_text = "\n".join([f"• {get_hobby_display_name(h)}" for h in all_hobbies[:30]])
            message = f"📋 Ваши увлечения ({len(all_hobbies)}):\n\n{hobbies_text}"
            if len(all_hobbies) > 30:
                message += f"\n\n... и ещё {len(all_hobbies) - 30} увлечений"
        
        await update.message.reply_text(message)

async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Проверяем состояние пользователя
    if user_id in user_states and user_states[user_id].startswith("waiting_new_hobby:"):
        hobby_name = update.message.text.strip().lower()
        target_date = user_states[user_id].split(":", 1)[1]
        user_states.pop(user_id, None)
        
        # Создаем клавиатуру для выбора оценки
        keyboard = create_score_keyboard(hobby_name, target_date)
        
        date_display = "сегодня" if target_date == date_for_time() else target_date
        await update.message.reply_text(
            f"⭐ Оцените '{hobby_name.capitalize()}' на {date_display}:\n\n" +
            "⭐ = минимальный приоритет\n" +
            "⭐⭐⭐ = средний приоритет\n" +
            "⭐⭐⭐⭐⭐ = максимальный приоритет",
            reply_markup=keyboard
        )
        return
    
    # Пытаемся распознать пары даже без /log
    payload = update.message.text
    await process_log(update, payload, silent_on_fail=True)

async def process_log(update: Update, payload: str, silent_on_fail: bool=False):
    pairs = parse_log_text(payload)
    if not pairs:
        if not silent_on_fail:
            await update.message.reply_text(
                "Я не нашёл пар «хобби число».\nПример: чтение 7 спорт 4 музыка 0"
            )
        return

    # Валидация диапазона и запись
    clean = {}
    out_of_range = []
    for h, v in pairs.items():
        v = float(v)
        if v < 0 or v > 10:
            out_of_range.append((h, v))
        clean[h] = clamp_0_10(v)

    headers, row_idx = write_values(clean)

    # Формируем ответ
    lines = [f"Дата: {today_str()} записано:"]
    for h, v in clean.items():
        lines.append(f"• {h.strip()}: {v:g}")
    if out_of_range:
        lines.append("\nНекоторые значения были за пределами 0–10 и приведены к границам.")

    await update.message.reply_text("\n".join(lines))

def main():
    # Создаем пример файла алиасов при первом запуске
    create_sample_aliases()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("quick", quick_cmd))
    app.add_handler(CommandHandler("list", list_all_cmd))
    app.add_handler(CommandHandler("log", log_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
