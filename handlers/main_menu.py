from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import  FSMContext

router = Router()

async def show_main_menu(message: Message, state: FSMContext):
	await message.answer(
		"С возвращением!\n"
	)