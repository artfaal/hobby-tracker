import os

# До любых импортов src: фейковое окружение для тестов
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("SPREADSHEET_ID", "test-spreadsheet-id")
