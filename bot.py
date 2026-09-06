import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from dotenv import load_dotenv

from console_log import log
from console_worker import console_worker
from database import init_db, get_user, get_registered_users
from fsm_manager import restore_main_menu_states
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


@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    await message.delete()

    if user is None:
        log("bot", "Команда /start — новый пользователь, старт регистрации", user_id)
        await start_registration(message, state)
    else:
        log("bot", "Команда /start — открытие главного меню", user_id)
        await show_main_menu(message, state)


async def main():
    log("bot", "ЗАПУСК БОТА")
    log("bot", "Инициализация базы данных...")
    await init_db()
    log("bot", "База данных готова")

    session = AiohttpSession(proxy=BOT_PROXY) if BOT_PROXY else AiohttpSession()

    bot = Bot(
        token=BOT_TOKEN,
        session=session
    )

    if BOT_PROXY:
        log("bot", f"Используется прокси: {BOT_PROXY}")

    log("bot", "Бот запускается...")
    await restore_main_menu_states(dp, bot)

    notification_task = asyncio.create_task(
        notification_worker(bot)
    )
    log("bot", "Воркер уведомлений запущен")

    try:
        log("bot", "Polling запущен")

        await asyncio.gather(
            dp.start_polling(bot),
            console_worker(
                dp,
                bot
            ),
        )

    finally:
        await stop_bot(
            bot,
            notification_task,
        )


async def stop_bot(
    bot,
    notification_task,
):
    log("bot", "Остановка бота...")

    if notification_task is not None and not notification_task.done():
        notification_task.cancel()

        try:
            await notification_task
        except asyncio.CancelledError:
            pass


    await bot.session.close()

    log("bot", "Бот остановлен")

if __name__ == '__main__':
    asyncio.run(main())
