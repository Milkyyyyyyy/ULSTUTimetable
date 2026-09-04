from random import setstate

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import  FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import CallbackQuery

from database import create_user
from encryption.encryption import encrypt_password
from handlers.main_menu import show_main_menu
from states.states import Registration
from utils import delete_after
from validator.group import is_group_valid

router = Router()

async def start_registration(message: Message, state: FSMContext):
	await state.update_data(telegram_id=message.from_user.id)
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


schedule_parts_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="МФ, РТФ, ЭФ, ИФМИ",
                callback_data="schedule_part:1",
	            style="success"
            ),
            InlineKeyboardButton(
                text="ФИСТ, ГФ",
                callback_data="schedule_part:2",
				style="success"
            )
		],
	    [
            InlineKeyboardButton(
                text="ИАТУ, ИЭФ, ЗВФ ИННО",
                callback_data="schedule_part:3",
				style="success"
            ),

            InlineKeyboardButton(
                text="КЭИ",
                callback_data="schedule_part:4",
				style="success"
            )
        ],
        [
            InlineKeyboardButton(
                text="СФ",
                callback_data="schedule_part:5",
				style="success"
            )
        ],
    ]
)
@router.message(Registration.waiting_for_password)
async def password_handler(message: Message, state: FSMContext):
	password = encrypt_password(message.text)
	await message.delete()

	await state.update_data(password=password)
	await message.answer(
		"<b>Выберите ваш факультет/часть расписания:</b>",
		parse_mode="HTML",
		reply_markup=schedule_parts_keyboard
	)

	await state.set_state(Registration.waiting_for_facult)

@router.callback_query(
	Registration.waiting_for_facult,
	F.data.startswith("schedule_part:")
)
async def facult_handler(callback: CallbackQuery, state: FSMContext):
	part = int(callback.data.split(":")[1])

	await state.update_data(schedule_part=part)

	await callback.message.edit_text(
		"<b>Введите название вашей группы:</b>\n"
		"Например: <code>ПИбд-11</code>",
		parse_mode="HTML"
	)
	await state.set_state(Registration.waiting_for_group)
	await callback.answer()


skip_subgroup_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
	    [
		    InlineKeyboardButton(
			    text="1 подгруппа",
			    callback_data="subgroup:1",
				style="primary"
		    ),
				InlineKeyboardButton(
			    text="2 подгруппа",
			    callback_data="subgroup:2",
				style="primary"
		    )
	    ],
        [
            InlineKeyboardButton(
                text="Пропустить",
                callback_data="subgroup:skip",
	            style="danger"
            )
        ]
    ]
)

@router.message(Registration.waiting_for_group)
async def group_handler(message: Message, state: FSMContext):
	group = message.text
	if not is_group_valid(group):
		sent_message = await message.answer(
			"<b>Неверный формат группы</b>\n"
			"Попробуйте ещё раз.",
			parse_mode="HTML"
		)
		await delete_after([sent_message, message], 5)
		return
	await state.update_data(group=group)

	await message.answer(
		"<b>Выберите вашу подгруппу</b>\n"
		"Если фильтр по подгруппе вам не нужен, нажмите \"Пропустить\"",
		parse_mode="HTML",
		reply_markup=skip_subgroup_keyboard
	)
	await state.set_state(Registration.waiting_for_subgroup)

@router.callback_query(
	Registration.waiting_for_subgroup,
	F.data.startswith("subgroup:")
)
async def subgroup_handler(callback: CallbackQuery, state: FSMContext):
	subgroup = callback.data.split(":")[1]
	if subgroup == "skip":
		await state.update_data(subgroup=None)
	else:
		await state.update_data(subgroup=int(subgroup))

	previous_message = await callback.message.edit_text(
		"Отлично!\n"
		"Регестрирую...",
		parse_mode="HTML"
	)

	data = await state.get_data()
	await create_user(
		telegram_id=data['telegram_id'],
		ulstu_login=data['login'],
		ulstu_password_encrypted=data['password'],
		schedule_part=data['schedule_part'],
		group_name=data['group'],
		subgroup=data['subgroup'],
		notification_time=""
	)

	await callback.answer(
		"Успешно!"
	)
	await delete_after(previous_message, 2)

	await show_main_menu(previous_message, state)
