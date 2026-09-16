"""
Фоновый воркер: ежедневно рассылает пользователям расписание на завтра
в указанное время (notification_time).
"""

import asyncio
from datetime import date, datetime, timedelta

from aiogram import Bot

from console_log import log
from database import get_users_for_notification, update_user
from ulstu.schedule import (
    format_day_schedule,
    get_schedule,
    get_schedule_for_date,
)
from utils import build_delete_button

# Лимит одновременных отправок (защита от rate-limit Telegram)
MAX_CONCURRENT_SENDS = 20

concurrency_gate = asyncio.Semaphore(MAX_CONCURRENT_SENDS)


async def notification_worker(bot: Bot):
    """Бесконечный цикл: раз в минуту проверяет, комему отправить расписание."""
    log("notifications", "Воркер уведомлений стартовал")

    while True:
        now = datetime.now().astimezone()

        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")

        users = await get_users_for_notification(
            current_time,
            current_date,
        )

        if users:
            tasks = [
                send_tomorrow_schedule(bot, user, current_date)
                for user in users
            ]

            await asyncio.gather(*tasks)

        delay = 60 - now.second - now.microsecond / 1_000_000

        await asyncio.sleep(delay)


async def send_tomorrow_schedule(
    bot: Bot,
    user: dict,
    current_date: str,
):
    """Формирует расписание на завтра и отправляет пользователю с кнопкой «Удалить»."""
    telegram_id = user["telegram_id"]

    async with concurrency_gate:
        try:
            log("notifications", "Отправка расписания на завтра", telegram_id)

            schedule = await get_schedule(telegram_id)

            if not schedule:
                log(
                    "notifications",
                    "Расписание пустое — пропуск",
                    telegram_id,
                )
                return

            tomorrow = date.today() + timedelta(days=1)

            tomorrow_schedule = get_schedule_for_date(
                schedule,
                tomorrow,
            )

            # Создаём пустой день, если на завтра занятий нет
            if tomorrow_schedule is None:
                tomorrow_schedule = {
                    "day": tomorrow.strftime("%d.%m.%Y"),
                    "date": tomorrow.strftime("%d.%m.%Y"),
                    "lessons": [],
                }

            message_text = await format_day_schedule(
                tomorrow_schedule,
                telegram_id,
            )

            await bot.send_message(
                chat_id=telegram_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=build_delete_button(),
            )

            await update_user(
                telegram_id,
                notification_last_sent=current_date,
            )

            log(
                "notifications",
                f"Оповещение отправлено "
                f"(scheduled={user['notification_time']})",
                telegram_id,
            )

        except Exception as e:
            log(
                "notifications",
                f"Ошибка отправки: "
                f"{type(e).__name__}: {e}",
                telegram_id,
            )
