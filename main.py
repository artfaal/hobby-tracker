#!/usr/bin/env python3
"""
Hobby Tracker Bot - Трекер увлечений для Telegram
"""

import sys
import os
import logging

# Добавляем src в путь для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update

from src.bot.handlers import (
    start, help_cmd, quick_cmd, stats_cmd, list_all_cmd, reminders_cmd,
    button_callback, text_message_handler
)
from src.data.files import create_sample_aliases
from src.utils.config import BOT_TOKEN, validate_config
from src.utils.scheduler import start_scheduler, stop_scheduler


def main():
    """Главная функция запуска бота"""
    # Настройка логирования
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.StreamHandler()  # Выводим в stdout для Docker logs
        ]
    )
    
    # Отключаем лишние логи от httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("🚀 Запуск Hobby Tracker Bot...")
    
    try:
        validate_config()
        # Создаем пример файла алиасов при первом запуске
        create_sample_aliases()
        logger.info("✅ Конфигурация готова")
    except Exception as e:
        logger.error(f"❌ Ошибка конфигурации: {e}")
        sys.exit(1)
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("quick", quick_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("list", list_all_cmd))
    app.add_handler(CommandHandler("reminders", reminders_cmd))
    
    # Регистрируем обработчики кнопок и текста
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    
    logger.info("✅ Все обработчики зарегистрированы")
    
    try:
        # Запускаем планировщик напоминаний
        start_scheduler(BOT_TOKEN)
        logger.info("✅ Планировщик напоминаний запущен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика: {e}")
    
    logger.info("🎯 Бот запущен и готов к работе!")
    
    try:
        # Запускаем бота
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка бота: {e}")
    finally:
        # Останавливаем планировщик при завершении
        try:
            stop_scheduler()
            logger.info("✅ Планировщик остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки планировщика: {e}")
        logger.info("👋 Бот остановлен")


if __name__ == "__main__":
    main()