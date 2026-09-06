from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import  FSMContext

router = Router()

async def show_main_menu(message: Message, user, state: FSMContext):
	await message.answer(
		"С возвращением!"
		f"твоя группа: {user['group_name']}"
	)