import asyncio
from datetime import datetime, date, timedelta

from aiogram import Bot

from console_log import log
from database import get_users_for_notification, update_user
from ulstu.schedule import (
    get_schedule,
    get_schedule_for_date, format_day_schedule,
)
from utils import build_delete_button


async def notification_worker(bot: Bot):
    log("notifications", "Воркер уведомлений стартовал")

    while True:
        now = datetime.now().astimezone()

        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")

        users = await get_users_for_notification(
            current_time,
            current_date,
        )

        for user in users:
            try:
                await send_tomorrow_schedule(bot, user)

                await update_user(
                    user["telegram_id"],
                    notification_last_sent=current_date,
                )

                log(
                    "notifications",
                    f"Оповещение отправлено "
                    f"(scheduled={user['notification_time']})",
                    user["telegram_id"],
                )
                await asyncio.sleep(0.5)

            except Exception as e:
                log(
                    "notifications",
                    f"Ошибка отправки: "
                    f"{type(e).__name__}: {e}",
                    user["telegram_id"],
                )

        delay = 60 - now.second - now.microsecond / 1_000_000

        await asyncio.sleep(delay)


async def send_tomorrow_schedule(bot: Bot, user: dict):
    telegram_id = user["telegram_id"]
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

    message = await bot.send_message(
        chat_id=telegram_id,
        text=message_text,
        parse_mode="HTML",
    )
    await bot.edit_message_text(
        chat_id=telegram_id,
        message_id=message.message_id,
        text=message_text,
        parse_mode="HTML",
        reply_markup=await build_delete_button(message)
    )
    log("notifications", "Уведомление отправлено", telegram_id)
