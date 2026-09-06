import os
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from handlers.registration import router as registration_router, start_registration
from handlers.main_menu import router as main_menu_router, show_main_menu

from database import init_db, get_user


load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
	raise ValueError("Не найден BOT_TOKEN в .env")

dp = Dispatcher()

dp.include_router(registration_router)
dp.include_router(main_menu_router)

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
	await message.reply(
		"Привет!\n"
		"Я бот расписания УлГТУ"
	)

	user = await get_user(message.from_user.id)
	if user is None:
		await start_registration(message, state)
	else:
		await show_main_menu(message, user, state)



async def main():
	await init_db()
	session = AiohttpSession(
		proxy="socks5://127.0.0.1:2080"
	)

	bot = Bot(
		token=BOT_TOKEN,
		session=session
	)

	print("Бот запускается...")

	await dp.start_polling(bot)

if __name__ == '__main__':
	asyncio.run(main())