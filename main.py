import os
import re
import time
import datetime as dt
from collections import defaultdict

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
        ws.update(f"A1:{gspread.utils.rowcol_to_a1(1, len(new_headers))}", [new_headers])
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

async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    app.add_handler(CommandHandler("log", log_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
