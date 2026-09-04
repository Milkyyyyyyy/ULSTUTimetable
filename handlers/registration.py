from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import  FSMContext

from encryption.encryption import encrypt_password
from states.states import Registration

router = Router()

async def start_registration(message: Message, state: FSMContext):
	await message.answer(
		"Ты ещё незарегестрирован.\n"
		"Давай настроим бота.\n\n"
		"<b>Введи логин на сайте УлГТУ:</b>",
		parse_mode="HTML"
	)

	await state.set_state(Registration.waiting_for_login)

@router.message(Registration.waiting_for_login)
async def login_handler(message: Message, state: FSMContext):
	login = message.text

	await state.update_data(login=login)
	await message.answer(
		"Отлично!\n"
		"<b>Теперь введите пароль от сайта УлГТУ:</b>\n\n"
		"<blockquote>"
		"🔒 <b>Ваш пароль перед сохранением шифруется и не хранится в открытом виде.</b>"
		"</blockquote>",
		parse_mode="HTML"
	)

	await state.set_state(Registration.waiting_for_password)

@router.message(Registration.waiting_for_password)
async def password_handler(message: Message, state: FSMContext):
	password = encrypt_password(message.text)

	await state.update_data(password=password)
	await message.answer(
		"<b>Введите вашу подгруппу:</b>",
		parse_mode="HTML"
	)

	await state.set_state(Registration.waiting_for_group)

@router.message(Registration.waiting_for_group)
async def group_handler(message: Message, state: FSMContext):
	group = message.text

	await state.update_data(group=group)
