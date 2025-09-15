#!/usr/bin/env python3
"""
Hobby Tracker Bot - Трекер увлечений для Telegram
"""

import sys
import os

# Добавляем src в путь для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update

from src.bot.handlers import (
    start, help_cmd, quick_cmd, stats_cmd, list_all_cmd,
    button_callback, free_text
)
from src.data.files import create_sample_aliases
from src.utils.config import BOT_TOKEN


def main():
    """Главная функция запуска бота"""
    print("🚀 Запуск Hobby Tracker Bot...")
    
    # Создаем пример файла алиасов при первом запуске
    create_sample_aliases()
    print("✅ Конфигурация готова")
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("quick", quick_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("list", list_all_cmd))
    
    # Регистрируем обработчики кнопок и текста
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))
    
    print("✅ Все обработчики зарегистрированы")
    print("🎯 Бот запущен и готов к работе!")
    
    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()