import asyncio
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Optional

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import get_user, update_user
from encryption.encryption import encrypt_password
from handlers.main_menu import show_main_menu
from states.states import MainMenu, Settings
from utils import delete_after
from utils import safe_edit_text, safe_bot_edit_text
from validator.group import is_group_valid

router = Router()

# --- #7: работаем только в приватных чатах -------------------------------
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

# --- #6: лок на пользователя, чтобы не было гонок при двойных кликах -----
_user_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

# --- #7: работаем только в приватных чатах -------------------------------
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

# --- #6: лок на пользователя, чтобы не было гонок при двойных кликах -----
_user_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def user_lock(telegram_id: int) -> asyncio.Lock:
	return _user_locks[telegram_id]


async def safe_get_user(telegram_id: int) -> Optional[dict]:
	try:
		return await get_user(telegram_id)
	except Exception:
		return None


async def safe_update_user(**kwargs) -> bool:
	try:
		await update_user(**kwargs)
		return True
	except Exception:
		return False


# --- #8: типизированные данные состояния вместо голого dict --------------
@dataclass
class SettingsData:
	ulstu_login: str = ""
	ulstu_password_encrypted: str = ""
	schedule_part: Optional[int] = None
	group_name: str = ""
	subgroup: Optional[int] = None
	has_changes: bool = False
	settings_chat_id: Optional[int] = None
	settings_message_id: Optional[int] = None

	def to_dict(self) -> dict:
		return asdict(self)

	@classmethod
	def from_dict(cls, data: dict) -> "SettingsData":
		known_fields = {f for f in cls.__dataclass_fields__}
		return cls(**{k: v for k, v in data.items() if k in known_fields})


async def get_settings_data(state: FSMContext) -> SettingsData:
	return SettingsData.from_dict(await state.get_data())


async def save_settings_data(state: FSMContext, data: SettingsData) -> None:
	await state.update_data(**data.to_dict())


# --- validation helpers (#4) ----------------------------------------------
MAX_LOGIN_LENGTH = 64
MAX_PASSWORD_LENGTH = 128


def is_login_valid(login: Optional[str]) -> bool:
	if not login or not login.strip():
		return False
	login = login.strip()
	if len(login) > MAX_LOGIN_LENGTH:
		return False
	if "\n" in login:
		return False
	return True


def is_password_valid(password: Optional[str]) -> bool:
	if not password or not password.strip():
		return False
	if len(password) > MAX_PASSWORD_LENGTH:
		return False
	return True


async def notify_invalid_input(message: Message, text: str) -> None:
	sent_message = await message.answer(f"<b>{text}</b>\nПопробуйте ещё раз.", parse_mode="HTML")
	await delete_after([sent_message, message], 2)


async def get_settings_keyboard(has_changes: bool) -> InlineKeyboardMarkup:
	buttons = [
		[
			InlineKeyboardButton(text="👤 Изменить логин", callback_data="settings:login", style="success"),
			InlineKeyboardButton(text="🔒 Изменить пароль", callback_data="settings:password", style="success"),
		],
		[
			InlineKeyboardButton(text="🏫 Изменить факультет", callback_data="settings:facult", style="success"),
			InlineKeyboardButton(text="👥 Изменить группу", callback_data="settings:group", style="success"),
		],
		[
			InlineKeyboardButton(text="🔢 Изменить подгруппу", callback_data="settings:subgroup", style="success"),
		],
	]

	if has_changes:
		buttons.append([
			InlineKeyboardButton(text="✅ Применить изменения", callback_data="settings:apply", style="success"),
			InlineKeyboardButton(text="❌ Отменить изменения", callback_data="settings:cancel", style="danger"),
		])
	else:
		buttons.append([
			InlineKeyboardButton(text="◀ Назад", callback_data="back_to_menu", style="primary"),
		])

	return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Общая логика рендеринга меню настроек --------------------------------
# Вынесена отдельно, чтобы её можно было звать как ИЗ-ПОД лока (после
# изменения конкретной настройки), так и напрямую по кнопке "Назад к
# настройкам", не рискуя повторным (реентерантным) захватом user_lock,
# который приводит к дедлоку.

async def _load_or_get_settings_data(callback: CallbackQuery, state: FSMContext, first_open: bool) -> Optional[
	SettingsData]:
	if first_open:
		user = await safe_get_user(callback.from_user.id)
		if user is None:
			await callback.answer("Не удалось загрузить ваши данные. Попробуйте позже.", show_alert=True)
			return None

		data = SettingsData(
			ulstu_login=user["ulstu_login"],
			ulstu_password_encrypted=user["ulstu_password_encrypted"],
			schedule_part=user["schedule_part"],
			group_name=user["group_name"],
			subgroup=user["subgroup"],
			has_changes=False,
			settings_chat_id=callback.message.chat.id,
			settings_message_id=callback.message.message_id,
		)
		await save_settings_data(state, data)
		return data

	return await get_settings_data(state)


async def render_settings_menu(callback: CallbackQuery, state: FSMContext, data: SettingsData) -> None:
	"""Рендерит меню настроек по уже готовым data. НЕ берёт user_lock —
	вызывающий код должен либо уже держать лок, либо не нуждаться в нём."""
	await callback.answer()
	await safe_edit_text(
		callback.message,
		"Выберите нужную опцию.",
		await get_settings_keyboard(data.has_changes),
	)


@router.callback_query(MainMenu.main_menu, F.data == "open_settings")
async def settings_handler(callback: CallbackQuery, state: FSMContext, first_open: bool = True):
	async with user_lock(callback.from_user.id):
		await state.set_state(Settings.settings)

		data = await _load_or_get_settings_data(callback, state, first_open)
		if data is None:
			return

		await render_settings_menu(callback, state, data)


back_to_settings_keyboard = InlineKeyboardMarkup(
	inline_keyboard=[
		[
			InlineKeyboardButton(text="◀  Назад к настройкам", callback_data="back_to_settings", style="primary"),
		]
	]
)


@router.callback_query(StateFilter(Settings), F.data == "back_to_settings")
async def back_to_settings(callback: CallbackQuery, state: FSMContext):
	# Сюда попадаем напрямую по клику пользователя — лок ещё не захвачен,
	# поэтому settings_handler может безопасно взять его сам.
	await settings_handler(callback, state, first_open=False)


async def render_settings_after_message(bot, state: FSMContext, data: SettingsData) -> None:
	"""Обновляет исходное сообщение настроек после ввода текста (#2)."""
	if data.settings_chat_id is None or data.settings_message_id is None:
		return
	await safe_bot_edit_text(
		bot,
		data.settings_chat_id,
		data.settings_message_id,
		"Выберите нужную опцию.",
		await get_settings_keyboard(data.has_changes),
	)


@router.callback_query(Settings.settings, F.data == "settings:login")
async def login_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_login)
	await callback.answer()
	await safe_edit_text(callback.message, "Введите новый логин:", back_to_settings_keyboard)


@router.message(Settings.waiting_for_login)
async def login_handler(message: Message, state: FSMContext):
	login = message.text

	if not is_login_valid(login):
		await notify_invalid_input(message, "Неверный формат логина")
		return

	async with user_lock(message.from_user.id):
		data = await get_settings_data(state)
		data.ulstu_login = login.strip()
		data.has_changes = True
		await save_settings_data(state, data)

		await message.delete()
		await state.set_state(Settings.settings)
		await render_settings_after_message(message.bot, state, data)


@router.callback_query(Settings.settings, F.data == "settings:password")
async def password_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_password)
	await callback.answer()
	await safe_edit_text(callback.message, "Введите новый пароль:", back_to_settings_keyboard)


@router.message(Settings.waiting_for_password)
async def password_handler(message: Message, state: FSMContext):
	raw_password = message.text

	if not is_password_valid(raw_password):
		await notify_invalid_input(message, "Неверный формат пароля")
		return

	async with user_lock(message.from_user.id):
		password = encrypt_password(raw_password)

		data = await get_settings_data(state)
		data.ulstu_password_encrypted = password
		data.has_changes = True
		await save_settings_data(state, data)

		await message.delete()
		await state.set_state(Settings.settings)
		await render_settings_after_message(message.bot, state, data)


schedule_parts_keyboard = InlineKeyboardMarkup(
	inline_keyboard=[
		[
			InlineKeyboardButton(text="МФ, РТФ, ЭФ, ИФМИ", callback_data="schedule_part:1", style="success"),
			InlineKeyboardButton(text="ФИСТ, ГФ", callback_data="schedule_part:2", style="success"),
		],
		[
			InlineKeyboardButton(text="ИАТУ, ИЭФ, ЗВФ ИННО", callback_data="schedule_part:3", style="success"),
			InlineKeyboardButton(text="КЭИ", callback_data="schedule_part:4", style="success"),
		],
		[
			InlineKeyboardButton(text="СФ", callback_data="schedule_part:5", style="success"),
		],
	]
)


@router.callback_query(Settings.settings, F.data == "settings:facult")
async def schedule_part_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_facult)
	await callback.answer()
	await safe_edit_text(callback.message, "Выберите нужный факультет", schedule_parts_keyboard)


@router.callback_query(Settings.waiting_for_facult, F.data.startswith("schedule_part:"))
async def schedule_part_handler(callback: CallbackQuery, state: FSMContext):
	async with user_lock(callback.from_user.id):
		part = int(callback.data.split(":")[1])

		data = await get_settings_data(state)
		data.schedule_part = part
		data.has_changes = True
		await save_settings_data(state, data)

		await state.set_state(Settings.settings)
		# ВАЖНО: не вызываем back_to_settings/settings_handler здесь —
		# это привело бы к повторному захвату user_lock и дедлоку,
		# т.к. лок уже держится этим же таском.
		await render_settings_menu(callback, state, data)


@router.callback_query(Settings.settings, F.data == "settings:group")
async def group_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_group)
	await callback.answer()
	await safe_edit_text(callback.message, "Введите новую группу:", back_to_settings_keyboard)


@router.message(Settings.waiting_for_group)
async def group_handler(message: Message, state: FSMContext):
	group_name = message.text
	if not is_group_valid(group_name):
		await notify_invalid_input(message, "Неверный формат группы")
		return

	async with user_lock(message.from_user.id):
		data = await get_settings_data(state)
		data.group_name = group_name
		data.has_changes = True
		await save_settings_data(state, data)

		await message.delete()
		await state.set_state(Settings.settings)
		await render_settings_after_message(message.bot, state, data)


subgroup_keyboard = InlineKeyboardMarkup(
	inline_keyboard=[
		[
			InlineKeyboardButton(text="1 подгруппа", callback_data="subgroup:1", style="primary"),
			InlineKeyboardButton(text="2 подгруппа", callback_data="subgroup:2", style="primary"),
		],
		[
			InlineKeyboardButton(text="Выкл. фильтр подгрупп", callback_data="subgroup:skip", style="danger"),
		],
	]
)


@router.callback_query(Settings.settings, F.data == "settings:subgroup")
async def subgroup_button_handler(callback: CallbackQuery, state: FSMContext):
	await state.set_state(Settings.waiting_for_subgroup)
	await callback.answer()
	await safe_edit_text(callback.message, "Выберите подгруппу:", subgroup_keyboard)


@router.callback_query(Settings.waiting_for_subgroup, F.data.startswith("subgroup:"))
async def subgroup_handler(callback: CallbackQuery, state: FSMContext):
	async with user_lock(callback.from_user.id):
		raw_subgroup = callback.data.split(":")[1]
		subgroup = None if raw_subgroup == "skip" else int(raw_subgroup)

		data = await get_settings_data(state)
		data.subgroup = subgroup
		data.has_changes = True
		await save_settings_data(state, data)

		await state.set_state(Settings.settings)
		# Аналогично schedule_part_handler — избегаем повторного лока.
		await render_settings_menu(callback, state, data)


# --- СОХРАНЕНИЕ/ОТМЕНА -----------------------------------------------------

@router.callback_query(Settings.settings, F.data == "settings:apply")
async def save_changes(callback: CallbackQuery, state: FSMContext):
	async with user_lock(callback.from_user.id):
		sent_message = await callback.message.answer("Сохраняю изменения..")
		data = await get_settings_data(state)

		success = await safe_update_user(
			telegram_id=callback.from_user.id,
			ulstu_login=data.ulstu_login,
			schedule_part=data.schedule_part,
			group_name=data.group_name,
			subgroup=data.subgroup,
			ulstu_password_encrypted=data.ulstu_password_encrypted,
		)

		await callback.answer()

		if not success:
			await sent_message.edit_text(
				"Не удалось сохранить изменения. Попробуйте ещё раз позже."
			)
			await delete_after(sent_message, 8)
			return

		await delete_after(sent_message, 3)
		await show_main_menu(callback.message, state, True)


@router.callback_query(Settings.settings, F.data == "settings:cancel")
async def cancel_changes(callback: CallbackQuery, state: FSMContext):
	async with user_lock(callback.from_user.id):
		await state.clear()
		await show_main_menu(callback.message, state, True)
