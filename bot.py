import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from dotenv import load_dotenv

from database import init_db, get_user, get_registered_users
from handlers.main_menu import router as main_menu_router, show_main_menu
from handlers.registration import router as registration_router, start_registration
from handlers.settings import router as settings_router
from notifications import notification_worker
from states.states import MainMenu
from utils import router as utils_router

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_PROXY = os.getenv("BOT_PROXY")
if not BOT_TOKEN:
	raise ValueError("Не найден BOT_TOKEN в .env")

dp = Dispatcher()

dp.include_router(registration_router)
dp.include_router(main_menu_router)
dp.include_router(settings_router)
dp.include_router(utils_router)


async def restore_main_menu_states(
		dp: Dispatcher,
		bot: Bot
):
	users = await get_registered_users()

	for user in users:
		telegram_id = user["telegram_id"]

		context = dp.fsm.get_context(
			bot=bot,
			chat_id=telegram_id,
			user_id=telegram_id,
		)

		await context.set_state(MainMenu.main_menu)


@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
	user = await get_user(message.from_user.id)
	if user is None:
		await start_registration(message, state)
	else:
		await show_main_menu(message, state)


async def main():
	await init_db()
	session = AiohttpSession(proxy=BOT_PROXY) if BOT_PROXY else AiohttpSession()

	bot = Bot(
		token=BOT_TOKEN,
		session=session
	)

	print("Бот запускается...")
	await restore_main_menu_states(dp, bot)

	notification_task = asyncio.create_task(
		notification_worker(bot)
	)
	try:
		await dp.start_polling(bot)
	finally:
		notification_task.cancel()

		try:
			await notification_task
		except asyncio.CancelledError:
			pass

		await bot.session.close()


if __name__ == '__main__':
	asyncio.run(main())
