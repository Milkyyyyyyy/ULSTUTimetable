from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import  FSMContext
from aiogram.filters import StateFilter

from database import get_user, update_user
from encryption.encryption import encrypt_password
from states.states import MainMenu, Settings
from utils import delete_after
from validator.group import is_group_valid

router = Router()

main_menu_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
	    [
		    InlineKeyboardButton(
			    text="⚙ Настройки",
			    callback_data="open_settings",
				style="primary"
		    )
		]
    ]
)
async def show_main_menu(message: Message, state: FSMContext, edit_previous_message: bool = False):
	await state.clear()
	await state.set_state(MainMenu.main_menu)

	message_text = "С возвращением!\n"
	if edit_previous_message:
		await message.edit_text(
			message_text,
			reply_markup=main_menu_keyboard
		)
	else:
		await message.answer(
			message_text,
			reply_markup=main_menu_keyboard
		)



async def get_settings_keyboard(has_changes: bool) -> InlineKeyboardMarkup:
	buttons = [
		[
			InlineKeyboardButton(
				text="👤 Изменить логин",
				callback_data="settings:login",
				style="success"
			),
			InlineKeyboardButton(
				text="🔒 Изменить пароль",
				callback_data="settings:password",
				style="success"
			)
		],
		[
			InlineKeyboardButton(
				text="🏫 Изменить факультет",
				callback_data="settings:facult",
				style="success"
			),
			InlineKeyboardButton(
				text="👥 Изменить группу",
				callback_data="settings:group",
				style="success"
			)
		],
		[
			InlineKeyboardButton(
				text="🔢 Изменить подгруппу",
				callback_data="settings:subgroup",
				style="success"
			)
		],
	]

	if has_changes:
		buttons.append([
			InlineKeyboardButton(
				text="✅ Применить изменения",
				callback_data="settings:apply",
				style="success"
			),
			InlineKeyboardButton(
				text="❌ Отменить изменения",
				callback_data="settings:cancel",
				style="danger"
			),
		])
	else:
		buttons.append([
			InlineKeyboardButton(
				text="◀ Назад",
				callback_data="back_to_menu",
				style="primary"
			)
		])

	return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(
	MainMenu.main_menu,
	F.data == "open_settings"
)
async def settings_handler(callback: CallbackQuery, state: FSMContext, first_open: bool = True):
	await state.set_state(Settings.settings)
	user = await get_user(callback.from_user.id)
	if first_open:
		await state.update_data(
			ulstu_login=user["ulstu_login"],
			ulstu_password_encrypted=user['ulstu_password_encrypted'],
			schedule_part=user['schedule_part'],
			group_name=user['group_name'],
			subgroup=user['subgroup'],
			has_changes=False
		)

	await callback.answer()

	data = await state.get_data()
	await callback.message.edit_text(
		"Выберите нужную опцию.",
			reply_markup=await get_settings_keyboard(data['has_changes'])
	)

@router.callback_query(
	Settings.settings,
	F.data == "back_to_menu"
)
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
	await show_main_menu(callback.message, state, edit_previous_message=True)

back_to_settings_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
	    [
		    InlineKeyboardButton(
			    text="◀  Назад к настройкам",
			    callback_data="back_to_settings",
				style="primary"
		    )
		]
    ]
)
@router.callback_query(
	StateFilter(Settings),
	F.data == "back_to_settings"
)
async def back_to_settings(callback: CallbackQuery, state: FSMContext):
	await settings_handler(callback, state, first_open=False)


@router.callback_query(
	Settings.settings,
	F.data == "settings:login"
)
async def login_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_login)

	await callback.answer()

	await callback.message.edit_text(
		"Введите новый логин:",
		reply_markup=back_to_settings_keyboard
	)
	await state.update_data(last_callback = callback)

@router.message(Settings.waiting_for_login)
async def login_handler(message: Message, state: FSMContext):
	login = message.text
	await state.update_data(ulstu_login=login, has_changes=True)
	await message.delete()
	data = await state.get_data()
	await back_to_settings(data['last_callback'], state)

@router.callback_query(
	Settings.settings,
	F.data == "settings:password"
)
async def password_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_password)

	await callback.answer()

	await callback.message.edit_text(
		"Введите новый пароль:",
		reply_markup=back_to_settings_keyboard
	)
	await state.update_data(last_callback = callback)

@router.message(Settings.waiting_for_password)
async def password_handler(message: Message, state: FSMContext):
	password = encrypt_password(message.text)

	await state.update_data(ulstu_password_encrypted=password, has_changes=True)
	await message.delete()

	data = await state.get_data()
	await back_to_settings(data['last_callback'], state)

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
@router.callback_query(
	Settings.settings,
	F.data == "settings:facult"
)
async def schedule_part_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_facult)

	await callback.answer()

	await callback.message.edit_text(
		"Выберите нужный факультет",
		reply_markup=schedule_parts_keyboard
	)
	await state.update_data(last_callback = callback)

@router.callback_query(
	Settings.waiting_for_facult,
	F.data.startswith("schedule_part:")
)
async def schedule_part_handler(callback: CallbackQuery, state: FSMContext):
	part = int(callback.data.split(":")[1])
	await state.update_data(schedule_part=part, has_changes=True)

	data = await state.get_data()
	await back_to_settings(callback, state)


@router.callback_query(
	Settings.settings,
	F.data == "settings:group"
)
async def group_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_group)

	await callback.answer()

	await callback.message.edit_text(
		"Введите новую группу:",
		reply_markup=back_to_settings_keyboard
	)
	await state.update_data(last_callback=callback)


@router.message(Settings.waiting_for_group)
async def group_handler(message: Message, state: FSMContext):
	group_name = message.text
	if not is_group_valid(group_name):
		sent_message = await message.answer(
			"<b>Неверный формат группы</b>\n"
			"Попробуйте ещё раз.",
			parse_mode="HTML"
		)
		await delete_after([sent_message, message], 2)
		return


	await state.update_data(group_name=group_name, has_changes=True)
	await message.delete()

	data = await state.get_data()
	await back_to_settings(data['last_callback'], state)

subgroup_keyboard = InlineKeyboardMarkup(
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
@router.callback_query(
	Settings.settings,
	F.data == "settings:subgroup"
)
async def subgroup_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_subgroup)

	await callback.answer()

	await callback.message.edit_text(
		"Выберите подгруппу:",
		reply_markup=subgroup_keyboard
	)
	await state.update_data(last_callback=callback)


@router.callback_query(
	Settings.waiting_for_subgroup,
	F.data.startswith("subgroup:")
)
async def subgroup_handler(callback: CallbackQuery, state: FSMContext):
	subgroup = callback.data.split(":")[1]
	if subgroup == "skip":
		subgroup = None
	else:
		subgroup = int(subgroup)

	await state.update_data(
		subgroup=subgroup,
		has_changes=True
	)

	data = await state.get_data()
	await back_to_settings(data['last_callback'], state)

# СОХРАНЕНИЕ/ОТМЕНА
@router.callback_query(
	Settings.settings,
	F.data == "settings:apply"
)
async def save_changes(callback: CallbackQuery, state: FSMContext):
	sent_message = await callback.message.answer(
		"Сохраняю изменения.."
	)

	data = await state.get_data()
	await update_user(
		telegram_id=callback.from_user.id,
		ulstu_login=data["ulstu_login"],
		schedule_part=data["schedule_part"],
		group_name=data["group_name"],
		subgroup=data["subgroup"],
		ulstu_password_encrypted=data["ulstu_password_encrypted"]
	)
	await callback.answer()
	await delete_after(sent_message, 1)

	await show_main_menu(callback.message, state, True)
@router.callback_query(
	Settings.settings,
	F.data == "settings:cancel"
)
async def cancel_changes(callback: CallbackQuery, state: FSMContext):
	await state.clear()
	await show_main_menu(callback.message, state, True)
