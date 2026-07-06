import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Google Sheets Configuration  
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME = os.getenv("SHEET_NAME", "Данные")

# Timezone Configuration
TZ_NAME = os.getenv("TIMEZONE", os.getenv("TZ", "Europe/Moscow"))

# Reminder Configuration
# Simplified - no threshold needed

# Mini App / API
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
ALLOWED_USER_IDS = [int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]
API_PORT = int(os.getenv("API_PORT", "8000"))
AUTH_DISABLED = os.getenv("AUTH_DISABLED") == "1"  # только локальная отладка

# File paths
HOBBIES_HISTORY_FILE = "data/hobbies_history.txt"
ALIASES_FILE = "data/aliases.txt"
REMINDERS_FILE = "data/reminders.txt"
STARS_FILE = "data/stars.txt"
SERVICE_ACCOUNT_FILE = "service_account.json"

# Журнал и кэш
JOURNAL_FILE = "data/journal.jsonl"
JOURNAL_OFFSET_FILE = "data/journal.offset"
DAYCACHE_FILE = "data/cache/days.json"

# Google Sheets Scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def validate_config() -> None:
    """Вызывается из main() — НЕ при импорте, чтобы тесты жили без .env"""
    if not BOT_TOKEN or not SPREADSHEET_ID:
        raise SystemExit("Отсутствуют TELEGRAM_BOT_TOKEN или SPREADSHEET_ID в .env")
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise SystemExit(f"Нет файла {SERVICE_ACCOUNT_FILE} рядом с main.py")