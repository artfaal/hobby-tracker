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

# File paths
HOBBIES_HISTORY_FILE = "data/hobbies_history.txt"
ALIASES_FILE = "data/aliases.txt"
REMINDERS_FILE = "data/reminders.txt"
STARS_FILE = "data/stars.txt"
SERVICE_ACCOUNT_FILE = "service_account.json"

# Google Sheets Scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Validation
if not BOT_TOKEN or not SPREADSHEET_ID:
    raise SystemExit("Отсутствуют TELEGRAM_BOT_TOKEN или SPREADSHEET_ID в .env")

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    raise SystemExit(f"Нет файла {SERVICE_ACCOUNT_FILE} рядом с main.py")