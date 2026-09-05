import asyncio
from datetime import datetime, date, timedelta

from aiogram import Bot

from console_log import log
from database import get_users_for_notification
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

        users = await get_users_for_notification(current_time)

        if users:
            log(
                "notifications",
                f"На {current_time} найдено "
                f"получателей: {len(users)}",
            )

        for user in users:
            try:
                await send_tomorrow_schedule(bot, user)
            except Exception as e:
                log(
                    "notifications",
                    f"Ошибка отправки: {e}",
                    user["telegram_id"],
                )

        now = datetime.now().astimezone()

        # Сколько осталось до начала следующей минуты
        delay = 60 - now.second - (now.microsecond+100) / 1_000_000

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
