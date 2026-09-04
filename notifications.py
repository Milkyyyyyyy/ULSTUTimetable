import asyncio
from datetime import datetime, date, timedelta

from aiogram import Bot

from database import get_users_for_notification
from ulstu.schedule import (
	get_schedule,
	get_schedule_for_date, format_day_schedule,
)
from utils import build_delete_button


async def notification_worker(bot: Bot):
	last_time_key = None
	sent_notifications = set()

	while True:
		now = datetime.now().astimezone()
		current_time = now.strftime("%H:%M")
		current_time_key = now.strftime("%Y-%m-%d %H:%M")

		if current_time_key != last_time_key:
			sent_notifications.clear()
			last_time_key = current_time_key

		users = await get_users_for_notification(current_time)

		for user in users:
			notification_key = (
				user["telegram_id"],
				current_time_key,
			)

			if notification_key in sent_notifications:
				continue

			try:
				await send_tomorrow_schedule(bot, user)
				sent_notifications.add(notification_key)
			except Exception as e:
				print(
					f"Ошибка отправки уведомления "
					f"пользователю {user['telegram_id']}: {e}"
				)

		await asyncio.sleep(50)


async def send_tomorrow_schedule(bot: Bot, user: dict):
	telegram_id = user["telegram_id"]

	schedule = await get_schedule(telegram_id)

	if not schedule:
		return

	tomorrow = date.today() + timedelta(days=1)

	tomorrow_schedule = get_schedule_for_date(
		schedule,
		tomorrow,
	)

	# Если завтра нет в расписании — создаём пустой день
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
