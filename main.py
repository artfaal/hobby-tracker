#!/usr/bin/env python3
"""Hobby Tracker Bot — бот + API Mini App + sync-воркер в одном процессе"""

import asyncio
import logging
import sys

import uvicorn
from telegram import MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from src import runtime
from src.api.server import create_app
from src.bot.handlers import (
    start, help_cmd, quick_cmd, stats_cmd, list_all_cmd, reminders_cmd,
    button_callback, text_message_handler,
)
from src.data.files import create_sample_aliases
from src.data.sheets import get_sheets_manager
from src.data.sync_worker import SyncWorker
from src.utils.config import API_PORT, BOT_TOKEN, WEBAPP_URL, validate_config
from src.utils.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def build_bot() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("quick", quick_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("list", list_all_cmd))
    app.add_handler(CommandHandler("reminders", reminders_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    return app


async def amain() -> None:
    runtime.init_runtime()
    await runtime.reconcile_cache()  # Sheets истина: подтянуть ручные правки, prune старых дат

    bot_app = build_bot()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("✅ Бот запущен (polling)")

    if WEBAPP_URL:
        await bot_app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="📝 Записать", web_app=WebAppInfo(url=WEBAPP_URL))
        )
        logger.info("✅ Menu button → %s", WEBAPP_URL)

    worker = SyncWorker(
        runtime.journal, runtime.wake,
        write_day=lambda values, date: get_sheets_manager().write_values(values, date),
        sheets_lock=runtime.sheets_lock,
    )
    worker_task = asyncio.create_task(worker.run())
    runtime.wake.set()  # доиграть несинканный хвост после рестарта
    logger.info("✅ Sync-воркер запущен")

    start_scheduler(BOT_TOKEN)
    logger.info("✅ Планировщик напоминаний запущен")

    server = uvicorn.Server(uvicorn.Config(
        create_app(), host="0.0.0.0", port=API_PORT, log_level="info"))
    logger.info("🎯 Всё запущено, API на :%d", API_PORT)
    await server.serve()  # блокируется до SIGTERM/SIGINT (uvicorn ловит сигналы)

    logger.info("🛑 Остановка...")
    worker_task.cancel()
    stop_scheduler()
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()
    logger.info("👋 Бот остановлен")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.info("🚀 Запуск Hobby Tracker...")
    try:
        validate_config()
        create_sample_aliases()
    except SystemExit:
        raise
    except Exception as e:
        logger.error("❌ Ошибка конфигурации: %s", e)
        sys.exit(1)
    asyncio.run(amain())


if __name__ == "__main__":
    main()
