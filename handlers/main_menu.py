import random
from datetime import date, timedelta, datetime

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.types import (
	Message,
	InlineKeyboardMarkup,
	InlineKeyboardButton,
	CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_user, update_user
from states.states import MainMenu, ScheduleSelection, NotificationSettings
from ulstu.schedule import get_schedule_for_date, get_schedule, send_schedule
from ulstu.schedule_image import generate_week_schedule_image
from utils import safe_edit_text, build_delete_button, delete_after

router = Router()

WELCOME_MESSAGES = [
	"С возвращением!",
	"Добро пожаловать обратно!",
	"Рад снова тебя видеть.",
	"Что сегодня по расписанию?",
	"Проверим расписание?",
	"Готово. Можно посмотреть расписание.",
	"Расписание готово.",
	"Можно начинать.",
	"Что тебя ждёт сегодня?",
	"Посмотрим, что запланировано.",
	"Всё готово к работе.",
	"Добро пожаловать!",
	"Хорошего дня!",
	"Давай посмотрим расписание.",
	"Расписание на месте.",
]


async def build_main_menu_buttons(
		telegram_id: int,
) -> InlineKeyboardMarkup:

	user = await get_user(telegram_id)

	buttons = []

	# --------------------------------------------------
	# Автоматическое оповещение
	# --------------------------------------------------

	if user["notification_enabled"] == 1:
		buttons.append([
			InlineKeyboardButton(
				text="🔔 Автооповещение: ВКЛ",
				callback_data="notification_settings:open",
				style="primary",
			)
		])

	else:
		buttons.append([
			InlineKeyboardButton(
				text="🔔 Автооповещение: ВЫКЛ",
				callback_data="notification_settings:open",
			)
		])

	# --------------------------------------------------
	# Расписание на сегодня / завтра
	# --------------------------------------------------

	buttons.append([
		InlineKeyboardButton(
			text="🗓 Сегодня",
			callback_data="schedule:today",
			style="success",
		),
		InlineKeyboardButton(
			text="🗓 Завтра",
			callback_data="schedule:tomorrow",
			style="success",
		),
	])

	# --------------------------------------------------
	# Расписание на неделю
	# --------------------------------------------------

	buttons.append([
		InlineKeyboardButton(
			text="На неделю",
			callback_data="schedule_week:this",
			style="success",
		),
		InlineKeyboardButton(
			text="На следующую неделю",
			callback_data="schedule_week:next",
			style="success",
		),
	])

	# --------------------------------------------------
	# Расписание на конкретную дату
	# --------------------------------------------------

	buttons.append([
		InlineKeyboardButton(
			text="📅 Расписание на дату",
			callback_data="schedule:select",
			style="success",
		),
	])

	# --------------------------------------------------
	# Настройки
	# --------------------------------------------------

	buttons.append([
		InlineKeyboardButton(
			text="⚙ Настройки",
			callback_data="open_settings",
			style="primary",
		)
	])

	return InlineKeyboardMarkup(
		inline_keyboard=buttons
	)


async def show_main_menu(
		message: Message,
		state: FSMContext,
		edit_previous_message: bool = False,
):
	await state.clear()
	await state.set_state(MainMenu.main_menu)

	message_text = random.choice(WELCOME_MESSAGES)

	if edit_previous_message:
		await safe_edit_text(
			message,
			message_text,
			await build_main_menu_buttons(message.chat.id),
		)
	else:
		await message.answer(
			message_text,
			reply_markup=await build_main_menu_buttons(message.chat.id),
		)


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
	await show_main_menu(callback.message, state, edit_previous_message=True)


# ---------------------------------------------------------------------------
# Клавиатура выбора недели и дня
# ---------------------------------------------------------------------------

def build_schedule_keyboard(
		schedule: list[dict],
		week_index: int,
) -> InlineKeyboardMarkup:
	"""
	Создаёт клавиатуру для выбора дня.
	"""

	builder = InlineKeyboardBuilder()

	# Защита от некорректного индекса
	if not schedule:
		return builder.as_markup()

	if week_index < 0:
		week_index = 0

	if week_index >= len(schedule):
		week_index = len(schedule) - 1

	week = schedule[week_index]
	days = week.get("days", [])

	# --------------------------------------------------
	# Кнопки дней
	# --------------------------------------------------

	for row_index in range(3):
		left_index = row_index
		right_index = row_index + 3

		builder.row(
			InlineKeyboardButton(
				text=days[left_index]["day"],
				callback_data=f"schedule_day:{week_index}:{left_index}",
			),
			InlineKeyboardButton(
				text=days[right_index]["day"],
				callback_data=f"schedule_day:{week_index}:{right_index}",
			),
		)

	# Воскресенье отдельно
	if len(days) > 6:
		day = days[6]

		builder.row(
			InlineKeyboardButton(
				text=day["day"],
				callback_data=f"schedule_day:{week_index}:6",
			)
		)

	# --------------------------------------------------
	# Навигация по неделям
	# --------------------------------------------------

	navigation_buttons = []

	if week_index > 0:
		navigation_buttons.append(
			InlineKeyboardButton(
				text="←",
				callback_data=f"schedule_select_week:{week_index - 1}",
			)
		)

	navigation_buttons.append(
		InlineKeyboardButton(
			text=f"Неделя {week['week']}",
			callback_data=f"schedule_week_current:{week_index}",
			style="success",
		)
	)

	if week_index < len(schedule) - 1:
		navigation_buttons.append(
			InlineKeyboardButton(
				text="→",
				callback_data=f"schedule_select_week:{week_index + 1}",
			)
		)

	builder.row(*navigation_buttons)

	# --------------------------------------------------
	# Назад
	# --------------------------------------------------

	builder.row(
		InlineKeyboardButton(
			text="◀ Назад",
			callback_data="back_to_menu",
			style="primary",
		)
	)

	return builder.as_markup()


# ---------------------------------------------------------------------------
# Открытие расписания / Сегодня / Завтра
# ---------------------------------------------------------------------------

@router.callback_query(
	MainMenu.main_menu,
	F.data.startswith("schedule:"),
)
async def schedule_button_handler(
		callback: CallbackQuery,
		state: FSMContext,
):
	await callback.answer()

	action = callback.data.split(":", 1)[1]

	# --------------------------------------------------
	# Получаем расписание только здесь
	# --------------------------------------------------

	schedule = await get_schedule(callback.from_user.id)

	# --------------------------------------------------
	# Сегодня
	# --------------------------------------------------

	if action == "today":
		schedule_date = get_schedule_for_date(
			schedule,
			date.today(),
		)

		if schedule_date is not None:
			await send_schedule(
				callback.message,
				schedule_date,
			)

		return

	# --------------------------------------------------
	# Завтра
	# --------------------------------------------------

	if action == "tomorrow":
		tomorrow = date.today() + timedelta(days=1)

		schedule_date = get_schedule_for_date(
			schedule,
			tomorrow,
		)

		if schedule_date is not None:
			await send_schedule(
				callback.message,
				schedule_date,
			)

		return

	# --------------------------------------------------
	# Выбор дня
	# --------------------------------------------------

	if action == "select":

		if not schedule:
			await callback.message.edit_text(
				"Расписание отсутствует."
			)
			return

		# Сохраняем весь schedule в FSM.
		# Благодаря этому при переключении недель
		# заново получать расписание не понадобится.
		await state.update_data(
			schedule=schedule,
			week_index=0,
		)

		await state.set_state(
			ScheduleSelection.selecting_day
		)

		keyboard = build_schedule_keyboard(
			schedule,
			week_index=0,
		)

		await callback.message.edit_text(
			text="📅 <b>Выберите день:</b>",
			parse_mode="HTML",
			reply_markup=keyboard,
		)


# ---------------------------------------------------------------------------
# Переключение недель
# ---------------------------------------------------------------------------

@router.callback_query(
	F.data.startswith("schedule_select_week:")
)
async def schedule_week_handler(
		callback: CallbackQuery,
		state: FSMContext,
):
	await callback.answer()

	# Получаем сохранённый schedule
	data = await state.get_data()
	schedule = data.get("schedule")

	if not schedule:
		await callback.message.edit_text(
			"Не удалось получить расписание. Откройте выбор даты заново."
		)
		return

	# Получаем индекс недели
	week_index = int(
		callback.data.split(":", 1)[1]
	)

	# Защита от выхода за пределы
	if week_index < 0 or week_index >= len(schedule):
		return

	await state.update_data(
		week_index=week_index
	)

	keyboard = build_schedule_keyboard(
		schedule,
		week_index,
	)

	await callback.message.edit_reply_markup(
		reply_markup=keyboard
	)


# ---------------------------------------------------------------------------
# Нажатие на номер текущей недели
# ---------------------------------------------------------------------------

@router.callback_query(
	F.data.startswith("schedule_week_current:")
)
async def schedule_week_current_handler(
		callback: CallbackQuery,
):
	"""
	Центральная кнопка 'Неделя N'.

	Ничего не делает — она просто показывает,
	на какой неделе сейчас находится пользователь.
	"""

	await callback.answer()


# ---------------------------------------------------------------------------
# Выбор конкретного дня
# ---------------------------------------------------------------------------

@router.callback_query(
	F.data.startswith("schedule_day:")
)
async def schedule_day_handler(
		callback: CallbackQuery,
		state: FSMContext,
):
	await callback.answer()

	data = await state.get_data()
	schedule = data.get("schedule")

	if not schedule:
		await callback.message.edit_text(
			"Не удалось получить расписание. Откройте выбор даты заново."
		)
		return

	# schedule_day:week_index:day_index
	_, week_index, day_index = callback.data.split(":")

	week_index = int(week_index)
	day_index = int(day_index)

	# Защита от некорректных индексов
	if week_index < 0 or week_index >= len(schedule):
		return

	week = schedule[week_index]

	if day_index < 0 or day_index >= len(week["days"]):
		return

	day_schedule = week["days"][day_index]

	await state.set_state(
		ScheduleSelection.selecting_day
	)

	await send_schedule(
		callback.message,
		day_schedule,
	)


# ---------------------------------------------------------------------------
# Отправка расписания
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Форматирование расписания
# ---------------------------------------------------------------------------


def get_week_index_for_date(
		schedule: list[dict],
		target_date: date,
) -> int | None:

	target_date_string = target_date.strftime("%d.%m.%Y")

	for week_index, week in enumerate(schedule):

		for day in week.get("days", []):

			if day.get("date") == target_date_string:
				return week_index

	for week_index, week in enumerate(schedule):

		date_range = week.get("date_range")

		if not date_range:
			continue

		start_date = parse_schedule_date(
			date_range[0]
		)

		end_date = parse_schedule_date(
			date_range[1]
		)

		if start_date <= target_date <= end_date:
			return week_index

	return None


def parse_schedule_date(value: str) -> date:
	return datetime.strptime(
		value,
		"%d.%m.%Y",
	).date()


@router.callback_query(
	MainMenu.main_menu,
	F.data.in_({"schedule_week:this", "schedule_week:next"}),
)
async def schedule_week_image_handler(
		callback: CallbackQuery,
		state: FSMContext,
):
	await callback.answer()

	# --------------------------------------------------
	# Узнаём, какую неделю запросил пользователь
	# --------------------------------------------------

	action = callback.data.split(":", 1)[1]

	# --------------------------------------------------
	# Получаем полный schedule
	# --------------------------------------------------

	schedule = await get_schedule(
		callback.from_user.id
	)

	if not schedule:
		await callback.message.answer(
			"Расписание отсутствует."
		)
		return

	# --------------------------------------------------
	# Находим текущую неделю
	# --------------------------------------------------

	current_week_index = get_week_index_for_date(
		schedule,
		date.today(),
	)

	if current_week_index is None:
		await callback.message.answer(
			"Не удалось определить текущую неделю "
			"в расписании."
		)
		return

	# --------------------------------------------------
	# Определяем нужную неделю
	# --------------------------------------------------

	if action == "this":
		week_index = current_week_index

	else:
		week_index = current_week_index + 1

	# --------------------------------------------------
	# Проверяем, существует ли следующая неделя
	# --------------------------------------------------

	if week_index >= len(schedule):

		if action == "next":
			await callback.message.answer(
				"Следующей недели в расписании нет."
			)

		return

	week = schedule[week_index]

	# --------------------------------------------------
	# Получаем подгруппу пользователя
	# --------------------------------------------------

	user = await get_user(
		callback.from_user.id
	)

	user_subgroup = None

	if user is not None:
		user_subgroup = user["subgroup"]

	# --------------------------------------------------
	# Генерируем изображение
	# --------------------------------------------------

	image = generate_week_schedule_image(
		week,
		user_subgroup=user_subgroup,
	)

	photo = BufferedInputFile(
		image.getvalue(),
		filename=f"schedule_week_{week['week']}.png",
	)

	# --------------------------------------------------
	# Подпись
	# --------------------------------------------------

	caption = (
		f"📅 <b>Расписание на неделю {week['week']}</b>\n"
		f"{week['date_range'][0]} — {week['date_range'][1]}"
	)

	# --------------------------------------------------
	# Отправляем
	# --------------------------------------------------

	await callback.message.answer_photo(
		photo=photo,
		caption=caption,
		parse_mode="HTML",
		reply_markup=await build_delete_button(
			callback.message
		),
	)


async def build_notification_settings_button(user) -> InlineKeyboardMarkup:
	buttons = []
	buttons.append([
		InlineKeyboardButton(
			text="🕒Задать время оповещения",
			callback_data="notification_settings:set_time"
		)
	])
	if user['notification_time'] is not None and user['notification_time'] != "":
		enabled = user['notification_enabled']
		if enabled:
			buttons.append([
				InlineKeyboardButton(
					text="Включено",
					callback_data="notification_settings:toggle",
					style="primary"
				)
			])
		else:
			buttons.append([
				InlineKeyboardButton(
					text="Выключено",
					callback_data="notification_settings:toggle",
					style="danger"
				)
			])
	buttons.append([
		InlineKeyboardButton(
			text="◀Назад",
			callback_data="back_to_menu"
		)
	])
	return InlineKeyboardMarkup(
		inline_keyboard=buttons
	)


@router.callback_query(
	StateFilter(
		MainMenu.main_menu,
		NotificationSettings.notification_setting
	),
	F.data.in_({
		"notification_settings:open",
		"notification_settings:toggle",
	}),
)
async def notification_settings_menu_button_handler(callback: CallbackQuery, state: FSMContext):
	await callback.answer()

	telegram_id = callback.from_user.id
	user = await get_user(telegram_id)

	if callback.data.split(":")[1] == "toggle":
		enabled = not bool(user['notification_enabled'])
		await update_user(
			telegram_id,
			notification_enabled=enabled
		)
		user = await get_user(telegram_id)

	await render_notification_settings_menu(callback.message, state, user)


async def render_notification_settings_menu(message: Message, state: FSMContext, user: dict | None = None):
	if user is None:
		telegram_id = message.chat.id
		user = await get_user(telegram_id)

	await state.set_state(NotificationSettings.notification_setting)

	if user['notification_time'] is None or user['notification_time'] == "":
		message_text = "Настройте время"
	else:
		message_text = ("Время оповещения:\n"
		                f"🕒{user['notification_time']}")
	await safe_edit_text(
		message,
		message_text,
		reply_markup=await build_notification_settings_button(user)
	)


def is_valid_time(value: str) -> bool:
	try:
		datetime.strptime(value, "%H:%M")
		return True
	except ValueError:
		return False


@router.callback_query(
	NotificationSettings.notification_setting,
	F.data == "notification_settings:set_time"
)
async def set_time_button_handler(
		callback: CallbackQuery,
		state: FSMContext,
):
	await callback.answer()

	sent_message = await callback.message.answer(
		"Введите время в формате чч:мм"
	)

	await state.update_data(
		callback_message=callback.message,
		previous_message=sent_message
	)

	await state.set_state(NotificationSettings.wait_for_time)


@router.message(NotificationSettings.wait_for_time)
async def time_handle(
		message: Message,
		state: FSMContext,
):
	time = message.text.strip()

	if not is_valid_time(time):
		sent_message = await message.answer(
			"Неверный формат.\n"
			"Попробуйте ещё раз"
		)
		await delete_after(sent_message, 5)
		return

	await update_user(
		message.chat.id,
		notification_time=time
	)

	data = await state.get_data()

	await message.delete()
	await data.get("previous_message").delete()
	callback_message = data.get("callback_message")

	await render_notification_settings_menu(
		callback_message,
		state
	)
