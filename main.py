import os
import re
import time
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
# Конфигурация увлечений
# ──────────────────────────────────────────────────────────────────────────────
# Базовые увлечения с их отображаемыми названиями
HOBBIES = {
    "программирование": "💻 Программирование",
    "ютуб": "📺 YouTube", 
    "чтение": "📚 Чтение",
    "спорт": "🏃 Спорт",
    "музыка": "🎵 Музыка",
    "игры": "🎮 Игры",
    "изучение": "📖 Изучение",
    "рисование": "🎨 Рисование"
}

# Состояние пользователей (в реальном приложении лучше использовать Redis/DB)
user_states = {}

# Файл для хранения истории увлечений
HOBBIES_HISTORY_FILE = "hobbies_history.txt"

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

def get_recent_hobbies(limit=20):
    # Загружает последние использованные увлечения из файла
    if not os.path.exists(HOBBIES_HISTORY_FILE):
        return list(HOBBIES.keys())
    
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
        
        # Добавляем базовые увлечения, которых нет в истории
        for base_hobby in HOBBIES.keys():
            if base_hobby not in seen:
                unique_recent.append(base_hobby)
        
        return unique_recent[:limit]
    except Exception:
        return list(HOBBIES.keys())

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

def get_day_stars(target_date):
    # Получает звезды всех увлечений за указанную дату (обратное преобразование из баллов)
    try:
        dates = ws.col_values(1)
        headers = ws.row_values(1)
        
        for i, date_str in enumerate(dates, start=1):
            if date_str == target_date:
                row_values = ws.row_values(i)
                stars_dict = {}
                total_score = 0
                
                # Сначала получаем все баллы
                scores = {}
                for j, val in enumerate(row_values[1:], start=1):  # Пропускаем колонку даты
                    if j < len(headers) and val:
                        try:
                            header = headers[j]
                            score = float(val.replace(',', '.'))
                            scores[header] = score
                            total_score += score
                        except ValueError:
                            continue
                
                # Преобразуем баллы обратно в звезды (приблизительно)
                if total_score > 0:
                    for header, score in scores.items():
                        # Приблизительное восстановление звезд из пропорции
                        proportion = score / total_score
                        estimated_stars = max(1, round(proportion * 15))  # Предполагаем макс 15 звезд на день
                        stars_dict[norm_hobby(header)] = min(5, estimated_stars)
                
                return stars_dict
        return {}
    except Exception:
        return {}

def redistribute_scores(new_hobby, new_score, target_date):
    # Перераспределяет оценки так, чтобы сумма была 10
    try:
        dates = ws.col_values(1)
        headers = ws.row_values(1)
        
        # Находим строку с нужной датой
        row_idx = None
        for i, date_str in enumerate(dates, start=1):
            if date_str == target_date:
                row_idx = i
                break
        
        if not row_idx:
            return {new_hobby: new_score}
        
        # Получаем текущие значения
        row_values = ws.row_values(row_idx)
        current_values = {}
        
        for j, header in enumerate(headers):
            if j == 0:  # Пропускаем колонку даты
                continue
            
            norm_header = norm_hobby(header)
            if j < len(row_values) and row_values[j]:
                try:
                    current_values[norm_header] = float(row_values[j].replace(',', '.'))
                except ValueError:
                    current_values[norm_header] = 0
            else:
                current_values[norm_header] = 0
        
        # Обновляем значение нового увлечения
        current_values[norm_hobby(new_hobby)] = float(new_score)
        
        # Считаем текущую сумму
        total = sum(current_values.values())
        
        if total == 0:
            return {new_hobby: new_score}
        
        # Если сумма не равна 10, перераспределяем
        if abs(total - 10) > 0.01:
            scale_factor = 10.0 / total
            for hobby in current_values:
                current_values[hobby] = round(current_values[hobby] * scale_factor, 1)
        
        # Преобразуем обратно в оригинальные названия
        result = {}
        for header in headers[1:]:  # Пропускаем колонку даты
            norm_header = norm_hobby(header)
            if norm_header in current_values:
                result[header] = current_values[norm_header]
        
        # Добавляем новое увлечение, если его нет в заголовках
        if norm_hobby(new_hobby) not in [norm_hobby(h) for h in headers[1:]]:
            result[new_hobby] = current_values[norm_hobby(new_hobby)]
        
        return result
        
    except Exception:
        return {new_hobby: new_score}

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
    "Привет! Я бот учёта увлечений (шкала 0–10).\n\n"
    "Команды:\n"
    "/start — приветствие\n"
    "/help — помощь\n"
    "/quick — быстрый ввод через кнопки 🚀\n"
    "/log <данные> — записать оценки за сегодня\n"
    "  Примеры:\n"
    "  /log чтение 7 спорт 4 музыка 0\n"
    "  /log чтение:7, спорт=4; музыка 0\n\n"
    "Свободный ввод сообщений без /log тоже работает — я попытаюсь распознать пары «хобби число».\n"
    "Новые увлечения можно указывать сразу — я добавлю колонку автоматически.\n"
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
    recent_hobbies = get_recent_hobbies()
    
    # Создаем кнопки по 2 в ряд
    for i in range(0, len(recent_hobbies), 2):
        row = []
        for j in range(i, min(i + 2, len(recent_hobbies))):
            hobby_key = recent_hobbies[j]
            hobby_display = HOBBIES.get(hobby_key, f"📌 {hobby_key.capitalize()}")
            row.append(InlineKeyboardButton(hobby_display, callback_data=f"hobby:{hobby_key}"))
        buttons.append(row)
    
    # Кнопки управления
    buttons.append([
        InlineKeyboardButton("➕ Добавить новое", callback_data="add_new"),
        InlineKeyboardButton("📅 Выбрать дату", callback_data="select_date")
    ])
    
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

def stars_to_score(stars_dict):
    # Конвертирует звезды в 10-бальную систему с пропорциональным распределением
    if not stars_dict:
        return {}
    
    total_stars = sum(stars_dict.values())
    if total_stars == 0:
        return {hobby: 0 for hobby in stars_dict}
    
    # Распределяем 10 баллов пропорционально звездам
    result = {}
    for hobby, stars in stars_dict.items():
        score = round((stars / total_stars) * 10, 1)
        result[hobby] = score
    
    return result

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
        hobby_display = HOBBIES.get(hobby_key, hobby_key.capitalize())
        
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
            
            # Получаем текущие звезды для этой даты
            current_stars = get_day_stars(target_date)
            current_stars[hobby_key] = stars
            
            # Конвертируем звезды в баллы
            score_values = stars_to_score(current_stars)
            
            # Записываем в Google Sheets с нужной датой
            old_today_str = globals()['today_str']
            globals()['today_str'] = lambda: target_date
            try:
                headers, row_idx = write_values(score_values)
            finally:
                globals()['today_str'] = old_today_str
            
            hobby_display = HOBBIES.get(hobby_key, hobby_key.capitalize())
            stars_display = "⭐" * stars if stars > 0 else "❌"
            
            # Получаем общую сумму
            total_score = sum(score_values.values())
            total_stars = sum(current_stars.values())
            
            # Формируем сообщение с результатами
            result_lines = [f"✅ Записано: {stars_display} {hobby_display}!", f"📅 Дата: {target_date}", ""]
            
            # Показываем все увлечения за день со звездами и баллами
            for h, score in score_values.items():
                if h in current_stars and current_stars[h] > 0:
                    display_name = HOBBIES.get(h, h.capitalize())
                    hobby_stars = current_stars[h]
                    stars_emoji = "⭐" * hobby_stars
                    emoji = "🔥" if h == hobby_key else "📊"
                    result_lines.append(f"{emoji} {display_name}: {stars_emoji} ({score:g} б.)")
            
            result_lines.append(f"\n🌟 Всего звезд: {total_stars}")
            result_lines.append(f"🎯 Общий балл: {total_score:g}/10")
            result_lines.append(f"\n📊 [Открыть Google Sheets](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID})")
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить еще", callback_data="back_to_hobbies")]
            ])
            
            await query.edit_message_text(
                "\n".join(result_lines),
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
    
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
    
    elif data == "back_to_hobbies":
        keyboard = create_hobby_keyboard()
        await query.edit_message_text(
            "🚀 Выберите увлечение:",
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
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("quick", quick_cmd))
    app.add_handler(CommandHandler("log", log_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
