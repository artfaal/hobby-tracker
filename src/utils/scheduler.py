import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.error import TelegramError

from .config import TZ_NAME
from ..data.reminders import get_reminders_for_hour
from ..data.sheets import SheetsManager
from ..utils.dates import date_for_time
from .dates import get_tz


class ReminderScheduler:
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.scheduler = AsyncIOScheduler(timezone=get_tz())
        self.sheets = SheetsManager()
        
    def start(self):
        """Запускает планировщик"""
        # Добавляем задачу проверки напоминаний каждый час
        self.scheduler.add_job(
            self._check_reminders,
            CronTrigger(minute=0, timezone=get_tz()),  # Каждый час ровно в 00 минут
            id='hourly_reminders'
        )
        
        self.scheduler.start()
        print("✅ Планировщик напоминаний запущен")
    
    def stop(self):
        """Останавливает планировщик"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            print("🛑 Планировщик напоминаний остановлен")
    
    async def _check_reminders(self):
        """Проверяет и отправляет напоминания для текущего часа"""
        try:
            current_hour = datetime.now(tz=get_tz()).hour
            user_ids = get_reminders_for_hour(current_hour)
            
            for user_id in user_ids:
                await self._send_reminder(user_id)
                
        except Exception as e:
            print(f"❌ Ошибка при проверке напоминаний: {e}")
    
    async def _send_reminder(self, user_id: int):
        """Отправляет напоминание конкретному пользователю"""
        try:
            # Получаем статистику за сегодня
            today = date_for_time()
            today_data = self.sheets.get_day_data(today)
            today_total = sum(today_data.values()) if today_data else 0
            
            # Формируем сообщение с полной статистикой
            message = "📝 Время записать активности!"
            
            if today_total > 0:
                # Показываем полную статистику
                activities = []
                for hobby, score in today_data.items():
                    if score > 0:
                        from ..data.files import get_hobby_display_name
                        from ..bot.messages import format_stars_display
                        display_name = get_hobby_display_name(hobby)
                        stars_display = format_stars_display(score)
                        # Форматируем число для отображения
                        if score == int(score):
                            score_text = str(int(score))
                        else:
                            score_text = str(score)
                        activities.append(f"{display_name}: {stars_display} ({score_text})")
                
                activities_text = "\n".join(activities)
                # Форматируем общий балл
                if today_total == int(today_total):
                    total_text = str(int(today_total))
                else:
                    total_text = str(today_total)
                
                message = (
                    f"📝 Время записать активности!\n\n"
                    f"📊 Статистика на сегодня:\n{activities_text}\n"
                    f"🎯 Общий балл: {total_text}\n\n"
                    f"Нажмите /quick для записи!"
                )
            else:
                # Еще ничего не записано
                message = (
                    "📝 Время записать активности!\n\n"
                    "📊 Пока не записано ни одной активности.\n\n"
                    "Нажмите /quick для начала!"
                )
            
            await self.bot.send_message(chat_id=user_id, text=message)
            
        except TelegramError as e:
            if e.message == "Forbidden: bot was blocked by the user":
                # Пользователь заблокировал бота, удаляем его напоминания
                from ..data.reminders import clear_user_reminders
                cleared = clear_user_reminders(user_id)
                print(f"🚫 Пользователь {user_id} заблокировал бота, удалено {cleared} напоминаний")
            else:
                print(f"❌ Ошибка отправки напоминания пользователю {user_id}: {e}")
        except Exception as e:
            print(f"❌ Неожиданная ошибка при отправке напоминания {user_id}: {e}")


# Глобальный экземпляр планировщика
_scheduler_instance = None


def get_scheduler(bot_token: str = None) -> ReminderScheduler:
    """Получает или создает глобальный экземпляр планировщика"""
    global _scheduler_instance
    if _scheduler_instance is None and bot_token:
        _scheduler_instance = ReminderScheduler(bot_token)
    return _scheduler_instance


def start_scheduler(bot_token: str):
    """Запускает глобальный планировщик"""
    scheduler = get_scheduler(bot_token)
    if scheduler:
        scheduler.start()


def stop_scheduler():
    """Останавливает глобальный планировщик"""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None